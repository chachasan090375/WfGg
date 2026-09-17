package main

import (
	"net/http"
	"os"
	"sort"
	"strings"
	"time"
)

// WFGG_RADAR_SERVER_CLUSTER_EVIDENCE_V6123
// Explainable, aggregate-only classification derived from the V6.12.2 cycle graph.
// No player identity data is returned or required by this layer.
type serverClusterNodeV6123 struct {
	ServerID                    string  `json:"serverId"`
	CyclesSeen                  int     `json:"cyclesSeen"`
	CycleCoverage               float64 `json:"cycleCoverage"`
	Observations                int     `json:"observations"`
	MeanObservationsPerCycle    float64 `json:"meanObservationsPerCycle"`
	RelativeVolumeToCoreMedian  float64 `json:"relativeVolumeToCoreMedian"`
	EvidenceClass               string  `json:"evidenceClass"`
}

type serverClusterEvidencePayloadV6123 struct {
	OK                   bool                     `json:"ok"`
	EvidenceVersion      string                   `json:"evidenceVersion"`
	Readonly             bool                     `json:"readonly"`
	RawPlayerDataExposed bool                     `json:"rawPlayerDataExposed"`
	CycleCount           int                      `json:"cycleCount"`
	PersistentCount      int                      `json:"persistentCount"`
	TransientCount       int                      `json:"transientCount"`
	CoreExpectedEdges    int                      `json:"coreExpectedEdges"`
	CoreStrongEdges      int                      `json:"coreStrongEdges"`
	CoreCliqueComplete   bool                     `json:"coreCliqueComplete"`
	LowVolumeThreshold   float64                  `json:"lowVolumeThreshold"`
	Persistent           []serverClusterNodeV6123 `json:"persistent"`
	Transient            []serverClusterNodeV6123 `json:"transient"`
}

type clusterAccumV6123 struct {
	cycles int
	obs    int
}

func medianFloatV6123(values []float64) float64 {
	if len(values) == 0 {
		return 0
	}
	v := append([]float64(nil), values...)
	sort.Float64s(v)
	m := len(v) / 2
	if len(v)%2 == 1 {
		return v[m]
	}
	return (v[m-1] + v[m]) / 2
}

func deriveServerClusterEvidenceV6123(m serverCycleMapPayloadV6122) serverClusterEvidencePayloadV6123 {
	const lowVolumeThreshold = 0.25
	acc := map[string]*clusterAccumV6123{}
	for _, cycle := range m.Cycles {
		seen := map[string]bool{}
		for _, member := range cycle.Servers {
			sid := strings.TrimSpace(member.ServerID)
			if sid == "" {
				continue
			}
			a := acc[sid]
			if a == nil {
				a = &clusterAccumV6123{}
				acc[sid] = a
			}
			a.obs += member.Observations
			if !seen[sid] {
				a.cycles++
				seen[sid] = true
			}
		}
	}

	cycleCount := len(m.Cycles)
	persistentIDs := make([]string, 0)
	transientIDs := make([]string, 0)
	for sid, a := range acc {
		if cycleCount > 0 && a.cycles == cycleCount {
			persistentIDs = append(persistentIDs, sid)
		} else {
			transientIDs = append(transientIDs, sid)
		}
	}
	sort.Strings(persistentIDs)
	sort.Strings(transientIDs)

	means := make([]float64, 0, len(persistentIDs))
	for _, sid := range persistentIDs {
		a := acc[sid]
		if a.cycles > 0 {
			means = append(means, float64(a.obs)/float64(a.cycles))
		}
	}
	coreMedian := medianFloatV6123(means)

	makeNode := func(sid string, persistent bool) serverClusterNodeV6123 {
		a := acc[sid]
		coverage := 0.0
		mean := 0.0
		if cycleCount > 0 {
			coverage = float64(a.cycles) / float64(cycleCount)
		}
		if a.cycles > 0 {
			mean = float64(a.obs) / float64(a.cycles)
		}
		rel := 0.0
		if coreMedian > 0 {
			rel = mean / coreMedian
		}
		class := "transient"
		if persistent {
			class = "persistent"
			if rel > 0 && rel < lowVolumeThreshold {
				class = "persistent_low_volume"
			}
		}
		return serverClusterNodeV6123{
			ServerID: sid,
			CyclesSeen: a.cycles,
			CycleCoverage: coverage,
			Observations: a.obs,
			MeanObservationsPerCycle: mean,
			RelativeVolumeToCoreMedian: rel,
			EvidenceClass: class,
		}
	}

	persistent := make([]serverClusterNodeV6123, 0, len(persistentIDs))
	for _, sid := range persistentIDs {
		persistent = append(persistent, makeNode(sid, true))
	}
	transient := make([]serverClusterNodeV6123, 0, len(transientIDs))
	for _, sid := range transientIDs {
		transient = append(transient, makeNode(sid, false))
	}

	persistentSet := map[string]bool{}
	for _, sid := range persistentIDs {
		persistentSet[sid] = true
	}
	expected := len(persistentIDs) * (len(persistentIDs) - 1) / 2
	strong := 0
	for _, edge := range m.Edges {
		if persistentSet[edge.ServerA] && persistentSet[edge.ServerB] && edge.CyclesTogether == cycleCount {
			strong++
		}
	}

	return serverClusterEvidencePayloadV6123{
		OK: true,
		EvidenceVersion: "v6.12.3",
		Readonly: true,
		RawPlayerDataExposed: false,
		CycleCount: cycleCount,
		PersistentCount: len(persistent),
		TransientCount: len(transient),
		CoreExpectedEdges: expected,
		CoreStrongEdges: strong,
		CoreCliqueComplete: expected > 0 && strong == expected,
		LowVolumeThreshold: lowVolumeThreshold,
		Persistent: persistent,
		Transient: transient,
	}
}

func (s *server) serverClusterEvidenceV6123(w http.ResponseWriter, r *http.Request, _ []byte) {
	dbPath := strings.TrimSpace(os.Getenv("WFGG_COLLECTOR_DB"))
	if dbPath == "" {
		dbPath = "/opt/wfgg-collector/data/collector.db"
	}
	ctx, cancel := context.WithTimeout(r.Context(), 30*time.Second)
	defer cancel()
	m, err := runServerCycleMapV6122(ctx, dbPath)
	if err != nil {
		writeJSON(w, http.StatusBadGateway, map[string]any{"ok": false, "evidenceVersion": "v6.12.3", "readonly": true, "error": "SERVER_CLUSTER_EVIDENCE_SOURCE_UNAVAILABLE"})
		return
	}
	writeJSON(w, http.StatusOK, deriveServerClusterEvidenceV6123(m))
}
