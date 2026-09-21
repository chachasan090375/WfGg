#!/usr/bin/env python3
from pathlib import Path

AUTOPILOT = Path('/tmp/wfgg-radar/connector-go/cmd/radar-connector/server_autopilot_v6194.go')
AUTOPILOT_TEST = Path('/tmp/wfgg-radar/connector-go/cmd/radar-connector/server_autopilot_v6194_test.go')
text = AUTOPILOT.read_text(encoding='utf-8')
marker = '// WFGG_RADAR_AUTOPILOT_CONTINUE_PARTIAL_LIMIT_V61910'

if marker not in text:
    anchor = 'func autopilotStoppedV6194(id string) bool {'
    if text.count(anchor) != 1:
        raise SystemExit(f'V61910_SKIP_ANCHOR_COUNT={text.count(anchor)}')
    helper = r'''// WFGG_RADAR_AUTOPILOT_CONTINUE_PARTIAL_LIMIT_V61910
func autopilotSkipCurrentSeedPartialV61910(jobID string) bool {
	job, ok := radarAutopilotJobsV6194.get(jobID)
	if !ok || strings.TrimSpace(job.CurrentSeed) == "" {
		return false
	}
	record := autopilotSkippedSeedV6196{
		Seed:            job.CurrentSeed,
		Command:         "@federated:" + job.CurrentSeed,
		Reason:          "PARTIAL_AFTER_RETRIES",
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
		a.Phase = "SEED_SKIPPED_PARTIAL"
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

'''
    text = text.replace(anchor, helper + anchor, 1)

old = '''		if job.PartialCycles >= job.PartialRetryLimit && job.ValidatedCycles < job.RequiredFullCycles {
			autopilotFailV6194(jobID, "PARTIAL_RETRY_LIMIT", "AUTOPILOT_PARTIAL_RETRY_LIMIT")
			return
		}
'''
new = '''		if job.PartialCycles >= job.PartialRetryLimit && job.ValidatedCycles < job.RequiredFullCycles {
			if !autopilotSkipCurrentSeedPartialV61910(jobID) {
				autopilotFailV6194(jobID, "PARTIAL_SKIP_FAILED", "AUTOPILOT_PARTIAL_SKIP_INVARIANT")
				return
			}
			time.Sleep(1200 * time.Millisecond)
			continue
		}
'''
if text.count(old) != 1:
    raise SystemExit(f'V61910_PARTIAL_LIMIT_ANCHOR_COUNT={text.count(old)}')
text = text.replace(old, new, 1)

if 'autopilotVersionV6194                    = "v6.19.9"' in text:
    text = text.replace(
        'autopilotVersionV6194                    = "v6.19.9"',
        'autopilotVersionV6194                    = "v6.19.10"',
        1,
    )
elif 'autopilotVersionV6194                    = "v6.19.10"' not in text:
    raise SystemExit('V61910_VERSION_ANCHOR_MISSING')

AUTOPILOT.write_text(text, encoding='utf-8')
print('RADAR_V61910_AUTOPILOT_CONTINUE_PARTIAL_LIMIT=READY')

test_text = AUTOPILOT_TEST.read_text(encoding='utf-8')
test_marker = 'func TestAutopilotSkipPartialPreservesEvidenceV61910'
if test_marker not in test_text:
    test_text += r'''

func TestAutopilotSkipPartialPreservesEvidenceV61910(t *testing.T) {
	id := "test-skip-partial-v61910"
	radarAutopilotJobsV6194.add(&autopilotJobV6194{
		ID: id, Status: "RUNNING", Phase: "CYCLE_PARTIAL_RETRY",
		CurrentSeed: "8120", CurrentCommand: "@federated:8120",
		CurrentFullCycleIDs: []int64{71}, RequiredFullCycles: 3,
		ValidatedCycles: 1, PartialCycles: 5, PartialRetryLimit: 5,
		MaxClusters: 5,
		History: []autopilotClusterResultV6194{},
		SkippedSeeds: []autopilotSkippedSeedV6196{},
	})
	if !autopilotSkipCurrentSeedPartialV61910(id) {
		t.Fatal("expected partial-limited seed skip")
	}
	job, ok := radarAutopilotJobsV6194.get(id)
	if !ok {
		t.Fatal("job missing")
	}
	if job.CurrentSeed != "" || job.ValidatedCycles != 0 || job.PartialCycles != 0 {
		t.Fatalf("current seed state not reset: %#v", job)
	}
	if job.ConfirmedClusters != 0 {
		t.Fatalf("skipped partial seed must not count as confirmed: %d", job.ConfirmedClusters)
	}
	if len(job.SkippedSeeds) != 1 || job.SkippedSeeds[0].Seed != "8120" {
		t.Fatalf("missing skipped partial seed evidence: %#v", job.SkippedSeeds)
	}
	skipped := job.SkippedSeeds[0]
	if skipped.Reason != "PARTIAL_AFTER_RETRIES" {
		t.Fatalf("wrong skip reason: %#v", skipped)
	}
	if skipped.ValidatedCycles != 1 || skipped.PartialCycles != 5 {
		t.Fatalf("quality counters not preserved in skip evidence: %#v", skipped)
	}
	if len(skipped.CycleIDs) != 1 || skipped.CycleIDs[0] != 71 {
		t.Fatalf("valid 9/9 evidence IDs not preserved: %#v", skipped)
	}
	if job.LastSkippedSeed == nil || job.LastSkippedSeed.Reason != "PARTIAL_AFTER_RETRIES" {
		t.Fatalf("last skipped partial seed missing: %#v", job.LastSkippedSeed)
	}
}
'''
    AUTOPILOT_TEST.write_text(test_text, encoding='utf-8')
    print('RADAR_V61910_PARTIAL_SKIP_TEST=ADDED')
else:
    print('RADAR_V61910_PARTIAL_SKIP_TEST=ALREADY_PRESENT')
