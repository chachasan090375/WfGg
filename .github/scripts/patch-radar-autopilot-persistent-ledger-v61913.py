#!/usr/bin/env python3
from pathlib import Path

ROOT = Path('/tmp/wfgg-radar')
AUTOPILOT = ROOT / 'connector-go/cmd/radar-connector/server_autopilot_v6194.go'
HELPER = ROOT / 'connector-go/cmd/radar-connector/autopilot_persistent_ledger_v61913.go'
TEST = ROOT / 'connector-go/cmd/radar-connector/autopilot_persistent_ledger_v61913_test.go'

text = AUTOPILOT.read_text(encoding='utf-8')
marker = '// WFGG_RADAR_AUTOPILOT_PERSISTENT_LEDGER_V61913'
bt = chr(96)

if marker not in text:
    field_anchor = '\tQualifiedSeedsSkipped   []string                        ' + bt + 'json:"qualifiedSeedsSkipped,omitempty"' + bt + '\n'
    if text.count(field_anchor) != 1:
        raise SystemExit(f'V61913_FIELD_ANCHOR_COUNT={text.count(field_anchor)}')
    field_add = (
        '\tPersistentSeedsSkipped  []string                        ' + bt + 'json:"persistentSeedsSkipped,omitempty"' + bt + '\n'
        '\tPersistentLedgerWrites  int                             ' + bt + 'json:"persistentLedgerWrites,omitempty"' + bt + '\n'
        '\tPersistentResume        bool                            ' + bt + 'json:"persistentResume,omitempty"' + bt + '\n'
    )
    text = text.replace(field_anchor, field_anchor + field_add, 1)

    clone_anchor = '\tout.QualifiedSeedsSkipped = append([]string(nil), src.QualifiedSeedsSkipped...)\n'
    if text.count(clone_anchor) != 1:
        raise SystemExit(f'V61913_CLONE_ANCHOR_COUNT={text.count(clone_anchor)}')
    text = text.replace(
        clone_anchor,
        clone_anchor + '\tout.PersistentSeedsSkipped = append([]string(nil), src.PersistentSeedsSkipped...)\n',
        1,
    )

    version_old = 'autopilotVersionV6194                    = "v6.19.12"'
    version_new = 'autopilotVersionV6194                    = "v6.19.13"'
    if version_old in text:
        text = text.replace(version_old, version_new, 1)
    elif version_new not in text:
        raise SystemExit('V61913_VERSION_ANCHOR_MISSING')

    # Before Seed Scout, skip terminal seeds already recorded in the durable ledger.
    scout_old = '''\t\thistoryCtx, historyCancel := context.WithTimeout(ctx, 90*time.Second)
\t\tcandidates, skippedQualified, err := autopilotFilterQualifiedCandidatesV61912(historyCtx, dbPath, rawCandidates, job.RequiredFullCycles)
\t\thistoryCancel()
\t\tif err != nil {
\t\t\treturn nil, "AUTOPILOT_SCOUT_HISTORY_QUALITY_UNAVAILABLE_V61912"
\t\t}
'''
    scout_new = '''\t\tledgerCtx, ledgerCancel := context.WithTimeout(ctx, 15*time.Second)
\t\tcandidates, skippedPersisted, err := autopilotFilterLedgerCandidatesV61913(ledgerCtx, dbPath, rawCandidates)
\t\tledgerCancel()
\t\tif err != nil {
\t\t\treturn nil, "AUTOPILOT_PERSISTENT_LEDGER_UNAVAILABLE_V61913"
\t\t}
\t\tif len(skippedPersisted) > 0 {
\t\t\tradarAutopilotJobsV6194.update(jobID, func(a *autopilotJobV6194) {
\t\t\t\ta.PersistentSeedsSkipped = appendUniqueStringsV61912(a.PersistentSeedsSkipped, skippedPersisted...)
\t\t\t\ta.PersistentResume = true
\t\t\t\ta.Phase = "SCOUT_SKIPPED_PERSISTED"
\t\t\t})
\t\t}
\t\tif len(candidates) == 0 {
\t\t\toffset += len(rawCandidates)
\t\t\tcontinue
\t\t}
\t\thistoryCtx, historyCancel := context.WithTimeout(ctx, 90*time.Second)
\t\tcandidates, skippedQualified, err := autopilotFilterQualifiedCandidatesV61912(historyCtx, dbPath, candidates, job.RequiredFullCycles)
\t\thistoryCancel()
\t\tif err != nil {
\t\t\treturn nil, "AUTOPILOT_SCOUT_HISTORY_QUALITY_UNAVAILABLE_V61912"
\t\t}
'''
    if text.count(scout_old) != 1:
        raise SystemExit(f'V61913_SCOUT_LEDGER_ANCHOR_COUNT={text.count(scout_old)}')
    text = text.replace(scout_old, scout_new, 1)

    # A fresh authenticated start resumes by rejecting a terminal initial seed from the durable ledger.
    initial_old = '''\tif initial, ok := radarAutopilotJobsV6194.get(jobID); ok && strings.TrimSpace(initial.CurrentSeed) != "" {
\t\tif errCode := s.autopilotApplyHistoricalEvidenceV6194(ctx, jobID, initial.CurrentSeed); errCode != "" {
\t\t\tautopilotFailV6194(jobID, "HISTORY_QUALITY_FAILED", errCode)
\t\t\treturn
\t\t}
\t}
'''
    initial_new = '''\tif initial, ok := radarAutopilotJobsV6194.get(jobID); ok && strings.TrimSpace(initial.CurrentSeed) != "" {
\t\tdbPath := autopilotLedgerDBPathV61913()
\t\tledgerCtx, ledgerCancel := context.WithTimeout(ctx, 15*time.Second)
\t\tkept, skipped, ledgerErr := autopilotFilterLedgerCandidatesV61913(ledgerCtx, dbPath, []string{initial.CurrentSeed})
\t\tledgerCancel()
\t\tif ledgerErr != nil {
\t\t\tautopilotFailV6194(jobID, "LEDGER_RESUME_FAILED", "AUTOPILOT_PERSISTENT_LEDGER_UNAVAILABLE_V61913")
\t\t\treturn
\t\t}
\t\tif len(skipped) > 0 {
\t\t\tradarAutopilotJobsV6194.update(jobID, func(a *autopilotJobV6194) {
\t\t\t\ta.PersistentSeedsSkipped = appendUniqueStringsV61912(a.PersistentSeedsSkipped, skipped...)
\t\t\t\ta.PersistentResume = true
\t\t\t\ta.CurrentSeed = ""
\t\t\t\ta.CurrentCommand = ""
\t\t\t\ta.CurrentFullCycleIDs = nil
\t\t\t\ta.ValidatedCycles = 0
\t\t\t\ta.PartialCycles = 0
\t\t\t\ta.FailedCycles = 0
\t\t\t\ta.JoinedCycles = 0
\t\t\t\ta.Phase = "LEDGER_RESUME_SKIPPED_TERMINAL"
\t\t\t})
\t\t} else if len(kept) == 1 {
\t\t\tif errCode := s.autopilotApplyHistoricalEvidenceV6194(ctx, jobID, initial.CurrentSeed); errCode != "" {
\t\t\t\tautopilotFailV6194(jobID, "HISTORY_QUALITY_FAILED", errCode)
\t\t\t\treturn
\t\t\t}
\t\t}
\t}
'''
    if text.count(initial_old) != 1:
        raise SystemExit(f'V61913_INITIAL_RESUME_ANCHOR_COUNT={text.count(initial_old)}')
    text = text.replace(initial_old, initial_new, 1)

    # Persist QUALIFIED before clearing the in-memory seed state.
    confirm_calls = '''\t\tif autopilotConfirmCurrentClusterV6194(jobID) {'''
    if text.count(confirm_calls) != 1:
        raise SystemExit(f'V61913_CONFIRM_EARLY_CALL_COUNT={text.count(confirm_calls)}')
    text = text.replace(
        confirm_calls,
        '''\t\tif autopilotPersistAndConfirmCurrentClusterV61913(jobID) {''',
        1,
    )

    final_confirm = '''\t\tif !autopilotConfirmCurrentClusterV6194(jobID) {
\t\t\tautopilotFailV6194(jobID, "CONFIRMATION_FAILED", "AUTOPILOT_CONFIRMATION_INVARIANT")
\t\t\treturn
\t\t}
'''
    final_confirm_new = '''\t\tif !autopilotPersistAndConfirmCurrentClusterV61913(jobID) {
\t\t\tautopilotFailV6194(jobID, "CONFIRMATION_FAILED", "AUTOPILOT_LEDGER_OR_CONFIRMATION_INVARIANT_V61913")
\t\t\treturn
\t\t}
'''
    if text.count(final_confirm) != 1:
        raise SystemExit(f'V61913_FINAL_CONFIRM_ANCHOR_COUNT={text.count(final_confirm)}')
    text = text.replace(final_confirm, final_confirm_new, 1)

    # Persist terminal skip decisions before resetting in-memory counters.
    nodata_old = '''\t\tif noDataFailure && job.ConsecutiveNoData >= job.NoDataRetryLimit {
\t\t\tif !autopilotSkipCurrentSeedNoDataV6196(jobID) {
'''
    nodata_new = '''\t\tif noDataFailure && job.ConsecutiveNoData >= job.NoDataRetryLimit {
\t\t\tif err := autopilotPersistCurrentSeedOutcomeV61913(jobID, "NO_DATA", "NO_DATA_AFTER_RETRIES"); err != nil {
\t\t\t\tautopilotFailV6194(jobID, "LEDGER_WRITE_FAILED", "AUTOPILOT_LEDGER_WRITE_NO_DATA_FAILED_V61913")
\t\t\t\treturn
\t\t\t}
\t\t\tif !autopilotSkipCurrentSeedNoDataV6196(jobID) {
'''
    if text.count(nodata_old) != 1:
        raise SystemExit(f'V61913_NODATA_ANCHOR_COUNT={text.count(nodata_old)}')
    text = text.replace(nodata_old, nodata_new, 1)

    partial_old = '''\t\tif job.PartialCycles >= job.PartialRetryLimit && job.ValidatedCycles < job.RequiredFullCycles {
\t\t\tif !autopilotSkipCurrentSeedPartialV61910(jobID) {
'''
    partial_new = '''\t\tif job.PartialCycles >= job.PartialRetryLimit && job.ValidatedCycles < job.RequiredFullCycles {
\t\t\tif err := autopilotPersistCurrentSeedOutcomeV61913(jobID, "PARTIAL_LIMIT", "PARTIAL_AFTER_RETRIES"); err != nil {
\t\t\t\tautopilotFailV6194(jobID, "LEDGER_WRITE_FAILED", "AUTOPILOT_LEDGER_WRITE_PARTIAL_FAILED_V61913")
\t\t\t\treturn
\t\t\t}
\t\t\tif !autopilotSkipCurrentSeedPartialV61910(jobID) {
'''
    if text.count(partial_old) != 1:
        raise SystemExit(f'V61913_PARTIAL_ANCHOR_COUNT={text.count(partial_old)}')
    text = text.replace(partial_old, partial_new, 1)

    func_anchor = 'func (s *server) autopilotScoutNextSeedV6194(ctx context.Context, jobID, token string) (*seedScoutRecommendationV6193, string) {'
    if text.count(func_anchor) != 1:
        raise SystemExit(f'V61913_MARKER_ANCHOR_COUNT={text.count(func_anchor)}')
    text = text.replace(func_anchor, marker + '\n' + func_anchor, 1)

