#!/usr/bin/env python3
from pathlib import Path

ROOT = Path('/tmp/wfgg-radar')
AUTOPILOT = ROOT / 'connector-go/cmd/radar-connector/server_autopilot_v6194.go'
HELPER = ROOT / 'connector-go/cmd/radar-connector/autopilot_adaptive_verification_v61917.go'
TEST = ROOT / 'connector-go/cmd/radar-connector/autopilot_adaptive_verification_v61917_test.go'

text = AUTOPILOT.read_text(encoding='utf-8')
marker = '// WFGG_RADAR_AUTOPILOT_ADAPTIVE_VERIFICATION_V61917'
bt = chr(96)

if marker not in text:
    old_version = 'autopilotVersionV6194                    = "v6.19.16"'
    new_version = 'autopilotVersionV6194                    = "v6.19.17"'
    if old_version in text:
        text = text.replace(old_version, new_version, 1)
    elif new_version not in text:
        raise SystemExit('V61917_VERSION_ANCHOR_MISSING')

    req_anchor = '\tFullCyclesPerCluster     int    ' + bt + 'json:"fullCyclesPerCluster,omitempty"' + bt + '\n'
    if text.count(req_anchor) != 1:
        raise SystemExit(f'V61917_REQUEST_ANCHOR_COUNT={text.count(req_anchor)}')
    text = text.replace(
        req_anchor,
        req_anchor + '\tAdaptiveVerification     bool   ' + bt + 'json:"adaptiveVerification,omitempty"' + bt + '\n',
        1,
    )

    job_anchor = '\tRequiredFullCycles      int                             ' + bt + 'json:"requiredFullCycles"' + bt + '\n'
    if text.count(job_anchor) != 1:
        raise SystemExit(f'V61917_JOB_ANCHOR_COUNT={text.count(job_anchor)}')
    text = text.replace(
        job_anchor,
        job_anchor
        + '\tAdaptiveVerification    bool                            ' + bt + 'json:"adaptiveVerification,omitempty"' + bt + '\n'
        + '\tVerificationMode        string                          ' + bt + 'json:"verificationMode,omitempty"' + bt + '\n',
        1,
    )

    old_cycles = """\tfullCycles := input.FullCyclesPerCluster
\tif fullCycles == 0 {
\t\tfullCycles = autopilotDefaultFullCyclesV6194
\t}
\tif fullCycles < 1 || fullCycles > autopilotMaxFullCyclesV6194 {
\t\twriteJSON(w, http.StatusBadRequest, map[string]any{"error": "AUTOPILOT_FULL_CYCLES_INVALID"})
\t\treturn
\t}
"""
    new_cycles = """\tfullCycles, verificationMode, verificationErr := autopilotResolveVerificationV61917(input.FullCyclesPerCluster, input.AdaptiveVerification)
\tif verificationErr != "" {
\t\twriteJSON(w, http.StatusBadRequest, map[string]any{"error": verificationErr})
\t\treturn
\t}
"""
    if text.count(old_cycles) != 1:
        raise SystemExit(f'V61917_CYCLE_VALIDATION_ANCHOR_COUNT={text.count(old_cycles)}')
    text = text.replace(old_cycles, new_cycles, 1)

    init_anchor = '\t\tRequiredFullCycles:      fullCycles,\n'
    if text.count(init_anchor) != 1:
        raise SystemExit(f'V61917_INIT_ANCHOR_COUNT={text.count(init_anchor)}')
    text = text.replace(
        init_anchor,
        init_anchor
        + '\t\tAdaptiveVerification:    input.AdaptiveVerification,\n'
        + '\t\tVerificationMode:        verificationMode,\n',
        1,
    )

    scout_anchor = 'func (s *server) autopilotScoutNextSeedV6194(ctx context.Context, jobID, token string) (*seedScoutRecommendationV6193, string) {'
    if text.count(scout_anchor) != 1:
        raise SystemExit(f'V61917_MARKER_ANCHOR_COUNT={text.count(scout_anchor)}')
    text = text.replace(scout_anchor, marker + '\n' + scout_anchor, 1)

