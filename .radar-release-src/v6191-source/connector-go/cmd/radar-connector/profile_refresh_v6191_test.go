package main

import (
	"testing"

	"wfgg-radar-connector/internal/protocol"
)

func p64v6191(v int64) *int64 { return &v }

func TestCollectorBasePlayerV6191(t *testing.T) {
	row := map[string]any{
		"game_uid": "101", "pseudo": "Pilot", "server_id": "992",
		"alliance_id": "7", "alliance_tag": "WfGg",
		"x": float64(96), "y": float64(450), "hq_level": float64(30),
		"power": float64(286651443), "last_seen": "2026-09-18T00:00:00Z",
	}
	p := collectorBasePlayerV6191(row)
	if p.GameUID != "101" || p.ServerID != "992" || p.X == nil || *p.X != 96 || p.Power == nil || *p.Power != 286651443 {
		t.Fatalf("unexpected base: %#v", p)
	}
}

func TestRichObservedV6191(t *testing.T) {
	if richObservedV6191(protocol.Player{}) {
		t.Fatal("empty profile must not be marked rich")
	}
	if !richObservedV6191(protocol.Player{ArmyPower: p64v6191(123)}) {
		t.Fatal("armyPower must count as observed rich data")
	}
	if !richObservedV6191(protocol.Player{Country: "FR"}) {
		t.Fatal("country must count as observed rich data")
	}
}
