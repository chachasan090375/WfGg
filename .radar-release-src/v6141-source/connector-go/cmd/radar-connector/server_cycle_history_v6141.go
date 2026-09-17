package main

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"os"
	"os/exec"
	"strings"
	"time"
)

// WFGG_RADAR_SERVER_CYCLE_HISTORY_STREAM_V6141
// Single-pass historical reconstruction. cycle_seen is joined once to its indexed
// cycle_baseline row; cycle_changes are read once and only changed states require
// SHA-256 recomputation. Current players.server_id is never consulted.
const serverCycleHistoryPythonV6141 = `
import hashlib, json, sqlite3, sys
from collections import defaultdict

path=sys.argv[1]
conn=sqlite3.connect('file:'+path+'?mode=ro',uri=True)
conn.row_factory=sqlite3.Row
conn.execute('PRAGMA query_only=ON')

required={'cycle_seen','cycle_baseline','cycle_changes'}
tables={r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
if not required.issubset(tables):
    print(json.dumps({'ok':False,'error':'HISTORICAL_SCHEMA_MISSING'},separators=(',',':')))
    raise SystemExit(0)

def sid_from_state(raw):
    if not raw:
        return ''
    try:
        obj=json.loads(raw)
    except Exception:
        return ''
    v=obj.get('server_id')
    return '' if v is None else str(v).strip()

def server_sort(v):
    try: return (0,int(v))
    except Exception: return (1,v)

# Last after_json wins if a player changed more than once inside the same cycle.
latest_change={}
for r in conn.execute('SELECT cycle_id,game_uid,after_json FROM cycle_changes WHERE after_json IS NOT NULL ORDER BY cycle_id,id'):
    latest_change[(int(r['cycle_id']),str(r['game_uid']))]=str(r['after_json'])

cycles=[]
pair_cycles=defaultdict(int)
total_seen=total_match=total_mismatch=total_unresolved=0
current_cycle=None
counts=defaultdict(int)
seen=matched=mismatched=unresolved=0

def flush_cycle():
    global counts,seen,matched,mismatched,unresolved
    if current_cycle is None:
        return
    members=[{'serverId':sid,'observations':counts[sid]} for sid in sorted(counts,key=server_sort)]
    present=[x['serverId'] for x in members]
    for i in range(len(present)):
        for j in range(i+1,len(present)):
            a,b=present[i],present[j]
            if server_sort(b)<server_sort(a): a,b=b,a
            pair_cycles[(a,b)]+=1
    cycles.append({
        'cycleId':current_cycle,'serverCount':len(members),'seenRows':seen,
        'hashMatched':matched,'hashMismatched':mismatched,'unresolved':unresolved,
        'servers':members,
    })
    counts=defaultdict(int); seen=matched=mismatched=unresolved=0

sql='''
SELECT s.cycle_id,s.game_uid,s.state_hash,
       b.state_hash AS baseline_hash,b.state_json AS baseline_json
FROM cycle_seen s
LEFT JOIN cycle_baseline b
  ON b.cycle_id=s.cycle_id AND b.game_uid=s.game_uid
ORDER BY s.cycle_id,s.game_uid
'''
for r in conn.execute(sql):
    cid=int(r['cycle_id'])
    if current_cycle is None:
        current_cycle=cid
    elif cid!=current_cycle:
        flush_cycle()
        current_cycle=cid

    seen+=1; total_seen+=1
    uid=str(r['game_uid'])
    expected=str(r['state_hash'] or '').strip().lower()
    changed_raw=latest_change.get((cid,uid))
    if changed_raw is not None:
        raw=changed_raw
        actual=hashlib.sha256(raw.encode('utf-8')).hexdigest()
    else:
        raw='' if r['baseline_json'] is None else str(r['baseline_json'])
        actual='' if r['baseline_hash'] is None else str(r['baseline_hash']).strip().lower()

    if not raw or not expected or not actual:
        unresolved+=1; total_unresolved+=1
        continue
    if actual!=expected:
        mismatched+=1; total_mismatch+=1
        continue
    sid=sid_from_state(raw)
    if not sid:
        unresolved+=1; total_unresolved+=1
        continue
    matched+=1; total_match+=1
    counts[sid]+=1

flush_cycle()
edges=[{'serverA':a,'serverB':b,'cyclesTogether':n} for (a,b),n in pair_cycles.items()]
edges.sort(key=lambda x:(server_sort(x['serverA']),server_sort(x['serverB'])))
rate=(total_match/total_seen) if total_seen else 0.0
payload={
    'ok':True,
    'mapVersion':'v6.14.1',
    'readonly':True,
    'rawPlayerDataExposed':False,
    'semantics':'OBSERVED_MAP_TARGET_HISTORY',
    'serverIdSource':'CYCLE_STATE_SERVER_ID',
    'underlyingAttribution':'WORLD_GET_BLOCK_TARGET',
    'clusterSemanticsProven':False,
    'cycleCount':len(cycles),
    'edgeCount':len(edges),
    'seenRows':total_seen,
    'hashMatched':total_match,
    'hashMismatched':total_mismatch,
    'unresolved':total_unresolved,
    'hashMatchRate':rate,
    'cycles':cycles,
    'edges':edges,
}
print(json.dumps(payload,separators=(',',':')))
`

