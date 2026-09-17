package main

import (
	"net/http"
)

// WFGG_RADAR_COLLECTOR_LIVE_AUDIT_V699
// This endpoint intentionally exposes aggregate persistence counters only.
// It never returns player rows, UIDs, pseudos, aliases, queries, tokens or credentials.
type collectorIdentityStatsV699 struct {
	Ready            bool   `json:"ready"`
	Identities       int    `json:"identities"`
	Aliases          int    `json:"aliases"`
	PseudoCollisions int    `json:"pseudoCollisions"`
	CoverageScopes   int    `json:"coverageScopes"`
	CoverageComplete int    `json:"coverageComplete"`
	LastSeen         string `json:"lastSeen,omitempty"`
}

type collectorCycleSummaryV699 struct {
	ID     int64  `json:"id"`
	Status string `json:"status"`
}

type collectorStatsV699 struct {
	Players       int                        `json:"players"`
	ActivePlayers int                        `json:"activePlayers"`
	Observations  int                        `json:"observations"`
	LastSeen      string                     `json:"lastSeen,omitempty"`
	IdentityIndex collectorIdentityStatsV699 `json:"identityIndex"`
	LastCycle     *collectorCycleSummaryV699 `json:"lastCycle"`
}

type collectorAuditPayloadV699 struct {
	OK                   bool                        `json:"ok"`
	AuditVersion         string                      `json:"auditVersion"`
	Readonly             bool                        `json:"readonly"`
	RawPlayerDataExposed bool                        `json:"rawPlayerDataExposed"`
	Collector            collectorStatsV699          `json:"collector"`
}

func (s *server) collectorAuditV699(w http.ResponseWriter, r *http.Request, _ []byte) {
	var stats collectorStatsV699
	if err := collectorJSON(r.Context(), http.MethodGet, "/stats", nil, &stats); err != nil {
		writeJSON(w, http.StatusBadGateway, map[string]any{
			"ok":           false,
			"auditVersion": "v6.9.9",
			"readonly":     true,
			"error":        "COLLECTOR_STATS_UNAVAILABLE",
		})
		return
	}
	writeJSON(w, http.StatusOK, collectorAuditPayloadV699{
		OK:                   true,
		AuditVersion:         "v6.9.9",
		Readonly:             true,
		RawPlayerDataExposed: false,
		Collector:            stats,
	})
}
