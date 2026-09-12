package protocol

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"time"
)

const maxCapturedOutput = 4 << 20

type SessionContext struct {
	IP          string `json:"ip"`
	Port        int    `json:"port"`
	Zone        string `json:"zone"`
	GameUID     string `json:"gameUid"`
	DeviceID    string `json:"deviceId"`
	ShumeiBoxID string `json:"shumeiBoxId"`
	IOSMode     bool   `json:"iosMode"`
	AccessToken string `json:"accessToken,omitempty"`
}

type ExecReadonly struct {
	Bin     string
	Context SessionContext
	Timeout time.Duration
}

func NewFromEnv() Client {
	raw := strings.TrimSpace(os.Getenv("LASTWAR_SESSION_CONTEXT_JSON"))
	if raw == "" {
		return NotConfigured{}
	}
	if native := newNativeTemplateFromEnv(raw); native != nil {
		return native
	}
	bin := strings.TrimSpace(os.Getenv("LASTWAR_CLIENT_BIN"))
	if bin == "" {
		return NotConfigured{}
	}
	var cfg SessionContext
	if err := json.Unmarshal([]byte(raw), &cfg); err != nil {
		return BrokenConfig{Err: fmt.Errorf("LASTWAR_SESSION_CONTEXT_INVALID")}
	}
	if cfg.AccessToken != "" {
		return BrokenConfig{Err: fmt.Errorf("LASTWAR_SESSION_CONTEXT_MUST_NOT_CONTAIN_ACCESS_TOKEN")}
	}
	timeout := 45 * time.Second
	if s := strings.TrimSpace(os.Getenv("LASTWAR_CLIENT_TIMEOUT_SECONDS")); s != "" {
		if n, err := strconv.Atoi(s); err == nil && n >= 10 && n <= 120 {
			timeout = time.Duration(n) * time.Second
		}
	}
	return &ExecReadonly{Bin: bin, Context: cfg, Timeout: timeout}
}

type BrokenConfig struct{ Err error }

func (b BrokenConfig) Authenticate(context.Context, string) (Identity, error) {
	return Identity{}, b.Err
}
func (b BrokenConfig) Snapshot(context.Context, string) (Snapshot, error) { return Snapshot{}, b.Err }
func (b BrokenConfig) ScanPlayer(context.Context, string, string) ([]Player, error) {
	return nil, b.Err
}
func (b BrokenConfig) Mode() string { return "broken-config" }

func (c *ExecReadonly) Mode() string { return "lastwar-client-exec-readonly" }

func (c *ExecReadonly) validate() error {
	if strings.TrimSpace(c.Bin) == "" {
		return errors.New("LASTWAR_CLIENT_BIN_REQUIRED")
	}
	if strings.TrimSpace(c.Context.IP) == "" || c.Context.Port <= 0 || strings.TrimSpace(c.Context.Zone) == "" || strings.TrimSpace(c.Context.GameUID) == "" || strings.TrimSpace(c.Context.DeviceID) == "" {
		return errors.New("LASTWAR_SESSION_CONTEXT_INCOMPLETE")
	}
	return nil
}

func (c *ExecReadonly) Authenticate(ctx context.Context, token string) (Identity, error) {
	snap, err := c.Snapshot(ctx, token)
	if err != nil {
		return Identity{}, err
	}
	if snap.Identity == nil || strings.TrimSpace(snap.Identity.Pseudo) == "" {
		return Identity{}, errors.New("LASTWAR_PSEUDO_NOT_OBSERVED_YET")
	}
	return *snap.Identity, nil
}

func (c *ExecReadonly) ScanPlayer(context.Context, string, string) ([]Player, error) {
	return nil, errors.New("LASTWAR_MAP_SCAN_NOT_IMPLEMENTED")
}

