package main

import (
	"testing"

	"wfgg-radar-connector/internal/protocol"
)

func int64pV618(v int64) *int64 { return &v }

func TestMergeProfileWithMapV618PreservesWorldFields(t *testing.T) {
	base := protocol.Player{
		GameUID: "u1", Pseudo: "Alpha", ServerID: "972",
		AllianceID: "a1", AllianceTag: "WFGG", HQLevel: int64pV618(31),
		X: int64pV618(123), Y: int64pV618(456), Rank: int64(7),
		ShieldState: "ACTIVE", ObservedAt: "map-time",
	}
	profile := protocol.Player{GameUID: "u1", Pseudo: "Alpha", Power: int64pV618(987654321), ObservedAt: "profile-time"}
	got := mergeProfileWithMapV618(base, profile)
	if got.ServerID != "972" || got.AllianceID != "a1" || got.AllianceTag != "WFGG" {
		t.Fatalf("world identity lost: %+v", got)
	}
	if got.HQLevel == nil || *got.HQLevel != 31 || got.X == nil || *got.X != 123 || got.Y == nil || *got.Y != 456 {
		t.Fatalf("world position/HQ lost: %+v", got)
	}
	if got.Power == nil || *got.Power != 987654321 {
		t.Fatalf("profile power not applied: %+v", got)
	}
	if got.Rank == nil || got.ShieldState == nil || got.ObservedAt != "profile-time" {
		t.Fatalf("map/profile metadata merge incomplete: %+v", got)
	}
}

func TestMergeProfileWithMapV618ExplicitProfileWins(t *testing.T) {
	base := protocol.Player{GameUID: "u1", ServerID: "972", X: int64pV618(10), Y: int64pV618(20)}
	profile := protocol.Player{GameUID: "u1", ServerID: "991", X: int64pV618(30), Y: int64pV618(40)}
	got := mergeProfileWithMapV618(base, profile)
	if got.ServerID != "991" || got.X == nil || *got.X != 30 || got.Y == nil || *got.Y != 40 {
		t.Fatalf("explicit profile values must win: %+v", got)
	}
}

func TestMergeProfileBatchV618UsesUIDMap(t *testing.T) {
	index := map[string]protocol.Player{
		"u1": {GameUID: "u1", ServerID: "972", X: int64pV618(1), Y: int64pV618(2)},
	}
	profiles := []protocol.Player{{GameUID: "u1", Power: int64pV618(99)}, {GameUID: "u2", Power: int64pV618(88)}}
	got := mergeProfileBatchV618(index, profiles)
	if len(got) != 2 || got[0].ServerID != "972" || got[0].X == nil || *got[0].X != 1 {
		t.Fatalf("known map row not merged: %+v", got)
	}
	if got[1].GameUID != "u2" || got[1].ServerID != "" {
		t.Fatalf("unknown profile must remain unchanged: %+v", got[1])
	}
}
