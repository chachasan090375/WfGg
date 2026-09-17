package main

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestCollectorIndexSearchV610NormalizesAndBounds(t *testing.T) {
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/search" {
			t.Fatalf("unexpected path: %s", r.URL.Path)
		}
		if r.URL.Query().Get("q") != "El TonTon" || r.URL.Query().Get("limit") != "100" {
			t.Fatalf("unexpected query: %s", r.URL.RawQuery)
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"ok":true,"players":[{"game_uid":" 123 ","pseudo":" El TonTon ","server_id":"990","alliance_id":"A1","alliance_tag":"WFGG","x":321,"y":654,"hq_level":35,"power":987654321,"last_seen":"2026-09-17T19:45:00Z","state_hash":"must-not-leak","status":"ACTIVE"}]}`))
	}))
	defer upstream.Close()
	t.Setenv("WFGG_COLLECTOR_URL", upstream.URL)

	req := httptest.NewRequest(http.MethodGet, "/v1/collector/index/search?q=El%20TonTon&limit=999", nil)
	rr := httptest.NewRecorder()
	(&server{}).collectorIndexSearchV610(rr, req, nil)
	if rr.Code != http.StatusOK {
		t.Fatalf("unexpected status: %d body=%s", rr.Code, rr.Body.String())
	}
	var body struct {
		OK bool `json:"ok"`
		Source string `json:"source"`
		Readonly bool `json:"readonly"`
		Count int `json:"count"`
		Players []map[string]any `json:"players"`
	}
	if err := json.Unmarshal(rr.Body.Bytes(), &body); err != nil {
		t.Fatal(err)
	}
	if !body.OK || !body.Readonly || body.Source != "collector-index-v610" || body.Count != 1 || len(body.Players) != 1 {
		t.Fatalf("unexpected response: %#v", body)
	}
	p := body.Players[0]
	if p["gameUid"] != "123" || p["pseudo"] != "El TonTon" || p["serverId"] != "990" || p["allianceTag"] != "WFGG" {
		t.Fatalf("normalization failed: %#v", p)
	}
	encoded := rr.Body.String()
	for _, forbidden := range []string{"state_hash", "last_change_cycle", "missing_count", "credential", "token"} {
		if strings.Contains(encoded, forbidden) {
			t.Fatalf("internal field leaked: %s", forbidden)
		}
	}
}

func TestCollectorIndexSearchV610RejectsEmptyQuery(t *testing.T) {
	req := httptest.NewRequest(http.MethodGet, "/v1/collector/index/search?q=", nil)
	rr := httptest.NewRecorder()
	(&server{}).collectorIndexSearchV610(rr, req, nil)
	if rr.Code != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d", rr.Code)
	}
}

func TestCollectorIndexLimitV610(t *testing.T) {
	cases := map[string]int{"":50,"0":1,"-10":1,"20":20,"999":100,"garbage":50}
	for raw, want := range cases {
		if got := collectorIndexLimitV610(raw); got != want {
			t.Fatalf("limit %q: got %d want %d", raw, got, want)
		}
	}
}
