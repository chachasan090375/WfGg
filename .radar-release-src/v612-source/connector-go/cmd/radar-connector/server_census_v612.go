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
join_mode = 'NONE'

if player_table:
    pc = schema[player_table]
    pserver = pick_col(pc, server_names)
    puid = pick_col(pc, uid_names)
    count_expr = 'COUNT(DISTINCT ' + qident(puid) + ')' if puid else 'COUNT(*)'
    sql = 'SELECT CAST(' + qident(pserver) + ' AS TEXT) server_id, ' + count_expr + ' players FROM ' + qident(player_table) + ' WHERE ' + qident(pserver) + ' IS NOT NULL AND TRIM(CAST(' + qident(pserver) + ' AS TEXT)) <> \'\' GROUP BY CAST(' + qident(pserver) + ' AS TEXT)'
    for r in conn.execute(sql):
        sid = str(r['server_id'])
        servers[sid] = {'serverId': sid, 'players': int(r['players'] or 0), 'observations': 0, 'distinctCycles': 0, 'firstCycle': None, 'lastCycle': None}

if obs_table:
    oc = schema[obs_table]
    oserver = pick_col(oc, server_names)
    ouid = pick_col(oc, uid_names)
    ocycle = pick_col(oc, cycle_names)
    if oserver:
        join_mode = 'OBSERVATION_SERVER'
        sql = 'SELECT CAST(' + qident(oserver) + ' AS TEXT) server_id, COUNT(*) observations, COUNT(DISTINCT ' + qident(ocycle) + ') cycles, MIN(CAST(' + qident(ocycle) + ' AS INTEGER)) first_cycle, MAX(CAST(' + qident(ocycle) + ' AS INTEGER)) last_cycle FROM ' + qident(obs_table) + ' WHERE ' + qident(oserver) + ' IS NOT NULL AND TRIM(CAST(' + qident(oserver) + ' AS TEXT)) <> \'\' GROUP BY CAST(' + qident(oserver) + ' AS TEXT)'
    elif player_table and ouid:
        pc = schema[player_table]
        pserver = pick_col(pc, server_names)
        puid = pick_col(pc, uid_names)
        if pserver and puid:
            join_mode = 'UID_JOIN'
            sql = 'SELECT CAST(p.' + qident(pserver) + ' AS TEXT) server_id, COUNT(*) observations, COUNT(DISTINCT o.' + qident(ocycle) + ') cycles, MIN(CAST(o.' + qident(ocycle) + ' AS INTEGER)) first_cycle, MAX(CAST(o.' + qident(ocycle) + ' AS INTEGER)) last_cycle FROM ' + qident(obs_table) + ' o JOIN ' + qident(player_table) + ' p ON CAST(o.' + qident(ouid) + ' AS TEXT)=CAST(p.' + qident(puid) + ' AS TEXT) WHERE p.' + qident(pserver) + ' IS NOT NULL AND TRIM(CAST(p.' + qident(pserver) + ' AS TEXT)) <> \'\' GROUP BY CAST(p.' + qident(pserver) + ' AS TEXT)'
        else:
            sql = None
    else:
        sql = None
    if sql:
        for r in conn.execute(sql):
            sid = str(r['server_id'])
            item = servers.setdefault(sid, {'serverId': sid, 'players': 0, 'observations': 0, 'distinctCycles': 0, 'firstCycle': None, 'lastCycle': None})
            item['observations'] = int(r['observations'] or 0)
            item['distinctCycles'] = int(r['cycles'] or 0)
            item['firstCycle'] = int(r['first_cycle']) if r['first_cycle'] is not None else None
            item['lastCycle'] = int(r['last_cycle']) if r['last_cycle'] is not None else None


def sort_key(item):
    sid = item['serverId']
    return (0, int(sid)) if sid.isdigit() else (1, sid)

rows = sorted(servers.values(), key=sort_key)
payload = {
    'ok': True,
    'censusVersion': 'v6.12',
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
	cmd := exec.CommandContext(ctx, "python3", "-c", serverCensusPythonV612, dbPath)
	out, err := cmd.Output()
	if err != nil {
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
	ctx, cancel := context.WithTimeout(r.Context(), 10*time.Second)
	defer cancel()
	payload, err := runServerCensusV612(ctx, dbPath)
	if err != nil {
		writeJSON(w, http.StatusBadGateway, map[string]any{
			"ok":            false,
			"censusVersion": "v6.12",
			"readonly":      true,
			"error":         err.Error(),
		})
		return
	}
	writeJSON(w, http.StatusOK, payload)
}