func (c *ExecReadonly) Snapshot(parent context.Context, token string) (Snapshot, error) {
	if err := c.validate(); err != nil {
		return Snapshot{}, err
	}
	if len(strings.TrimSpace(token)) < 8 {
		return Snapshot{}, errors.New("GAME_TOKEN_REQUIRED")
	}

	dir, err := os.MkdirTemp("", "wfgg-radar-lastwar-*")
	if err != nil {
		return Snapshot{}, fmt.Errorf("LASTWAR_TEMP_DIR_FAILED")
	}
	defer os.RemoveAll(dir)
	if err := os.Chmod(dir, 0700); err != nil {
		return Snapshot{}, fmt.Errorf("LASTWAR_TEMP_DIR_PERMISSIONS_FAILED")
	}

	cfg := c.Context
	cfg.AccessToken = token
	configPath := filepath.Join(dir, "session.json")
	data, _ := json.MarshalIndent(cfg, "", "  ")
	if err := os.WriteFile(configPath, data, 0600); err != nil {
		return Snapshot{}, fmt.Errorf("LASTWAR_SESSION_WRITE_FAILED")
	}

	timeout := c.Timeout
	if timeout <= 0 {
		timeout = 45 * time.Second
	}
	timeoutCtx, cancel := context.WithTimeout(parent, timeout)
	defer cancel()
	// Strictly READONLY: no -collect and no -interactive. The reference client
	// only reconnects, receives init, prints owned-building state, then exits.
	cmd := exec.CommandContext(timeoutCtx, c.Bin, "-config", configPath, "-list-buildings", "-log-level", "info")
	cmd.Env = childEnv(dir)
	var stdout, stderr limitedBuffer
	stdout.N, stderr.N = maxCapturedOutput, maxCapturedOutput
	cmd.Stdout, cmd.Stderr = &stdout, &stderr
	runErr := cmd.Run()
	if timeoutCtx.Err() != nil {
		return Snapshot{}, errors.New("LASTWAR_READONLY_PROBE_TIMEOUT")
	}
	if runErr != nil {
		var exitErr *exec.ExitError
		if errors.As(runErr, &exitErr) && exitErr.ExitCode() == 2 {
			return Snapshot{}, errors.New("LASTWAR_AUTH_REJECTED")
		}
		return Snapshot{}, errors.New("LASTWAR_READONLY_PROBE_FAILED")
	}

	// The reference client persists serverInfo redirects into the config. We read
	// that final config back but NEVER return or log its access token.
	finalCfg := cfg
	if updated, readErr := os.ReadFile(configPath); readErr == nil {
		var parsed SessionContext
		if json.Unmarshal(updated, &parsed) == nil {
			finalCfg = parsed
		}
	}

	transcript := append(append([]byte{}, stdout.Bytes()...), stderr.Bytes()...)
	sum := sha256.Sum256(transcript)
	observedAt := time.Now().UTC().Format(time.RFC3339Nano)
	serverID := serverIDFromZone(finalCfg.Zone)
	observations := []Observation{
		{Path: "identity.gameUid", Value: finalCfg.GameUID, Source: "login.accepted/session-config", Status: "OBSERVED", ObservedAt: observedAt},
		{Path: "session.zone", Value: finalCfg.Zone, Source: "login.accepted/session-config", Status: "OBSERVED", ObservedAt: observedAt},
		{Path: "session.serverId", Value: serverID, Source: "login.accepted/session-config", Status: "OBSERVED", ObservedAt: observedAt},
		{Path: "session.resolvedAddress", Value: netAddress(finalCfg.IP, finalCfg.Port), Source: "login.accepted/session-config", Status: "OBSERVED", ObservedAt: observedAt},
	}
	pseudo, extra := safeStructuredObservations(stderr.Bytes(), observedAt)
	observations = append(observations, extra...)

	var identity *Identity
	if pseudo != "" {
		identity = &Identity{GameUID: finalCfg.GameUID, Pseudo: pseudo, ServerID: serverID, ZoneID: finalCfg.Zone}
	}
	return Snapshot{
		Identity: identity,
		Session: SessionMeta{
			ZoneID:           finalCfg.Zone,
			ServerID:         serverID,
			ResolvedAddress:  netAddress(finalCfg.IP, finalCfg.Port),
			Redirected:       finalCfg.Zone != c.Context.Zone || finalCfg.IP != c.Context.IP || finalCfg.Port != c.Context.Port,
			TranscriptSHA256: hex.EncodeToString(sum[:]),
		},
		Observations: observations,
		Readonly:     true,
		Source:       "lastwar-client/apache-2.0/exec-readonly",
	}, nil
}

