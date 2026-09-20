package main

import (
	"context"
	"encoding/json"
	"errors"
	"os"
	"os/exec"
	"strings"
)

// WFGG_RADAR_AUTOPILOT_TARGETED_HISTORY_QUALITY_V6199
//
// Autopilot only needs reusable full-cycle evidence for its current seed.
// Rebuilding every historical cycle is O(history * table-size) on Collector
// databases without cycle_id indexes and eventually exceeds the 90s guard.
// This implementation first selects quality-eligible candidate cycle IDs from
// the small cycles table, then scans the large history tables only once for
// those candidates. Collector access remains strictly read-only.
type autopilotTargetedHistoryReportV6199 struct {
	OK             bool    `json:"ok"`
	CandidateCount int     `json:"candidateCount"`
	CycleIDs       []int64 `json:"cycleIds"`
}

const autopilotTargetedHistoryPythonV6199 = `
import hashlib, json, sqlite3, sys

path, seed = sys.argv[1:3]
query = '@federated:' + seed
conn = sqlite3.connect('file:' + path + '?mode=ro', uri=True)
conn.row_factory = sqlite3.Row
conn.execute('PRAGMA query_only=ON')

tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
required = {'cycles', 'cycle_seen', 'cycle_baseline', 'cycle_changes'}
if not required.issubset(tables):
    print(json.dumps({'ok': False, 'candidateCount': 0, 'cycleIds': []}, separators=(',', ':')))
    raise SystemExit(0)

cycle_cols = {r[1] for r in conn.execute('PRAGMA table_info(cycles)')}
if not {'id', 'status', 'error', 'query'}.issubset(cycle_cols):
    print(json.dumps({'ok': False, 'candidateCount': 0, 'cycleIds': []}, separators=(',', ':')))
    raise SystemExit(0)

candidate_ids = [
    int(r['id']) for r in conn.execute(
        """SELECT id FROM cycles
           WHERE upper(trim(COALESCE(status,'')))='SUCCESS'
             AND trim(COALESCE(error,''))=''
             AND lower(trim(COALESCE(query,'')))=lower(?)
           ORDER BY id""",
        (query,)
    )
]
if not candidate_ids:
    print(json.dumps({'ok': True, 'candidateCount': 0, 'cycleIds': []}, separators=(',', ':')))
    raise SystemExit(0)

marks = ','.join('?' for _ in candidate_ids)
params = tuple(candidate_ids)

baseline = {}
for r in conn.execute(
    f'SELECT cycle_id,game_uid,state_json FROM cycle_baseline WHERE cycle_id IN ({marks})',
    params
):
    baseline[(int(r['cycle_id']), str(r['game_uid']))] = str(r['state_json'] or '')

changes = {}
for r in conn.execute(
    f'SELECT cycle_id,game_uid,after_json FROM cycle_changes WHERE cycle_id IN ({marks}) ORDER BY id',
    params
):
    if r['after_json']:
        changes[(int(r['cycle_id']), str(r['game_uid']))] = str(r['after_json'])

found = set()
for r in conn.execute(
    f'SELECT cycle_id,game_uid,state_hash FROM cycle_seen WHERE cycle_id IN ({marks})',
    params
):
    cid = int(r['cycle_id'])
    if cid in found:
        continue
    uid = str(r['game_uid'])
    expected = str(r['state_hash'] or '').strip().lower()
    raw = changes.get((cid, uid)) or baseline.get((cid, uid)) or ''
    if not raw or not expected:
        continue
    actual = hashlib.sha256(raw.encode('utf-8')).hexdigest()
    if actual != expected:
        continue
    try:
        obj = json.loads(raw)
    except Exception:
        continue
    sid = obj.get('server_id')
    sid = '' if sid is None else str(sid).strip()
    if sid == seed:
        found.add(cid)

conn.close()
eligible = [cid for cid in candidate_ids if cid in found]
print(json.dumps({
    'ok': True,
    'candidateCount': len(candidate_ids),
    'cycleIds': eligible,
}, separators=(',', ':')))
`

func autopilotTargetedFullCycleIDsV6199(ctx context.Context, dbPath, seed string) ([]int64, error) {
	dbPath = strings.TrimSpace(dbPath)
	seed = strings.TrimSpace(seed)
	if dbPath == "" {
		return nil, errors.New("AUTOPILOT_TARGET_HISTORY_DB_PATH_EMPTY_V6199")
	}
	if seed == "" {
		return nil, nil
	}
	if _, err := os.Stat(dbPath); err != nil {
		return nil, errors.New("AUTOPILOT_TARGET_HISTORY_DB_UNAVAILABLE_V6199")
	}
	if _, err := exec.LookPath("python3"); err != nil {
		return nil, errors.New("AUTOPILOT_TARGET_HISTORY_PYTHON3_MISSING_V6199")
	}
	cmd := exec.CommandContext(ctx, "python3", "-c", autopilotTargetedHistoryPythonV6199, dbPath, seed)
	out, err := cmd.Output()
	if err != nil {
		if errors.Is(ctx.Err(), context.DeadlineExceeded) {
			return nil, errors.New("AUTOPILOT_TARGET_HISTORY_TIMEOUT_V6199")
		}
		return nil, errors.New("AUTOPILOT_TARGET_HISTORY_EXEC_FAILED_V6199")
	}
	var report autopilotTargetedHistoryReportV6199
	if err := json.Unmarshal(out, &report); err != nil || !report.OK {
		return nil, errors.New("AUTOPILOT_TARGET_HISTORY_REPORT_INVALID_V6199")
	}
	return append([]int64(nil), report.CycleIDs...), nil
}
