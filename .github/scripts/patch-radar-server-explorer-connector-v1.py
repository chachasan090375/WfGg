#!/usr/bin/env python3
from pathlib import Path

ROOT = Path('/tmp/wfgg-radar/connector-go')
PROTO = ROOT / 'internal/protocol/protocol.go'
REGION = ROOT / 'internal/protocol/region_scan.go'
JOBS = ROOT / 'cmd/radar-connector/collector_jobs.go'

# --- protocol interface -----------------------------------------------------
s = PROTO.read_text(encoding='utf-8')
if 'SERVER_EXPLORER_PROTOCOL_V1' not in s:
    anchor = '''type ProfileScanner interface {\n\tScanProfiles(ctx context.Context, token string, uids []string) ([]Player, error)\n}\n'''
    add = '''type ProfileScanner interface {\n\tScanProfiles(ctx context.Context, token string, uids []string) ([]Player, error)\n}\n\n// SERVER_EXPLORER_PROTOCOL_V1\n// ServerRegionScanner performs a bounded READONLY world.get.block probe against\n// an explicit serverId. It never changes the authenticated account server.\ntype ServerRegionScanner interface {\n\tScanPlayerServerRegion(ctx context.Context, token, query, serverID string, region int) ([]Player, error)\n}\n'''
    if s.count(anchor) != 1:
        raise SystemExit('SERVER_EXPLORER_PROTOCOL_ANCHOR_MISSING')
    s = s.replace(anchor, add, 1)
    PROTO.write_text(s, encoding='utf-8')

# --- native process wrapper -------------------------------------------------
s = REGION.read_text(encoding='utf-8')
if 'SERVER_EXPLORER_CONNECTOR_V1' not in s:
    anchor = '''func (c *NativeTemplateReadonly) ScanPlayerRegion(parent context.Context, token, query string, region int) ([]Player, error) {\n\tif region < 0 || region > 8 {\n\t\treturn nil, errors.New("COLLECTOR_REGION_INVALID")\n\t}\n\treturn c.scanNativeV4(parent, token, query, &region)\n}\n'''
    add = anchor + '''\n// SERVER_EXPLORER_CONNECTOR_V1\nfunc (c *NativeTemplateReadonly) ScanPlayerServerRegion(parent context.Context, token, query, serverID string, region int) ([]Player, error) {\n\tif region < 0 || region > 8 {\n\t\treturn nil, errors.New("COLLECTOR_REGION_INVALID")\n\t}\n\tserverID = strings.TrimPrefix(strings.TrimSpace(serverID), "APS")\n\tn, err := strconv.Atoi(serverID)\n\tif err != nil || n <= 0 || n > 999999 {\n\t\treturn nil, errors.New("COLLECTOR_SERVER_ID_INVALID")\n\t}\n\treturn c.scanNativeV4Server(parent, token, query, &region, serverID)\n}\n'''
    if s.count(anchor) != 1:
        raise SystemExit('SERVER_EXPLORER_REGION_METHOD_ANCHOR_MISSING')
    s = s.replace(anchor, add, 1)

    old_decl = '''func (c *NativeTemplateReadonly) scanNativeV4(parent context.Context, token, query string, region *int) ([]Player, error) {\n'''
    new_decl = '''func (c *NativeTemplateReadonly) scanNativeV4(parent context.Context, token, query string, region *int) ([]Player, error) {\n\treturn c.scanNativeV4Server(parent, token, query, region, "")\n}\n\nfunc (c *NativeTemplateReadonly) scanNativeV4Server(parent context.Context, token, query string, region *int, serverIDOverride string) ([]Player, error) {\n'''
    if s.count(old_decl) != 1:
        raise SystemExit('SERVER_EXPLORER_SCAN_DECL_ANCHOR_MISSING')
    s = s.replace(old_decl, new_decl, 1)

    old_env = '''\tif region != nil {\n\t\tenv = append(env, "WFGG_COLLECTOR_ORIGIN_INDEX="+strconv.Itoa(*region))\n\t}\n\tcmd.Env = env\n'''
    new_env = '''\tif region != nil {\n\t\tenv = append(env, "WFGG_COLLECTOR_ORIGIN_INDEX="+strconv.Itoa(*region))\n\t}\n\tif serverIDOverride != "" {\n\t\tenv = append(env, "WFGG_SERVER_ID_OVERRIDE="+serverIDOverride, "WFGG_SERVER_PROBE=1")\n\t}\n\tcmd.Env = env\n'''
    if s.count(old_env) != 1:
        raise SystemExit('SERVER_EXPLORER_ENV_ANCHOR_MISSING')
    s = s.replace(old_env, new_env, 1)
    REGION.write_text(s, encoding='utf-8')

