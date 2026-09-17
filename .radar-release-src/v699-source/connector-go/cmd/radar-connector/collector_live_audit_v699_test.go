package main

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestCollectorAuditV699AggregateOnly(t *testing.T) {
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet || r.URL.Path != "/stats" {
			t.Fatalf("unexpected Collector request: %s %s", r.Method, r.URL.Path)
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"players":21688,"activePlayers":21000,"observations":60000,"lastSeen":"2026-09-17T19:45:00Z","identityIndex":{"ready":true,"identities":21688,"aliases":23001,"pseudoCollisions":7,"coverageScopes":1,"coverageComplete":1,"lastSeen":"2026-09-17T19:45:00Z"},"lastCycle":{"id":42,"status":"SUCCESS","query":"must-not-leak"}}`))
	}))
	defer upstream.Close()
	t.Setenv("WFGG_COLLECTOR_URL", upstream.URL)

	req := httptest.NewRequest(http.MethodGet, "/v1/collector/audit", nil)
	rr := httptest.NewRecorder()
	(&server{}).collectorAuditV699(rr, req, nil)
	if rr.Code != http.StatusOK {
		t.Fatalf("unexpected status: %d body=%s", rr.Code, rr.Body.String())
	}

	var body map[string]any
	if err := json.Unmarshal(rr.Body.Bytes(), &body); err != nil {
		t.Fatal(err)
	}
	if body["auditVersion"] != "v6.9.9" || body["readonly"] != true || body["rawPlayerDataExposed"] != false {
		t.Fatalf("unexpected audit contract: %#v", body)
	}
	collector, ok := body["collector"].(map[string]any)
	if !ok {
		t.Fatalf("collector summary missing: %#v", body)
	}
	allowedCollector := map[string]bool{"players":true,"activePlayers":true,"observations":true,"lastSeen":true,"identityIndex":true,"lastCycle":true}
	for key := range collector {
		if !allowedCollector[key] {
			t.Fatalf("unexpected Collector field exposed: %q", key)
		}
	}
	cycle, ok := collector["lastCycle"].(map[string]any)
	if !ok {
		t.Fatalf("lastCycle missing: %#v", collector)
	}
	if _, leaked := cycle["query"]; leaked {
		t.Fatal("cycle query leaked through aggregate audit")
	}
	if len(cycle) != 2 || cycle["status"] != "SUCCESS" {
		t.Fatalf("unexpected cycle summary: %#v", cycle)
	}
}

func TestCollectorAuditV699SanitizesUpstreamFailure(t *testing.T) {
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "raw upstream details must never escape", http.StatusInternalServerError)
	}))
	defer upstream.Close()
	t.Setenv("WFGG_COLLECTOR_URL", upstream.URL)

	req := httptest.NewRequest(http.MethodGet, "/v1/collector/audit", nil)
	rr := httptest.NewRecorder()
	(&server{}).collectorAuditV699(rr, req, nil)
	if rr.Code != http.StatusBadGateway {
		t.Fatalf("unexpected status: %d", rr.Code)
	}
	var body map[string]any
	if err := json.Unmarshal(rr.Body.Bytes(), &body); err != nil {
		t.Fatal(err)
	}
	if body["error"] != "COLLECTOR_STATS_UNAVAILABLE" {
		t.Fatalf("unexpected sanitized error: %#v", body)
	}
	if _, exists := body["collector"]; exists {
		t.Fatal("collector data must not be present on failure")
	}
}
