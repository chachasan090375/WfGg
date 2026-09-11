package protocol

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"time"
)

type NativeTemplateReadonly struct {
	Bin         string
	CapturePath string
	ScanSeed    string
	Context     SessionContext
	Timeout     time.Duration
}

type nativeTemplateReport struct {
	OK                bool     `json:"ok"`
	Mode              string   `json:"mode"`
	LoginResponse     string   `json:"loginResponse"`
	InitReceived      bool     `json:"initReceived"`
	NativeFields      int      `json:"nativeFields"`
	CopiedNative      int      `json:"copiedNative"`
	FreshDynamic      int      `json:"freshDynamic"`
	Zone              string   `json:"zone"`
	ServerID          string   `json:"serverId"`
	ResolvedAddress   string   `json:"resolvedAddress"`
	TopFields         int      `json:"topFields"`
	Heroes            int      `json:"heroes"`
	Buildings         int      `json:"buildings"`
	Science           int      `json:"science"`
	Pseudo            string   `json:"pseudo"`
	InitTopKeys       []string `json:"initTopKeys"`
	ScanTemplateFound bool     `json:"scanTemplateFound"`
	ScanCommand       string   `json:"scanCommand"`
	ScanPerformed     bool     `json:"scanPerformed"`
	Players           []Player `json:"players"`
	ErrorCode         any      `json:"errorCode"`
}

func (c *NativeTemplateReadonly) Mode() string { return "native-template-readonly-v2" }

func (c *NativeTemplateReadonly) validate() error {
	if strings.TrimSpace(c.Bin) == "" {
		return errors.New("LASTWAR_NATIVE_TEMPLATE_BIN_REQUIRED")
	}
	if strings.TrimSpace(c.CapturePath) == "" {
		return errors.New("LASTWAR_NATIVE_CAPTURE_REQUIRED")
	}
	if _, err := os.Stat(c.CapturePath); err != nil {
		return errors.New("LASTWAR_NATIVE_CAPTURE_UNREADABLE")
	}
	if strings.TrimSpace(c.Context.Zone) == "" || strings.TrimSpace(c.Context.GameUID) == "" || strings.TrimSpace(c.Context.DeviceID) == "" || strings.TrimSpace(c.Context.ShumeiBoxID) == "" {
		return errors.New("LASTWAR_SESSION_CONTEXT_INCOMPLETE")
	}
	return nil
}

func (c *NativeTemplateReadonly) Authenticate(ctx context.Context, token string) (Identity, error) {
	snap, err := c.Snapshot(ctx, token)
	if err != nil {
		return Identity{}, err
	}
	if snap.Identity == nil || strings.TrimSpace(snap.Identity.Pseudo) == "" {
		return Identity{}, errors.New("LASTWAR_PSEUDO_NOT_OBSERVED_YET")
	}
	return *snap.Identity, nil
}