# --- hidden diagnostic route through the existing authenticated Radar search -
s = JOBS.read_text(encoding='utf-8')
if 'SERVER_EXPLORER_JOB_V1' not in s:
    old_start = '''\tradarCollectorJobs.update(jobID, func(j *collectorJob) { j.Status = "RUNNING"; j.Phase = "STARTING" })\n\tsentinelOracle(jobID, "START", 1, "IDENTITY_INDEX_V1", "")\n'''
    new_start = '''\tradarCollectorJobs.update(jobID, func(j *collectorJob) { j.Status = "RUNNING"; j.Phase = "STARTING" })\n\tif strings.HasPrefix(strings.ToLower(strings.TrimSpace(query)), "@servers:") {\n\t\ts.handleServerExplorer(ctx, token, query, jobID)\n\t\treturn\n\t}\n\tsentinelOracle(jobID, "START", 1, "IDENTITY_INDEX_V1", "")\n'''
    if s.count(old_start) != 1:
        raise SystemExit('SERVER_EXPLORER_JOB_START_ANCHOR_MISSING')
    s = s.replace(old_start, new_start, 1)

    anchor = '''// PLAYER_ORACLE_SENTINEL_V1\n'''
    helper = r'''// SERVER_EXPLORER_JOB_V1
// Syntax: @servers:989-995 or @servers:989,991,995 . The list is deliberately
// capped so a diagnostic can never turn into an accidental global sweep.
func parseServerExplorerQuery(query string) ([]string, error) {
	raw := strings.TrimSpace(query)
	if !strings.HasPrefix(strings.ToLower(raw), "@servers:") {
		return nil, errors.New("SERVER_EXPLORER_QUERY_REQUIRED")
	}
	raw = strings.TrimSpace(raw[len("@servers:"):])
	if raw == "" {
		return nil, errors.New("SERVER_EXPLORER_QUERY_INVALID")
	}
	out := []string{}
	seen := map[int]bool{}
	add := func(n int) error {
		if n <= 0 || n > 999999 {
			return errors.New("SERVER_EXPLORER_SERVER_ID_INVALID")
		}
		if !seen[n] {
			seen[n] = true
			out = append(out, strconv.Itoa(n))
		}
		if len(out) > 12 {
			return errors.New("SERVER_EXPLORER_TOO_MANY_SERVERS")
		}
		return nil
	}
	for _, part := range strings.Split(raw, ",") {
		part = strings.TrimSpace(part)
		if part == "" { continue }
		if strings.Count(part, "-") == 1 {
			bits := strings.SplitN(part, "-", 2)
			a, errA := strconv.Atoi(strings.TrimSpace(bits[0]))
			b, errB := strconv.Atoi(strings.TrimSpace(bits[1]))
			if errA != nil || errB != nil || a <= 0 || b < a || b-a > 11 {
				return nil, errors.New("SERVER_EXPLORER_RANGE_INVALID")
			}
			for n := a; n <= b; n++ { if err := add(n); err != nil { return nil, err } }
			continue
		}
		n, err := strconv.Atoi(part)
		if err != nil { return nil, errors.New("SERVER_EXPLORER_SERVER_ID_INVALID") }
		if err := add(n); err != nil { return nil, err }
	}
	if len(out) == 0 { return nil, errors.New("SERVER_EXPLORER_QUERY_INVALID") }
	return out, nil
}

func (s *server) handleServerExplorer(ctx context.Context, token, query, jobID string) {
	ids, err := parseServerExplorerQuery(query)
	if err != nil {
		radarCollectorJobs.update(jobID, func(j *collectorJob) {
			j.Status = "FAILED"; j.Phase = "SERVER_EXPLORER_FAILED"; j.Error = err.Error(); j.FinishedAt = utcNow()
		})
		slog.Info("SERVER_EXPLORER_SENTINEL", "jobId", jobID, "stage", "QUERY_REJECTED", "reason", err.Error())
		return
	}
	scanner, ok := s.game.(protocol.ServerRegionScanner)
	if !ok {
		radarCollectorJobs.update(jobID, func(j *collectorJob) {
			j.Status = "FAILED"; j.Phase = "SERVER_EXPLORER_FAILED"; j.Error = "SERVER_REGION_SCANNER_UNAVAILABLE"; j.FinishedAt = utcNow()
		})
		return
	}

	radarCollectorJobs.update(jobID, func(j *collectorJob) {
		j.Strategy = "SERVER_EXPLORER_V1"; j.Phase = "SERVER_PROBE"; j.Region = 1; j.Regions = len(ids)
	})
	results := make([]map[string]any, 0, len(ids))
	accessible := make([]string, 0, len(ids))
	for i, sid := range ids {
		radarCollectorJobs.update(jobID, func(j *collectorJob) { j.Region = i + 1 })
		probeCtx, cancel := context.WithTimeout(ctx, 5*time.Second)
		players, probeErr := scanner.ScanPlayerServerRegion(probeCtx, token, "*", sid, 0)
		cancel()
		row := map[string]any{"serverId": sid, "playersObserved": len(players)}
		if probeErr != nil {
			row["status"] = "FAILED"
			row["reason"] = probeErr.Error()
			slog.Info("SERVER_EXPLORER_SENTINEL", "jobId", jobID, "serverId", sid, "status", "FAILED", "players", 0, "reason", probeErr.Error())
		} else {
			row["status"] = "ACCESSIBLE"
			accessible = append(accessible, sid)
			slog.Info("SERVER_EXPLORER_SENTINEL", "jobId", jobID, "serverId", sid, "status", "ACCESSIBLE", "players", len(players))
		}
		results = append(results, row)
	}
	player := map[string]any{
		"pseudo": "SERVER EXPLORER",
		"game_uid": "server-explorer-v1",
		"server_id": strings.Join(accessible, ","),
		"serverProbe": results,
		"observed_at": utcNow(),
	}
	completeCollectorJob(jobID, player)
	slog.Info("SERVER_EXPLORER_SENTINEL", "jobId", jobID, "stage", "DONE", "tested", len(ids), "accessible", len(accessible))
}

'''
    if s.count(anchor) != 1:
        raise SystemExit('SERVER_EXPLORER_HELPER_ANCHOR_MISSING')
    s = s.replace(anchor, helper + anchor, 1)
    JOBS.write_text(s, encoding='utf-8')

print('SERVER_EXPLORER_CONNECTOR=PATCHED')
print('SERVER_EXPLORER_QUERY=@servers:<range-or-list>')
print('SERVER_EXPLORER_MAX_SERVERS=12')
print('SERVER_EXPLORER_PER_SERVER_BUDGET_SECONDS=5')
