package main

import "testing"

func TestFederatedServerTargetV615(t *testing.T) {
	for in, want := range map[string]string{
		"@federated:972":    "972",
		"@FEDERATED:APS972": "972",
		" @federated:00972 ": "972",
	} {
		got, ok := federatedServerTargetV615(in)
		if !ok || got != want {
			t.Fatalf("%q => %q,%v want %q,true", in, got, ok, want)
		}
	}
	for _, in := range []string{"El TonTon", "@federated:", "@federated:abc", "@profile:972", "@federated:0"} {
		if got, ok := federatedServerTargetV615(in); ok {
			t.Fatalf("%q unexpectedly resolved to %q", in, got)
		}
	}
}
