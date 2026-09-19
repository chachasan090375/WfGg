package main

import (
	"testing"

	"wfgg-radar-connector/internal/protocol"
)

func censusV6193(ids ...string) serverCensusPayloadV612 {
	rows := make([]serverCensusRowV612, 0, len(ids))
	for _, id := range ids {
		rows = append(rows, serverCensusRowV612{ServerID: id, Players: 100})
	}
	return serverCensusPayloadV612{OK: true, Readonly: true, Servers: rows}
}

func TestSeedScoutCandidatesExcludeKnownAndNoise(t *testing.T) {
	census := censusV6193("953", "954", "956", "1006", "1040", "1059", "8119")
	got := seedScoutCandidateSequenceV6193(census, 8)
	if len(got) != 8 {
		t.Fatalf("len=%d got=%v", len(got), got)
	}
	for _, id := range got {
		if id == "953" || id == "954" || id == "956" || id == "1006" || id == "1040" || id == "1059" || id == "8119" {
			t.Fatalf("known id returned: %s in %v", id, got)
		}
	}
}

func TestSeedScoutCandidateOrderUsesTrialProximityOnly(t *testing.T) {
	census := censusV6193("10", "12", "20")
	got := seedScoutCandidateSequenceV6193(census, 4)
	want := []string{"11", "13", "19", "14"}
	for i := range want {
		if got[i] != want[i] {
			t.Fatalf("got=%v want=%v", got, want)
		}
	}
}

func TestSeedScoutAggregateDropsPlayerIdentity(t *testing.T) {
	known := map[string]bool{"990": true}
	players := []protocol.Player{
		{GameUID: "uid-1", Pseudo: "Alice", ServerID: "990"},
		{GameUID: "uid-2", Pseudo: "Bob", ServerID: "1060"},
		{GameUID: "uid-3", Pseudo: "Carol", ServerID: "1060"},
	}
	observed, novel := seedScoutAggregateV6193(players, known)
	if len(observed) != 2 || observed[0].ServerID != "1060" || observed[0].Players != 2 {
		t.Fatalf("observed=%v", observed)
	}
	if len(novel) != 1 || novel[0].ServerID != "1060" || novel[0].Players != 2 {
		t.Fatalf("novel=%v", novel)
	}
}

func TestSeedScoutRecommendationPrefersTarget(t *testing.T) {
	observed := []seedScoutServerCountV6193{{ServerID: "1060", Players: 25}, {ServerID: "1061", Players: 30}}
	novel := append([]seedScoutServerCountV6193(nil), observed...)
	got := seedScoutChooseRecommendationV6193("1060", observed, novel, 20)
	if got == nil || got.ServerID != "1060" || got.Command != "@federated:1060" {
		t.Fatalf("got=%+v", got)
	}
}

func TestSeedScoutRecommendationUsesNovelFallback(t *testing.T) {
	observed := []seedScoutServerCountV6193{{ServerID: "990", Players: 50}, {ServerID: "1062", Players: 22}}
	novel := []seedScoutServerCountV6193{{ServerID: "1062", Players: 22}}
	got := seedScoutChooseRecommendationV6193("1060", observed, novel, 20)
	if got == nil || got.ServerID != "1062" || got.Reason != "novel_server_observed_in_single_region" {
		t.Fatalf("got=%+v", got)
	}
}
