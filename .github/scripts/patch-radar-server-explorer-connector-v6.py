#!/usr/bin/env python3
from pathlib import Path

ROOT = Path('/tmp/wfgg-radar/connector-go')
PROTO = ROOT / 'internal/protocol/protocol.go'
NATIVE = ROOT / 'internal/protocol/native_template.go'
BATCH = ROOT / 'internal/protocol/server_batch_v6.go'
JOBS = ROOT / 'cmd/radar-connector/collector_jobs.go'


def once(text, old, new, label):
    n = text.count(old)
    if n != 1:
        raise SystemExit(f'{label}: expected 1 match, got {n}')
    return text.replace(old, new, 1)

s = PROTO.read_text(encoding='utf-8')
if 'SERVER_EXPLORER_BATCH_PROTOCOL_V6' not in s:
    anchor = '''type ServerRegionScanner interface {\n\tScanPlayerServerRegion(ctx context.Context, token, query, serverID string, region int) ([]Player, error)\n}\n'''
    add = anchor + '''\n// SERVER_EXPLORER_BATCH_PROTOCOL_V6\ntype ServerProbeResult struct {\n\tServerID        string `json:"serverId"`\n\tAccessible      bool   `json:"accessible"`\n\tPlayersObserved int    `json:"playersObserved"`\n\tDurationMs      int64  `json:"durationMs"`\n\tError           string `json:"error,omitempty"`\n}\n\ntype ServerBatchScanner interface {\n\tProbeServerRegions(ctx context.Context, token string, serverIDs []string) ([]ServerProbeResult, error)\n}\n'''
    s = once(s, anchor, add, 'protocol batch interface')
    PROTO.write_text(s, encoding='utf-8')

s = NATIVE.read_text(encoding='utf-8')
if 'ServerProbe       []ServerProbeResult' not in s:
    anchor = '\tPlayers           []Player `json:"players"`\n\tErrorCode         any      `json:"errorCode"`\n'
    new = '\tPlayers           []Player             `json:"players"`\n\tServerProbe       []ServerProbeResult  `json:"serverProbe"`\n\tErrorCode         any                  `json:"errorCode"`\n'
    s = once(s, anchor, new, 'native report serverProbe')
    NATIVE.write_text(s, encoding='utf-8')

BATCH.write_text(r'''package protocol

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

// SERVER_EXPLORER_BATCH_CONNECTOR_V6
// ProbeServerRegions starts one native helper, therefore one authenticated
// login/INIT, for the whole explicit server list. The native helper itself is
// bounded to 12 serverIds; V5 remains available as a per-server fallback.
func (c *NativeTemplateReadonly) ProbeServerRegions(parent context.Context, token string, serverIDs []string) ([]ServerProbeResult, error) {
    if err := c.validate(); err != nil {
        return nil, err
    }
    token = strings.TrimSpace(token)
    if len(token) < 8 {
        return nil, errors.New("GAME_TOKEN_REQUIRED")
    }
    if len(serverIDs) == 0 || len(serverIDs) > 12 {
        return nil, errors.New("SERVER_EXPLORER_BATCH_SIZE_INVALID")
    }
    clean := make([]string, 0, len(serverIDs))
    seen := map[string]bool{}
    for _, raw := range serverIDs {
        sid := strings.TrimPrefix(strings.TrimSpace(raw), "APS")
        n, err := strconv.Atoi(sid)
        if err != nil || n <= 0 || n > 999999 {
            return nil, errors.New("SERVER_EXPLORER_SERVER_ID_INVALID")
        }
        sid = strconv.Itoa(n)
        if !seen[sid] {
            seen[sid] = true
            clean = append(clean, sid)
        }
    }
    if len(clean) == 0 {
        return nil, errors.New("SERVER_EXPLORER_BATCH_SIZE_INVALID")
    }

    dir, err := os.MkdirTemp("", "wfgg-radar-v6-batch-*")
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
    if timeout < 45*time.Second {
        timeout = 45 * time.Second
    }
    ctx, cancel := context.WithTimeout(parent, timeout)
    defer cancel()

    cmd := exec.CommandContext(ctx, c.Bin, c.CapturePath, sessionPath, "--scan-player", "*")
    cmd.Env = append(childEnv(dir),
        "LASTWAR_NATIVE_SCAN_SEED="+c.ScanSeed,
        "WFGG_SERVER_PROBE=1",
        "WFGG_SERVER_ID_LIST="+strings.Join(clean, ","),
    )
    var stdout, stderr limitedBuffer
    stdout.N, stderr.N = 4<<20, 64<<10
    cmd.Stdout, cmd.Stderr = &stdout, &stderr
    runErr := cmd.Run()
    if ctx.Err() != nil {
        return nil, errors.New("LASTWAR_SERVER_BATCH_TIMEOUT")
    }

    var rep nativeTemplateReport
    if err := json.Unmarshal(stdout.Bytes(), &rep); err != nil {
        return nil, errors.New("LASTWAR_SERVER_BATCH_REPORT_INVALID")
    }
    if runErr != nil || rep.LoginResponse != "OK" || !rep.ScanPerformed {
        return nil, errors.New("LASTWAR_SERVER_BATCH_FAILED")
    }
    if len(rep.ServerProbe) == 0 {
        return nil, errors.New("LASTWAR_SERVER_BATCH_EMPTY")
    }
    return rep.ServerProbe, nil
}
''', encoding='utf-8')

