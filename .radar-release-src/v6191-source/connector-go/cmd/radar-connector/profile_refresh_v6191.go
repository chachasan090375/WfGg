package main

import (
	"context"
	"encoding/json"
	"net/http"
	"strings"
	"time"

	"wfgg-radar-connector/internal/protocol"
)

// WFGG_RADAR_TARGET_PROFILE_REFRESH_V6191
// Bounded, explicit and read-only refresh for one already-known player.
// It uses get.user.info.multi only; it never starts a map scan or Collector cycle.
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

func profileOnlyUIDV6191(query string) (string, bool) {
	q := strings.TrimSpace(query)
	if !strings.HasPrefix(strings.ToLower(q), "@profile:") {
		return "", false
	}
	uid := strings.TrimSpace(q[len("@profile:"):])
	if uid == "" || len(uid) > 64 {
		return "", false
	}
	for _, r := range uid {
		if r < '0' || r > '9' {
			return "", false
		}
	}
	return uid, true
}

func richObservedV6191(p protocol.Player) bool {
	return p.ArmyPower != nil || p.ArmyKill != nil || p.SVIPLevel != nil ||
		strings.TrimSpace(p.Country) != "" || strings.TrimSpace(p.AvatarRef) != ""
}

func playerMapV6191(p protocol.Player) map[string]any {
	raw, _ := json.Marshal(p)
	out := map[string]any{}
	_ = json.Unmarshal(raw, &out)
	return out
}

func (s *server) runTargetProfileRefreshV6191(ctx context.Context, token, gameUID string) (protocol.Player, error) {
	baseRow, err := collectorGetPlayer(ctx, gameUID)
	if err != nil {
		return protocol.Player{}, errPlayerNotFound
	}
	base := collectorBasePlayerV6191(baseRow)
	if strings.TrimSpace(base.GameUID) == "" {
		return protocol.Player{}, errPlayerNotFound
	}

	scanner, ok := s.game.(protocol.ProfileScanner)
	if !ok {
		return protocol.Player{}, errPlayerNotFound
	}

	var (
		profiles []protocol.Player
		lastErr  error
	)
	for attempt := 0; attempt < 3; attempt++ {
		profiles, lastErr = scanner.ScanProfiles(ctx, token, []string{base.GameUID})
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
		return protocol.Player{}, lastErr
	}
	if len(profiles) == 0 {
		return protocol.Player{}, errPlayerNotFound
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
		return protocol.Player{}, errPlayerNotFound
	}

	merged := mergeProfileWithMapV618(base, *selected)
	if strings.TrimSpace(merged.GameUID) == "" {
		merged.GameUID = base.GameUID
	}
	if strings.TrimSpace(merged.ObservedAt) == "" {
		merged.ObservedAt = utcNow()
	}

	accepted, err := collectorIngest(ctx, []protocol.Player{merged}, 0)
	if err != nil {
		return protocol.Player{}, err
	}
	if accepted != 1 {
		return protocol.Player{}, errPlayerNotFound
	}
	return merged, nil
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

	ctx, cancel := context.WithTimeout(r.Context(), 35*time.Second)
	defer cancel()
	player, err := s.runTargetProfileRefreshV6191(ctx, input.Token, input.GameUID)
	if err != nil {
		writeGameError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, profileRefreshResponseV6191{
		OK: true, Readonly: true, Command: "get.user.info.multi", Player: player,
	})
}
