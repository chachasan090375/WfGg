package main

import (
	"errors"
	"testing"
)

func TestFederatedDiagnosticsV65Categories(t *testing.T) {
	cases := []struct {
		name     string
		code     string
		cause    error
		category string
	}{
		{"auth", "MAP_REGION_FAILED", errors.New("LASTWAR_AUTH_REJECTED"), "AUTH"},
		{"network", "MAP_REGION_FAILED", errors.New("LASTWAR_NATIVE_DIAL_FAILED"), "NETWORK"},
		{"decode", "MAP_REGION_FAILED", errors.New("LASTWAR_PLAYER_SCAN_REPORT_INVALID"), "DECODE"},
		{"ingest", "MAP_INGEST_FAILED", errors.New("collector http 503"), "INGEST"},
		{"server", "MAP_REGION_FAILED", errors.New("COLLECTOR_REGION_INVALID"), "SERVER_TARGET"},
		{"protocol", "PROFILE_BATCH_FAILED", errors.New("LASTWAR_PLAYER_SCAN_TEMPLATE_NOT_FOUND"), "PROTOCOL"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			d := buildCollectorFailureDiagnosticV65("@federated:APS990", "FEDERATED_MAP", 4, tc.code, tc.cause)
			if d.Category != tc.category {
				t.Fatalf("category=%s want=%s cause=%s", d.Category, tc.category, d.Cause)
			}
			if d.ServerTarget != "990" {
				t.Fatalf("serverTarget=%q", d.ServerTarget)
			}
			if d.FailurePhase != "FEDERATED_MAP" {
				t.Fatalf("failurePhase=%q", d.FailurePhase)
			}
		})
	}
}

func TestFederatedDiagnosticsV65SanitizesCause(t *testing.T) {
	d := buildCollectorFailureDiagnosticV65("@federated:990", "MAP", 1, "MAP_REGION_FAILED", errors.New("dial tcp 10.0.0.1:443: secret=value"))
	if d.Cause == "" || len(d.Cause) > 96 {
		t.Fatalf("unsafe cause length=%d", len(d.Cause))
	}
	for _, forbidden := range []string{"=", ".", "/", " "} {
		if contains := stringContains(d.Cause, forbidden); contains {
			t.Fatalf("unsafe character %q in %q", forbidden, d.Cause)
		}
	}
}

func stringContains(s, part string) bool {
	for i := 0; i+len(part) <= len(s); i++ {
		if s[i:i+len(part)] == part {
			return true
		}
	}
	return false
}
