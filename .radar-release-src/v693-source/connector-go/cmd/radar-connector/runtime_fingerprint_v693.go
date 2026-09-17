package main

import (
	"crypto/sha256"
	"encoding/hex"
	"io"
	"os"
)

// WFGG_RADAR_CONNECTOR_RUNTIME_FINGERPRINT_V693
// Reports a safe fingerprint of the executable that is actually serving the
// current /v1/health request. No paths, process arguments or environment values
// are exposed.
func connectorRuntimeDiagnosticsV693() map[string]any {
	out := map[string]any{
		"state":                  "CONNECTOR_READY",
		"profileExecDiagnostics": "v6.9.2",
	}
	exe, err := os.Executable()
	if err != nil {
		out["state"] = "CONNECTOR_EXECUTABLE_UNAVAILABLE"
		return out
	}
	f, err := os.Open(exe)
	if err != nil {
		out["state"] = "CONNECTOR_EXECUTABLE_READ_FAILED"
		return out
	}
	defer f.Close()
	h := sha256.New()
	if _, err := io.Copy(h, f); err != nil {
		out["state"] = "CONNECTOR_EXECUTABLE_HASH_FAILED"
		return out
	}
	out["sha256"] = hex.EncodeToString(h.Sum(nil))
	return out
}
