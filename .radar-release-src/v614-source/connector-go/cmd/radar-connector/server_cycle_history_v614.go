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

// WFGG_RADAR_SERVER_CYCLE_HISTORY_V614
// Reconstructs cycle-time server attribution from cycle_seen.state_hash plus
// cycle_baseline/cycle_changes. It deliberately does NOT join historical UIDs to
// the current players.server_id value.
type serverCycleHistoryCycleV614 struct {
	CycleID        int64                    `json:"cycleId"`
	ServerCount    int                      `json:"serverCount"`
	SeenRows       int                      `json:"seenRows"`
	HashMatched    int                      `json:"hashMatched"`
	HashMismatched int                      `json:"hashMismatched"`
	Unresolved     int                      `json:"unresolved"`
	Servers        []serverCycleMemberV6122 `json:"servers"`
}

type serverCycleHistoryPayloadV614 struct {
	OK                       bool                         `json:"ok"`
	MapVersion               string                       `json:"mapVersion"`
	Readonly                 bool                         `json:"readonly"`
	RawPlayerDataExposed     bool                         `json:"rawPlayerDataExposed"`
	Semantics                string                       `json:"semantics"`
	ServerIDSource           string                       `json:"serverIdSource"`
	UnderlyingAttribution    string                       `json:"underlyingAttribution"`
	ClusterSemanticsProven   bool                         `json:"clusterSemanticsProven"`
	CycleCount               int                          `json:"cycleCount"`
	EdgeCount                int                          `json:"edgeCount"`
	SeenRows                 int                          `json:"seenRows"`
	HashMatched              int                          `json:"hashMatched"`
	HashMismatched           int                          `json:"hashMismatched"`
	Unresolved               int                          `json:"unresolved"`
	HashMatchRate            float64                      `json:"hashMatchRate"`
	Cycles                    []serverCycleHistoryCycleV614 `json:"cycles"`
	Edges                     []serverPairEdgeV6122        `json:"edges"`
}

const serverCycleHistoryPythonV614 = `
import hashlib, json, sqlite3, sys
from collections import defaultdict

path=sys.argv[1]
conn=sqlite3.connect('file:'+path+'?mode=ro',uri=True)
conn.row_factory=sqlite3.Row

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

cycle_ids=[int(r[0]) for r in conn.execute('SELECT DISTINCT cycle_id FROM cycle_seen ORDER BY cycle_id')]
cycles=[]
pair_cycles=defaultdict(int)
total_seen=total_match=total_mismatch=total_unresolved=0

for cid in cycle_ids:
    baseline={str(r['game_uid']):str(r['state_json'] or '') for r in conn.execute(
        'SELECT game_uid,state_json FROM cycle_baseline WHERE cycle_id=?',(cid,))}
    changes={}
    for r in conn.execute('SELECT game_uid,after_json FROM cycle_changes WHERE cycle_id=? ORDER BY id',(cid,)):
        if r['after_json']:
            changes[str(r['game_uid'])]=str(r['after_json'])

    counts=defaultdict(int)
    seen=matched=mismatched=unresolved=0
    for r in conn.execute('SELECT game_uid,state_hash FROM cycle_seen WHERE cycle_id=?',(cid,)):
        seen+=1
        uid=str(r['game_uid'])
        expected=str(r['state_hash'] or '').strip().lower()
        raw=changes.get(uid) or baseline.get(uid) or ''
        if not raw or not expected:
            unresolved+=1
            continue
        actual=hashlib.sha256(raw.encode('utf-8')).hexdigest()
        if actual != expected:
            mismatched+=1
            continue
        sid=sid_from_state(raw)
        if not sid:
            unresolved+=1
            continue
        matched+=1
        counts[sid]+=1

    members=[{'serverId':sid,'observations':counts[sid]} for sid in sorted(counts,key=server_sort)]
    present=[x['serverId'] for x in members]
    for i in range(len(present)):
        for j in range(i+1,len(present)):
            a,b=present[i],present[j]
            if server_sort(b)<server_sort(a): a,b=b,a
            pair_cycles[(a,b)]+=1

    cycles.append({
        'cycleId':cid,'serverCount':len(members),'seenRows':seen,
        'hashMatched':matched,'hashMismatched':mismatched,'unresolved':unresolved,
        'servers':members,
    })
    total_seen+=seen; total_match+=matched; total_mismatch+=mismatched; total_unresolved+=unresolved

edges=[{'serverA':a,'serverB':b,'cyclesTogether':n} for (a,b),n in pair_cycles.items()]
edges.sort(key=lambda x:(server_sort(x['serverA']),server_sort(x['serverB'])))
rate=(total_match/total_seen) if total_seen else 0.0
payload={
    'ok':True,
    'mapVersion':'v6.14',
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

func runServerCycleHistoryV614(ctx context.Context, dbPath string) (serverCycleHistoryPayloadV614, error) {
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
	cmd := exec.CommandContext(ctx, "python3", "-c", serverCycleHistoryPythonV614, dbPath)
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

func (s *server) serverCycleHistoryV614(w http.ResponseWriter, r *http.Request, _ []byte) {
	dbPath := strings.TrimSpace(os.Getenv("WFGG_COLLECTOR_DB"))
	if dbPath == "" {
		dbPath = "/opt/wfgg-collector/data/collector.db"
	}
	ctx, cancel := context.WithTimeout(r.Context(), 30*time.Second)
	defer cancel()
	payload, err := runServerCycleHistoryV614(ctx, dbPath)
	if err != nil {
		writeJSON(w, http.StatusBadGateway, map[string]any{
			"ok": false, "mapVersion": "v6.14", "readonly": true, "error": err.Error(),
		})
		return
	}
	writeJSON(w, http.StatusOK, payload)
}
