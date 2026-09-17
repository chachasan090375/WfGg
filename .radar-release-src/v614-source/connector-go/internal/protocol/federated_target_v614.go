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

// FederatedRegionDiagnosticScanner is the V6.14 read-only extension that lets
// Collector select the serverId carried by world.get.block independently from
// the authenticated account's home server. Each region still executes in its
// own native process, so the target cannot leak between concurrent jobs.
type FederatedRegionDiagnosticScanner interface {
	ScanPlayerRegionDiagnosticOnServer(ctx context.Context, token, query string, region int, serverID string) ([]Player, RegionScanDiagnostic, error)
}

func normalizeFederatedTargetServerV614(serverID string) (string, error) {
	raw := strings.TrimSpace(serverID)
	raw = strings.TrimPrefix(strings.ToUpper(raw), "APS")
	if raw == "" || len(raw) > 8 {
		return "", errors.New("FEDERATED_TARGET_SERVER_INVALID")
	}
	for _, r := range raw {
		if r < '0' || r > '9' {
			return "", errors.New("FEDERATED_TARGET_SERVER_INVALID")
		}
	}
	n, err := strconv.Atoi(raw)
	if err != nil || n <= 0 {
		return "", errors.New("FEDERATED_TARGET_SERVER_INVALID")
	}
	return strconv.Itoa(n), nil
}

func (c *NativeTemplateReadonly) ScanPlayerRegionDiagnosticOnServer(parent context.Context, token, query string, region int, serverID string) ([]Player, RegionScanDiagnostic, error) {
	diag := emptyRegionDiagnosticV67(region)
	if region < 0 || region > 8 {
		return nil, diag, errors.New("COLLECTOR_REGION_INVALID")
	}
	target, err := normalizeFederatedTargetServerV614(serverID)
	if err != nil {
		return nil, diag, err
	}
	if err := c.validate(); err != nil {
		return nil, diag, err
	}
	token = strings.TrimSpace(token)
	query = strings.TrimSpace(query)
	if len(token) < 8 {
		return nil, diag, errors.New("GAME_TOKEN_REQUIRED")
	}
	if query == "" || len(query) > 4096 {
		return nil, diag, errors.New("PLAYER_QUERY_REQUIRED")
	}

	dir, err := os.MkdirTemp("", "wfgg-radar-v614-region-*")
	if err != nil {
		return nil, diag, errors.New("LASTWAR_TEMP_DIR_FAILED")
	}
	defer os.RemoveAll(dir)
	if err := os.Chmod(dir, 0700); err != nil {
		return nil, diag, errors.New("LASTWAR_TEMP_DIR_PERMISSIONS_FAILED")
	}

	cfg := c.Context
	cfg.AccessToken = token
	sessionPath := filepath.Join(dir, "session.json")
	raw, err := json.Marshal(cfg)
	if err != nil {
		return nil, diag, errors.New("LASTWAR_SESSION_JSON_FAILED")
	}
	if err := os.WriteFile(sessionPath, raw, 0600); err != nil {
		return nil, diag, errors.New("LASTWAR_SESSION_WRITE_FAILED")
	}

	timeout := c.Timeout
	if timeout <= 0 {
		timeout = 45 * time.Second
	}
	ctx, cancel := context.WithTimeout(parent, timeout)
	defer cancel()

	cmd := exec.CommandContext(ctx, c.Bin, c.CapturePath, sessionPath, "--scan-player", query)
	cmd.Env = append(
		childEnv(dir),
		"WFGG_COLLECTOR_ORIGIN_INDEX="+strconv.Itoa(region),
		"WFGG_COLLECTOR_TARGET_SERVER_ID="+target,
	)
	var stdout, stderr limitedBuffer
	stdout.N, stderr.N = 4<<20, 64<<10
	cmd.Stdout, cmd.Stderr = &stdout, &stderr
	runErr := cmd.Run()
	diag = parseRegionDiagnosticV67(stderr.Bytes(), region)
	if ctx.Err() != nil {
		return nil, diag, errors.New("LASTWAR_PLAYER_SCAN_TIMEOUT")
	}

	var rep nativeTemplateReport
	if err := json.Unmarshal(stdout.Bytes(), &rep); err != nil {
		if runErr != nil {
			return nil, diag, errors.New("LASTWAR_PLAYER_SCAN_FAILED")
		}
		return nil, diag, errors.New("LASTWAR_PLAYER_SCAN_REPORT_INVALID")
	}
	if runErr != nil {
		return nil, diag, mapRegionNativeErrorV67(rep.LoginResponse)
	}
	if rep.LoginResponse != "OK" || !rep.ScanTemplateFound || !rep.ScanPerformed {
		return nil, diag, errors.New("LASTWAR_PLAYER_SCAN_NOT_CONFIRMED")
	}
	return rep.Players, diag, nil
}
