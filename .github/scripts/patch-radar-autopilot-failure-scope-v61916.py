#!/usr/bin/env python3
from pathlib import Path

ROOT=Path('/tmp/wfgg-radar')
AUTOPILOT=ROOT/'connector-go/cmd/radar-connector/server_autopilot_v6194.go'
LEDGER=ROOT/'connector-go/cmd/radar-connector/autopilot_persistent_ledger_v61913.go'
HELPER=ROOT/'connector-go/cmd/radar-connector/autopilot_failure_scope_v61916.go'
TEST=ROOT/'connector-go/cmd/radar-connector/autopilot_failure_scope_v61916_test.go'
UI=ROOT/'public/live-radar.html'

text=AUTOPILOT.read_text(encoding='utf-8')
marker='// WFGG_RADAR_AUTOPILOT_FAILURE_SCOPE_CONTINUE_V61916'
if marker not in text:
    old_version='autopilotVersionV6194                    = "v6.19.15"'
    new_version='autopilotVersionV6194                    = "v6.19.16"'
    if old_version in text:
        text=text.replace(old_version,new_version,1)
    elif new_version not in text:
        raise SystemExit('V61916_VERSION_ANCHOR_MISSING')

    old='''		if job.ConsecutiveFailures >= job.ConsecutiveFailureLimit {
			autopilotFailV6194(jobID, "FAILURE_LIMIT", "AUTOPILOT_CONSECUTIVE_FAILURE_LIMIT")
			return
		}
'''
    new='''		if job.ConsecutiveFailures >= job.ConsecutiveFailureLimit {
			if autopilotFailureScopeV61916(final) == "SEED_LOCAL" {
				if err := autopilotPersistCurrentSeedOutcomeV61913(jobID, "SEED_LOCAL_LIMIT", "SEED_LOCAL_FAILURE_LIMIT"); err != nil {
					autopilotFailV6194(jobID, "LEDGER_WRITE_FAILED", "AUTOPILOT_LEDGER_WRITE_SEED_LOCAL_LIMIT_FAILED_V61916")
					return
				}
				if !autopilotSkipCurrentSeedFailureScopeV61916(jobID) {
					autopilotFailV6194(jobID, "SEED_LOCAL_SKIP_FAILED", "AUTOPILOT_SEED_LOCAL_SKIP_INVARIANT_V61916")
					return
				}
				time.Sleep(1200 * time.Millisecond)
				continue
			}
			autopilotFailV6194(jobID, "FAILURE_LIMIT", "AUTOPILOT_CONSECUTIVE_FAILURE_LIMIT")
			return
		}
'''
    if text.count(old)!=1:
        raise SystemExit(f'V61916_FAILURE_LIMIT_ANCHOR_COUNT={text.count(old)}')
    text=text.replace(old,new,1)

    anchor='func (s *server) autopilotScoutNextSeedV6194(ctx context.Context, jobID, token string) (*seedScoutRecommendationV6193, string) {'
    if text.count(anchor)!=1:
        raise SystemExit(f'V61916_MARKER_ANCHOR_COUNT={text.count(anchor)}')
    text=text.replace(anchor,marker+'\n'+anchor,1)

AUTOPILOT.write_text(text,encoding='utf-8')

ledger=LEDGER.read_text(encoding='utf-8')
ledger=ledger.replace(
    'case "QUALIFIED", "NO_DATA", "PARTIAL_LIMIT":',
    'case "QUALIFIED", "NO_DATA", "PARTIAL_LIMIT", "SEED_LOCAL_LIMIT":',
    1,
)
ledger=ledger.replace(
    "state not in {'QUALIFIED','NO_DATA','PARTIAL_LIMIT','FAILED_RETRYABLE'}",
    "state not in {'QUALIFIED','NO_DATA','PARTIAL_LIMIT','SEED_LOCAL_LIMIT','FAILED_RETRYABLE'}",
    1,
)
if 'SEED_LOCAL_LIMIT' not in ledger:
    raise SystemExit('V61916_LEDGER_STATE_PATCH_FAILED')
LEDGER.write_text(ledger,encoding='utf-8')

