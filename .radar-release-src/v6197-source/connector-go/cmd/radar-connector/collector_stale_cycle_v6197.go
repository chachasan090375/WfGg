package main

import (
	"context"
	"encoding/json"
	"errors"
	"os"
	"os/exec"
	"strconv"
	"strings"
	"time"
)

// WFGG_RADAR_AUTOPILOT_STALE_CYCLE_RECOVERY_V6197
// A joined Collector cycle is recoverable only when the Collector DB proves
// that it has remained RUNNING beyond a conservative 15-minute threshold.
// The normal Connector search timeout is 12 minutes. If inspection is
// unavailable or ambiguous, recovery fails closed and the pre-V6.19.7
// join/wait behavior is preserved.
const collectorStaleCycleThresholdV6197 = 15 * time.Minute

const collectorCycleRuntimePythonV6197 = `
import json, sqlite3, sys
path=sys.argv[1]
cycle_id=int(sys.argv[2])
conn=sqlite3.connect('file:'+path+'?mode=ro',uri=True)
conn.row_factory=sqlite3.Row
row=conn.execute("SELECT status,COALESCE(started_at,'') started_at FROM cycles WHERE id=?",(cycle_id,)).fetchone()
if row is None:
    print(json.dumps({'found':False},separators=(',',':')))
    raise SystemExit(0)
print(json.dumps({'found':True,'status':str(row['status'] or ''),'started_at':str(row['started_at'] or '')},separators=(',',':')))
`

type collectorCycleRuntimeV6197 struct {
	Found     bool   `json:"found"`
	Status    string `json:"status"`
	StartedAt string `json:"started_at"`
}

func collectorCycleStaleByStartedAtV6197(status, startedAt string, now time.Time) bool {
	if strings.ToUpper(strings.TrimSpace(status)) != "RUNNING" {
		return false
	}
	startedAt = strings.TrimSpace(startedAt)
	if startedAt == "" {
		return false
	}
	started, err := time.Parse(time.RFC3339Nano, startedAt)
	if err != nil {
		started, err = time.Parse(time.RFC3339, startedAt)
	}
	if err != nil || started.After(now) {
		return false
	}
	return now.Sub(started) >= collectorStaleCycleThresholdV6197
}

func collectorCycleRuntimeV6197Read(ctx context.Context, cycleID int64) (collectorCycleRuntimeV6197, error) {
	dbPath := strings.TrimSpace(os.Getenv("WFGG_COLLECTOR_DB"))
	if dbPath == "" {
		dbPath = "/opt/wfgg-collector/data/collector.db"
	}
	if _, err := os.Stat(dbPath); err != nil {
		return collectorCycleRuntimeV6197{}, errors.New("COLLECTOR_DB_UNAVAILABLE")
	}
	py, err := exec.LookPath("python3")
	if err != nil {
		return collectorCycleRuntimeV6197{}, errors.New("COLLECTOR_STALE_CHECK_PYTHON3_MISSING")
	}
	checkCtx, cancel := context.WithTimeout(ctx, 5*time.Second)
	defer cancel()
	cmd := exec.CommandContext(checkCtx, py, "-c", collectorCycleRuntimePythonV6197, dbPath, strconv.FormatInt(cycleID, 10))
	out, err := cmd.Output()
	if err != nil {
		return collectorCycleRuntimeV6197{}, errors.New("COLLECTOR_STALE_CHECK_FAILED")
	}
	var snap collectorCycleRuntimeV6197
	if err := json.Unmarshal(out, &snap); err != nil {
		return collectorCycleRuntimeV6197{}, errors.New("COLLECTOR_STALE_CHECK_INVALID")
	}
	return snap, nil
}

func collectorRecoverStaleJoinedCycleV6197(ctx context.Context, cycleID int64) (bool, error) {
	snap, err := collectorCycleRuntimeV6197Read(ctx, cycleID)
	if err != nil {
		return false, nil
	}
	if !snap.Found || !collectorCycleStaleByStartedAtV6197(snap.Status, snap.StartedAt, time.Now().UTC()) {
		return false, nil
	}
	finishCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	if err := collectorFinishCycle(finishCtx, cycleID, "FAILED", "STALE_RUNNING_CYCLE_RECOVERED_V6197"); err != nil {
		return false, errors.New("COLLECTOR_STALE_CYCLE_FINISH_FAILED")
	}
	return true, nil
}

func collectorStartCycleWithStaleRecoveryV6197(ctx context.Context, query string) (collectorCycle, bool, bool, error) {
	cycle, joined, err := collectorStartCycle(ctx, query)
	if err != nil || !joined {
		return cycle, joined, false, err
	}
	recovered, recoveryErr := collectorRecoverStaleJoinedCycleV6197(ctx, cycle.ID)
	if recoveryErr != nil {
		return collectorCycle{}, false, false, recoveryErr
	}
	if !recovered {
		return cycle, joined, false, nil
	}
	cycle, joined, err = collectorStartCycle(ctx, query)
	if err != nil {
		return collectorCycle{}, false, true, err
	}
	if joined && cycle.ID == 0 {
		return collectorCycle{}, false, true, errors.New("COLLECTOR_STALE_CYCLE_RESTART_INVALID")
	}
	return cycle, joined, true, nil
}
