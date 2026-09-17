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

// RegionScanDiagnostic contains only aggregate, non-sensitive protocol counters.
// It intentionally excludes payloads, tokens, session identifiers and player values.
type RegionScanDiagnostic struct {
	OriginIndex    int `json:"originIndex"`
	OriginX        int `json:"originX"`
	OriginY        int `json:"originY"`
	Requests       int `json:"requests"`
	Packets        int `json:"packets"`
	DecodeErrors   int `json:"decodeErrors"`
	Objects        int `json:"objects"`
	Arrays         int `json:"arrays"`
	Blobs          int `json:"blobs"`
	ProtoValid     int `json:"protoValid"`
	PlayerCities   int `json:"playerCities"`
	DetailPresent  int `json:"detailPresent"`
	DetailParsed   int `json:"detailParsed"`
	UIDPresent     int `json:"uidPresent"`
	NamePresent    int `json:"namePresent"`
	PlayersDecoded int `json:"playersDecoded"`
	QueryMatches   int `json:"queryMatches"`
	ReadTimeouts   int `json:"readTimeouts"`
}

// RegionDiagnosticScanner is the V6.7 read-only discovery extension. The legacy
// RegionScanner remains valid and is used as fallback by Collector.
type RegionDiagnosticScanner interface {
	ScanPlayerRegionDiagnostic(ctx context.Context, token, query string, region int) ([]Player, RegionScanDiagnostic, error)
}

var v67OriginGrid = [9][2]int{
	{0, 0}, {1000, 0}, {2000, 0},
	{0, 1000}, {1000, 1000}, {2000, 1000},
	{0, 2000}, {1000, 2000}, {2000, 2000},
}

func emptyRegionDiagnosticV67(region int) RegionScanDiagnostic {
	d := RegionScanDiagnostic{OriginIndex: region}
	if region >= 0 && region < len(v67OriginGrid) {
		d.OriginX = v67OriginGrid[region][0]
		d.OriginY = v67OriginGrid[region][1]
	}
	return d
}

func parseRegionDiagnosticV67(raw []byte, region int) RegionScanDiagnostic {
	d := emptyRegionDiagnosticV67(region)
	for _, line := range strings.Split(string(raw), "\n") {
		line = strings.TrimSpace(line)
		if !strings.HasPrefix(line, "WFGG_SCAN_V67 ") {
			continue
		}
		for _, field := range strings.Fields(strings.TrimPrefix(line, "WFGG_SCAN_V67 ")) {
			parts := strings.SplitN(field, "=", 2)
			if len(parts) != 2 {
				continue
			}
			n, err := strconv.Atoi(parts[1])
			if err != nil || n < 0 {
				continue
			}
			switch parts[0] {
			case "requests":
				d.Requests = n
			case "packets":
				d.Packets = n
			case "decode_errors":
				d.DecodeErrors = n
			case "objects":
				d.Objects = n
			case "arrays":
				d.Arrays = n
			case "blobs":
				d.Blobs = n
			case "proto":
				d.ProtoValid = n
			case "kind6":
				d.PlayerCities = n
			case "detail3_present":
				d.DetailPresent = n
			case "detail_parse_ok":
				d.DetailParsed = n
			case "uid_present":
				d.UIDPresent = n
			case "name14_present":
				d.NamePresent = n
			case "decoded_players":
				d.PlayersDecoded = n
			case "query_matches":
				d.QueryMatches = n
			case "read_timeouts":
				d.ReadTimeouts = n
			}
		}
	}
	return d
}

// ScanPlayerRegionDiagnostic runs exactly one canonical 3x3 origin. The helper
// receives WFGG_COLLECTOR_ORIGIN_INDEX and V6.7 makes that selector authoritative.
func (c *NativeTemplateReadonly) ScanPlayerRegionDiagnostic(parent context.Context, token, query string, region int) ([]Player, RegionScanDiagnostic, error) {
	diag := emptyRegionDiagnosticV67(region)
	if region < 0 || region > 8 {
		return nil, diag, errors.New("COLLECTOR_REGION_INVALID")
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

	dir, err := os.MkdirTemp("", "wfgg-radar-v67-region-*")
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
	cmd.Env = append(childEnv(dir), "WFGG_COLLECTOR_ORIGIN_INDEX="+strconv.Itoa(region))
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

func mapRegionNativeErrorV67(code string) error {
	code = strings.TrimSpace(code)
	if code == "REJECTED" {
		return errors.New("LASTWAR_AUTH_REJECTED")
	}
	for _, prefix := range []string{
		"PLAYER_SCAN_SYNTHETIC_WRITE_TIMEOUT",
		"PLAYER_SCAN_SYNTHETIC_WRITE_FAILED",
		"PLAYER_SCAN_SYNTHETIC_READ_FAILED",
	} {
		if strings.HasPrefix(code, prefix+":") {
			return errors.New("LASTWAR_" + code)
		}
	}
	switch code {
	case "NATIVE_LOGIN_TEMPLATE_NOT_FOUND":
		return errors.New("LASTWAR_NATIVE_LOGIN_TEMPLATE_NOT_FOUND")
	case "CAPTURE_READ_FAILED", "CAPTURE_PARSE_FAILED":
		return errors.New("LASTWAR_NATIVE_CAPTURE_INVALID")
	case "PLAYER_SCAN_TEMPLATE_NOT_FOUND":
		return errors.New("LASTWAR_PLAYER_SCAN_TEMPLATE_NOT_FOUND")
	case "PLAYER_SCAN_TEMPLATE_UNSAFE":
		return errors.New("LASTWAR_PLAYER_SCAN_TEMPLATE_UNSAFE")
	case "PLAYER_SCAN_INIT_REQUIRED":
		return errors.New("LASTWAR_PLAYER_SCAN_INIT_REQUIRED")
	case "PLAYER_SCAN_QUERY_REPLACEMENT_FAILED":
		return errors.New("LASTWAR_PLAYER_SCAN_QUERY_REPLACEMENT_FAILED")
	case "PLAYER_SCAN_ENCODE_FAILED", "PLAYER_SCAN_FRAME_FAILED":
		return errors.New("LASTWAR_PLAYER_SCAN_ENCODE_FAILED")
	case "PLAYER_SCAN_WRITE_FAILED":
		return errors.New("LASTWAR_PLAYER_SCAN_SEND_FAILED")
	case "PLAYER_SCAN_READ_FAILED":
		return errors.New("LASTWAR_PLAYER_SCAN_READ_FAILED")
	case "PLAYER_SCAN_SERVER_ID_INVALID":
		return errors.New("LASTWAR_PLAYER_SCAN_SERVER_ID_INVALID")
	case "PLAYER_SCAN_SYNTHETIC_ENCODE_FAILED":
		return errors.New("LASTWAR_PLAYER_SCAN_SYNTHETIC_ENCODE_FAILED")
	case "PLAYER_SCAN_SYNTHETIC_DEADLINE_FAILED":
		return errors.New("LASTWAR_PLAYER_SCAN_SYNTHETIC_DEADLINE_FAILED")
	case "DIAL_FAILED":
		return errors.New("LASTWAR_NATIVE_DIAL_FAILED")
	case "LOGIN_WRITE_FAILED":
		return errors.New("LASTWAR_NATIVE_LOGIN_SEND_FAILED")
	case "READ_FAILED":
		return errors.New("LASTWAR_NATIVE_READ_FAILED")
	default:
		return errors.New("LASTWAR_PLAYER_SCAN_FAILED")
	}
}