HELPER.write_text(r'''package main

import "strings"

func autopilotFailureScopeV61916(job collectorJob) string {
    hardTokens := []string{
        "AUTH", "NETWORK", "CONNECTOR", "SYSTEM", "TIMEOUT", "DIAL", "CONNECTION",
        "INGEST", "DECODE", "REPORT_INVALID", "CAPTURE_INVALID", "TEMPLATE_NOT_FOUND",
        "BINARY", "EXEC", "PERMISSION", "NO_SPACE", "DISK", "MEMORY", "OOM", "PANIC", "INTERNAL",
    }
    joinedParts := []string{job.Error, job.FailureCategory, job.FailureCode, job.FailureCause, job.AuthState}
    for _, region := range job.RegionFailures {
        joinedParts = append(joinedParts, region.Category, region.Code, region.Cause)
    }
    joined := strings.ToUpper(strings.Join(joinedParts, " "))
    for _, token := range hardTokens {
        if strings.Contains(joined, token) {
            return "BLOCKING"
        }
    }

    category := strings.ToUpper(strings.TrimSpace(job.FailureCategory))
    if category == "PROTOCOL" || category == "SERVER_TARGET" {
        return "SEED_LOCAL"
    }

    if len(job.RegionFailures) > 0 {
        for _, region := range job.RegionFailures {
            c := strings.ToUpper(strings.TrimSpace(region.Category))
            if c != "PROTOCOL" && c != "SERVER_TARGET" {
                return "BLOCKING"
            }
        }
        return "SEED_LOCAL"
    }

    return "BLOCKING"
}

func autopilotSkipCurrentSeedFailureScopeV61916(jobID string) bool {
    job, ok := radarAutopilotJobsV6194.get(jobID)
    if !ok || strings.TrimSpace(job.CurrentSeed) == "" {
        return false
    }
    record := autopilotSkippedSeedV6196{
        Seed:            job.CurrentSeed,
        Command:         "@federated:" + job.CurrentSeed,
        Reason:          "SEED_LOCAL_FAILURE_LIMIT",
        ValidatedCycles: job.ValidatedCycles,
        PartialCycles:   job.PartialCycles,
        FailedCycles:    job.FailedCycles,
        CycleIDs:        append([]int64(nil), job.CurrentFullCycleIDs...),
        SkippedAt:       utcNow(),
    }
    radarAutopilotJobsV6194.update(jobID, func(a *autopilotJobV6194) {
        a.SkippedSeeds = append(a.SkippedSeeds, record)
        x := record
        a.LastSkippedSeed = &x
        a.Phase = "SEED_SKIPPED_FAILURE_SCOPE"
        a.CurrentSeed = ""
        a.CurrentCommand = ""
        a.CurrentFullCycleIDs = nil
        a.ValidatedCycles = 0
        a.PartialCycles = 0
        a.FailedCycles = 0
        a.JoinedCycles = 0
        a.ConsecutiveFailures = 0
        a.ConsecutiveNoData = 0
        a.ScoutBatch = 0
        a.ScoutOffset = 0
        a.LastError = ""
    })
    return true
}
''',encoding='utf-8')

