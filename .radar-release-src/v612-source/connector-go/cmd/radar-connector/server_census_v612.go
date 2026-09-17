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

// WFGG_RADAR_SERVER_CENSUS_V612
// WFGG_RADAR_SERVER_CENSUS_STREAM_V6121
// This endpoint reads the local Collector SQLite database strictly in read-only mode
// and returns aggregate server/cycle counts only. It never exposes UIDs, pseudos,
// alliances, coordinates, tokens or credentials.
type serverCensusRowV612 struct {
	ServerID       string `json:"serverId"`
	Players        int    `json:"players"`
	Observations   int    `json:"observations"`
	DistinctCycles int    `json:"distinctCycles"`
	FirstCycle     *int64 `json:"firstCycle,omitempty"`
	LastCycle      *int64 `json:"lastCycle,omitempty"`
}

type serverCensusSchemaV612 struct {
	PlayerTable      string `json:"playerTable,omitempty"`
	ObservationTable string `json:"observationTable,omitempty"`
	JoinMode         string `json:"joinMode,omitempty"`
}

type serverCensusPayloadV612 struct {
	OK                   bool                    `json:"ok"`
	CensusVersion        string                  `json:"censusVersion"`
	Readonly             bool                    `json:"readonly"`
	RawPlayerDataExposed bool                    `json:"rawPlayerDataExposed"`
	ServerCount          int                     `json:"serverCount"`
	PlayersTotal         int                     `json:"playersTotal"`
	ObservationsTotal    int                     `json:"observationsTotal"`
	Schema               serverCensusSchemaV612 `json:"schema"`
	Servers              []serverCensusRowV612   `json:"servers"`
}

const serverCensusPythonV612 = `
import json, sqlite3, sys

path = sys.argv[1]
conn = sqlite3.connect('file:' + path + '?mode=ro', uri=True)
conn.row_factory = sqlite3.Row


def qident(name):
    return '"' + str(name).replace('"', '""') + '"'


def cols(table):
    return [r[1] for r in conn.execute('PRAGMA table_info(' + qident(table) + ')')]


def pick_col(columns, candidates):
    exact = {str(c).lower(): c for c in columns}
    for candidate in candidates:
        if candidate.lower() in exact:
            return exact[candidate.lower()]
    return None


def norm_server(value):
    if value is None:
        return ''
    return str(value).strip()


def cycle_int(value):
    if value is None:
        return None
    try:
        return int(value)
    except Exception:
        return None


tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
server_names = ['server_id', 'serverId', 'server', 'serverid']
uid_names = ['game_uid', 'gameUid', 'uid', 'player_uid', 'playerId', 'player_id']
cycle_names = ['cycle_id', 'cycleId', 'cycle', 'scan_cycle_id']


def score_player(table, columns):
    score = 0
    low = table.lower()
    if low == 'players': score += 100
    if 'player' in low: score += 20
    if pick_col(columns, server_names): score += 20
    if pick_col(columns, uid_names): score += 20
    return score


def score_obs(table, columns):
    score = 0
    low = table.lower()
    if low in ('observations', 'player_observations'): score += 100
    if 'observation' in low: score += 40
    if pick_col(columns, cycle_names): score += 30
    if pick_col(columns, uid_names) or pick_col(columns, server_names): score += 20
    return score

schema = {t: cols(t) for t in tables}
player_candidates = [(score_player(t, schema[t]), t) for t in tables if pick_col(schema[t], server_names)]
player_candidates.sort(reverse=True)
player_table = player_candidates[0][1] if player_candidates else None
obs_candidates = [(score_obs(t, schema[t]), t) for t in tables if pick_col(schema[t], cycle_names)]
obs_candidates.sort(reverse=True)
obs_table = obs_candidates[0][1] if obs_candidates else None

servers = {}
uid_to_server = {}
player_sets = {}
cycle_sets = {}
join_mode = 'NONE'


def ensure(sid):
    return servers.setdefault(sid, {
        'serverId': sid,
        'players': 0,
        'observations': 0,
        'distinctCycles': 0,
        'firstCycle': None,
        'lastCycle': None,
    })

if player_table:
    pc = schema[player_table]
    pserver = pick_col(pc, server_names)
    puid = pick_col(pc, uid_names)
    if puid:
        sql = 'SELECT ' + qident(pserver) + ' server_id, ' + qident(puid) + ' player_uid FROM ' + qident(player_table) + ' WHERE ' + qident(pserver) + ' IS NOT NULL'
        for r in conn.execute(sql):
            sid = norm_server(r['server_id'])
            if not sid:
                continue
            uid = '' if r['player_uid'] is None else str(r['player_uid']).strip()
            ensure(sid)
            if uid:
                uid_to_server[uid] = sid
                player_sets.setdefault(sid, set()).add(uid)
        for sid, values in player_sets.items():
            ensure(sid)['players'] = len(values)
    else:
        sql = 'SELECT ' + qident(pserver) + ' server_id FROM ' + qident(player_table) + ' WHERE ' + qident(pserver) + ' IS NOT NULL'
        for r in conn.execute(sql):
            sid = norm_server(r['server_id'])
            if sid:
                ensure(sid)['players'] += 1

if obs_table:
    oc = schema[obs_table]
    oserver = pick_col(oc, server_names)
    ouid = pick_col(oc, uid_names)
    ocycle = pick_col(oc, cycle_names)
    if oserver:
        join_mode = 'OBSERVATION_SERVER_STREAM'
        sql = 'SELECT ' + qident(oserver) + ' server_id, ' + qident(ocycle) + ' cycle_id FROM ' + qident(obs_table) + ' WHERE ' + qident(oserver) + ' IS NOT NULL'
        for r in conn.execute(sql):
            sid = norm_server(r['server_id'])
            if not sid:
                continue
            ensure(sid)['observations'] += 1
            cycle = cycle_int(r['cycle_id'])
            if cycle is not None:
                cycle_sets.setdefault(sid, set()).add(cycle)
    elif ouid and uid_to_server:
        join_mode = 'UID_STREAM'
        sql = 'SELECT ' + qident(ouid) + ' player_uid, ' + qident(ocycle) + ' cycle_id FROM ' + qident(obs_table) + ' WHERE ' + qident(ouid) + ' IS NOT NULL'
        for r in conn.execute(sql):
            uid = '' if r['player_uid'] is None else str(r['player_uid']).strip()
            sid = uid_to_server.get(uid, '')
            if not sid:
                continue
            ensure(sid)['observations'] += 1
            cycle = cycle_int(r['cycle_id'])
            if cycle is not None:
                cycle_sets.setdefault(sid, set()).add(cycle)

for sid, cycles in cycle_sets.items():
    item = ensure(sid)
    item['distinctCycles'] = len(cycles)
    if cycles:
        item['firstCycle'] = min(cycles)
        item['lastCycle'] = max(cycles)


def sort_key(item):
    sid = item['serverId']
    return (0, int(sid)) if sid.isdigit() else (1, sid)

rows = sorted(servers.values(), key=sort_key)
payload = {
    'ok': True,
    'censusVersion': 'v6.12.1',
    'readonly': True,
    'rawPlayerDataExposed': False,
    'serverCount': len(rows),
    'playersTotal': sum(x['players'] for x in rows),
    'observationsTotal': sum(x['observations'] for x in rows),
    'schema': {
        'playerTable': player_table or '',
        'observationTable': obs_table or '',
        'joinMode': join_mode,
    },
    'servers': rows,
}
print(json.dumps(payload, separators=(',', ':')))
`

