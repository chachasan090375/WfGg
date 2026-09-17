package main

import (
	"context"
	"crypto/sha256"
	"fmt"
	"net/http"
	"os"
	"sort"
	"strconv"
	"strings"
	"time"
)

// WFGG_RADAR_SERVER_CLUSTER_CATALOG_V613
// Materializes confirmed server clusters from persisted cycle cooccurrence history and
// ranks unmapped server populations as the discovery frontier. Aggregate-only: no
// player identity data is exposed by this layer.
const (
	clusterConfirmMinCyclesV613 = 3
	clusterSeedMinPlayersV613   = 50
)

type serverClusterCatalogClusterV613 struct {
	ClusterID         string   `json:"clusterId"`
	Status            string   `json:"status"`
	Members           []string `json:"members"`
	MemberCount       int      `json:"memberCount"`
	MinCyclesTogether int      `json:"minCyclesTogether"`
	MaxCyclesTogether int      `json:"maxCyclesTogether"`
	CliqueComplete    bool     `json:"cliqueComplete"`
	EvidenceMethod    string   `json:"evidenceMethod"`
}

type serverClusterFrontierV613 struct {
	ServerID       string `json:"serverId"`
	Players        int    `json:"players"`
	Observations   int    `json:"observations"`
	DistinctCycles int    `json:"distinctCycles"`
	Reason          string `json:"reason"`
}

type serverClusterSeedV613 struct {
	ServerID string `json:"serverId"`
	Players  int    `json:"players"`
	Command  string `json:"command"`
	Reason   string `json:"reason"`
}

type serverClusterCatalogPayloadV613 struct {
	OK                   bool                            `json:"ok"`
	CatalogVersion       string                          `json:"catalogVersion"`
	Readonly             bool                            `json:"readonly"`
	RawPlayerDataExposed bool                            `json:"rawPlayerDataExposed"`
	PersistentHistory    bool                            `json:"persistentHistory"`
	ConfirmMinCycles     int                             `json:"confirmMinCycles"`
	SeedMinPlayers       int                             `json:"seedMinPlayers"`
	ConfirmedClusterCount int                            `json:"confirmedClusterCount"`
	ConfirmedServerCount int                             `json:"confirmedServerCount"`
	FrontierCount        int                             `json:"frontierCount"`
	NoiseCount           int                             `json:"noiseCount"`
	ConfirmedClusters    []serverClusterCatalogClusterV613 `json:"confirmedClusters"`
	Frontier             []serverClusterFrontierV613    `json:"frontier"`
	Noise                []serverClusterFrontierV613    `json:"noise"`
	RecommendedSeed      *serverClusterSeedV613          `json:"recommendedSeed,omitempty"`
}

func serverIDLessV613(a, b string) bool {
	ai, ae := strconv.Atoi(a)
	bi, be := strconv.Atoi(b)
	if ae == nil && be == nil {
		return ai < bi
	}
	return a < b
}

func edgeKeyV613(a, b string) string {
	if serverIDLessV613(b, a) {
		a, b = b, a
	}
	return a + "\x00" + b
}

func stableClusterIDV613(members []string) string {
	copyMembers := append([]string(nil), members...)
	sort.Slice(copyMembers, func(i, j int) bool { return serverIDLessV613(copyMembers[i], copyMembers[j]) })
	sum := sha256.Sum256([]byte(strings.Join(copyMembers, ",")))
	return fmt.Sprintf("cluster-%x", sum[:5])
}

