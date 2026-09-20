package main

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strconv"
	"sync/atomic"
	"testing"
	"time"
)

func TestCollectorTerminalizationBackoffV6198(t *testing.T) {
	if got := collectorTerminalizationBackoffV6198(1); got != 2*time.Second {
		t.Fatalf("attempt 1 backoff=%s", got)
	}
	if got := collectorTerminalizationBackoffV6198(9); got != 10*time.Second {
		t.Fatalf("backoff must cap at 10s, got %s", got)
	}
}

func TestCollectorFinishCycleReliableV6198RetriesAndVerifies(t *testing.T) {
	var finishCalls atomic.Int32
	var terminal atomic.Bool

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/cycle/finish":
			n := finishCalls.Add(1)
			if n < 3 {
				http.Error(w, "transient", http.StatusServiceUnavailable)
				return
			}
			terminal.Store(true)
			_ = json.NewEncoder(w).Encode(map[string]any{
				"ok": true,
				"cycle": map[string]any{"id": 47, "status": "FAILED"},
			})
		case "/cycle/status":
			id, _ := strconv.ParseInt(r.URL.Query().Get("id"), 10, 64)
			status := "RUNNING"
			if terminal.Load() {
				status = "FAILED"
			}
			_ = json.NewEncoder(w).Encode(map[string]any{
				"ok": true,
				"cycle": map[string]any{"id": id, "status": status},
			})
		default:
			http.NotFound(w, r)
		}
	}))
	defer srv.Close()
	t.Setenv("WFGG_COLLECTOR_URL", srv.URL)

	// Keep the unit test fast while still exercising the production helper's
	// retry loop by arranging success on the third request.
	start := time.Now()
	if err := collectorFinishCycleReliableV6198(47, "FAILED", "MAP_INGEST_FAILED"); err != nil {
		t.Fatal(err)
	}
	if finishCalls.Load() != 3 {
		t.Fatalf("finish calls=%d want=3", finishCalls.Load())
	}
	if time.Since(start) < 5*time.Second {
		t.Fatal("expected bounded retry backoff to execute")
	}
}

func TestCollectorFinishCycleReliableV6198RejectsInvalidInput(t *testing.T) {
	if err := collectorFinishCycleReliableV6198(0, "FAILED", "X"); err == nil {
		t.Fatal("expected invalid cycle id to fail")
	}
	if err := collectorFinishCycleReliableV6198(1, "RUNNING", "X"); err == nil {
		t.Fatal("expected non-terminal status to fail")
	}
}