func (c *NativeTemplateReadonly) ScanPlayer(parent context.Context, token, query string) ([]Player, error) {
	if err := c.validate(); err != nil {
		return nil, err
	}
	token = strings.TrimSpace(token)
	query = strings.TrimSpace(query)
	if len(token) < 8 {
		return nil, errors.New("GAME_TOKEN_REQUIRED")
	}
	if query == "" || len(query) > 128 {
		return nil, errors.New("PLAYER_QUERY_REQUIRED")
	}

	dir, err := os.MkdirTemp("", "wfgg-radar-native-scan-*")
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
	cmd.Env = append(childEnv(dir), "LASTWAR_NATIVE_SCAN_SEED="+c.ScanSeed)
	var stdout, stderr limitedBuffer
	stdout.N, stderr.N = 1<<20, 64<<10
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

func (c *NativeTemplateReadonly) Snapshot(parent context.Context, token string) (Snapshot, error) {
	if err := c.validate(); err != nil {
		return Snapshot{}, err
	}
	token = strings.TrimSpace(token)
	if len(token) < 8 {
		return Snapshot{}, errors.New("GAME_TOKEN_REQUIRED")
	}

	dir, err := os.MkdirTemp("", "wfgg-radar-native-template-*")
	if err != nil {
		return Snapshot{}, errors.New("LASTWAR_TEMP_DIR_FAILED")
	}
	defer os.RemoveAll(dir)
	if err := os.Chmod(dir, 0700); err != nil {
		return Snapshot{}, errors.New("LASTWAR_TEMP_DIR_PERMISSIONS_FAILED")
	}

	cfg := c.Context
	cfg.AccessToken = token
	sessionPath := filepath.Join(dir, "session.json")
	raw, err := json.Marshal(cfg)
	if err != nil {
		return Snapshot{}, errors.New("LASTWAR_SESSION_JSON_FAILED")
	}
	if err := os.WriteFile(sessionPath, raw, 0600); err != nil {
		return Snapshot{}, errors.New("LASTWAR_SESSION_WRITE_FAILED")
	}

	timeout := c.Timeout
	if timeout <= 0 {
		timeout = 45 * time.Second
	}
	ctx, cancel := context.WithTimeout(parent, timeout)
	defer cancel()

	cmd := exec.CommandContext(ctx, c.Bin, c.CapturePath, sessionPath)
	cmd.Env = childEnv(dir)
	var stdout, stderr limitedBuffer
	stdout.N, stderr.N = 1<<20, 64<<10
	cmd.Stdout, cmd.Stderr = &stdout, &stderr
	runErr := cmd.Run()
	if ctx.Err() != nil {
		return Snapshot{}, errors.New("LASTWAR_NATIVE_TEMPLATE_TIMEOUT")
	}

	var rep nativeTemplateReport
	if err := json.Unmarshal(stdout.Bytes(), &rep); err != nil {
		if runErr != nil {
			return Snapshot{}, errors.New("LASTWAR_NATIVE_TEMPLATE_FAILED")
		}
		return Snapshot{}, errors.New("LASTWAR_NATIVE_TEMPLATE_REPORT_INVALID")
	}

	if runErr != nil {
		if rep.LoginResponse == "REJECTED" {
			return Snapshot{}, errors.New("LASTWAR_AUTH_REJECTED")
		}
		switch rep.LoginResponse {
		case "NATIVE_LOGIN_TEMPLATE_NOT_FOUND":
			return Snapshot{}, errors.New("LASTWAR_NATIVE_LOGIN_TEMPLATE_NOT_FOUND")
		case "CAPTURE_READ_FAILED", "CAPTURE_PARSE_FAILED":
			return Snapshot{}, errors.New("LASTWAR_NATIVE_CAPTURE_INVALID")
		case "DIAL_FAILED":
			return Snapshot{}, errors.New("LASTWAR_NATIVE_DIAL_FAILED")
		case "LOGIN_WRITE_FAILED":
			return Snapshot{}, errors.New("LASTWAR_NATIVE_LOGIN_SEND_FAILED")
		case "READ_FAILED":
			return Snapshot{}, errors.New("LASTWAR_NATIVE_READ_FAILED")
		default:
			return Snapshot{}, errors.New("LASTWAR_NATIVE_TEMPLATE_FAILED")
		}
	}
	if rep.LoginResponse != "OK" {
		return Snapshot{}, errors.New("LASTWAR_NATIVE_LOGIN_NOT_CONFIRMED")
	}

	observedAt := time.Now().UTC().Format(time.RFC3339Nano)
	observations := []Observation{
		{Path: "auth.loginResponse", Value: rep.LoginResponse, Source: "native-template/login-response", Status: "OBSERVED", ObservedAt: observedAt},
		{Path: "auth.nativeFields", Value: rep.NativeFields, Source: "native-template/template", Status: "OBSERVED", ObservedAt: observedAt},
		{Path: "auth.copiedNativeFields", Value: rep.CopiedNative, Source: "native-template/template", Status: "OBSERVED", ObservedAt: observedAt},
		{Path: "auth.freshDynamicFields", Value: rep.FreshDynamic, Source: "native-template/template", Status: "OBSERVED", ObservedAt: observedAt},
		{Path: "session.zone", Value: rep.Zone, Source: "native-template/login", Status: "OBSERVED", ObservedAt: observedAt},
		{Path: "session.serverId", Value: rep.ServerID, Source: "native-template/login", Status: "OBSERVED", ObservedAt: observedAt},
		{Path: "session.resolvedAddress", Value: rep.ResolvedAddress, Source: "native-template/capture-endpoint", Status: "OBSERVED", ObservedAt: observedAt},
		{Path: "init.received", Value: rep.InitReceived, Source: "native-template/init", Status: "OBSERVED", ObservedAt: observedAt},
	}
	if rep.InitReceived {
		observations = append(observations,
			Observation{Path: "init.topFields", Value: rep.TopFields, Source: "native-template/init", Status: "OBSERVED", ObservedAt: observedAt},
			Observation{Path: "init.userHero.count", Value: rep.Heroes, Source: "native-template/init", Status: "OBSERVED", ObservedAt: observedAt},
			Observation{Path: "init.building_new.count", Value: rep.Buildings, Source: "native-template/init", Status: "OBSERVED", ObservedAt: observedAt},
			Observation{Path: "init.science_new.count", Value: rep.Science, Source: "native-template/init", Status: "OBSERVED", ObservedAt: observedAt},
		)
		for i, key := range rep.InitTopKeys {
			if i >= 256 {
				break
			}
			observations = append(observations, Observation{Path: "init.topKey[" + strconv.Itoa(i) + "]", Value: key, Source: "native-template/init-schema", Status: "OBSERVED", ObservedAt: observedAt})
		}
	}

	var identity *Identity
	if strings.TrimSpace(rep.Pseudo) != "" {
		identity = &Identity{GameUID: c.Context.GameUID, Pseudo: strings.TrimSpace(rep.Pseudo), ServerID: rep.ServerID, ZoneID: rep.Zone}
		observations = append(observations, Observation{Path: "identity.pseudo", Value: identity.Pseudo, Source: "native-template/init", Status: "OBSERVED", ObservedAt: observedAt})
	}
	observations = append(observations, Observation{Path: "identity.gameUid", Value: c.Context.GameUID, Source: "native-template/session-context", Status: "OBSERVED", ObservedAt: observedAt})

	sum := sha256.Sum256(stdout.Bytes())
	return Snapshot{
		Identity: identity,
		Session: SessionMeta{
			ZoneID:           rep.Zone,
			ServerID:         rep.ServerID,
			ResolvedAddress:  rep.ResolvedAddress,
			Redirected:       false,
			TranscriptSHA256: hex.EncodeToString(sum[:]),
		},
		Observations: observations,
		Readonly:     true,
		Source:       "wfgg/master-v3/phase5-native-template",
	}, nil
}

func newNativeTemplateFromEnv(raw string) Client {
	capture := strings.TrimSpace(os.Getenv("LASTWAR_NATIVE_CAPTURE"))
	if capture == "" {
		return nil
	}
	var cfg SessionContext
	if err := json.Unmarshal([]byte(raw), &cfg); err != nil {
		return BrokenConfig{Err: fmt.Errorf("LASTWAR_SESSION_CONTEXT_INVALID")}
	}
	if cfg.AccessToken != "" {
		return BrokenConfig{Err: fmt.Errorf("LASTWAR_SESSION_CONTEXT_MUST_NOT_CONTAIN_ACCESS_TOKEN")}
	}
	bin := strings.TrimSpace(os.Getenv("LASTWAR_NATIVE_TEMPLATE_BIN"))
	if bin == "" {
		bin = "/radar-native-template"
	}
	timeout := 45 * time.Second
	if s := strings.TrimSpace(os.Getenv("LASTWAR_CLIENT_TIMEOUT_SECONDS")); s != "" {
		if n, err := strconv.Atoi(s); err == nil && n >= 10 && n <= 120 {
			timeout = time.Duration(n) * time.Second
		}
	}
	scanSeed := strings.TrimSpace(os.Getenv("LASTWAR_NATIVE_SCAN_SEED"))
	return &NativeTemplateReadonly{Bin: bin, CapturePath: capture, ScanSeed: scanSeed, Context: cfg, Timeout: timeout}
}
