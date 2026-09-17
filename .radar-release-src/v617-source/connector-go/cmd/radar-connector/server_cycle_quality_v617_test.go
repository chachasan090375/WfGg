package main

import "testing"

func historyCycleV617(id int64, servers ...string) serverCycleHistoryCycleV614 {
	members := make([]serverCycleMemberV6122, 0, len(servers))
	for _, sid := range servers {
		members = append(members, serverCycleMemberV6122{ServerID: sid, Observations: 100})
	}
	return serverCycleHistoryCycleV614{CycleID: id, ServerCount: len(members), SeenRows: len(members) * 100, HashMatched: len(members) * 100, Servers: members}
}

func target972V617() []string {
	return []string{"953", "964", "972", "977", "991", "1027", "1042", "1057", "8119"}
}

func census972V617() serverCensusPayloadV612 {
	rows := make([]serverCensusRowV612, 0, 9)
	for _, sid := range target972V617() {
		rows = append(rows, serverCensusRowV612{ServerID: sid, Players: 1000, Observations: 1000})
	}
	return serverCensusPayloadV612{OK: true, Servers: rows}
}

func TestCycleQualityV617RejectsPersistedPartialMarker(t *testing.T) {
	c := historyCycleV617(34, target972V617()...)
	ok, reason := cycleEligibleForClusterV617(c, cycleQualityMetaV617{ID: 34, Status: "SUCCESS", Error: "PARTIAL_REGIONS_1", Query: "@federated:972"}, true)
	if ok || reason != "CYCLE_HAS_ERROR_MARKER" {
		t.Fatalf("partial marker must be rejected: ok=%v reason=%s", ok, reason)
	}
}

func TestCycleQualityV617RejectsHistoricalMissingTarget(t *testing.T) {
	members := []string{"953", "964", "977", "991", "1027", "1042", "1057", "8119"}
	c := historyCycleV617(34, members...)
	ok, reason := cycleEligibleForClusterV617(c, cycleQualityMetaV617{ID: 34, Status: "SUCCESS", Query: "@federated:972"}, true)
	if ok || reason != "FEDERATED_TARGET_MISSING" {
		t.Fatalf("missing target must be rejected: ok=%v reason=%s", ok, reason)
	}
}

func TestQualityCatalogV617DoesNotConfirmTwoFullPlusOnePartial(t *testing.T) {
	full := target972V617()
	partial := []string{"953", "964", "977", "991", "1027", "1042", "1057", "8119"}
	history := serverCycleHistoryPayloadV614{OK: true, Cycles: []serverCycleHistoryCycleV614{
		historyCycleV617(32, full...),
		historyCycleV617(33, full...),
		historyCycleV617(34, partial...),
	}}
	quality := map[int64]cycleQualityMetaV617{
		32: {ID: 32, Status: "SUCCESS", Query: "@federated:972"},
		33: {ID: 33, Status: "SUCCESS", Query: "@federated:972"},
		34: {ID: 34, Status: "SUCCESS", Query: "@federated:972"},
	}
	graph, counts, eligible, excluded := serverCycleGraphFromQualityHistoryV617(history, quality)
	if eligible != 2 || excluded != 1 || graph.CycleCount != 2 {
		t.Fatalf("unexpected quality counts: eligible=%d excluded=%d graph=%d", eligible, excluded, graph.CycleCount)
	}
	catalog := markQualityGatedCatalogV617(deriveServerClusterCatalogV613(serverCensusWithQualityCyclesV617(census972V617(), counts), graph))
	if catalog.ConfirmedClusterCount != 0 {
		t.Fatalf("two full cycles plus one partial must not confirm: %#v", catalog.ConfirmedClusters)
	}
	for _, row := range catalog.Frontier {
		if row.ServerID == "972" && row.DistinctCycles != 2 {
			t.Fatalf("972 must remain at two eligible cycles: %#v", row)
		}
	}
}

func TestQualityCatalogV617ConfirmsThreeFullCycles(t *testing.T) {
	full := target972V617()
	history := serverCycleHistoryPayloadV614{OK: true, Cycles: []serverCycleHistoryCycleV614{
		historyCycleV617(32, full...),
		historyCycleV617(33, full...),
		historyCycleV617(35, full...),
	}}
	quality := map[int64]cycleQualityMetaV617{
		32: {ID: 32, Status: "SUCCESS", Query: "@federated:972"},
		33: {ID: 33, Status: "SUCCESS", Query: "@federated:972"},
		35: {ID: 35, Status: "SUCCESS", Query: "@federated:972"},
	}
	graph, counts, eligible, excluded := serverCycleGraphFromQualityHistoryV617(history, quality)
	if eligible != 3 || excluded != 0 {
		t.Fatalf("unexpected quality counts: eligible=%d excluded=%d", eligible, excluded)
	}
	catalog := markQualityGatedCatalogV617(deriveServerClusterCatalogV613(serverCensusWithQualityCyclesV617(census972V617(), counts), graph))
	if catalog.ConfirmedClusterCount != 1 || catalog.ConfirmedServerCount != 9 {
		t.Fatalf("three full cycles must confirm nine-server cluster: %#v", catalog)
	}
	if catalog.CatalogVersion != "v6.17" || catalog.ConfirmedClusters[0].MinCyclesTogether != 3 {
		t.Fatalf("unexpected confirmed evidence: %#v", catalog.ConfirmedClusters[0])
	}
}
