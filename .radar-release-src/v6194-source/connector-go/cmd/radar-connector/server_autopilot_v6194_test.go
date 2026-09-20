package main

import (
	"testing"
	"time"
)

func TestNormalizeAutopilotSeedV6194(t *testing.T) {
	cases := map[string]string{
		"8122":            "8122",
		" @federated:8122 ":"8122",
		"@federated:APS972":"972",
		"":                "",
	}
	for in, want := range cases {
		got, ok := normalizeAutopilotSeedV6194(in)
		if !ok || got != want {
			t.Fatalf("normalize %q = %q ok=%v; want %q", in, got, ok, want)
		}
	}
	for _, in := range []string{"abc", "@federated:-1", "@federated:0"} {
		if _, ok := normalizeAutopilotSeedV6194(in); ok {
			t.Fatalf("expected invalid seed %q", in)
		}
	}
}

func TestClassifyAutopilotCycleV6194(t *testing.T) {
	if got := classifyAutopilotCycleV6194(collectorJob{Status:"SUCCESS", RegionsCompleted:9, RegionsFailed:0}); got != "FULL" {
		t.Fatalf("full classified %s", got)
	}
	if got := classifyAutopilotCycleV6194(collectorJob{Status:"SUCCESS", RegionsCompleted:8, RegionsFailed:1}); got != "PARTIAL" {
		t.Fatalf("partial classified %s", got)
	}
	if got := classifyAutopilotCycleV6194(collectorJob{Status:"SUCCESS", Joined:true}); got != "JOINED" {
		t.Fatalf("joined classified %s", got)
	}
	if got := classifyAutopilotCycleV6194(collectorJob{Status:"FAILED", Error:"X"}); got != "FAILED" {
		t.Fatalf("failed classified %s", got)
	}
}

func TestAutopilotAuthFailureV6194(t *testing.T) {
	if !autopilotIsAuthFailureV6194(collectorJob{FailureCategory:"AUTH", FailureCode:"LASTWAR_AUTH_REJECTED"}) {
		t.Fatal("expected auth failure")
	}
	if autopilotIsAuthFailureV6194(collectorJob{FailureCategory:"PROTOCOL", FailureCode:"FMTWIREERROR"}) {
		t.Fatal("unexpected auth failure")
	}
}

func TestAutopilotConfirmCurrentClusterV6194SkipsRedundantScan(t *testing.T) {
	id := "test-confirm-complete"
	radarAutopilotJobsV6194.add(&autopilotJobV6194{
		ID:                  id,
		Status:              "RUNNING",
		Phase:               "HISTORICAL_EVIDENCE_REUSED",
		CurrentSeed:         "8122",
		CurrentCommand:      "@federated:8122",
		CurrentFullCycleIDs: []int64{101, 102, 103},
		RequiredFullCycles:  3,
		ValidatedCycles:     3,
		MaxClusters:         5,
		History:             []autopilotClusterResultV6194{},
	})
	if !autopilotConfirmCurrentClusterV6194(id) {
		t.Fatal("expected existing 3/3 evidence to confirm without another scan")
	}
	job, ok := radarAutopilotJobsV6194.get(id)
	if !ok {
		t.Fatal("job missing")
	}
	if job.ConfirmedClusters != 1 {
		t.Fatalf("confirmed clusters=%d want=1", job.ConfirmedClusters)
	}
	if job.CurrentSeed != "" {
		t.Fatalf("current seed should be cleared, got %q", job.CurrentSeed)
	}
	if len(job.History) != 1 || len(job.History[0].CycleIDs) != 3 {
		t.Fatalf("unexpected history: %#v", job.History)
	}
}


