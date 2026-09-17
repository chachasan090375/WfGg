package main

import "testing"

func historyV616(cycles int) serverCycleHistoryPayloadV614 {
	rows := make([]serverCycleHistoryCycleV614, 0, cycles)
	for i := 0; i < cycles; i++ {
		rows = append(rows, serverCycleHistoryCycleV614{
			CycleID: int64(32 + i),
			Servers: []serverCycleMemberV6122{
				{ServerID: "972", Observations: 2400},
				{ServerID: "1027", Observations: 2900},
				{ServerID: "1057", Observations: 3700},
			},
		})
	}
	edges := []serverPairEdgeV6122{
		{ServerA: "972", ServerB: "1027", CyclesTogether: cycles},
		{ServerA: "972", ServerB: "1057", CyclesTogether: cycles},
		{ServerA: "1027", ServerB: "1057", CyclesTogether: cycles},
	}
	return serverCycleHistoryPayloadV614{OK: true, Readonly: true, Cycles: rows, Edges: edges}
}

func censusV616() serverCensusPayloadV612 {
	return serverCensusPayloadV612{OK: true, Servers: []serverCensusRowV612{
		{ServerID: "972", Players: 2443, DistinctCycles: 99},
		{ServerID: "1027", Players: 2989, DistinctCycles: 99},
		{ServerID: "1057", Players: 3728, DistinctCycles: 99},
	}}
}

func TestHistoryBackedCatalogDoesNotConfirmTwoCyclesV616(t *testing.T) {
	history := historyV616(2)
	census := serverCensusWithHistoryCyclesV616(censusV616(), history)
	graph := serverCycleGraphFromHistoryV616(history)
	got := markHistoryBackedCatalogV616(deriveServerClusterCatalogV613(census, graph))
	if got.ConfirmedClusterCount != 0 {
		t.Fatalf("two real cycles must not confirm cluster: %#v", got.ConfirmedClusters)
	}
	if got.CatalogVersion != "v6.16" {
		t.Fatalf("wrong catalog version: %s", got.CatalogVersion)
	}
	for _, row := range got.Frontier {
		if row.DistinctCycles != 2 {
			t.Fatalf("history cycle count not applied: %#v", row)
		}
	}
}

func TestHistoryBackedCatalogConfirmsThreeCyclesV616(t *testing.T) {
	history := historyV616(3)
	census := serverCensusWithHistoryCyclesV616(censusV616(), history)
	graph := serverCycleGraphFromHistoryV616(history)
	got := markHistoryBackedCatalogV616(deriveServerClusterCatalogV613(census, graph))
	if got.ConfirmedClusterCount != 1 || got.ConfirmedServerCount != 3 {
		t.Fatalf("three real cycles should confirm cluster: %#v", got)
	}
	cluster := got.ConfirmedClusters[0]
	if cluster.MinCyclesTogether != 3 || !cluster.CliqueComplete {
		t.Fatalf("unexpected evidence: %#v", cluster)
	}
	if cluster.EvidenceMethod != "cycle_time_state_hash_pairwise_cooccurrence_clique" {
		t.Fatalf("wrong evidence method: %s", cluster.EvidenceMethod)
	}
}
