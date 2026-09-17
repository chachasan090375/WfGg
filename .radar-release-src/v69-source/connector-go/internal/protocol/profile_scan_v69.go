package protocol

import (
	"context"
	"encoding/json"
	"errors"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"
)

// WFGG_RADAR_NATIVE_PROFILE_BRIDGE_V69
// This path is deliberately separate from --scan-player. Profile batches are
// sent to the native helper through --scan-profiles and therefore cannot fall
// back to the map query parser.
type nativeProfileDiagnosticsV69 struct {
	Requested        int  `json:"requested"`
	Packets          int  `json:"packets"`
	DecodeErrors     int  `json:"decodeErrors"`
	CommandMatches   int  `json:"commandMatches"`
	ProfilesResolved int  `json:"profilesResolved"`
	UIDsReplaced     bool `json:"uidsReplaced"`
}

type nativeProfileReportV69 struct {
	OK                 bool                        `json:"ok"`
	LoginResponse      string                      `json:"loginResponse"`
	ScanTemplateFound  bool                        `json:"scanTemplateFound"`
	ScanPerformed      bool                        `json:"scanPerformed"`
	Players            []Player                    `json:"players"`
	ProfileDiagnostics *nativeProfileDiagnosticsV69 `json:"profileDiagnostics,omitempty"`
}

func profileFailureV69(rep nativeProfileReportV69) error {
	if rep.LoginResponse == "REJECTED" {
		return errors.New("LASTWAR_AUTH_REJECTED")
	}
	switch rep.LoginResponse {
	case "NATIVE_LOGIN_TEMPLATE_NOT_FOUND":
		return errors.New("LASTWAR_NATIVE_LOGIN_TEMPLATE_NOT_FOUND")
	case "CAPTURE_READ_FAILED", "CAPTURE_PARSE_FAILED":
		return errors.New("LASTWAR_NATIVE_CAPTURE_INVALID")
	case "PLAYER_PROFILE_TEMPLATE_NOT_FOUND":
		return errors.New("LASTWAR_PLAYER_PROFILE_TEMPLATE_NOT_FOUND")
	case "PLAYER_PROFILE_BATCH_INVALID":
		return errors.New("LASTWAR_PLAYER_PROFILE_BATCH_INVALID")
	case "PLAYER_PROFILE_UIDS_FIELD_NOT_FOUND":
		return errors.New("LASTWAR_PLAYER_PROFILE_UIDS_FIELD_NOT_FOUND")
	case "PLAYER_PROFILE_ENCODE_FAILED", "PLAYER_PROFILE_FRAME_FAILED":
		return errors.New("LASTWAR_PLAYER_PROFILE_ENCODE_FAILED")
	case "PLAYER_PROFILE_WRITE_FAILED":
		return errors.New("LASTWAR_PLAYER_PROFILE_SEND_FAILED")
	case "PLAYER_PROFILE_READ_FAILED":
		return errors.New("LASTWAR_PLAYER_PROFILE_READ_FAILED")
	case "PLAYER_PROFILE_RESPONSE_NOT_OBSERVED":
		return errors.New("LASTWAR_PLAYER_PROFILE_RESPONSE_NOT_OBSERVED")
	case "PLAYER_SCAN_INIT_REQUIRED":
		return errors.New("LASTWAR_PLAYER_PROFILE_INIT_REQUIRED")
	case "DIAL_FAILED":
		return errors.New("LASTWAR_NATIVE_DIAL_FAILED")
	case "LOGIN_WRITE_FAILED":
		return errors.New("LASTWAR_NATIVE_LOGIN_SEND_FAILED")
	case "READ_FAILED":
		return errors.New("LASTWAR_NATIVE_READ_FAILED")
	default:
		return errors.New("LASTWAR_PLAYER_PROFILE_FAILED")
	}
}

func (c *NativeTemplateReadonly) scanNativeProfilesV69(parent context.Context, token string, uids []string) ([]Player, error) {
	if err := c.validate(); err != nil {
		return nil, err
	}
	token = strings.TrimSpace(token)
	if len(token) < 8 {
		return nil, errors.New("GAME_TOKEN_REQUIRED")
	}
	if len(uids) == 0 || len(uids) > 50 {
		return nil, errors.New("COLLECTOR_PROFILE_BATCH_INVALID")
	}
	clean := make([]string, 0, len(uids))
	seen := map[string]bool{}
	for _, uid := range uids {
		uid = strings.TrimSpace(uid)
		if uid == "" || seen[uid] {
			continue
		}
		seen[uid] = true
		clean = append(clean, uid)
	}
	if len(clean) == 0 || len(clean) > 50 {
		return nil, errors.New("COLLECTOR_PROFILE_BATCH_INVALID")
	}

	dir, err := os.MkdirTemp("", "wfgg-radar-v69-profile-*")
	if err != nil {
		return nil, errors.New("LASTWAR_TEMP_DIR_FAILED")
	}
	defer os.RemoveAll(dir)
	if err := os.Chmod(dir, 0700); err != nil {
		return nil, errors.New("LASTWAR_TEMP_DIR_PERMISSIONS_FAILED")
	}

	cfg := c.Context
	cfg.AccessToken = token
	sessionPath := filepath.Join(dir, "session.json")
	raw, err := json.Marshal(cfg)
	if err != nil {
		return nil, errors.New("LASTWAR_SESSION_JSON_FAILED")
	}
	if err := os.WriteFile(sessionPath, raw, 0600); err != nil {
		return nil, errors.New("LASTWAR_SESSION_WRITE_FAILED")
	}

	timeout := c.Timeout
	if timeout <= 0 {
		timeout = 45 * time.Second
	}
	ctx, cancel := context.WithTimeout(parent, timeout)
	defer cancel()

	cmd := exec.CommandContext(ctx, c.Bin, c.CapturePath, sessionPath, "--scan-profiles", strings.Join(clean, ","))
	cmd.Env = childEnv(dir)
	var stdout, stderr limitedBuffer
	stdout.N, stderr.N = 4<<20, 64<<10
	cmd.Stdout, cmd.Stderr = &stdout, &stderr
	runErr := cmd.Run()
	if ctx.Err() != nil {
		return nil, errors.New("LASTWAR_PLAYER_PROFILE_TIMEOUT")
	}

	var rep nativeProfileReportV69
	if err := json.Unmarshal(stdout.Bytes(), &rep); err != nil {
		if runErr != nil {
			return nil, errors.New("LASTWAR_PLAYER_PROFILE_FAILED")
		}
		return nil, errors.New("LASTWAR_PLAYER_PROFILE_REPORT_INVALID")
	}
	if runErr != nil {
		return nil, profileFailureV69(rep)
	}
	if rep.LoginResponse != "OK" || !rep.ScanTemplateFound || !rep.ScanPerformed {
		return nil, errors.New("LASTWAR_PLAYER_PROFILE_NOT_CONFIRMED")
	}
	if rep.ProfileDiagnostics != nil {
		if rep.ProfileDiagnostics.Requested != len(clean) || !rep.ProfileDiagnostics.UIDsReplaced {
			return nil, errors.New("LASTWAR_PLAYER_PROFILE_DIAGNOSTIC_MISMATCH")
		}
		if len(rep.Players) == 0 && rep.ProfileDiagnostics.CommandMatches == 0 {
			return nil, errors.New("LASTWAR_PLAYER_PROFILE_RESPONSE_NOT_OBSERVED")
		}
	}
	return rep.Players, nil
}
