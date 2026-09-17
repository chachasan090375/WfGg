package protocol

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"os"
	"strings"
)

// WFGG_RADAR_NATIVE_PROFILE_HANDSHAKE_V691
// RuntimeDiagnostics reports only non-secret local helper capabilities. It never
// executes the helper and never exposes tokens, session data or payloads.
func (c *NativeTemplateReadonly) RuntimeDiagnostics() map[string]any {
	out := map[string]any{
		"profileHandshake": "v6.9.1",
		"profileMode":      "--scan-profiles",
		"helperReadable":   false,
		"profileCLI":       false,
		"profileCommand":   false,
	}
	if c == nil || strings.TrimSpace(c.Bin) == "" {
		out["helperState"] = "BIN_NOT_CONFIGURED"
		return out
	}
	raw, err := os.ReadFile(c.Bin)
	if err != nil {
		out["helperState"] = "BIN_UNREADABLE"
		return out
	}
	sum := sha256.Sum256(raw)
	out["helperReadable"] = true
	out["helperSha256"] = hex.EncodeToString(sum[:])
	out["profileCLI"] = bytes.Contains(raw, []byte("--scan-profiles"))
	out["profileCommand"] = bytes.Contains(raw, []byte("get.user.info.multi"))
	if out["profileCLI"] == true && out["profileCommand"] == true {
		out["helperState"] = "PROFILE_READY"
	} else {
		out["helperState"] = "PROFILE_CAPABILITY_MISSING"
	}
	return out
}

func profileFailureV691(rep nativeProfileReportV69) error {
	code := strings.TrimSpace(rep.LoginResponse)
	switch code {
	case "INVALID_ARGS":
		return errors.New("LASTWAR_PLAYER_PROFILE_CLI_UNSUPPORTED")
	case "TOKEN_REQUIRED":
		return errors.New("LASTWAR_PLAYER_PROFILE_CLI_TOKEN_REQUIRED")
	case "REJECTED":
		return errors.New("LASTWAR_AUTH_REJECTED")
	case "NO_RESPONSE":
		return errors.New("LASTWAR_PLAYER_PROFILE_LOGIN_NO_RESPONSE")
	case "INVALID":
		return errors.New("LASTWAR_PLAYER_PROFILE_LOGIN_INVALID")
	case "NATIVE_LOGIN_TEMPLATE_NOT_FOUND":
		return errors.New("LASTWAR_NATIVE_LOGIN_TEMPLATE_NOT_FOUND")
	case "CAPTURE_READ_FAILED", "CAPTURE_PARSE_FAILED":
		return errors.New("LASTWAR_NATIVE_CAPTURE_INVALID")
	case "PLAYER_SCAN_INIT_REQUIRED":
		return errors.New("LASTWAR_PLAYER_PROFILE_INIT_REQUIRED")
	case "PLAYER_PROFILE_TEMPLATE_NOT_FOUND":
		return errors.New("LASTWAR_PLAYER_PROFILE_TEMPLATE_NOT_FOUND")
	case "PLAYER_PROFILE_BATCH_INVALID":
		return errors.New("LASTWAR_PLAYER_PROFILE_BATCH_INVALID")
	case "PLAYER_PROFILE_UIDS_FIELD_NOT_FOUND":
		return errors.New("LASTWAR_PLAYER_PROFILE_UID_REPLACE_FAILED")
	case "PLAYER_PROFILE_ENCODE_FAILED", "PLAYER_PROFILE_FRAME_FAILED":
		return errors.New("LASTWAR_PLAYER_PROFILE_SEND_ENCODE_FAILED")
	case "PLAYER_PROFILE_WRITE_FAILED":
		return errors.New("LASTWAR_PLAYER_PROFILE_SEND_FAILED")
	case "PLAYER_PROFILE_READ_FAILED":
		return errors.New("LASTWAR_PLAYER_PROFILE_RESPONSE_READ_FAILED")
	case "PLAYER_PROFILE_RESPONSE_NOT_OBSERVED":
		return errors.New("LASTWAR_PLAYER_PROFILE_RESPONSE_NOT_OBSERVED")
	case "PLAYER_PROFILE_DECODE_FAILED":
		return errors.New("LASTWAR_PLAYER_PROFILE_DECODE_FAILED")
	case "DIAL_FAILED":
		return errors.New("LASTWAR_NATIVE_DIAL_FAILED")
	case "LOGIN_WRITE_FAILED":
		return errors.New("LASTWAR_NATIVE_LOGIN_SEND_FAILED")
	case "READ_FAILED":
		return errors.New("LASTWAR_NATIVE_READ_FAILED")
	default:
		return errors.New("LASTWAR_PLAYER_PROFILE_UNKNOWN_STATE")
	}
}