s = JOBS.read_text(encoding='utf-8')
if 'SERVER_EXPLORER_JOB_V6_SINGLE_SESSION' not in s:
    anchor = '''\tscanner, ok := s.game.(protocol.ServerRegionScanner)\n\tif !ok {\n'''
    block = '''\t// SERVER_EXPLORER_JOB_V6_SINGLE_SESSION\n\tif batchScanner, batchOK := s.game.(protocol.ServerBatchScanner); batchOK {\n\t\tradarCollectorJobs.update(jobID, func(j *collectorJob) {\n\t\t\tj.Strategy = "SERVER_EXPLORER_V6_SINGLE_SESSION"\n\t\t\tj.Phase = "SERVER_BATCH_PROBE"\n\t\t\tj.Region = 1\n\t\t\tj.Regions = len(ids)\n\t\t})\n\t\tstarted := time.Now()\n\t\tbatchCtx, cancel := context.WithTimeout(ctx, 45*time.Second)\n\t\trows, batchErr := batchScanner.ProbeServerRegions(batchCtx, token, ids)\n\t\tcancel()\n\t\tif batchErr == nil && len(rows) > 0 {\n\t\t\tresults := make([]map[string]any, 0, len(rows))\n\t\t\taccessible := make([]string, 0, len(rows))\n\t\t\tfor _, row := range rows {\n\t\t\t\tstatus := "FAILED"\n\t\t\t\tif row.Accessible {\n\t\t\t\t\tstatus = "ACCESSIBLE"\n\t\t\t\t\taccessible = append(accessible, row.ServerID)\n\t\t\t\t}\n\t\t\t\titem := map[string]any{\n\t\t\t\t\t"serverId": row.ServerID,\n\t\t\t\t\t"status": status,\n\t\t\t\t\t"playersObserved": row.PlayersObserved,\n\t\t\t\t\t"durationMs": row.DurationMs,\n\t\t\t\t}\n\t\t\t\tif row.Error != "" { item["reason"] = row.Error }\n\t\t\t\tresults = append(results, item)\n\t\t\t\tslog.Info("SERVER_EXPLORER_V6_SENTINEL", "jobId", jobID, "serverId", row.ServerID, "status", status, "players", row.PlayersObserved, "durationMs", row.DurationMs)\n\t\t\t}\n\t\t\tplayer := map[string]any{\n\t\t\t\t"pseudo": "SERVER EXPLORER V6",\n\t\t\t\t"game_uid": "server-explorer-v6",\n\t\t\t\t"server_id": strings.Join(accessible, ","),\n\t\t\t\t"serverProbe": results,\n\t\t\t\t"observed_at": utcNow(),\n\t\t\t}\n\t\t\tcompleteCollectorJob(jobID, player)\n\t\t\tslog.Info("SERVER_EXPLORER_V6_SENTINEL", "jobId", jobID, "stage", "DONE", "tested", len(rows), "accessible", len(accessible), "batchDurationMs", time.Since(started).Milliseconds())\n\t\t\treturn\n\t\t}\n\t\tslog.Info("SERVER_EXPLORER_V6_SENTINEL", "jobId", jobID, "stage", "FALLBACK_V5", "reason", "BATCH_UNAVAILABLE")\n\t}\n\n\tscanner, ok := s.game.(protocol.ServerRegionScanner)\n\tif !ok {\n'''
    s = once(s, anchor, block, 'V6 job batch hook')
    JOBS.write_text(s, encoding='utf-8')

print('SERVER_EXPLORER_CONNECTOR_V6=PATCHED')
print('SERVER_EXPLORER_V6_BATCH_ADAPTER=READY')
print('SERVER_EXPLORER_V5_FALLBACK=PRESERVED')