func deriveServerClusterCatalogV613(census serverCensusPayloadV612, graph serverCycleMapPayloadV6122) serverClusterCatalogPayloadV613 {
	parent := map[string]string{}
	find := func(x string) string { return x }
	var findRoot func(string) string
	findRoot = func(x string) string {
		p, ok := parent[x]
		if !ok {
			parent[x] = x
			return x
		}
		if p != x {
			parent[x] = findRoot(p)
		}
		return parent[x]
	}
	_ = find
	union := func(a, b string) {
		ra, rb := findRoot(a), findRoot(b)
		if ra != rb {
			if serverIDLessV613(rb, ra) {
				ra, rb = rb, ra
			}
			parent[rb] = ra
		}
	}

	edgeWeights := map[string]int{}
	for _, edge := range graph.Edges {
		a := strings.TrimSpace(edge.ServerA)
		b := strings.TrimSpace(edge.ServerB)
		if a == "" || b == "" || a == b {
			continue
		}
		edgeWeights[edgeKeyV613(a, b)] = edge.CyclesTogether
		if edge.CyclesTogether >= clusterConfirmMinCyclesV613 {
			union(a, b)
		}
	}

	groups := map[string][]string{}
	for sid := range parent {
		root := findRoot(sid)
		groups[root] = append(groups[root], sid)
	}

	confirmed := make([]serverClusterCatalogClusterV613, 0)
	confirmedSet := map[string]bool{}
	for _, members := range groups {
		if len(members) < 2 {
			continue
		}
		sort.Slice(members, func(i, j int) bool { return serverIDLessV613(members[i], members[j]) })
		clique := true
		minCycles := int(^uint(0) >> 1)
		maxCycles := 0
		for i := 0; i < len(members); i++ {
			for j := i + 1; j < len(members); j++ {
				weight := edgeWeights[edgeKeyV613(members[i], members[j])]
				if weight < clusterConfirmMinCyclesV613 {
					clique = false
				}
				if weight < minCycles {
					minCycles = weight
				}
				if weight > maxCycles {
					maxCycles = weight
				}
			}
		}
		if !clique {
			continue
		}
		if minCycles == int(^uint(0)>>1) {
			minCycles = 0
		}
		for _, sid := range members {
			confirmedSet[sid] = true
		}
		confirmed = append(confirmed, serverClusterCatalogClusterV613{
			ClusterID: stableClusterIDV613(members),
			Status: "confirmed",
			Members: append([]string(nil), members...),
			MemberCount: len(members),
			MinCyclesTogether: minCycles,
			MaxCyclesTogether: maxCycles,
			CliqueComplete: true,
			EvidenceMethod: "persistent_pairwise_cooccurrence_clique",
		})
	}

	sort.Slice(confirmed, func(i, j int) bool {
		if confirmed[i].MemberCount != confirmed[j].MemberCount {
			return confirmed[i].MemberCount > confirmed[j].MemberCount
		}
		return confirmed[i].ClusterID < confirmed[j].ClusterID
	})

	frontier := make([]serverClusterFrontierV613, 0)
	noise := make([]serverClusterFrontierV613, 0)
	for _, row := range census.Servers {
		sid := strings.TrimSpace(row.ServerID)
		if sid == "" || confirmedSet[sid] {
			continue
		}
		reason := "unmapped_population"
		if row.DistinctCycles > 0 {
			reason = "partial_cycle_evidence"
		}
		item := serverClusterFrontierV613{
			ServerID: sid,
			Players: row.Players,
			Observations: row.Observations,
			DistinctCycles: row.DistinctCycles,
			Reason: reason,
		}
		if row.Players < clusterSeedMinPlayersV613 {
			item.Reason = "insufficient_population_evidence"
			noise = append(noise, item)
			continue
		}
		frontier = append(frontier, item)
	}

	sort.Slice(frontier, func(i, j int) bool {
		if frontier[i].Players != frontier[j].Players {
			return frontier[i].Players > frontier[j].Players
		}
		if frontier[i].DistinctCycles != frontier[j].DistinctCycles {
			return frontier[i].DistinctCycles < frontier[j].DistinctCycles
		}
		return serverIDLessV613(frontier[i].ServerID, frontier[j].ServerID)
	})
	sort.Slice(noise, func(i, j int) bool {
		if noise[i].Players != noise[j].Players {
			return noise[i].Players > noise[j].Players
		}
		return serverIDLessV613(noise[i].ServerID, noise[j].ServerID)
	})

	confirmedServerCount := 0
	for _, cluster := range confirmed {
		confirmedServerCount += cluster.MemberCount
	}

	var recommended *serverClusterSeedV613
	if len(frontier) > 0 {
		top := frontier[0]
		recommended = &serverClusterSeedV613{
			ServerID: top.ServerID,
			Players: top.Players,
			Command: "@federated:" + top.ServerID,
			Reason: "largest_unmapped_known_population",
		}
	}

	return serverClusterCatalogPayloadV613{
		OK: true,
		CatalogVersion: "v6.13",
		Readonly: true,
		RawPlayerDataExposed: false,
		PersistentHistory: true,
		ConfirmMinCycles: clusterConfirmMinCyclesV613,
		SeedMinPlayers: clusterSeedMinPlayersV613,
		ConfirmedClusterCount: len(confirmed),
		ConfirmedServerCount: confirmedServerCount,
		FrontierCount: len(frontier),
		NoiseCount: len(noise),
		ConfirmedClusters: confirmed,
		Frontier: frontier,
		Noise: noise,
		RecommendedSeed: recommended,
	}
}

func (s *server) serverClusterCatalogV613(w http.ResponseWriter, r *http.Request, _ []byte) {
	dbPath := strings.TrimSpace(os.Getenv("WFGG_COLLECTOR_DB"))
	if dbPath == "" {
		dbPath = "/opt/wfgg-collector/data/collector.db"
	}
	ctx, cancel := context.WithTimeout(r.Context(), 30*time.Second)
	defer cancel()
	census, err := runServerCensusV612(ctx, dbPath)
	if err != nil {
		writeJSON(w, http.StatusBadGateway, map[string]any{"ok": false, "catalogVersion": "v6.13", "readonly": true, "error": "SERVER_CLUSTER_CATALOG_CENSUS_UNAVAILABLE"})
		return
	}
	graph, err := runServerCycleMapV6122(ctx, dbPath)
	if err != nil {
		writeJSON(w, http.StatusBadGateway, map[string]any{"ok": false, "catalogVersion": "v6.13", "readonly": true, "error": "SERVER_CLUSTER_CATALOG_GRAPH_UNAVAILABLE"})
		return
	}
	writeJSON(w, http.StatusOK, deriveServerClusterCatalogV613(census, graph))
}
