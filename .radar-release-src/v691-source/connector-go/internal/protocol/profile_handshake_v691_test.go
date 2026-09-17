package protocol

import (
	"os"
	"path/filepath"
	"testing"
)

func TestRuntimeDiagnosticsV691(t *testing.T) {
	dir := t.TempDir()
	bin := filepath.Join(dir, "radar-native-template")
	script := "#!/bin/sh\nprintf '%s\\n' '{\"ok\":true,\"readonly\":true,\"profileHandshake\":\"v6.9.1\",\"profileCLI\":true,\"profileCommand\":\"get.user.info.multi\"}'\n"
	if err := os.WriteFile(bin, []byte(script), 0o755); err != nil {
		t.Fatal(err)
	}
	c := &NativeTemplateReadonly{Bin: bin}
	d := c.RuntimeDiagnostics()
	if d["helperState"] != "PROFILE_READY" {
		t.Fatalf("helperState=%v", d["helperState"])
	}
	if d["profileCLI"] != true || d["profileCommand"] != true {
		t.Fatalf("capabilities=%v", d)
	}
	if sha, _ := d["helperSha256"].(string); len(sha) != 64 {
		t.Fatalf("helperSha256=%q", sha)
	}
}

func TestProfileFailureStagesV691(t *testing.T) {
	cases := map[string]string{
		"INVALID_ARGS":                       "LASTWAR_PLAYER_PROFILE_CLI_UNSUPPORTED",
		"NO_RESPONSE":                        "LASTWAR_PLAYER_PROFILE_LOGIN_NO_RESPONSE",
		"PLAYER_SCAN_INIT_REQUIRED":          "LASTWAR_PLAYER_PROFILE_INIT_REQUIRED",
		"PLAYER_PROFILE_TEMPLATE_NOT_FOUND":  "LASTWAR_PLAYER_PROFILE_TEMPLATE_NOT_FOUND",
		"PLAYER_PROFILE_UIDS_FIELD_NOT_FOUND": "LASTWAR_PLAYER_PROFILE_UID_REPLACE_FAILED",
		"PLAYER_PROFILE_WRITE_FAILED":         "LASTWAR_PLAYER_PROFILE_SEND_FAILED",
		"PLAYER_PROFILE_RESPONSE_NOT_OBSERVED": "LASTWAR_PLAYER_PROFILE_RESPONSE_NOT_OBSERVED",
		"PLAYER_PROFILE_DECODE_FAILED":        "LASTWAR_PLAYER_PROFILE_DECODE_FAILED",
		"SOMETHING_NEW":                      "LASTWAR_PLAYER_PROFILE_UNKNOWN_STATE",
	}
	for input, want := range cases {
		if got := profileFailureV691(nativeProfileReportV69{LoginResponse: input}).Error(); got != want {
			t.Fatalf("%s => %s, want %s", input, got, want)
		}
	}
}