func serverIDFromZone(zone string) string {
	if strings.HasPrefix(zone, "APS") && len(zone) > 3 {
		return zone[3:]
	}
	return zone
}

func netAddress(ip string, port int) string {
	return strings.TrimSpace(strings.Split(ip, "|")[0]) + ":" + strconv.Itoa(port)
}

func childEnv(home string) []string {
	out := make([]string, 0, len(os.Environ())+1)
	for _, item := range os.Environ() {
		key := item
		if i := strings.IndexByte(item, '='); i >= 0 {
			key = item[:i]
		}
		upper := strings.ToUpper(key)
		if upper == "HOME" || strings.HasPrefix(upper, "LWDEBUG_") || strings.HasPrefix(upper, "LASTWAR_SESSION_CONTEXT") || strings.HasPrefix(upper, "RADAR_CONNECTOR_") {
			continue
		}
		out = append(out, item)
	}
	return append(out, "HOME="+home)
}

var sensitiveKeys = map[string]bool{
	"token": true, "accesstoken": true, "access_tok": true, "at": true, "rt": true,
	"shumeiboxid": true, "deviceid": true, "airkey": true, "securitycode": true,
	"loginkey": true, "password": true, "pw": true,
}
var pseudoKeys = map[string]bool{"pseudo": true, "nickname": true, "nick": true, "playername": true, "username": true, "user_name": true}

func safeStructuredObservations(data []byte, observedAt string) (string, []Observation) {
	var pseudo string
	out := make([]Observation, 0, 32)
	lines := bytes.Split(data, []byte{'\n'})
	for _, line := range lines {
		line = bytes.TrimSpace(line)
		if len(line) == 0 || line[0] != '{' {
			continue
		}
		var obj map[string]any
		if json.Unmarshal(line, &obj) != nil {
			continue
		}
		msg, _ := obj["msg"].(string)
		walkSafe(obj, "runtime", msg, observedAt, &pseudo, &out, 0)
		if len(out) >= 128 {
			break
		}
	}
	return pseudo, out
}

func walkSafe(v any, path, source, observedAt string, pseudo *string, out *[]Observation, depth int) {
	if depth > 5 || len(*out) >= 128 {
		return
	}
	switch t := v.(type) {
	case map[string]any:
		for k, value := range t {
			lk := strings.ToLower(k)
			if sensitiveKeys[lk] || strings.Contains(lk, "token") || strings.Contains(lk, "secret") || strings.Contains(lk, "shumei") || strings.Contains(lk, "device") {
				continue
			}
			next := path + "." + k
			if pseudoKeys[lk] {
				if s, ok := value.(string); ok && plausiblePseudo(s) && *pseudo == "" {
					*pseudo = strings.TrimSpace(s)
				}
			}
			walkSafe(value, next, source, observedAt, pseudo, out, depth+1)
		}
	case []any:
		// Arrays can be huge; only traverse a small prefix for schema discovery.
		for i, value := range t {
			if i >= 8 {
				break
			}
			walkSafe(value, path+"["+strconv.Itoa(i)+"]", source, observedAt, pseudo, out, depth+1)
		}
	case string, float64, bool, nil:
		if path == "runtime.time" || path == "runtime.level" || path == "runtime.msg" {
			return
		}
		*out = append(*out, Observation{Path: path, Value: t, Source: "runtime-log/" + source, Status: "OBSERVED", ObservedAt: observedAt})
	}
}

func plausiblePseudo(s string) bool {
	s = strings.TrimSpace(s)
	return len(s) >= 2 && len(s) <= 64 && !strings.ContainsAny(s, "\r\n\t")
}

type limitedBuffer struct {
	bytes.Buffer
	N int
}

func (b *limitedBuffer) Write(p []byte) (int, error) {
	original := len(p)
	if b.N <= 0 {
		return original, nil
	}
	if len(p) > b.N {
		p = p[:b.N]
	}
	n, _ := b.Buffer.Write(p)
	b.N -= n
	return original, nil
}

var _ io.Writer = (*limitedBuffer)(nil)