AUTOPILOT.write_text(text, encoding='utf-8')

HELPER.write_text(r'''package main

import (
    "context"
    "encoding/json"
    "errors"
    "os"
    "os/exec"
    "strings"
    "time"
)

const autopilotLedgerTableV61913 = "radar_autopilot_ledger_v61913"

type autopilotLedgerEntryV61913 struct {
    Seed               string  `json:"seed"`
    State              string  `json:"state"`
    Reason             string  `json:"reason,omitempty"`
    RequiredFullCycles int     `json:"requiredFullCycles"`
    ValidatedCycles    int     `json:"validatedCycles"`
    PartialCycles      int     `json:"partialCycles"`
    FailedCycles       int     `json:"failedCycles"`
    CycleIDs           []int64 `json:"cycleIds,omitempty"`
    UpdatedAt          string  `json:"updatedAt,omitempty"`
}

type autopilotLedgerReportV61913 struct {
    OK      bool                         `json:"ok"`
    Entries []autopilotLedgerEntryV61913 `json:"entries"`
}

func autopilotLedgerDBPathV61913() string {
    dbPath := strings.TrimSpace(os.Getenv("WFGG_COLLECTOR_DB"))
    if dbPath == "" {
        dbPath = "/opt/wfgg-collector/data/collector.db"
    }
    return dbPath
}

func autopilotLedgerTerminalStateV61913(state string) bool {
    switch strings.ToUpper(strings.TrimSpace(state)) {
    case "QUALIFIED", "NO_DATA", "PARTIAL_LIMIT":
        return true
    default:
        return false
    }
}

const autopilotLedgerReadPythonV61913 = `
import json,sqlite3,sys
path=sys.argv[1]
seeds=json.loads(sys.argv[2])
conn=sqlite3.connect('file:'+path+'?mode=ro',uri=True)
conn.row_factory=sqlite3.Row
conn.execute('PRAGMA query_only=ON')
tables={r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
table='radar_autopilot_ledger_v61913'
if table not in tables or not seeds:
    print(json.dumps({'ok':True,'entries':[]},separators=(',',':')))
    raise SystemExit(0)
marks=','.join('?' for _ in seeds)
rows=[]
for r in conn.execute(
    f"""SELECT seed,state,COALESCE(reason,'') reason,
               required_full_cycles,validated_cycles,partial_cycles,failed_cycles,
               COALESCE(cycle_ids_json,'[]') cycle_ids_json,COALESCE(updated_at,'') updated_at
        FROM {table} WHERE seed IN ({marks})""",
    tuple(seeds)
):
    try: cycle_ids=[int(x) for x in json.loads(r['cycle_ids_json'] or '[]')]
    except Exception: cycle_ids=[]
    rows.append({
        'seed':str(r['seed'] or ''),
        'state':str(r['state'] or ''),
        'reason':str(r['reason'] or ''),
        'requiredFullCycles':int(r['required_full_cycles'] or 0),
        'validatedCycles':int(r['validated_cycles'] or 0),
        'partialCycles':int(r['partial_cycles'] or 0),
        'failedCycles':int(r['failed_cycles'] or 0),
        'cycleIds':cycle_ids,
        'updatedAt':str(r['updated_at'] or ''),
    })
conn.close()
print(json.dumps({'ok':True,'entries':rows},separators=(',',':')))
`

const autopilotLedgerWritePythonV61913 = `
import json,sqlite3,sys
path=sys.argv[1]
entry=json.loads(sys.argv[2])
seed=str(entry.get('seed') or '').strip()
state=str(entry.get('state') or '').strip().upper()
if not seed or state not in {'QUALIFIED','NO_DATA','PARTIAL_LIMIT','FAILED_RETRYABLE'}:
    raise SystemExit(2)
conn=sqlite3.connect(path,timeout=5)
conn.execute('PRAGMA busy_timeout=5000')
conn.execute("""CREATE TABLE IF NOT EXISTS radar_autopilot_ledger_v61913(
    seed TEXT PRIMARY KEY,
    state TEXT NOT NULL,
    reason TEXT NOT NULL DEFAULT '',
    required_full_cycles INTEGER NOT NULL DEFAULT 3,
    validated_cycles INTEGER NOT NULL DEFAULT 0,
    partial_cycles INTEGER NOT NULL DEFAULT 0,
    failed_cycles INTEGER NOT NULL DEFAULT 0,
    cycle_ids_json TEXT NOT NULL DEFAULT '[]',
    first_seen_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)""")
now=str(entry.get('updatedAt') or '')
cycle_ids=json.dumps(entry.get('cycleIds') or [],separators=(',',':'))
conn.execute("""INSERT INTO radar_autopilot_ledger_v61913(
    seed,state,reason,required_full_cycles,validated_cycles,partial_cycles,failed_cycles,
    cycle_ids_json,first_seen_at,updated_at
) VALUES(?,?,?,?,?,?,?,?,?,?)
ON CONFLICT(seed) DO UPDATE SET
    state=excluded.state,
    reason=excluded.reason,
    required_full_cycles=excluded.required_full_cycles,
    validated_cycles=excluded.validated_cycles,
    partial_cycles=excluded.partial_cycles,
    failed_cycles=excluded.failed_cycles,
    cycle_ids_json=excluded.cycle_ids_json,
    updated_at=excluded.updated_at""",(
    seed,state,str(entry.get('reason') or ''),
    int(entry.get('requiredFullCycles') or 0),
    int(entry.get('validatedCycles') or 0),
    int(entry.get('partialCycles') or 0),
    int(entry.get('failedCycles') or 0),
    cycle_ids,now,now
))
conn.commit()
conn.close()
print(json.dumps({'ok':True},separators=(',',':')))
`

func autopilotLedgerReadV61913(ctx context.Context, dbPath string, seeds []string) ([]autopilotLedgerEntryV61913, error) {
    dbPath = strings.TrimSpace(dbPath)
    if dbPath == "" {
        return nil, errors.New("AUTOPILOT_LEDGER_DB_PATH_EMPTY_V61913")
    }
    if _, err := os.Stat(dbPath); err != nil {
        return nil, errors.New("AUTOPILOT_LEDGER_DB_UNAVAILABLE_V61913")
    }
    if _, err := exec.LookPath("python3"); err != nil {
        return nil, errors.New("AUTOPILOT_LEDGER_PYTHON3_MISSING_V61913")
    }
    normalized := make([]string, 0, len(seeds))
    seen := map[string]bool{}
    for _, seed := range seeds {
        seed = strings.TrimSpace(seed)
        if seed == "" || seen[seed] {
            continue
        }
        seen[seed] = true
        normalized = append(normalized, seed)
    }
    raw, _ := json.Marshal(normalized)
    cmd := exec.CommandContext(ctx, "python3", "-c", autopilotLedgerReadPythonV61913, dbPath, string(raw))
    out, err := cmd.Output()
    if err != nil {
        if errors.Is(ctx.Err(), context.DeadlineExceeded) {
            return nil, errors.New("AUTOPILOT_LEDGER_READ_TIMEOUT_V61913")
        }
        return nil, errors.New("AUTOPILOT_LEDGER_READ_FAILED_V61913")
    }
    var report autopilotLedgerReportV61913
    if err := json.Unmarshal(out, &report); err != nil || !report.OK {
        return nil, errors.New("AUTOPILOT_LEDGER_READ_REPORT_INVALID_V61913")
    }
    return append([]autopilotLedgerEntryV61913(nil), report.Entries...), nil
}

func autopilotLedgerWriteV61913(ctx context.Context, dbPath string, entry autopilotLedgerEntryV61913) error {
    dbPath = strings.TrimSpace(dbPath)
    if dbPath == "" {
        return errors.New("AUTOPILOT_LEDGER_DB_PATH_EMPTY_V61913")
    }
    if strings.TrimSpace(entry.Seed) == "" {
        return errors.New("AUTOPILOT_LEDGER_SEED_EMPTY_V61913")
    }
    if _, err := exec.LookPath("python3"); err != nil {
        return errors.New("AUTOPILOT_LEDGER_PYTHON3_MISSING_V61913")
    }
    entry.State = strings.ToUpper(strings.TrimSpace(entry.State))
    if entry.UpdatedAt == "" {
        entry.UpdatedAt = utcNow()
    }
    raw, _ := json.Marshal(entry)
    cmd := exec.CommandContext(ctx, "python3", "-c", autopilotLedgerWritePythonV61913, dbPath, string(raw))
    if out, err := cmd.CombinedOutput(); err != nil {
        if errors.Is(ctx.Err(), context.DeadlineExceeded) {
            return errors.New("AUTOPILOT_LEDGER_WRITE_TIMEOUT_V61913")
        }
        _ = out
        return errors.New("AUTOPILOT_LEDGER_WRITE_FAILED_V61913")
    }
    return nil
}

func autopilotFilterLedgerCandidatesV61913(ctx context.Context, dbPath string, candidates []string) ([]string, []string, error) {
    entries, err := autopilotLedgerReadV61913(ctx, dbPath, candidates)
    if err != nil {
        return nil, nil, err
    }
    terminal := map[string]bool{}
    for _, entry := range entries {
        if autopilotLedgerTerminalStateV61913(entry.State) {
            terminal[strings.TrimSpace(entry.Seed)] = true
        }
    }
    kept := make([]string, 0, len(candidates))
    skipped := make([]string, 0)
    for _, seed := range candidates {
        seed = strings.TrimSpace(seed)
        if seed == "" {
            continue
        }
        if terminal[seed] {
            skipped = append(skipped, seed)
            continue
        }
        kept = append(kept, seed)
    }
    return kept, skipped, nil
}

func autopilotPersistCurrentSeedOutcomeV61913(jobID, state, reason string) error {
    job, ok := radarAutopilotJobsV6194.get(jobID)
    if !ok || strings.TrimSpace(job.CurrentSeed) == "" {
        return errors.New("AUTOPILOT_LEDGER_CURRENT_SEED_MISSING_V61913")
    }
    entry := autopilotLedgerEntryV61913{
        Seed:               job.CurrentSeed,
        State:              state,
        Reason:             reason,
        RequiredFullCycles: job.RequiredFullCycles,
        ValidatedCycles:    job.ValidatedCycles,
        PartialCycles:      job.PartialCycles,
        FailedCycles:       job.FailedCycles,
        CycleIDs:           append([]int64(nil), job.CurrentFullCycleIDs...),
        UpdatedAt:          utcNow(),
    }
    ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
    defer cancel()
    if err := autopilotLedgerWriteV61913(ctx, autopilotLedgerDBPathV61913(), entry); err != nil {
        return err
    }
    radarAutopilotJobsV6194.update(jobID, func(a *autopilotJobV6194) {
        a.PersistentLedgerWrites++
    })
    return nil
}

func autopilotPersistAndConfirmCurrentClusterV61913(jobID string) bool {
    job, ok := radarAutopilotJobsV6194.get(jobID)
    if !ok || strings.TrimSpace(job.CurrentSeed) == "" || job.ValidatedCycles < job.RequiredFullCycles {
        return false
    }
    if err := autopilotPersistCurrentSeedOutcomeV61913(jobID, "QUALIFIED", "FULL_CYCLES_QUALIFIED"); err != nil {
        return false
    }
    return autopilotConfirmCurrentClusterV6194(jobID)
}
''', encoding='utf-8')