func TestAutopilotNoDataFailureV6196(t *testing.T) {
	regions := make([]collectorRegionFailure, 0, 9)
	for i := 1; i <= 9; i++ {
		regions = append(regions, collectorRegionFailure{
			Region: i, Category: "PROTOCOL", Code: "MAP_REGION_FAILED",
			Cause: "LASTWAR_PLAYER_SCAN_SYNTHETIC_READ_FAILED:FMTWIREERROR",
		})
	}
	job := collectorJob{
		Status: "FAILED", Error: "MAP_ALL_REGIONS_FAILED",
		RegionsCompleted: 0, RegionsFailed: 9, PlayersSeen: 0,
		RegionFailures: regions,
	}
	if !autopilotIsNoDataFailureV6196(job) {
		t.Fatal("expected all-region protocol/no-data failure to be skippable")
	}
	job.RegionFailures[0].Category = "NETWORK"
	job.RegionFailures[0].Cause = "LASTWAR_NATIVE_DIAL_FAILED"
	if autopilotIsNoDataFailureV6196(job) {
		t.Fatal("network failure must not be classified as no-data")
	}
	job.RegionFailures[0].Category = "AUTH"
	job.RegionFailures[0].Cause = "LASTWAR_AUTH_REJECTED"
	if autopilotIsNoDataFailureV6196(job) {
		t.Fatal("auth failure must not be classified as no-data")
	}
}

func TestAutopilotSkipNoDataPreservesEvidenceV6196(t *testing.T) {
	id := "test-skip-no-data"
	radarAutopilotJobsV6194.add(&autopilotJobV6194{
		ID: id, Status: "RUNNING", Phase: "CYCLE_NO_DATA_RETRY",
		CurrentSeed: "8124", CurrentCommand: "@federated:8124",
		CurrentFullCycleIDs: []int64{41}, RequiredFullCycles: 3,
		ValidatedCycles: 1, FailedCycles: 3, ConsecutiveNoData: 3,
		NoDataRetryLimit: 3, MaxClusters: 5,
		History: []autopilotClusterResultV6194{},
		SkippedSeeds: []autopilotSkippedSeedV6196{},
	})
	if !autopilotSkipCurrentSeedNoDataV6196(id) {
		t.Fatal("expected seed skip")
	}
	job, ok := radarAutopilotJobsV6194.get(id)
	if !ok {
		t.Fatal("job missing")
	}
	if job.CurrentSeed != "" || job.ValidatedCycles != 0 || job.ConsecutiveNoData != 0 {
		t.Fatalf("current seed state not reset: %#v", job)
	}
	if job.ConfirmedClusters != 0 {
		t.Fatalf("skipped seed must not count as confirmed: %d", job.ConfirmedClusters)
	}
	if len(job.SkippedSeeds) != 1 || job.SkippedSeeds[0].Seed != "8124" {
		t.Fatalf("missing skipped seed evidence: %#v", job.SkippedSeeds)
	}
	if job.SkippedSeeds[0].ValidatedCycles != 1 || len(job.SkippedSeeds[0].CycleIDs) != 1 || job.SkippedSeeds[0].CycleIDs[0] != 41 {
		t.Fatalf("valid historical evidence was not preserved: %#v", job.SkippedSeeds[0])
	}
}


func TestCollectorCycleStaleByStartedAtV6197(t *testing.T) {
	now := time.Date(2026, 9, 20, 15, 5, 0, 0, time.UTC)
	if !collectorCycleStaleByStartedAtV6197("RUNNING", "2026-09-20T13:56:37.954143Z", now) {
		t.Fatal("expected 68-minute running cycle to be stale")
	}
	if collectorCycleStaleByStartedAtV6197("RUNNING", "2026-09-20T14:55:00Z", now) {
		t.Fatal("10-minute running cycle must not be recovered")
	}
	if collectorCycleStaleByStartedAtV6197("SUCCESS", "2026-09-20T13:00:00Z", now) {
		t.Fatal("completed cycle must never be recovered as stale")
	}
	if collectorCycleStaleByStartedAtV6197("RUNNING", "not-a-time", now) {
		t.Fatal("unparseable start time must fail closed")
	}
}
