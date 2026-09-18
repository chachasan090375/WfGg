package main

import "strings"

// WFGG_RADAR_CLUSTER_NOISE_GATE_V6171
// V6.17 correctly rejects partial cycles, but confirmation still operated on
// every co-occurring server regardless of population. A persistent one-row
// anomaly could therefore join a clique after three eligible cycles.
// V6.17.1 applies the same population floor already used by V6.13 to classify
// frontier vs noise before cluster edges are considered.
func clusterEligibleServersV6171(census serverCensusPayloadV612) map[string]bool {
	eligible := make(map[string]bool, len(census.Servers))
	for _, row := range census.Servers {
		sid := strings.TrimSpace(row.ServerID)
		if sid == "" {
			continue
		}
		if row.Players >= clusterSeedMinPlayersV613 {
			eligible[sid] = true
		}
	}
	return eligible
}

func filterClusterGraphNoiseV6171(census serverCensusPayloadV612, graph serverCycleMapPayloadV6122) serverCycleMapPayloadV6122 {
	eligible := clusterEligibleServersV6171(census)
	out := graph
	out.MapVersion = "v6.17.1-noise-gated"
	out.Edges = make([]serverPairEdgeV6122, 0, len(graph.Edges))
	for _, edge := range graph.Edges {
		a := strings.TrimSpace(edge.ServerA)
		b := strings.TrimSpace(edge.ServerB)
		if !eligible[a] || !eligible[b] {
			continue
		}
		out.Edges = append(out.Edges, edge)
	}
	out.EdgeCount = len(out.Edges)

	out.Cycles = make([]serverCycleRowV6122, 0, len(graph.Cycles))
	for _, cycle := range graph.Cycles {
		members := make([]serverCycleMemberV6122, 0, len(cycle.Servers))
		for _, member := range cycle.Servers {
			if eligible[strings.TrimSpace(member.ServerID)] {
				members = append(members, member)
			}
		}
		row := cycle
		row.Servers = members
		row.ServerCount = len(members)
		out.Cycles = append(out.Cycles, row)
	}
	out.CycleCount = len(out.Cycles)
	return out
}

func deriveServerClusterCatalogV6171(census serverCensusPayloadV612, graph serverCycleMapPayloadV6122) serverClusterCatalogPayloadV613 {
	filtered := filterClusterGraphNoiseV6171(census, graph)
	payload := markQualityGatedCatalogV617(deriveServerClusterCatalogV613(census, filtered))
	payload.CatalogVersion = "v6.17.1"
	for i := range payload.ConfirmedClusters {
		payload.ConfirmedClusters[i].EvidenceMethod = "cycle_time_state_hash_full_success_quality_gate_population_noise_gate"
	}
	return payload
}
