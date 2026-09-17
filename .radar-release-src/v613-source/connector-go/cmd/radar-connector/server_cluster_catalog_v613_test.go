package main

import (
	"encoding/json"
	"strings"
	"testing"
)

func TestDeriveServerClusterCatalogV613(t *testing.T) {
	graph := serverCycleMapPayloadV6122{
		OK: true,
		Cycles: []serverCycleRowV6122{
			{CycleID: 1, Servers: []serverCycleMemberV6122{{ServerID: "990", Observations: 100}, {ServerID: "992", Observations: 120}, {ServerID: "1008", Observations: 110}}},
			{CycleID: 2, Servers: []serverCycleMemberV6122{{ServerID: "990", Observations: 100}, {ServerID: "992", Observations: 120}, {ServerID: "1008", Observations: 110}}},
			{CycleID: 3, Servers: []serverCycleMemberV6122{{ServerID: "990", Observations: 100}, {ServerID: "992", Observations: 120}, {ServerID: "1008", Observations: 110}, {ServerID: "1006", Observations: 1}}},
		},
		Edges: []serverPairEdgeV6122{
			{ServerA: "990", ServerB: "992", CyclesTogether: 3},
			{ServerA: "990", ServerB: "1008", CyclesTogether: 3},
			{ServerA: "992", ServerB: "1008", CyclesTogether: 3},
			{ServerA: "990", ServerB: "1006", CyclesTogether: 1},
		},
	}
	census := serverCensusPayloadV612{
		OK: true,
		Servers: []serverCensusRowV612{
			{ServerID: "990", Players: 3600, Observations: 300, DistinctCycles: 3},
			{ServerID: "992", Players: 5200, Observations: 360, DistinctCycles: 3},
			{ServerID: "1008", Players: 3600, Observations: 330, DistinctCycles: 3},
			{ServerID: "972", Players: 430},
			{ServerID: "977", Players: 395},
			{ServerID: "1006", Players: 1, Observations: 1, DistinctCycles: 1},
		},
	}

	got := deriveServerClusterCatalogV613(census, graph)
	if got.ConfirmedClusterCount != 1 || got.ConfirmedServerCount != 3 {
		t.Fatalf("unexpected confirmed counts: %#v", got)
	}
	if !got.ConfirmedClusters[0].CliqueComplete || got.ConfirmedClusters[0].MinCyclesTogether != 3 {
		t.Fatalf("cluster not confirmed as expected: %#v", got.ConfirmedClusters[0])
	}
	if got.FrontierCount != 2 || got.Frontier[0].ServerID != "972" {
		t.Fatalf("unexpected frontier: %#v", got.Frontier)
	}
	if got.RecommendedSeed == nil || got.RecommendedSeed.ServerID != "972" || got.RecommendedSeed.Command != "@federated:972" {
		t.Fatalf("unexpected recommended seed: %#v", got.RecommendedSeed)
	}
	if got.NoiseCount != 1 || got.Noise[0].ServerID != "1006" {
		t.Fatalf("unexpected noise: %#v", got.Noise)
	}
}

func TestServerClusterCatalogV613ContainsNoIdentityKeys(t *testing.T) {
	got := deriveServerClusterCatalogV613(serverCensusPayloadV612{}, serverCycleMapPayloadV6122{})
	b, err := json.Marshal(got)
	if err != nil {
		t.Fatal(err)
	}
	s := strings.ToLower(string(b))
	for _, forbidden := range []string{"gameuid", "game_uid", "pseudo", "alliance", "credential", "token"} {
		if strings.Contains(s, forbidden) {
			t.Fatalf("identity key leaked: %s", forbidden)
		}
	}
}
