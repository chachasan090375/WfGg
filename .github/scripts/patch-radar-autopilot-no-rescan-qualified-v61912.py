#!/usr/bin/env python3
from pathlib import Path

ROOT = Path('/tmp/wfgg-radar')
AUTOPILOT = ROOT / 'connector-go/cmd/radar-connector/server_autopilot_v6194.go'
HELPER = ROOT / 'connector-go/cmd/radar-connector/autopilot_no_rescan_v61912.go'
TEST = ROOT / 'connector-go/cmd/radar-connector/autopilot_no_rescan_v61912_test.go'

text = AUTOPILOT.read_text(encoding='utf-8')
marker = '// WFGG_RADAR_AUTOPILOT_NO_RESCAN_QUALIFIED_V61912'
bt = chr(96)

if marker not in text:
    field_anchor = '\tLastSkippedSeed         *autopilotSkippedSeedV6196      ' + bt + 'json:"lastSkippedSeed,omitempty"' + bt + '\n'
    if text.count(field_anchor) != 1:
        raise SystemExit(f'V61912_FIELD_ANCHOR_COUNT={text.count(field_anchor)}')
    field_add = '\tQualifiedSeedsSkipped   []string                        ' + bt + 'json:"qualifiedSeedsSkipped,omitempty"' + bt + '\n'
    text = text.replace(field_anchor, field_anchor + field_add, 1)

    clone_anchor = '\tout.SkippedSeeds = append([]autopilotSkippedSeedV6196(nil), src.SkippedSeeds...)\n'
    if text.count(clone_anchor) != 1:
        raise SystemExit(f'V61912_CLONE_ANCHOR_COUNT={text.count(clone_anchor)}')
    text = text.replace(
        clone_anchor,
        clone_anchor + '\tout.QualifiedSeedsSkipped = append([]string(nil), src.QualifiedSeedsSkipped...)\n',
        1,
    )

    scout_anchor = '''\t\tcandidates := seedScoutCandidateWindowV6193(census, offset, job.ScoutLimit)
\t\tif len(candidates) == 0 {
\t\t\treturn nil, "AUTOPILOT_SCOUT_NO_CANDIDATES"
\t\t}
\t\tnow := utcNow()
'''
    if text.count(scout_anchor) != 1:
        raise SystemExit(f'V61912_SCOUT_ANCHOR_COUNT={text.count(scout_anchor)}')
    scout_replacement = '''\t\trawCandidates := seedScoutCandidateWindowV6193(census, offset, job.ScoutLimit)
\t\tif len(rawCandidates) == 0 {
\t\t\treturn nil, "AUTOPILOT_SCOUT_NO_CANDIDATES"
\t\t}
\t\tdbPath := strings.TrimSpace(os.Getenv("WFGG_COLLECTOR_DB"))
\t\tif dbPath == "" {
\t\t\tdbPath = "/opt/wfgg-collector/data/collector.db"
\t\t}
\t\thistoryCtx, historyCancel := context.WithTimeout(ctx, 90*time.Second)
\t\tcandidates, skippedQualified, err := autopilotFilterQualifiedCandidatesV61912(historyCtx, dbPath, rawCandidates, job.RequiredFullCycles)
\t\thistoryCancel()
\t\tif err != nil {
\t\t\treturn nil, "AUTOPILOT_SCOUT_HISTORY_QUALITY_UNAVAILABLE_V61912"
\t\t}
\t\tif len(skippedQualified) > 0 {
\t\t\tradarAutopilotJobsV6194.update(jobID, func(a *autopilotJobV6194) {
\t\t\t\ta.QualifiedSeedsSkipped = appendUniqueStringsV61912(a.QualifiedSeedsSkipped, skippedQualified...)
\t\t\t\ta.Phase = "SCOUT_SKIPPED_QUALIFIED"
\t\t\t})
\t\t}
\t\tif len(candidates) == 0 {
\t\t\toffset += len(rawCandidates)
\t\t\tcontinue
\t\t}
\t\tnow := utcNow()
'''
    text = text.replace(scout_anchor, scout_replacement, 1)

    next_anchor = '\t\t\tNextOffset:          offset + len(candidates),\n'
    if text.count(next_anchor) != 1:
        raise SystemExit(f'V61912_NEXT_OFFSET_ANCHOR_COUNT={text.count(next_anchor)}')
    text = text.replace(
        next_anchor,
        '\t\t\tNextOffset:          offset + len(rawCandidates),\n',
        1,
    )

    version_old = 'autopilotVersionV6194                    = "v6.19.10"'
    version_new = 'autopilotVersionV6194                    = "v6.19.12"'
    if version_old in text:
        text = text.replace(version_old, version_new, 1)
    elif version_new not in text:
        raise SystemExit('V61912_VERSION_ANCHOR_MISSING')

    func_anchor = 'func (s *server) autopilotScoutNextSeedV6194(ctx context.Context, jobID, token string) (*seedScoutRecommendationV6193, string) {'
    if text.count(func_anchor) != 1:
        raise SystemExit(f'V61912_FUNC_ANCHOR_COUNT={text.count(func_anchor)}')
    text = text.replace(func_anchor, marker + '\n' + func_anchor, 1)

AUTOPILOT.write_text(text, encoding='utf-8')