TEST.write_text(r'''package main

import (
    "context"
    "os/exec"
    "path/filepath"
    "reflect"
    "testing"
    "time"
)

func requirePythonV61913(t *testing.T) {
    t.Helper()
    if _, err := exec.LookPath("python3"); err != nil {
        t.Skip("python3 unavailable")
    }
}

func newLedgerDBV61913(t *testing.T) string {
    t.Helper()
    requirePythonV61913(t)
    db := filepath.Join(t.TempDir(), "collector.db")
    cmd := exec.Command("python3", "-c", "import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); c.execute('CREATE TABLE cycles(id INTEGER PRIMARY KEY,status TEXT,error TEXT,query TEXT)'); c.commit(); c.close()", db)
    if out, err := cmd.CombinedOutput(); err != nil {
        t.Fatalf("fixture failed: %v: %s", err, out)
    }
    return db
}

func TestAutopilotPersistentLedgerRestartResumeV61913(t *testing.T) {
    db := newLedgerDBV61913(t)
    ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
    defer cancel()

    entries := []autopilotLedgerEntryV61913{
        {Seed:"8120", State:"QUALIFIED", Reason:"FULL_CYCLES_QUALIFIED", RequiredFullCycles:3, ValidatedCycles:3, CycleIDs:[]int64{11,12,13}},
        {Seed:"8121", State:"NO_DATA", Reason:"NO_DATA_AFTER_RETRIES", RequiredFullCycles:3, FailedCycles:3},
        {Seed:"8122", State:"PARTIAL_LIMIT", Reason:"PARTIAL_AFTER_RETRIES", RequiredFullCycles:3, ValidatedCycles:1, PartialCycles:5, CycleIDs:[]int64{21}},
        {Seed:"8123", State:"FAILED_RETRYABLE", Reason:"NETWORK", RequiredFullCycles:3, FailedCycles:1},
    }
    for _, entry := range entries {
        if err := autopilotLedgerWriteV61913(ctx, db, entry); err != nil {
            t.Fatalf("write %s: %v", entry.Seed, err)
        }
    }

    // Simulated process restart: no in-memory job state is used here. The next
    // start reads only the durable Collector ledger.
    kept, skipped, err := autopilotFilterLedgerCandidatesV61913(ctx, db, []string{"8120","8121","8122","8123","8124"})
    if err != nil {
        t.Fatal(err)
    }
    if !reflect.DeepEqual(kept, []string{"8123","8124"}) {
        t.Fatalf("kept=%v", kept)
    }
    if !reflect.DeepEqual(skipped, []string{"8120","8121","8122"}) {
        t.Fatalf("skipped=%v", skipped)
    }
}

func TestAutopilotPersistentLedgerUpsertV61913(t *testing.T) {
    db := newLedgerDBV61913(t)
    ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
    defer cancel()

    if err := autopilotLedgerWriteV61913(ctx, db, autopilotLedgerEntryV61913{
        Seed:"8120", State:"PARTIAL_LIMIT", RequiredFullCycles:3, ValidatedCycles:1, PartialCycles:5,
    }); err != nil {
        t.Fatal(err)
    }
    if err := autopilotLedgerWriteV61913(ctx, db, autopilotLedgerEntryV61913{
        Seed:"8120", State:"QUALIFIED", RequiredFullCycles:3, ValidatedCycles:3, CycleIDs:[]int64{31,32,33},
    }); err != nil {
        t.Fatal(err)
    }
    rows, err := autopilotLedgerReadV61913(ctx, db, []string{"8120"})
    if err != nil {
        t.Fatal(err)
    }
    if len(rows) != 1 || rows[0].State != "QUALIFIED" || rows[0].ValidatedCycles != 3 {
        t.Fatalf("rows=%#v", rows)
    }
}

func TestAutopilotLedgerTerminalStatesV61913(t *testing.T) {
    for _, state := range []string{"QUALIFIED","NO_DATA","PARTIAL_LIMIT"} {
        if !autopilotLedgerTerminalStateV61913(state) {
            t.Fatalf("expected terminal: %s", state)
        }
    }
    for _, state := range []string{"FAILED_RETRYABLE","NETWORK","AUTH_FAILED",""} {
        if autopilotLedgerTerminalStateV61913(state) {
            t.Fatalf("must remain retryable: %s", state)
        }
    }
}
''', encoding='utf-8')

print('RADAR_V61913_PERSISTENT_AUTOPILOT_LEDGER=READY')
