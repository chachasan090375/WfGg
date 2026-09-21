#!/usr/bin/env python3
from pathlib import Path

ROOT = Path('/tmp/wfgg-radar')
AUTOPILOT = ROOT / 'connector-go/cmd/radar-connector/server_autopilot_v6194.go'
HELPER = ROOT / 'connector-go/cmd/radar-connector/autopilot_coverage_completion_v61914.go'
TEST = ROOT / 'connector-go/cmd/radar-connector/autopilot_coverage_completion_v61914_test.go'

text = AUTOPILOT.read_text(encoding='utf-8')
marker = '// WFGG_RADAR_AUTOPILOT_COVERAGE_COMPLETION_V61914'
bt = chr(96)

if marker not in text:
    # Explicit opt-in request flag. Existing API callers keep bounded MaxClusters behavior.
    req_anchor = '\tScoutMinPlayers          int    ' + bt + 'json:"scoutMinPlayers,omitempty"' + bt + '\n'
    if text.count(req_anchor) != 1:
        raise SystemExit(f'V61914_REQUEST_ANCHOR_COUNT={text.count(req_anchor)}')
    text = text.replace(
        req_anchor,
        req_anchor + '\tCoverageMode             bool   ' + bt + 'json:"coverageMode,omitempty"' + bt + '\n',
        1,
    )

    # Runtime coverage state is observable but contains no credential.
    field_anchor = '\tPersistentResume        bool                            ' + bt + 'json:"persistentResume,omitempty"' + bt + '\n'
    if text.count(field_anchor) != 1:
        raise SystemExit(f'V61914_JOB_FIELD_ANCHOR_COUNT={text.count(field_anchor)}')
    field_add = (
        '\tCoverageMode             bool                            ' + bt + 'json:"coverageMode,omitempty"' + bt + '\n'
        '\tCoverageComplete         bool                            ' + bt + 'json:"coverageComplete,omitempty"' + bt + '\n'
        '\tCoverageReason           string                          ' + bt + 'json:"coverageReason,omitempty"' + bt + '\n'
        '\tCoverageWindows          int                             ' + bt + 'json:"coverageWindows,omitempty"' + bt + '\n'
        '\tCoverageCandidatesScouted int                            ' + bt + 'json:"coverageCandidatesScouted,omitempty"' + bt + '\n'
    )
    text = text.replace(field_anchor, field_anchor + field_add, 1)

    version_old = 'autopilotVersionV6194                    = "v6.19.13"'
    version_new = 'autopilotVersionV6194                    = "v6.19.14"'
    if version_old in text:
        text = text.replace(version_old, version_new, 1)
    elif version_new not in text:
        raise SystemExit('V61914_VERSION_ANCHOR_MISSING')

    # Coverage mode resumes the Seed Scout frontier after a window exhausts.
    offset_old = '\toffset := 0\n'
    if text.count(offset_old) != 1:
        raise SystemExit(f'V61914_SCOUT_OFFSET_ANCHOR_COUNT={text.count(offset_old)}')
    text = text.replace(
        offset_old,
        '\toffset := autopilotScoutStartOffsetV61914(job)\n',
        1,
    )

    # Record actual scout work and persist the next in-memory frontier within this run.
    scout_done_old = '''\t\tif finalScout.RecommendedSeed != nil {
\t\t\trec := *finalScout.RecommendedSeed
\t\t\treturn &rec, ""
\t\t}
\t\toffset = finalScout.NextOffset
'''
    scout_done_new = '''\t\tif job.CoverageMode {
\t\t\tradarAutopilotJobsV6194.update(jobID, func(a *autopilotJobV6194) {
\t\t\t\ta.CoverageCandidatesScouted += len(finalScout.Attempts)
\t\t\t})
\t\t}
\t\tif finalScout.RecommendedSeed != nil {
\t\t\trec := *finalScout.RecommendedSeed
\t\t\treturn &rec, ""
\t\t}
\t\toffset = finalScout.NextOffset
\t\tif job.CoverageMode {
\t\t\tradarAutopilotJobsV6194.update(jobID, func(a *autopilotJobV6194) {
\t\t\t\ta.ScoutOffset = offset
\t\t\t})
\t\t}
'''
    if text.count(scout_done_old) != 1:
        raise SystemExit(f'V61914_SCOUT_DONE_ANCHOR_COUNT={text.count(scout_done_old)}')
    text = text.replace(scout_done_old, scout_done_new, 1)

    # Coverage mode is unbounded by cluster count. Bounded API mode remains unchanged.
    limit_old = '''\t\tif job.ConfirmedClusters >= job.MaxClusters {
\t\t\tautopilotCompleteV6194(jobID, "MAX_CLUSTERS_REACHED")
\t\t\treturn
\t\t}
'''
    limit_new = '''\t\tif autopilotReachedClusterLimitV61914(job) {
\t\t\tautopilotCompleteV6194(jobID, "MAX_CLUSTERS_REACHED")
\t\t\treturn
\t\t}
'''
    if text.count(limit_old) != 1:
        raise SystemExit(f'V61914_CLUSTER_LIMIT_ANCHOR_COUNT={text.count(limit_old)}')
    text = text.replace(limit_old, limit_new, 1)

    # Distinguish true frontier exhaustion from a finite scout window.
    error_old = '''\t\t\tif errCode != "" {
\t\t\t\tif errCode == "AUTOPILOT_STOP_REQUESTED" {
\t\t\t\t\tautopilotCompleteV6194(jobID, "STOPPED")
\t\t\t\t} else if errCode == "AUTOPILOT_SCOUT_NO_CANDIDATES" || errCode == "AUTOPILOT_SCOUT_BATCH_LIMIT" {
\t\t\t\t\tautopilotCompleteV6194(jobID, "NO_MORE_SEED")
\t\t\t\t} else {
\t\t\t\t\tautopilotFailV6194(jobID, "SCOUT_FAILED", errCode)
\t\t\t\t}
\t\t\t\treturn
\t\t\t}
'''
    error_new = '''\t\t\tif errCode != "" {
\t\t\t\tif errCode == "AUTOPILOT_STOP_REQUESTED" {
\t\t\t\t\tautopilotCompleteV6194(jobID, "STOPPED")
\t\t\t\t\treturn
\t\t\t\t}
\t\t\t\tif job.CoverageMode && errCode == "AUTOPILOT_SCOUT_BATCH_LIMIT" {
\t\t\t\t\tif !autopilotContinueCoverageWindowV61914(jobID) {
\t\t\t\t\t\tautopilotFailV6194(jobID, "COVERAGE_WINDOW_FAILED", "AUTOPILOT_COVERAGE_WINDOW_INVARIANT_V61914")
\t\t\t\t\t\treturn
\t\t\t\t\t}
\t\t\t\t\ttime.Sleep(1500 * time.Millisecond)
\t\t\t\t\tcontinue
\t\t\t\t}
\t\t\t\tif errCode == "AUTOPILOT_SCOUT_NO_CANDIDATES" {
\t\t\t\t\tif job.CoverageMode {
\t\t\t\t\t\tautopilotCompleteCoverageV61914(jobID, "SEED_SCOUT_FRONTIER_EXHAUSTED")
\t\t\t\t\t} else {
\t\t\t\t\t\tautopilotCompleteV6194(jobID, "NO_MORE_SEED")
\t\t\t\t\t}
\t\t\t\t\treturn
\t\t\t\t}
\t\t\t\tif errCode == "AUTOPILOT_SCOUT_BATCH_LIMIT" {
\t\t\t\t\tautopilotCompleteV6194(jobID, "NO_MORE_SEED")
\t\t\t\t\treturn
\t\t\t\t}
\t\t\t\tautopilotFailV6194(jobID, "SCOUT_FAILED", errCode)
\t\t\t\treturn
\t\t\t}
'''
    if text.count(error_old) != 1:
        raise SystemExit(f'V61914_ERROR_BLOCK_ANCHOR_COUNT={text.count(error_old)}')
    text = text.replace(error_old, error_new, 1)

    # Do not reset the frontier until a new seed was actually found; once found,
    # the census may change, so restarting at offset zero is completeness-safe.
    collect_anchor = '''\t\t\t\ta.ScoutBatch = 0
\t\t\t\ta.ScoutOffset = 0
\t\t\t\ta.Phase = "COLLECTING"
'''
    if text.count(collect_anchor) != 1:
        raise SystemExit(f'V61914_COLLECT_ANCHOR_COUNT={text.count(collect_anchor)}')
    # Existing behavior already resets after a recommendation; keep it intentionally.

    # Coverage-mode validation: zero maxClusters means no cluster ceiling.
    max_old = '''\tmaxClusters := input.MaxClusters
\tif maxClusters == 0 {
\t\tmaxClusters = autopilotDefaultMaxClustersV6194
\t}
\tif maxClusters < 1 || maxClusters > autopilotMaxClustersV6194 {
\t\twriteJSON(w, http.StatusBadRequest, map[string]any{"error": "AUTOPILOT_MAX_CLUSTERS_INVALID"})
\t\treturn
\t}
'''
    max_new = '''\tcoverageMode := input.CoverageMode
\tmaxClusters := input.MaxClusters
\tif coverageMode {
\t\tif maxClusters != 0 {
\t\t\twriteJSON(w, http.StatusBadRequest, map[string]any{"error": "AUTOPILOT_COVERAGE_MAX_CLUSTERS_CONFLICT_V61914"})
\t\t\treturn
\t\t}
\t} else {
\t\tif maxClusters == 0 {
\t\t\tmaxClusters = autopilotDefaultMaxClustersV6194
\t\t}
\t\tif maxClusters < 1 || maxClusters > autopilotMaxClustersV6194 {
\t\t\twriteJSON(w, http.StatusBadRequest, map[string]any{"error": "AUTOPILOT_MAX_CLUSTERS_INVALID"})
\t\t\treturn
\t\t}
\t}
'''
    if text.count(max_old) != 1:
        raise SystemExit(f'V61914_MAX_VALIDATION_ANCHOR_COUNT={text.count(max_old)}')
    text = text.replace(max_old, max_new, 1)

    init_anchor = '\t\tMaxClusters:             maxClusters,\n'
    if text.count(init_anchor) != 1:
        raise SystemExit(f'V61914_INIT_ANCHOR_COUNT={text.count(init_anchor)}')
    text = text.replace(
        init_anchor,
        init_anchor + '\t\tCoverageMode:            coverageMode,\n',
        1,
    )

    func_anchor = 'func (s *server) autopilotScoutNextSeedV6194(ctx context.Context, jobID, token string) (*seedScoutRecommendationV6193, string) {'
    if text.count(func_anchor) != 1:
        raise SystemExit(f'V61914_MARKER_ANCHOR_COUNT={text.count(func_anchor)}')
    text = text.replace(func_anchor, marker + '\n' + func_anchor, 1)

