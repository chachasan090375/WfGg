package main

import (
	"context"
	"errors"
	"net/http"
	"strings"
	"time"

	"wfgg-radar-connector/internal/protocol"
)

// WFGG_RADAR_TARGET_PROFILE_REFRESH_V6191
// A bounded, explicit, read-only profile refresh for exactly one already-known
// player. It never starts a map scan or Collector cycle. The Last War command
// used behind protocol.ProfileScanner is get.user.info.multi.
type profileRefreshRequestV6191 struct {
	Token   string `json:"token"`
	GameUID string `json:"gameUid"`
}

type profileRefreshResponseV6191 struct {
	OK       bool            `json:"ok"`
	Readonly bool            `json:"readonly"`
	Command  string          `json:"command"`
	Player   protocol.Player `json:"player"`
}

func anyInt64PtrV6191(v any) *int64 {
	switch n := v.(type) {
	case int:
		x := int64(n); return &x
	case int8:
		x := int64(n); return &x
	case int16:
		x := int64(n); return &x
	case int32:
		x := int64(n); return &x
	case int64:
		x := n; return &x
	case float64:
		x := int64(n); return &x
	case float32:
		x := int64(n); return &x
	}
	return nil
}

func collectorBasePlayerV6191(row map[string]any) protocol.Player {
	if row == nil {
		return protocol.Player{}
	}
	return protocol.Player{
		GameUID:     stringField(row, "game_uid", "gameUid"),
		Pseudo:      stringField(row, "pseudo"),
		ServerID:    stringField(row, "server_id", "serverId"),
		AllianceID:  stringField(row, "alliance_id", "allianceId"),
		AllianceTag: stringField(row, "alliance_tag", "allianceTag"),
		Rank:        row["rank"],
		HQLevel:     anyInt64PtrV6191(row["hq_level"]),
		Power:       anyInt64PtrV6191(row["power"]),
		X:           anyInt64PtrV6191(row["x"]),
		Y:           anyInt64PtrV6191(row["y"]),
		ShieldState: row["shield_state"],
		ObservedAt:  stringField(row, "last_seen", "observedAt"),
	}
}

func richObservedV6191(p protocol.Player) bool {
	return p.ArmyPower != nil || p.ArmyKill != nil || p.SVIPLevel != nil ||
		strings.TrimSpace(p.Country) != "" || strings.TrimSpace(p.AvatarRef) != ""
}

func (s *server) profileRefreshV6191(w http.ResponseWriter, r *http.Request, body []byte) {
	var input profileRefreshRequestV6191
	if err := decodeJSON(body, &input); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]any{"error": "PROFILE_REFRESH_BODY_INVALID"})
		return
	}
	input.Token = strings.TrimSpace(input.Token)
	input.GameUID = strings.TrimSpace(input.GameUID)
	if len(input.Token) < 8 || input.GameUID == "" || len(input.GameUID) > 64 {
		writeJSON(w, http.StatusBadRequest, map[string]any{"error": "TOKEN_AND_UID_REQUIRED"})
		return
	}

	baseRow, err := collectorGetPlayer(r.Context(), input.GameUID)
	if err != nil {
		writeJSON(w, http.StatusNotFound, map[string]any{"error": "COLLECTOR_PLAYER_NOT_FOUND"})
		return
	}
	base := collectorBasePlayerV6191(baseRow)
	if strings.TrimSpace(base.GameUID) == "" {
		writeJSON(w, http.StatusNotFound, map[string]any{"error": "COLLECTOR_PLAYER_UID_MISSING"})
		return
	}

	scanner, ok := s.game.(protocol.ProfileScanner)
	if !ok {
		writeJSON(w, http.StatusServiceUnavailable, map[string]any{"error": "PROFILE_SCANNER_UNAVAILABLE"})
		return
	}

	ctx, cancel := context.WithTimeout(r.Context(), 35*time.Second)
	defer cancel()

	var (
		profiles []protocol.Player
		lastErr  error
	)
	for attempt := 0; attempt < 3; attempt++ {
		profiles, lastErr = scanner.ScanProfiles(ctx, input.Token, []string{base.GameUID})
		if lastErr == nil && len(profiles) > 0 {
			break
		}
		if ctx.Err() != nil {
			break
		}
		select {
		case <-ctx.Done():
			lastErr = ctx.Err()
		case <-time.After(time.Duration(attempt+1) * 250 * time.Millisecond):
		}
	}
	if lastErr != nil {
		writeGameError(w, lastErr)
		return
	}
	if len(profiles) == 0 {
		writeJSON(w, http.StatusBadGateway, map[string]any{"error": "PROFILE_TARGET_NOT_RETURNED"})
		return
	}

	var selected *protocol.Player
	for i := range profiles {
		if strings.TrimSpace(profiles[i].GameUID) == base.GameUID {
			selected = &profiles[i]
			break
		}
	}
	if selected == nil {
		selected = &profiles[0]
	}
	if strings.TrimSpace(selected.GameUID) != "" && strings.TrimSpace(selected.GameUID) != base.GameUID {
		writeJSON(w, http.StatusBadGateway, map[string]any{"error": "PROFILE_TARGET_UID_MISMATCH"})
		return
	}

	merged := mergeProfileWithMapV618(base, *selected)
	if strings.TrimSpace(merged.GameUID) == "" {
		merged.GameUID = base.GameUID
	}
	if strings.TrimSpace(merged.ObservedAt) == "" {
		merged.ObservedAt = utcNow()
	}

	// Persist via the existing Collector ingest endpoint outside a cycle.
	// Collector V6.19.1 stores rich profile fields as time-watermarked
	// observations, so storage-governor continues to cover them without a new
	// table or a synthetic Collector cycle.
	accepted, err := collectorIngest(ctx, []protocol.Player{merged}, 0)
	if err != nil {
		writeJSON(w, http.StatusBadGateway, map[string]any{"error": "PROFILE_REFRESH_INGEST_FAILED"})
		return
	}
	if accepted != 1 {
		writeJSON(w, http.StatusBadGateway, map[string]any{"error": "PROFILE_REFRESH_NOT_ACCEPTED"})
		return
	}
	if !richObservedV6191(merged) {
		// This is still a valid read-only refresh. Keep the response explicit:
		// no rich value was invented when Last War omitted the keys.
	}

	writeJSON(w, http.StatusOK, profileRefreshResponseV6191{
		OK: true, Readonly: true, Command: "get.user.info.multi", Player: merged,
	})
}

var _ = errors.New
