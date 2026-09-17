package main

import (
	"net/http"
	"net/url"
	"strings"
)

// WFGG_RADAR_FAST_IDENTITY_LOOKUP_V611
// Fast, read-only player lookup. It never starts a Collector cycle and never
// talks to Last War directly. Current pseudo/UID hits use /player immediately;
// historical aliases fall back to the identity index, then resolve the UID to
// the canonical player row.
type collectorFastPlayerV611 struct {
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

type collectorFastPlayerEnvelopeV611 struct {
	OK     bool                     `json:"ok"`
	Player *collectorFastPlayerV611 `json:"player"`
}

type collectorIdentityRowV611 struct {
	GameUID string `json:"game_uid"`
}

type collectorIdentityResolveV611 struct {
	OK         bool                       `json:"ok"`
	Resolved   bool                       `json:"resolved"`
	Ambiguous  bool                       `json:"ambiguous"`
	Route      string                     `json:"route"`
	Identity   *collectorIdentityRowV611  `json:"identity"`
	Candidates []collectorIdentityRowV611 `json:"candidates"`
}

type collectorFastLookupPlayerV611 struct {
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

type collectorFastLookupResponseV611 struct {
	OK             bool                           `json:"ok"`
	Resolved       bool                           `json:"resolved"`
	Ambiguous      bool                           `json:"ambiguous"`
	Route          string                         `json:"route"`
	Readonly       bool                           `json:"readonly"`
	CandidateCount int                            `json:"candidateCount,omitempty"`
	Player         *collectorFastLookupPlayerV611 `json:"player,omitempty"`
}

func fastLookupQueryV611(raw string) (string, bool) {
	q := strings.TrimSpace(raw)
	return q, q != "" && len(q) <= 128
}

func fastLookupPlayerV611(p *collectorFastPlayerV611) *collectorFastLookupPlayerV611 {
	if p == nil {
		return nil
	}
	uid := strings.TrimSpace(p.GameUID)
	pseudo := strings.TrimSpace(p.Pseudo)
	if uid == "" && pseudo == "" {
		return nil
	}
	return &collectorFastLookupPlayerV611{
		GameUID: uid, Pseudo: pseudo,
		ServerID: strings.TrimSpace(p.ServerID), AllianceID: strings.TrimSpace(p.AllianceID), AllianceTag: strings.TrimSpace(p.AllianceTag),
		X: p.X, Y: p.Y, HQLevel: p.HQLevel, Power: p.Power, ObservedAt: strings.TrimSpace(p.LastSeen),
	}
}

func (s *server) collectorFastLookupV611(w http.ResponseWriter, r *http.Request, _ []byte) {
	q, valid := fastLookupQueryV611(r.URL.Query().Get("q"))
	if !valid {
		writeJSON(w, http.StatusBadRequest, map[string]any{"error": "COLLECTOR_FAST_LOOKUP_QUERY_REQUIRED"})
		return
	}

	// Shortest path: current pseudo or UID resolves directly to the canonical row.
	var direct collectorFastPlayerEnvelopeV611
	if err := collectorJSON(r.Context(), http.MethodGet, "/player?q="+url.QueryEscape(q), nil, &direct); err == nil && direct.OK {
		if player := fastLookupPlayerV611(direct.Player); player != nil {
			writeJSON(w, http.StatusOK, collectorFastLookupResponseV611{
				OK: true, Resolved: true, Route: "EXACT_PLAYER", Readonly: true, Player: player,
			})
			return
		}
	}

	// Historical pseudo path: resolve alias -> stable UID -> canonical current row.
	identityPath := "/identity/resolve?q=" + url.QueryEscape(q)
	if serverHint := strings.TrimSpace(r.URL.Query().Get("server")); serverHint != "" {
		identityPath += "&server=" + url.QueryEscape(serverHint)
	}
	var identity collectorIdentityResolveV611
	if err := collectorJSON(r.Context(), http.MethodGet, identityPath, nil, &identity); err != nil {
		writeJSON(w, http.StatusOK, collectorFastLookupResponseV611{OK: true, Route: "MISS", Readonly: true})
		return
	}
	if identity.Ambiguous {
		writeJSON(w, http.StatusOK, collectorFastLookupResponseV611{
			OK: true, Ambiguous: true, Route: identity.Route, Readonly: true, CandidateCount: len(identity.Candidates),
		})
		return
	}
	if !identity.Resolved || identity.Identity == nil || strings.TrimSpace(identity.Identity.GameUID) == "" {
		writeJSON(w, http.StatusOK, collectorFastLookupResponseV611{OK: true, Route: "MISS", Readonly: true})
		return
	}

	uid := strings.TrimSpace(identity.Identity.GameUID)
	var byUID collectorFastPlayerEnvelopeV611
	if err := collectorJSON(r.Context(), http.MethodGet, "/player?q="+url.QueryEscape(uid), nil, &byUID); err != nil || !byUID.OK {
		writeJSON(w, http.StatusOK, collectorFastLookupResponseV611{OK: true, Route: "IDENTITY_UID_MISSING", Readonly: true})
		return
	}
	player := fastLookupPlayerV611(byUID.Player)
	if player == nil {
		writeJSON(w, http.StatusOK, collectorFastLookupResponseV611{OK: true, Route: "IDENTITY_UID_MISSING", Readonly: true})
		return
	}
	writeJSON(w, http.StatusOK, collectorFastLookupResponseV611{
		OK: true, Resolved: true, Route: identity.Route, Readonly: true, Player: player,
	})
}
