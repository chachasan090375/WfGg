package main

import (
	"strings"

	"wfgg-radar-connector/internal/protocol"
)

// WFGG_RADAR_MAP_PROFILE_MERGE_V618
// Profile replies are intentionally sparse: they may add power while omitting
// world-map fields such as server and coordinates. Merge them over the latest
// observation from the same map cycle so enrichment can never erase valid map
// evidence.
func mergeProfileWithMapV618(base, profile protocol.Player) protocol.Player {
	out := profile
	if strings.TrimSpace(out.GameUID) == "" {
		out.GameUID = base.GameUID
	}
	if strings.TrimSpace(out.Pseudo) == "" {
		out.Pseudo = base.Pseudo
	}
	if strings.TrimSpace(out.ServerID) == "" {
		out.ServerID = base.ServerID
	}
	if strings.TrimSpace(out.AllianceID) == "" {
		out.AllianceID = base.AllianceID
	}
	if strings.TrimSpace(out.AllianceTag) == "" {
		out.AllianceTag = base.AllianceTag
	}
	if out.Rank == nil {
		out.Rank = base.Rank
	}
	if out.HQLevel == nil {
		out.HQLevel = base.HQLevel
	}
	if out.Power == nil {
		out.Power = base.Power
	}
	if out.X == nil {
		out.X = base.X
	}
	if out.Y == nil {
		out.Y = base.Y
	}
	if out.ShieldState == nil {
		out.ShieldState = base.ShieldState
	}
	if strings.TrimSpace(out.ObservedAt) == "" {
		out.ObservedAt = base.ObservedAt
	}
	return out
}

func rememberMapPlayersV618(index map[string]protocol.Player, players []protocol.Player) {
	if index == nil {
		return
	}
	for _, p := range players {
		uid := strings.TrimSpace(p.GameUID)
		if uid == "" {
			continue
		}
		if old, ok := index[uid]; ok {
			index[uid] = mergeProfileWithMapV618(old, p)
		} else {
			index[uid] = p
		}
	}
}

func mergeProfileBatchV618(index map[string]protocol.Player, profiles []protocol.Player) []protocol.Player {
	if len(profiles) == 0 {
		return profiles
	}
	out := make([]protocol.Player, len(profiles))
	for i, p := range profiles {
		uid := strings.TrimSpace(p.GameUID)
		if base, ok := index[uid]; ok {
			out[i] = mergeProfileWithMapV618(base, p)
		} else {
			out[i] = p
		}
	}
	return out
}
