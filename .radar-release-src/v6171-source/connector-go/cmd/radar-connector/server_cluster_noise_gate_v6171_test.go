package main

import "testing"

func censusWithNoiseV6171() serverCensusPayloadV612 {
	rows := []serverCensusRowV612{
		{ServerID: "953", Players: 2970, Observations: 8906},
		{ServerID: "964", Players: 3157, Observations: 6266},
		{ServerID: "972", Players: 3771, Observations: 6203},
		{ServerID: "977", Players: 2838, Observations: 7401},
		{ServerID: "991", Players: 3085, Observations: 6842},
		{ServerID: "1027", Players: 2983, Observations: 8948},
		{ServerID: "1040", Players: 1, Observations: 4},
		{ServerID: "1042", Players: 3451, Observations: 8996},
		{ServerID: "1057", Players: 3730, Observations: 9464},
		{ServerID: "8119", Players: 177, Observations: 531},
	}
	return serverCensusPayloadV612{OK: true, Servers: rows}
}

func full972WithNoiseV6171(id int64) serverCycleHistoryCycleV614 {
	return historyCycleV617(id, "953", "964", "972", "977", "991", "1027", "1040", "1042", "1057", "8119")
}

func TestNoiseGateV6171FiltersPersistentOnePlayerServer(t *testing.T) {
	history := serverCycleHistoryPayloadV614{OK: true, Cycles: []serverCycleHistoryCycleV614{
		full972WithNoiseV6171(32),
		full972WithNoiseV6171(33),
		full972WithNoiseV6171(35),
	}}
	quality := map[int64]cycleQualityMetaV617{
		32: {ID: 32, Status: "SUCCESS", Query: "@federated:972"},
		33: {ID: 33, Status: "SUCCESS", Query: "@federated:972"},
		35: {ID: 35, Status: "SUCCESS", Query: "@federated:972"},
	}
	graph, _, eligible, excluded := serverCycleGraphFromQualityHistoryV617(history, quality)
	if eligible != 3 || excluded != 0 {
		t.Fatalf("unexpected quality counts: eligible=%d excluded=%d", eligible, excluded)
	}

	catalog := deriveServerClusterCatalogV6171(censusWithNoiseV6171(), graph)
	if catalog.CatalogVersion != "v6.17.1" {
		t.Fatalf("unexpected version: %s", catalog.CatalogVersion)
	}
	if catalog.ConfirmedClusterCount != 1 || catalog.ConfirmedServerCount != 9 {
		t.Fatalf("noise gate must confirm exactly nine servers: %#v", catalog)
	}
	if len(catalog.ConfirmedClusters) != 1 {
		t.Fatalf("expected one cluster: %#v", catalog.ConfirmedClusters)
	}
	for _, sid := range catalog.ConfirmedClusters[0].Members {
		if sid == "1040" {
			t.Fatal("1040 must never enter confirmed cluster")
		}
	}
	foundNoise := false
	for _, row := range catalog.Noise {
		if row.ServerID == "1040" {
			foundNoise = true
			if row.Players != 1 || row.Reason != "insufficient_population_evidence" {
				t.Fatalf("unexpected 1040 noise row: %#v", row)
			}
		}
	}
	if !foundNoise {
		t.Fatal("1040 must remain visible as noise")
	}
}

func TestNoiseGateV6171KeepsLegitimateSmallServer(t *testing.T) {
	census := censusWithNoiseV6171()
	eligible := clusterEligibleServersV6171(census)
	if eligible["1040"] {
		t.Fatal("one-player anomaly must be ineligible")
	}
	if !eligible["8119"] {
		t.Fatal("8119 with 177 players must remain eligible")
	}
}

func TestNoiseGateV6171UsesExistingThresholdBoundary(t *testing.T) {
	census := serverCensusPayloadV612{OK: true, Servers: []serverCensusRowV612{
		{ServerID: "49", Players: clusterSeedMinPlayersV613 - 1},
		{ServerID: "50", Players: clusterSeedMinPlayersV613},
	}}
	eligible := clusterEligibleServersV6171(census)
	if eligible["49"] {
		t.Fatal("below-threshold server must be filtered")
	}
	if !eligible["50"] {
		t.Fatal("threshold server must remain eligible")
	}
}