AUTOPILOT.write_text(text, encoding='utf-8')

HELPER.write_text(r'''package main

func autopilotReachedClusterLimitV61914(job autopilotJobV6194) bool {
    if job.CoverageMode {
        return false
    }
    return job.MaxClusters > 0 && job.ConfirmedClusters >= job.MaxClusters
}

func autopilotScoutStartOffsetV61914(job autopilotJobV6194) int {
    if job.CoverageMode && job.ScoutOffset > 0 {
        return job.ScoutOffset
    }
    return 0
}

func autopilotContinueCoverageWindowV61914(jobID string) bool {
    job, ok := radarAutopilotJobsV6194.get(jobID)
    if !ok || !job.CoverageMode || job.ScoutOffset <= 0 {
        return false
    }
    _, ok = radarAutopilotJobsV6194.update(jobID, func(a *autopilotJobV6194) {
        a.CoverageWindows++
        a.CoverageReason = "SCOUT_WINDOW_EXHAUSTED_CONTINUE"
        a.Phase = "COVERAGE_FRONTIER_CONTINUE"
    })
    return ok
}

func autopilotCompleteCoverageV61914(jobID, reason string) bool {
    job, ok := radarAutopilotJobsV6194.get(jobID)
    if !ok || !job.CoverageMode {
        return false
    }
    _, ok = radarAutopilotJobsV6194.update(jobID, func(a *autopilotJobV6194) {
        a.Status = "SUCCESS"
        a.Phase = "COVERAGE_COMPLETE"
        a.CoverageComplete = true
        a.CoverageReason = reason
        a.CurrentChildJobID = ""
        a.CurrentScoutJobID = ""
        a.FinishedAt = utcNow()
    })
    return ok
}
''', encoding='utf-8')