HELPER.write_text(r'''package main

import (
    "context"
)

type autopilotQualifiedLookupV61912 func(context.Context, string) ([]int64, error)

func appendUniqueStringsV61912(dst []string, values ...string) []string {
    seen := make(map[string]bool, len(dst)+len(values))
    out := make([]string, 0, len(dst)+len(values))
    for _, value := range dst {
        if value == "" || seen[value] {
            continue
        }
        seen[value] = true
        out = append(out, value)
    }
    for _, value := range values {
        if value == "" || seen[value] {
            continue
        }
        seen[value] = true
        out = append(out, value)
    }
    return out
}

func autopilotFilterQualifiedCandidatesWithLookupV61912(
    ctx context.Context,
    candidates []string,
    required int,
    lookup autopilotQualifiedLookupV61912,
) ([]string, []string, error) {
    if required <= 0 {
        required = 3
    }
    kept := make([]string, 0, len(candidates))
    skipped := make([]string, 0)
    for _, seed := range candidates {
        if ctx.Err() != nil {
            return nil, nil, ctx.Err()
        }
        ids, err := lookup(ctx, seed)
        if err != nil {
            return nil, nil, err
        }
        if len(ids) >= required {
            skipped = append(skipped, seed)
            continue
        }
        kept = append(kept, seed)
    }
    return kept, skipped, nil
}

func autopilotFilterQualifiedCandidatesV61912(
    ctx context.Context,
    dbPath string,
    candidates []string,
    required int,
) ([]string, []string, error) {
    return autopilotFilterQualifiedCandidatesWithLookupV61912(
        ctx,
        candidates,
        required,
        func(child context.Context, seed string) ([]int64, error) {
            return autopilotTargetedFullCycleIDsV6199(child, dbPath, seed)
        },
    )
}
''', encoding='utf-8')

TEST.write_text(r'''package main

import (
    "context"
    "errors"
    "os/exec"
    "path/filepath"
    "reflect"
    "testing"
)

func TestAutopilotNoRescanQualifiedSeedsV61912(t *testing.T) {
    evidence := map[string][]int64{
        "8120": {1, 2, 3},
        "8121": {4, 5},
        "8122": {6, 7, 8, 9},
    }
    kept, skipped, err := autopilotFilterQualifiedCandidatesWithLookupV61912(
        context.Background(),
        []string{"8120", "8121", "8122"},
        3,
        func(_ context.Context, seed string) ([]int64, error) {
            return evidence[seed], nil
        },
    )
    if err != nil {
        t.Fatal(err)
    }
    if !reflect.DeepEqual(kept, []string{"8121"}) {
        t.Fatalf("kept=%v", kept)
    }
    if !reflect.DeepEqual(skipped, []string{"8120", "8122"}) {
        t.Fatalf("skipped=%v", skipped)
    }
}

func TestAutopilotNoRescanHistoryFailureV61912(t *testing.T) {
    want := errors.New("history unavailable")
    _, _, err := autopilotFilterQualifiedCandidatesWithLookupV61912(
        context.Background(),
        []string{"8120"},
        3,
        func(_ context.Context, _ string) ([]int64, error) {
            return nil, want
        },
    )
    if !errors.Is(err, want) {
        t.Fatalf("err=%v", err)
    }
}

func TestAppendUniqueStringsV61912(t *testing.T) {
    got := appendUniqueStringsV61912([]string{"8120"}, "8120", "8121", "", "8122", "8121")
    want := []string{"8120", "8121", "8122"}
    if !reflect.DeepEqual(got, want) {
        t.Fatalf("got=%v want=%v", got, want)
    }
}


func TestAutopilotNoRescanRealHistoryV61912(t *testing.T) {
    if _, err := exec.LookPath("python3"); err != nil {
        t.Skip("python3 unavailable")
    }
    db := filepath.Join(t.TempDir(), "collector.db")
    script := `
import hashlib,json,sqlite3,sys
db=sys.argv[1]
con=sqlite3.connect(db)
con.execute("CREATE TABLE cycles(id INTEGER PRIMARY KEY,status TEXT,error TEXT,query TEXT)")
con.execute("CREATE TABLE cycle_seen(cycle_id INTEGER,game_uid TEXT,state_hash TEXT)")
con.execute("CREATE TABLE cycle_baseline(cycle_id INTEGER,game_uid TEXT,state_json TEXT)")
con.execute("CREATE TABLE cycle_changes(id INTEGER PRIMARY KEY AUTOINCREMENT,cycle_id INTEGER,game_uid TEXT,after_json TEXT)")
def add(cid,seed):
    raw=json.dumps({"server_id":seed},separators=(",",":"))
    h=hashlib.sha256(raw.encode()).hexdigest()
    uid=f"u{cid}"
    con.execute("INSERT INTO cycles(id,status,error,query) VALUES(?,?,?,?)",(cid,"SUCCESS","","@federated:"+seed))
    con.execute("INSERT INTO cycle_seen(cycle_id,game_uid,state_hash) VALUES(?,?,?)",(cid,uid,h))
    con.execute("INSERT INTO cycle_baseline(cycle_id,game_uid,state_json) VALUES(?,?,?)",(cid,uid,raw))
for cid in (1,2,3): add(cid,"8120")
for cid in (4,5): add(cid,"8121")
con.commit(); con.close()
`
    cmd := exec.Command("python3", "-c", script, db)
    if out, err := cmd.CombinedOutput(); err != nil {
        t.Fatalf("fixture failed: %v: %s", err, out)
    }
    kept, skipped, err := autopilotFilterQualifiedCandidatesV61912(
        context.Background(), db, []string{"8120", "8121"}, 3,
    )
    if err != nil {
        t.Fatal(err)
    }
    if !reflect.DeepEqual(kept, []string{"8121"}) {
        t.Fatalf("kept=%v", kept)
    }
    if !reflect.DeepEqual(skipped, []string{"8120"}) {
        t.Fatalf("skipped=%v", skipped)
    }
}
''', encoding='utf-8')

print('RADAR_V61912_NO_RESCAN_QUALIFIED_SEEDS=READY')
