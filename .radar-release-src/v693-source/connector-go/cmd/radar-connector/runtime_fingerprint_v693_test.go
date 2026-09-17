package main

import "testing"

func TestConnectorRuntimeDiagnosticsV693(t *testing.T) {
	d := connectorRuntimeDiagnosticsV693()
	if d["state"] != "CONNECTOR_READY" {
		t.Fatalf("state=%v", d["state"])
	}
	sha, _ := d["sha256"].(string)
	if len(sha) != 64 {
		t.Fatalf("sha256=%q", sha)
	}
	if d["profileExecDiagnostics"] != "v6.9.2" {
		t.Fatalf("profileExecDiagnostics=%v", d["profileExecDiagnostics"])
	}
}
