package main

import (
	"strings"

	"wfgg-radar-connector/internal/protocol"
)

// WFGG_RADAR_FULL_PROFILE_UNIVERSE_V697
// Profile candidates come from every unique GameUID observed by the current
// nine-region map cycle, not from the Collector delta/change feed.
func appendProfileUIDsV697(dst []string, seen map[string]struct{}, players []protocol.Player) []string {
	for _, p := range players {
		uid := strings.TrimSpace(p.GameUID)
		if uid == "" {
			continue
		}
		if _, ok := seen[uid]; ok {
			continue
		}
		seen[uid] = struct{}{}
		dst = append(dst, uid)
	}
	return dst
}

// V6.8's fixed 192-attempt ceiling was appropriate for delta enrichment but
// can stop a full-cycle population before all initial 50-UID batches are seen.
// Scale with population and retain an absolute safety ceiling.
func profileAttemptBudgetV697(requested int) int {
	if requested <= 0 {
		return 192
	}
	baseBatches := (requested + 49) / 50
	budget := baseBatches*3 + 64
	if budget < 192 {
		budget = 192
	}
	if budget > 2048 {
		budget = 2048
	}
	return budget
}