TEST.write_text(r'''package main

import "testing"

func TestAutopilotCoverageIgnoresClusterCeilingV61914(t *testing.T) {
    coverage := autopilotJobV6194{CoverageMode: true, MaxClusters: 5, ConfirmedClusters: 99}
    if autopilotReachedClusterLimitV61914(coverage) {
        t.Fatal("coverage mode must not stop at MaxClusters")
    }
    bounded := autopilotJobV6194{CoverageMode: false, MaxClusters: 5, ConfirmedClusters: 5}
    if !autopilotReachedClusterLimitV61914(bounded) {
        t.Fatal("bounded mode must preserve MaxClusters")
    }
}

func TestAutopilotCoverageScoutOffsetV61914(t *testing.T) {
    if got := autopilotScoutStartOffsetV61914(autopilotJobV6194{CoverageMode:true, ScoutOffset:160}); got != 160 {
        t.Fatalf("coverage offset=%d", got)
    }
    if got := autopilotScoutStartOffsetV61914(autopilotJobV6194{CoverageMode:false, ScoutOffset:160}); got != 0 {
        t.Fatalf("bounded offset=%d", got)
    }
}

func TestAutopilotCoverageWindowAndCompletionV61914(t *testing.T) {
    id := "coverage-v61914"
    radarAutopilotJobsV6194.add(&autopilotJobV6194{
        ID:id, Status:"RUNNING", Phase:"SCOUTING", CoverageMode:true,
        ScoutOffset:160, ConfirmedClusters:7,
    })
    if !autopilotContinueCoverageWindowV61914(id) {
        t.Fatal("expected coverage continuation")
    }
    job, _ := radarAutopilotJobsV6194.get(id)
    if job.Phase != "COVERAGE_FRONTIER_CONTINUE" || job.CoverageWindows != 1 || job.CoverageComplete {
        t.Fatalf("unexpected continuation state: %#v", job)
    }
    if !autopilotCompleteCoverageV61914(id, "SEED_SCOUT_FRONTIER_EXHAUSTED") {
        t.Fatal("expected coverage completion")
    }
    job, _ = radarAutopilotJobsV6194.get(id)
    if job.Status != "SUCCESS" || job.Phase != "COVERAGE_COMPLETE" || !job.CoverageComplete {
        t.Fatalf("unexpected complete state: %#v", job)
    }
    if job.CoverageReason != "SEED_SCOUT_FRONTIER_EXHAUSTED" {
        t.Fatalf("reason=%s", job.CoverageReason)
    }
}
''', encoding='utf-8')

print('RADAR_V61914_COVERAGE_COMPLETION=READY')
