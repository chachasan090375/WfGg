package main

// WFGG_RADAR_HISTORY_BACKED_CLUSTER_CATALOG_V616
// Converts cycle-time server attribution reconstructed by V6.14 into the
// graph shape consumed by the V6.13 catalog. No player identity data is added.
func serverCycleGraphFromHistoryV616(history serverCycleHistoryPayloadV614) serverCycleMapPayloadV6122 {
	cycles := make([]serverCycleRowV6122, 0, len(history.Cycles))
	for _, c := range history.Cycles {
		members := append([]serverCycleMemberV6122(nil), c.Servers...)
		cycles = append(cycles, serverCycleRowV6122{
			CycleID:     c.CycleID,
			ServerCount: len(members),
			Servers:     members,
		})
	}
	edges := append([]serverPairEdgeV6122(nil), history.Edges...)
	return serverCycleMapPayloadV6122{
		OK:                   history.OK,
		MapVersion:           "v6.16-history-backed",
		Readonly:             true,
		RawPlayerDataExposed: false,
		CycleCount:           len(cycles),
		EdgeCount:            len(edges),
		Cycles:               cycles,
		Edges:                edges,
	}
}

// serverCensusWithHistoryCyclesV616 keeps current population sizes from the
// census but replaces distinct-cycle counts with cycle-time historical truth.
func serverCensusWithHistoryCyclesV616(census serverCensusPayloadV612, history serverCycleHistoryPayloadV614) serverCensusPayloadV612 {
	counts := map[string]int{}
	for _, c := range history.Cycles {
		seen := map[string]bool{}
		for _, member := range c.Servers {
			if member.ServerID == "" || seen[member.ServerID] {
				continue
			}
			seen[member.ServerID] = true
			counts[member.ServerID]++
		}
	}
	out := census
	out.Servers = append([]serverCensusRowV612(nil), census.Servers...)
	for i := range out.Servers {
		out.Servers[i].DistinctCycles = counts[out.Servers[i].ServerID]
	}
	return out
}

func markHistoryBackedCatalogV616(payload serverClusterCatalogPayloadV613) serverClusterCatalogPayloadV613 {
	payload.CatalogVersion = "v6.16"
	for i := range payload.ConfirmedClusters {
		payload.ConfirmedClusters[i].EvidenceMethod = "cycle_time_state_hash_pairwise_cooccurrence_clique"
	}
	return payload
}