TEST.write_text(r'''package main

import "testing"

func TestAutopilotFailureScopeV61916(t *testing.T) {
    localCases := []collectorJob{
        {Status:"FAILED", Error:"MAP_ALL_REGIONS_FAILED", FailureCategory:"PROTOCOL"},
        {Status:"FAILED", Error:"TARGET_NOT_AVAILABLE", FailureCategory:"SERVER_TARGET"},
    }
    for _, tc := range localCases {
        if got := autopilotFailureScopeV61916(tc); got != "SEED_LOCAL" {
            t.Fatalf("local case classified %s: %#v", got, tc)
        }
    }

    blockingCases := []collectorJob{
        {Status:"FAILED", Error:"AUTH_EXPIRED", FailureCategory:"AUTH"},
        {Status:"FAILED", Error:"NETWORK_TIMEOUT", FailureCategory:"NETWORK"},
        {Status:"FAILED", Error:"CONNECTOR_UNAVAILABLE", FailureCategory:"CONNECTOR"},
        {Status:"FAILED", Error:"SYSTEM_ERROR", FailureCategory:"SYSTEM"},
        {Status:"FAILED", Error:"UNKNOWN_FAILURE"},
    }
    for _, tc := range blockingCases {
        if got := autopilotFailureScopeV61916(tc); got != "BLOCKING" {
            t.Fatalf("blocking case classified %s: %#v", got, tc)
        }
    }
}

func TestAutopilotSkipFailureScopePreservesEvidenceV61916(t *testing.T) {
    id := "test-failure-scope-v61916"
    radarAutopilotJobsV6194.add(&autopilotJobV6194{
        ID:id, Status:"RUNNING", Phase:"CYCLE_FAILED_RETRY",
        CurrentSeed:"8121", CurrentCommand:"@federated:8121",
        CurrentFullCycleIDs:[]int64{101,102}, RequiredFullCycles:3,
        ValidatedCycles:2, PartialCycles:1, FailedCycles:3,
        ConsecutiveFailures:3, ConsecutiveFailureLimit:3,
        History:[]autopilotClusterResultV6194{},
        SkippedSeeds:[]autopilotSkippedSeedV6196{},
    })
    if !autopilotSkipCurrentSeedFailureScopeV61916(id) {
        t.Fatal("expected seed-local failure skip")
    }
    job, ok := radarAutopilotJobsV6194.get(id)
    if !ok {
        t.Fatal("job missing")
    }
    if job.CurrentSeed != "" || job.ValidatedCycles != 0 || job.PartialCycles != 0 || job.ConsecutiveFailures != 0 {
        t.Fatalf("current seed state not reset: %#v", job)
    }
    if len(job.SkippedSeeds) != 1 {
        t.Fatalf("skipped evidence missing: %#v", job.SkippedSeeds)
    }
    skipped := job.SkippedSeeds[0]
    if skipped.Reason != "SEED_LOCAL_FAILURE_LIMIT" || skipped.ValidatedCycles != 2 || skipped.PartialCycles != 1 || skipped.FailedCycles != 3 {
        t.Fatalf("wrong preserved evidence: %#v", skipped)
    }
    if len(skipped.CycleIDs) != 2 || skipped.CycleIDs[0] != 101 || skipped.CycleIDs[1] != 102 {
        t.Fatalf("cycle IDs not preserved: %#v", skipped)
    }
    if job.Phase != "SEED_SKIPPED_FAILURE_SCOPE" {
        t.Fatalf("phase=%s", job.Phase)
    }
}

func TestAutopilotLedgerSeedLocalLimitTerminalV61916(t *testing.T) {
    if !autopilotLedgerTerminalStateV61913("SEED_LOCAL_LIMIT") {
        t.Fatal("SEED_LOCAL_LIMIT must be terminal for no-rescan")
    }
    if autopilotLedgerTerminalStateV61913("FAILED_RETRYABLE") {
        t.Fatal("FAILED_RETRYABLE must remain retryable")
    }
}
''',encoding='utf-8')

ui=UI.read_text(encoding='utf-8')
ui_marker='WFGG_RADAR_AUTOPILOT_FAILURE_SCOPE_CONTINUE_UI_V61916'
if ui_marker not in ui:
    anchor='<!-- WFGG_RADAR_AUTOPILOT_WORKER_COVERAGE_PROPAGATION_UI_V61915 -->'
    if ui.count(anchor)!=1:
        raise SystemExit(f'V61916_UI_MARKER_ANCHOR_COUNT={ui.count(anchor)}')
    ui=ui.replace(anchor,anchor+'\n  <!-- '+ui_marker+' -->',1)
    old_title='<span id="autopilotTitle" class="federated-title">AUTOPILOT V6.19.15 · ARRÊTÉ</span>'
    new_title='<span id="autopilotTitle" class="federated-title">AUTOPILOT V6.19.16 · ARRÊTÉ</span>'
    if ui.count(old_title)!=1:
        raise SystemExit(f'V61916_UI_TITLE_ANCHOR_COUNT={ui.count(old_title)}')
    ui=ui.replace(old_title,new_title,1)

    note_anchor="  if(phase==='COVERAGE_COMPLETE')note.textContent='COUVERTURE TERMINÉE · aucune nouvelle seed exploitable dans la frontière Seed Scout.';"
    if ui.count(note_anchor)!=1:
        raise SystemExit(f'V61916_UI_NOTE_ANCHOR_COUNT={ui.count(note_anchor)}')
    ui=ui.replace(
        note_anchor,
        "  if(phase==='SEED_SKIPPED_FAILURE_SCOPE')note.textContent='Seed ignorée après limite d’échecs locaux PROTOCOL/SERVER_TARGET · preuves conservées · couverture poursuivie.';\n"
        "  else if(phase==='FAILURE_LIMIT')note.textContent='Autopilot arrêté sur erreurs bloquantes AUTH/NETWORK/CONNECTOR/SYSTEM ou erreur non classée.';\n"
        +note_anchor.replace("  if(","  else if("),
        1,
    )

UI.write_text(ui,encoding='utf-8')
print('RADAR_V61916_FAILURE_SCOPE_CONTINUE=READY')