func runServerCensusV612(ctx context.Context, dbPath string) (serverCensusPayloadV612, error) {
	if strings.TrimSpace(dbPath) == "" {
		return serverCensusPayloadV612{}, errors.New("COLLECTOR_DB_PATH_EMPTY")
	}
	if _, err := exec.LookPath("python3"); err != nil {
		return serverCensusPayloadV612{}, errors.New("COLLECTOR_CENSUS_PYTHON3_MISSING")
	}
	if _, err := os.Stat(dbPath); err != nil {
		if os.IsNotExist(err) {
			return serverCensusPayloadV612{}, errors.New("COLLECTOR_DB_NOT_FOUND")
		}
		return serverCensusPayloadV612{}, errors.New("COLLECTOR_DB_ACCESS_FAILED")
	}
	cmd := exec.CommandContext(ctx, "python3", "-c", serverCensusPythonV612, dbPath)
	out, err := cmd.Output()
	if err != nil {
		if errors.Is(ctx.Err(), context.DeadlineExceeded) {
			return serverCensusPayloadV612{}, errors.New("COLLECTOR_CENSUS_TIMEOUT")
		}
		return serverCensusPayloadV612{}, errors.New("COLLECTOR_CENSUS_EXEC_FAILED")
	}
	var payload serverCensusPayloadV612
	if err := json.Unmarshal(out, &payload); err != nil {
		return serverCensusPayloadV612{}, errors.New("COLLECTOR_CENSUS_REPORT_INVALID")
	}
	if !payload.OK || !payload.Readonly || payload.RawPlayerDataExposed {
		return serverCensusPayloadV612{}, errors.New("COLLECTOR_CENSUS_SAFETY_FAILED")
	}
	return payload, nil
}

func (s *server) serverCensusV612(w http.ResponseWriter, r *http.Request, _ []byte) {
	dbPath := strings.TrimSpace(os.Getenv("WFGG_COLLECTOR_DB"))
	if dbPath == "" {
		dbPath = "/opt/wfgg-collector/data/collector.db"
	}
	ctx, cancel := context.WithTimeout(r.Context(), 30*time.Second)
	defer cancel()
	payload, err := runServerCensusV612(ctx, dbPath)
	if err != nil {
		writeJSON(w, http.StatusBadGateway, map[string]any{
			"ok":            false,
			"censusVersion": "v6.12.1",
			"readonly":      true,
			"error":         err.Error(),
		})
		return
	}
	writeJSON(w, http.StatusOK, payload)
}