AUTOPILOT.write_text(text, encoding='utf-8')

HELPER.write_text("""package main

func autopilotResolveVerificationV61917(requested int, adaptive bool) (int, string, string) {
    if adaptive {
        if requested != 0 && requested != 1 {
            return 0, "", "AUTOPILOT_ADAPTIVE_FULL_CYCLES_CONFLICT_V61917"
        }
        return 1, "ADAPTIVE_FAST", ""
    }
    fullCycles := requested
    if fullCycles == 0 {
        fullCycles = autopilotDefaultFullCyclesV6194
    }
    if fullCycles < 1 || fullCycles > autopilotMaxFullCyclesV6194 {
        return 0, "", "AUTOPILOT_FULL_CYCLES_INVALID"
    }
    return fullCycles, "FIXED", ""
}
""", encoding='utf-8')

TEST.write_text("""package main

import "testing"

func TestAutopilotResolveVerificationV61917(t *testing.T) {
    cases := []struct{ requested int; adaptive bool; wantCycles int; wantMode string; wantErr string }{
        {0,true,1,"ADAPTIVE_FAST",""},
        {1,true,1,"ADAPTIVE_FAST",""},
        {3,true,0,"","AUTOPILOT_ADAPTIVE_FULL_CYCLES_CONFLICT_V61917"},
        {0,false,autopilotDefaultFullCyclesV6194,"FIXED",""},
        {3,false,3,"FIXED",""},
    }
    for _, tc := range cases {
        cycles, mode, errCode := autopilotResolveVerificationV61917(tc.requested, tc.adaptive)
        if cycles != tc.wantCycles || mode != tc.wantMode || errCode != tc.wantErr {
            t.Fatalf("requested=%d adaptive=%v -> cycles=%d mode=%s err=%s", tc.requested, tc.adaptive, cycles, mode, errCode)
        }
    }
}

func TestAutopilotAdaptiveOneFullCycleConfirmsV61917(t *testing.T) {
    id := "adaptive-one-full-v61917"
    radarAutopilotJobsV6194.add(&autopilotJobV6194{
        ID:id, Status:"RUNNING", Phase:"CYCLE_FULL", CurrentSeed:"8121", CurrentCommand:"@federated:8121",
        CurrentFullCycleIDs:[]int64{501}, RequiredFullCycles:1, ValidatedCycles:1,
        AdaptiveVerification:true, VerificationMode:"ADAPTIVE_FAST",
        History:[]autopilotClusterResultV6194{}, SkippedSeeds:[]autopilotSkippedSeedV6196{},
    })
    if !autopilotConfirmCurrentClusterV6194(id) { t.Fatal("one valid 9/9 cycle must confirm in adaptive mode") }
    job, _ := radarAutopilotJobsV6194.get(id)
    if job.ConfirmedClusters != 1 || len(job.History) != 1 { t.Fatalf("unexpected confirmation state: %#v", job) }
    if job.History[0].FullCycles != 1 || len(job.History[0].CycleIDs) != 1 || job.History[0].CycleIDs[0] != 501 {
        t.Fatalf("adaptive evidence not preserved: %#v", job.History[0])
    }
}

func TestAutopilotAdaptivePartialDoesNotConfirmV61917(t *testing.T) {
    id := "adaptive-partial-v61917"
    radarAutopilotJobsV6194.add(&autopilotJobV6194{
        ID:id, Status:"RUNNING", Phase:"CYCLE_PARTIAL_RETRY", CurrentSeed:"8122", CurrentCommand:"@federated:8122",
        RequiredFullCycles:1, ValidatedCycles:0, PartialCycles:1, AdaptiveVerification:true, VerificationMode:"ADAPTIVE_FAST",
        History:[]autopilotClusterResultV6194{}, SkippedSeeds:[]autopilotSkippedSeedV6196{},
    })
    if autopilotConfirmCurrentClusterV6194(id) { t.Fatal("partial cycle must not confirm adaptive coverage") }
}
""", encoding='utf-8')

print('RADAR_V61917_CONNECTOR_ADAPTIVE_VERIFICATION=READY')
