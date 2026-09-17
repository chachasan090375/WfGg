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

// WFGG_RADAR_SERVER_CYCLE_MAP_V6122
// Aggregate-only evidence for server clustering. No player identity data leaves the VPS.
type serverCycleMemberV6122 struct {
	ServerID     string `json:"serverId"`
	Observations int    `json:"observations"`
}

type serverCycleRowV6122 struct {
	CycleID     int64                    `json:"cycleId"`
	ServerCount int                      `json:"serverCount"`
	Servers     []serverCycleMemberV6122 `json:"servers"`
}

type serverPairEdgeV6122 struct {
	ServerA        string `json:"serverA"`
	ServerB        string `json:"serverB"`
	CyclesTogether int    `json:"cyclesTogether"`
}

type serverCycleMapPayloadV6122 struct {
	OK                   bool                  `json:"ok"`
	MapVersion           string                `json:"mapVersion"`
	Readonly             bool                  `json:"readonly"`
	RawPlayerDataExposed bool                  `json:"rawPlayerDataExposed"`
	CycleCount           int                   `json:"cycleCount"`
	EdgeCount            int                   `json:"edgeCount"`
	Cycles               []serverCycleRowV6122 `json:"cycles"`
	Edges                []serverPairEdgeV6122 `json:"edges"`
}

const serverCycleMapPythonV6122 = `
import itertools, json, sqlite3, sys

path=sys.argv[1]
conn=sqlite3.connect('file:' + path + '?mode=ro', uri=True)
conn.row_factory=sqlite3.Row

def qi(v): return '"' + str(v).replace('"','""') + '"'
def cols(t): return [r[1] for r in conn.execute('PRAGMA table_info(' + qi(t) + ')')]
def pick(cs, names):
    low={str(c).lower():c for c in cs}
    for n in names:
        if n.lower() in low: return low[n.lower()]
    return None

def sid(v):
    if v is None: return ''
    return str(v).strip()

def cint(v):
    try: return int(v)
    except Exception: return None

tables=[r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
schema={t:cols(t) for t in tables}
server_names=['server_id','serverId','server','serverid']
uid_names=['game_uid','gameUid','uid','player_uid','playerId','player_id']
cycle_names=['cycle_id','cycleId','cycle','scan_cycle_id']

def pscore(t):
    c=schema[t]; s=0; l=t.lower()
    if l=='players': s+=100
    if 'player' in l: s+=20
    if pick(c,server_names): s+=20
    if pick(c,uid_names): s+=20
    return s

def oscore(t):
    c=schema[t]; s=0; l=t.lower()
    if l in ('cycle_seen','observations','player_observations'): s+=100
    if 'cycle' in l or 'observation' in l: s+=30
    if pick(c,cycle_names): s+=30
    if pick(c,uid_names) or pick(c,server_names): s+=20
    return s

pcands=sorted([(pscore(t),t) for t in tables if pick(schema[t],server_names)], reverse=True)
ocands=sorted([(oscore(t),t) for t in tables if pick(schema[t],cycle_names)], reverse=True)
pt=pcands[0][1] if pcands else None
ot=ocands[0][1] if ocands else None
uid_to_server={}
if pt:
    pc=schema[pt]; ps=pick(pc,server_names); pu=pick(pc,uid_names)
    if pu:
        sql='SELECT '+qi(ps)+' server_id, '+qi(pu)+' player_uid FROM '+qi(pt)+' WHERE '+qi(ps)+' IS NOT NULL AND '+qi(pu)+' IS NOT NULL'
        for r in conn.execute(sql):
            s=sid(r['server_id']); u=str(r['player_uid']).strip()
            if s and u: uid_to_server[u]=s

cycle_counts={}
if ot:
    oc=schema[ot]; osrv=pick(oc,server_names); ouid=pick(oc,uid_names); ocy=pick(oc,cycle_names)
    if osrv:
        sql='SELECT '+qi(osrv)+' server_id, '+qi(ocy)+' cycle_id FROM '+qi(ot)+' WHERE '+qi(osrv)+' IS NOT NULL AND '+qi(ocy)+' IS NOT NULL'
        for r in conn.execute(sql):
            c=cint(r['cycle_id']); s=sid(r['server_id'])
            if c is None or not s: continue
            d=cycle_counts.setdefault(c,{})
            d[s]=d.get(s,0)+1
    elif ouid and uid_to_server:
        sql='SELECT '+qi(ouid)+' player_uid, '+qi(ocy)+' cycle_id FROM '+qi(ot)+' WHERE '+qi(ouid)+' IS NOT NULL AND '+qi(ocy)+' IS NOT NULL'
        for r in conn.execute(sql):
            c=cint(r['cycle_id']); u=str(r['player_uid']).strip(); s=uid_to_server.get(u,'')
            if c is None or not s: continue
            d=cycle_counts.setdefault(c,{})
            d[s]=d.get(s,0)+1

def skey(s): return (0,int(s)) if s.isdigit() else (1,s)
cycles=[]
edges={}
for c in sorted(cycle_counts):
    counts=cycle_counts[c]
    members=[{'serverId':s,'observations':counts[s]} for s in sorted(counts,key=skey)]
    cycles.append({'cycleId':c,'serverCount':len(members),'servers':members})
    ids=[m['serverId'] for m in members]
    for a,b in itertools.combinations(ids,2):
        k=(a,b)
        edges[k]=edges.get(k,0)+1
edge_rows=[{'serverA':a,'serverB':b,'cyclesTogether':n} for (a,b),n in sorted(edges.items(), key=lambda x:(-x[1],skey(x[0][0]),skey(x[0][1])))]
print(json.dumps({
  'ok':True,
  'mapVersion':'v6.12.2',
  'readonly':True,
  'rawPlayerDataExposed':False,
  'cycleCount':len(cycles),
  'edgeCount':len(edge_rows),
  'cycles':cycles,
  'edges':edge_rows,
}, separators=(',',':')))
`

