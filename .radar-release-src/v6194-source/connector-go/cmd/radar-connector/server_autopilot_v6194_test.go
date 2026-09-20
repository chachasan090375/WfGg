package main

import "testing"

func TestNormalizeAutopilotSeedV6194(t *testing.T) {
	cases := map[string]string{
		"8122":            "8122",
		" @federated:8122 ":"8122",
		"@federated:APS972":"972",
		"":                "",
	}
	for in, want := range cases {
		got, ok := normalizeAutopilotSeedV6194(in)
		if !ok || got != want {
			t.Fatalf("normalize %q = %q ok=%v; want %q", in, got, ok, want)
		}
	}
	for _, in := range []string{"abc", "@federated:-1", "@federated:0"} {
		if _, ok := normalizeAutopilotSeedV6194(in); ok {
			t.Fatalf("expected invalid seed %q", in)
		}
	}
}

func TestClassifyAutopilotCycleV6194(t *testing.T) {
	if got := classifyAutopilotCycleV6194(collectorJob{Status:"SUCCESS", RegionsCompleted:9, RegionsFailed:0}); got != "FULL" {
		t.Fatalf("full classified %s", got)
	}
	if got := classifyAutopilotCycleV6194(collectorJob{Status:"SUCCESS", RegionsCompleted:8, RegionsFailed:1}); got != "PARTIAL" {
		t.Fatalf("partial classified %s", got)
	}
	if got := classifyAutopilotCycleV6194(collectorJob{Status:"SUCCESS", Joined:true}); got != "JOINED" {
		t.Fatalf("joined classified %s", got)
	}
	if got := classifyAutopilotCycleV6194(collectorJob{Status:"FAILED", Error:"X"}); got != "FAILED" {
		t.Fatalf("failed classified %s", got)
	}
}

func TestAutopilotAuthFailureV6194(t *testing.T) {
	if !autopilotIsAuthFailureV6194(collectorJob{FailureCategory:"AUTH", FailureCode:"LASTWAR_AUTH_REJECTED"}) {
		t.Fatal("expected auth failure")
	}
	if autopilotIsAuthFailureV6194(collectorJob{FailureCategory:"PROTOCOL", FailureCode:"FMTWIREERROR"}) {
		t.Fatal("unexpected auth failure")
	}
}
