package protocol

import (
	"context"
	"encoding/json"
	"errors"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"time"
)

// ScanPlayerRegion runs one isolated native process against one of the nine
// validated Collector origins. The Last War token exists only in a 0600 temp
// session file and is removed with the private temp directory after the call.
func (c *NativeTemplateReadonly) ScanPlayerRegion(parent context.Context, token, query string, region int) ([]Player, error) {
	if region < 0 || region > 8 {
		return nil, errors.New("COLLECTOR_REGION_INVALID")
	}
	return c.scanNativeV4(parent, token, query, &region)
}

// ScanProfiles uses the already validated V4 direct profile mode.  Batches are
// capped at 50 UIDs here, matching the Collector V4 executor contract.
func (c *NativeTemplateReadonly) ScanProfiles(parent context.Context, token string, uids []string) ([]Player, error) {
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
	if len(clean) == 0 {
		return nil, errors.New("COLLECTOR_PROFILE_BATCH_INVALID")
	}
	return c.scanNativeV4(parent, token, "@profile:"+strings.Join(clean, ","), nil)
}

func (c *NativeTemplateReadonly) scanNativeV4(parent context.Context, token, query string, region *int) ([]Player, error) {
	if err := c.validate(); err != nil {
		return nil, err
	}
	token = strings.TrimSpace(token)
	query = strings.TrimSpace(query)
	if len(token) < 8 {
		return nil, errors.New("GAME_TOKEN_REQUIRED")
	}
	if query == "" || len(query) > 4096 {
		return nil, errors.New("PLAYER_QUERY_REQUIRED")
	}

	dir, err := os.MkdirTemp("", "wfgg-radar-v4-scan-*")
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

	cmd := exec.CommandContext(ctx, c.Bin, c.CapturePath, sessionPath, "--scan-player", query)
	env := append(childEnv(dir), "LASTWAR_NATIVE_SCAN_SEED="+c.ScanSeed)
	if region != nil {
		env = append(env, "WFGG_COLLECTOR_ORIGIN_INDEX="+strconv.Itoa(*region))
	}
	cmd.Env = env
	var stdout, stderr limitedBuffer
	stdout.N, stderr.N = 4<<20, 64<<10
	cmd.Stdout, cmd.Stderr = &stdout, &stderr
	runErr := cmd.Run()
	if ctx.Err() != nil {
		return nil, errors.New("LASTWAR_PLAYER_SCAN_TIMEOUT")
	}

	var rep nativeTemplateReport
	if err := json.Unmarshal(stdout.Bytes(), &rep); err != nil {
		if runErr != nil {
			return nil, errors.New("LASTWAR_PLAYER_SCAN_FAILED")
		}
		return nil, errors.New("LASTWAR_PLAYER_SCAN_REPORT_INVALID")
	}
	if runErr != nil {
		if rep.LoginResponse == "REJECTED" {
			return nil, errors.New("LASTWAR_AUTH_REJECTED")
		}
		switch rep.LoginResponse {
		case "NATIVE_LOGIN_TEMPLATE_NOT_FOUND":
			return nil, errors.New("LASTWAR_NATIVE_LOGIN_TEMPLATE_NOT_FOUND")
		case "CAPTURE_READ_FAILED", "CAPTURE_PARSE_FAILED":
			return nil, errors.New("LASTWAR_NATIVE_CAPTURE_INVALID")
		case "PLAYER_SCAN_TEMPLATE_NOT_FOUND":
			return nil, errors.New("LASTWAR_PLAYER_SCAN_TEMPLATE_NOT_FOUND")
		case "PLAYER_SCAN_TEMPLATE_UNSAFE":
			return nil, errors.New("LASTWAR_PLAYER_SCAN_TEMPLATE_UNSAFE")
		case "PLAYER_SCAN_INIT_REQUIRED":
			return nil, errors.New("LASTWAR_PLAYER_SCAN_INIT_REQUIRED")
		case "PLAYER_SCAN_QUERY_REPLACEMENT_FAILED":
			return nil, errors.New("LASTWAR_PLAYER_SCAN_QUERY_REPLACEMENT_FAILED")
		case "PLAYER_SCAN_ENCODE_FAILED", "PLAYER_SCAN_FRAME_FAILED":
			return nil, errors.New("LASTWAR_PLAYER_SCAN_ENCODE_FAILED")
		case "PLAYER_SCAN_WRITE_FAILED":
			return nil, errors.New("LASTWAR_PLAYER_SCAN_SEND_FAILED")
		case "PLAYER_SCAN_READ_FAILED":
			return nil, errors.New("LASTWAR_PLAYER_SCAN_READ_FAILED")
		case "DIAL_FAILED":
			return nil, errors.New("LASTWAR_NATIVE_DIAL_FAILED")
		case "LOGIN_WRITE_FAILED":
			return nil, errors.New("LASTWAR_NATIVE_LOGIN_SEND_FAILED")
		case "READ_FAILED":
			return nil, errors.New("LASTWAR_NATIVE_READ_FAILED")
		default:
			return nil, errors.New("LASTWAR_PLAYER_SCAN_FAILED")
		}
	}
	if rep.LoginResponse != "OK" || !rep.ScanTemplateFound || !rep.ScanPerformed {
		return nil, errors.New("LASTWAR_PLAYER_SCAN_NOT_CONFIRMED")
	}
	return rep.Players, nil
}