func runServerCycleHistoryV6141(ctx context.Context, dbPath string) (serverCycleHistoryPayloadV614, error) {
	if strings.TrimSpace(dbPath) == "" {
		return serverCycleHistoryPayloadV614{}, errors.New("COLLECTOR_DB_PATH_EMPTY")
	}
	if _, err := exec.LookPath("python3"); err != nil {
		return serverCycleHistoryPayloadV614{}, errors.New("COLLECTOR_HISTORY_PYTHON3_MISSING")
	}
	if _, err := os.Stat(dbPath); err != nil {
		if os.IsNotExist(err) {
			return serverCycleHistoryPayloadV614{}, errors.New("COLLECTOR_DB_NOT_FOUND")
		}
		return serverCycleHistoryPayloadV614{}, errors.New("COLLECTOR_DB_ACCESS_FAILED")
	}
	cmd := exec.CommandContext(ctx, "python3", "-c", serverCycleHistoryPythonV6141, dbPath)
	out, err := cmd.Output()
	if err != nil {
		if errors.Is(ctx.Err(), context.DeadlineExceeded) {
			return serverCycleHistoryPayloadV614{}, errors.New("COLLECTOR_HISTORY_TIMEOUT")
		}
		return serverCycleHistoryPayloadV614{}, errors.New("COLLECTOR_HISTORY_EXEC_FAILED")
	}
	var payload serverCycleHistoryPayloadV614
	if err := json.Unmarshal(out, &payload); err != nil {
		return serverCycleHistoryPayloadV614{}, errors.New("COLLECTOR_HISTORY_REPORT_INVALID")
	}
	if !payload.OK {
		return serverCycleHistoryPayloadV614{}, errors.New("COLLECTOR_HISTORY_SCHEMA_UNAVAILABLE")
	}
	if !payload.Readonly || payload.RawPlayerDataExposed {
		return serverCycleHistoryPayloadV614{}, errors.New("COLLECTOR_HISTORY_SAFETY_FAILED")
	}
	return payload, nil
}

func (s *server) serverCycleHistoryV6141(w http.ResponseWriter, r *http.Request, _ []byte) {
	dbPath := strings.TrimSpace(os.Getenv("WFGG_COLLECTOR_DB"))
	if dbPath == "" {
		dbPath = "/opt/wfgg-collector/data/collector.db"
	}
	ctx, cancel := context.WithTimeout(r.Context(), 90*time.Second)
	defer cancel()
	payload, err := runServerCycleHistoryV6141(ctx, dbPath)
	if err != nil {
		writeJSON(w, http.StatusBadGateway, map[string]any{
			"ok": false, "mapVersion": "v6.14.1", "readonly": true, "error": err.Error(),
		})
		return
	}
	writeJSON(w, http.StatusOK, payload)
}
