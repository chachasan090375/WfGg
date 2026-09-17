package main

import (
	"testing"

	"wfgg-radar-connector/internal/protocol"
)

func TestAppendProfileUIDsV697DeduplicatesAcrossRegions(t *testing.T) {
	seen := map[string]struct{}{}
	var got []string
	got = appendProfileUIDsV697(got, seen, []protocol.Player{
		{GameUID: "101"}, {GameUID: " 202 "}, {GameUID: ""},
	})
	got = appendProfileUIDsV697(got, seen, []protocol.Player{
		{GameUID: "202"}, {GameUID: "303"}, {GameUID: "101"},
	})
	if len(got) != 3 || got[0] != "101" || got[1] != "202" || got[2] != "303" {
		t.Fatalf("unexpected UID universe: %#v", got)
	}
}

func TestProfileAttemptBudgetV697ScalesBeyondDeltaBudget(t *testing.T) {
	if got := profileAttemptBudgetV697(271); got != 192 {
		t.Fatalf("small population should retain V6.8 floor: %d", got)
	}
	if got := profileAttemptBudgetV697(23483); got <= 470 {
		t.Fatalf("full population budget must exceed initial batch count: %d", got)
	}
	if got := profileAttemptBudgetV697(1000000); got != 2048 {
		t.Fatalf("safety ceiling not enforced: %d", got)
	}
}