func runServerCycleMapV6122(ctx context.Context, dbPath string) (serverCycleMapPayloadV6122, error) {
	if strings.TrimSpace(dbPath) == "" {
		return serverCycleMapPayloadV6122{}, errors.New("COLLECTOR_DB_PATH_EMPTY")
	}
	if _, err := exec.LookPath("python3"); err != nil {
		return serverCycleMapPayloadV6122{}, errors.New("SERVER_CYCLE_MAP_PYTHON3_MISSING")
	}
	if _, err := os.Stat(dbPath); err != nil {
		return serverCycleMapPayloadV6122{}, errors.New("SERVER_CYCLE_MAP_DB_UNAVAILABLE")
	}
	cmd := exec.CommandContext(ctx, "python3", "-c", serverCycleMapPythonV6122, dbPath)
	out, err := cmd.Output()
	if err != nil {
		if errors.Is(ctx.Err(), context.DeadlineExceeded) {
			return serverCycleMapPayloadV6122{}, errors.New("SERVER_CYCLE_MAP_TIMEOUT")
		}
		return serverCycleMapPayloadV6122{}, errors.New("SERVER_CYCLE_MAP_EXEC_FAILED")
	}
	var payload serverCycleMapPayloadV6122
	if err := json.Unmarshal(out, &payload); err != nil {
		return serverCycleMapPayloadV6122{}, errors.New("SERVER_CYCLE_MAP_REPORT_INVALID")
	}
	if !payload.OK || !payload.Readonly || payload.RawPlayerDataExposed {
		return serverCycleMapPayloadV6122{}, errors.New("SERVER_CYCLE_MAP_SAFETY_FAILED")
	}
	return payload, nil
}

func (s *server) serverCycleMapV6122(w http.ResponseWriter, r *http.Request, _ []byte) {
	dbPath := strings.TrimSpace(os.Getenv("WFGG_COLLECTOR_DB"))
	if dbPath == "" {
		dbPath = "/opt/wfgg-collector/data/collector.db"
	}
	ctx, cancel := context.WithTimeout(r.Context(), 30*time.Second)
	defer cancel()
	payload, err := runServerCycleMapV6122(ctx, dbPath)
	if err != nil {
		writeJSON(w, http.StatusBadGateway, map[string]any{"ok":false,"mapVersion":"v6.12.2","readonly":true,"error":err.Error()})
		return
	}
	writeJSON(w, http.StatusOK, payload)
}
