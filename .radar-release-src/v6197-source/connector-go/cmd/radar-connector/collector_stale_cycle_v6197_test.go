package main

import (
	"testing"
	"time"
)

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
