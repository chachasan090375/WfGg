package main

import (
	"net/http"
	"net/url"
	"strconv"
	"strings"
)

// WFGG_RADAR_COLLECTOR_INDEX_SEARCH_V610
// Exposes a bounded, read-only projection of the local Collector search index.
// Internal Collector state (hashes, cycle ids, status internals, credentials) is never returned.
type collectorIndexRowV610 struct {
	GameUID     string `json:"game_uid"`
	Pseudo      string `json:"pseudo"`
	ServerID    string `json:"server_id"`
	AllianceID  string `json:"alliance_id"`
	AllianceTag string `json:"alliance_tag"`
	X           *int   `json:"x"`
	Y           *int   `json:"y"`
	HQLevel     *int   `json:"hq_level"`
	Power       *int64 `json:"power"`
	LastSeen    string `json:"last_seen"`
}

type collectorIndexUpstreamV610 struct {
	OK      bool                    `json:"ok"`
	Players []collectorIndexRowV610 `json:"players"`
}

type collectorIndexPlayerV610 struct {
	GameUID     string `json:"gameUid"`
	Pseudo      string `json:"pseudo"`
	ServerID    string `json:"serverId,omitempty"`
	AllianceID  string `json:"allianceId,omitempty"`
	AllianceTag string `json:"allianceTag,omitempty"`
	X           *int   `json:"x,omitempty"`
	Y           *int   `json:"y,omitempty"`
	HQLevel     *int   `json:"hqLevel,omitempty"`
	Power       *int64 `json:"power,omitempty"`
	ObservedAt  string `json:"observedAt,omitempty"`
}

type collectorIndexResponseV610 struct {
	OK       bool                       `json:"ok"`
	Source   string                     `json:"source"`
	Readonly bool                       `json:"readonly"`
	Count    int                        `json:"count"`
	Players  []collectorIndexPlayerV610 `json:"players"`
}

func collectorIndexLimitV610(raw string) int {
	limit := 50
	if n, err := strconv.Atoi(strings.TrimSpace(raw)); err == nil {
		limit = n
	}
	if limit < 1 {
		limit = 1
	}
	if limit > 100 {
		limit = 100
	}
	return limit
}

func (s *server) collectorIndexSearchV610(w http.ResponseWriter, r *http.Request, _ []byte) {
	q := strings.TrimSpace(r.URL.Query().Get("q"))
	if q == "" || len(q) > 128 {
		writeJSON(w, http.StatusBadRequest, map[string]any{"error": "COLLECTOR_INDEX_QUERY_REQUIRED"})
		return
	}
	limit := collectorIndexLimitV610(r.URL.Query().Get("limit"))
	path := "/search?q=" + url.QueryEscape(q) + "&limit=" + strconv.Itoa(limit)
	var upstream collectorIndexUpstreamV610
	if err := collectorJSON(r.Context(), http.MethodGet, path, nil, &upstream); err != nil || !upstream.OK {
		writeJSON(w, http.StatusBadGateway, map[string]any{"error": "COLLECTOR_INDEX_UNAVAILABLE"})
		return
	}
	players := make([]collectorIndexPlayerV610, 0, len(upstream.Players))
	for _, p := range upstream.Players {
		uid := strings.TrimSpace(p.GameUID)
		pseudo := strings.TrimSpace(p.Pseudo)
		if uid == "" && pseudo == "" {
			continue
		}
		players = append(players, collectorIndexPlayerV610{
			GameUID: uid, Pseudo: pseudo,
			ServerID: strings.TrimSpace(p.ServerID), AllianceID: strings.TrimSpace(p.AllianceID), AllianceTag: strings.TrimSpace(p.AllianceTag),
			X: p.X, Y: p.Y, HQLevel: p.HQLevel, Power: p.Power, ObservedAt: strings.TrimSpace(p.LastSeen),
		})
	}
	writeJSON(w, http.StatusOK, collectorIndexResponseV610{
		OK: true, Source: "collector-index-v610", Readonly: true, Count: len(players), Players: players,
	})
}
