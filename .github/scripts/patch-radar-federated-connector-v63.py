#!/usr/bin/env python3
from pathlib import Path

ROOT = Path('/tmp/wfgg-radar/connector-go')
PROTO = ROOT / 'internal/protocol/protocol.go'
REGION = ROOT / 'internal/protocol/region_scan.go'
JOBS = ROOT / 'cmd/radar-connector/collector_jobs.go'


def once(text: str, old: str, new: str, label: str) -> str:
    n = text.count(old)
    if n != 1:
        raise SystemExit(f'{label}: expected 1 match, got {n}')
    return text.replace(old, new, 1)

# ---------------------------------------------------------------------------
# Protocol contract: a full federated map region is deliberately separate from
# Server Explorer's cheap foreign-server probe contract.
# ---------------------------------------------------------------------------
s = PROTO.read_text(encoding='utf-8')
if 'FEDERATED_COLLECTOR_PROTOCOL_V63' not in s:
    anchor = '''type ServerRegionScanner interface {\n\tScanPlayerServerRegion(ctx context.Context, token, query, serverID string, region int) ([]Player, error)\n}\n'''
    add = anchor + '''\n// FEDERATED_COLLECTOR_PROTOCOL_V63\n// FederatedRegionScanner performs a full READONLY map-region scan against an\n// explicit foreign serverId. It never changes the authenticated account server.\ntype FederatedRegionScanner interface {\n\tScanPlayerFederatedServerRegion(ctx context.Context, token, query, serverID string, region int) ([]Player, error)\n}\n'''
    s = once(s, anchor, add, 'federated protocol interface')
    PROTO.write_text(s, encoding='utf-8')

# ---------------------------------------------------------------------------
# Native adapter: preserve the existing probe method exactly semantically, but
# factor the shared executor so Federated Collector can omit WFGG_SERVER_PROBE
# and request one explicit origin with MAP_ONLY enabled.
# ---------------------------------------------------------------------------
s = REGION.read_text(encoding='utf-8')
if 'FEDERATED_COLLECTOR_CONNECTOR_V63' not in s:
    old = '''func (c *NativeTemplateReadonly) ScanPlayerServerRegion(parent context.Context, token, query, serverID string, region int) ([]Player, error) {\n\tif region < 0 || region > 8 {\n\t\treturn nil, errors.New("COLLECTOR_REGION_INVALID")\n\t}\n\tserverID = strings.TrimPrefix(strings.TrimSpace(serverID), "APS")\n\tn, err := strconv.Atoi(serverID)\n\tif err != nil || n <= 0 || n > 999999 {\n\t\treturn nil, errors.New("COLLECTOR_SERVER_ID_INVALID")\n\t}\n\treturn c.scanNativeV4Server(parent, token, query, &region, serverID)\n}\n'''
    new = '''func (c *NativeTemplateReadonly) ScanPlayerServerRegion(parent context.Context, token, query, serverID string, region int) ([]Player, error) {\n\tif region < 0 || region > 8 {\n\t\treturn nil, errors.New("COLLECTOR_REGION_INVALID")\n\t}\n\tserverID = strings.TrimPrefix(strings.TrimSpace(serverID), "APS")\n\tn, err := strconv.Atoi(serverID)\n\tif err != nil || n <= 0 || n > 999999 {\n\t\treturn nil, errors.New("COLLECTOR_SERVER_ID_INVALID")\n\t}\n\treturn c.scanNativeV4ServerMode(parent, token, query, &region, serverID, true, false)\n}\n\n// FEDERATED_COLLECTOR_CONNECTOR_V63\nfunc (c *NativeTemplateReadonly) ScanPlayerFederatedServerRegion(parent context.Context, token, query, serverID string, region int) ([]Player, error) {\n\tif region < 0 || region > 8 {\n\t\treturn nil, errors.New("FEDERATED_COLLECTOR_REGION_INVALID")\n\t}\n\tserverID = strings.TrimPrefix(strings.TrimSpace(serverID), "APS")\n\tn, err := strconv.Atoi(serverID)\n\tif err != nil || n <= 0 || n > 999999 {\n\t\treturn nil, errors.New("FEDERATED_COLLECTOR_SERVER_ID_INVALID")\n\t}\n\treturn c.scanNativeV4ServerMode(parent, token, query, &region, serverID, false, true)\n}\n'''
    s = once(s, old, new, 'federated server region method')

    old = '''func (c *NativeTemplateReadonly) scanNativeV4(parent context.Context, token, query string, region *int) ([]Player, error) {\n\treturn c.scanNativeV4Server(parent, token, query, region, "")\n}\n\nfunc (c *NativeTemplateReadonly) scanNativeV4Server(parent context.Context, token, query string, region *int, serverIDOverride string) ([]Player, error) {\n'''
    new = '''func (c *NativeTemplateReadonly) scanNativeV4(parent context.Context, token, query string, region *int) ([]Player, error) {\n\treturn c.scanNativeV4ServerMode(parent, token, query, region, "", false, false)\n}\n\nfunc (c *NativeTemplateReadonly) scanNativeV4ServerMode(parent context.Context, token, query string, region *int, serverIDOverride string, probeMode bool, federatedMapOnly bool) ([]Player, error) {\n'''
    s = once(s, old, new, 'federated scan executor signature')

    old = '''\tif serverIDOverride != "" {\n\t\tenv = append(env, "WFGG_SERVER_ID_OVERRIDE="+serverIDOverride, "WFGG_SERVER_PROBE=1")\n\t}\n\tcmd.Env = env\n'''
    new = '''\tif serverIDOverride != "" {\n\t\tenv = append(env, "WFGG_SERVER_ID_OVERRIDE="+serverIDOverride)\n\t\tif probeMode {\n\t\t\tenv = append(env, "WFGG_SERVER_PROBE=1")\n\t\t}\n\t\tif federatedMapOnly {\n\t\t\tenv = append(env, "WFGG_FEDERATED_MAP_ONLY=1")\n\t\t\tif region != nil {\n\t\t\t\tenv = append(env, "WFGG_FEDERATED_ORIGIN_INDEX="+strconv.Itoa(*region))\n\t\t\t}\n\t\t}\n\t}\n\tcmd.Env = env\n'''
    s = once(s, old, new, 'federated native environment')
    REGION.write_text(s, encoding='utf-8')

# ---------------------------------------------------------------------------
# Hidden canary route. It intentionally scans ONE explicit server only. This is
# not yet the 1..1008 orchestrator: first prove 9/9 regions, decoded identities,
# server attribution, and Collector ingestion on server 991.
# ---------------------------------------------------------------------------
s = JOBS.read_text(encoding='utf-8')
if 'FEDERATED_COLLECTOR_CANARY_V63' not in s:
    route_anchor = '''\t// SERVER_EXPLORER_DISCOVERY_V62_ROUTE\n\tif strings.HasPrefix(strings.ToLower(strings.TrimSpace(query)), "@discover:auto") {\n'''
    route = '''\t// FEDERATED_COLLECTOR_CANARY_V63\n\tif strings.HasPrefix(strings.ToLower(strings.TrimSpace(query)), "@federated:") {\n\t\ts.handleFederatedCollectorCanaryV63(ctx, token, query, jobID)\n\t\treturn\n\t}\n\n'''
    if s.count(route_anchor) != 1:
        raise SystemExit(f'federated route anchor: expected 1 match, got {s.count(route_anchor)}')
    s = s.replace(route_anchor, route + route_anchor, 1)

    helper_anchor = 'var errPlayerNotFound = errors.New("COLLECTOR_PLAYER_NOT_FOUND")\n'
    helper = r'''// FEDERATED_COLLECTOR_CANARY_V63
func parseFederatedCollectorCanaryV63(query string) (string, error) {
	raw := strings.TrimSpace(query)
	if !strings.HasPrefix(strings.ToLower(raw), "@federated:") {
		return "", errors.New("FEDERATED_COLLECTOR_QUERY_REQUIRED")
	}
	part := strings.TrimSpace(raw[len("@federated:"):])
	n, err := strconv.Atoi(strings.TrimPrefix(part, "APS"))
	if err != nil || n <= 0 || n > 999999 {
		return "", errors.New("FEDERATED_COLLECTOR_SERVER_ID_INVALID")
	}
	return strconv.Itoa(n), nil
}

func (s *server) handleFederatedCollectorCanaryV63(ctx context.Context, token, query, jobID string) {
	serverID, err := parseFederatedCollectorCanaryV63(query)
	if err != nil {
		radarCollectorJobs.update(jobID, func(j *collectorJob) {
			j.Status = "FAILED"
			j.Phase = "FEDERATED_V63_FAILED"
			j.Error = err.Error()
			j.FinishedAt = utcNow()
		})
		return
	}

	scanner, ok := s.game.(protocol.FederatedRegionScanner)
	if !ok {
		radarCollectorJobs.update(jobID, func(j *collectorJob) {
			j.Status = "FAILED"
			j.Phase = "FEDERATED_V63_FAILED"
			j.Error = "FEDERATED_REGION_SCANNER_UNAVAILABLE"
			j.FinishedAt = utcNow()
		})
		return
	}

	radarCollectorJobs.update(jobID, func(j *collectorJob) {
		j.Strategy = "FEDERATED_COLLECTOR_V63_CANARY"
		j.Phase = "FEDERATED_MAP"
		j.Region = 0
		j.Regions = 9
	})
	slog.Info("FEDERATED_COLLECTOR_V63_SENTINEL", "jobId", jobID, "stage", "START", "serverId", serverID, "regions", 9)

	unique := map[string]protocol.Player{}
	totalDecoded := 0
	totalAccepted := 0
	regionsOK := 0

	for region := 0; region < 9; region++ {
		started := time.Now()
		radarCollectorJobs.update(jobID, func(j *collectorJob) {
			j.Phase = "FEDERATED_MAP"
			j.Region = region + 1
		})
		slog.Info("FEDERATED_COLLECTOR_V63_SENTINEL", "jobId", jobID, "stage", "REGION_START", "serverId", serverID, "region", region)

		regionCtx, cancel := context.WithTimeout(context.Background(), 20*time.Second)
		players, scanErr := scanner.ScanPlayerFederatedServerRegion(regionCtx, token, "@all", serverID, region)
		cancel()
		if scanErr != nil {
			slog.Error("FEDERATED_COLLECTOR_V63_SENTINEL", "jobId", jobID, "stage", "REGION_ERROR", "serverId", serverID, "region", region, "error", scanErr.Error(), "durationMs", time.Since(started).Milliseconds())
			radarCollectorJobs.update(jobID, func(j *collectorJob) {
				j.Status = "FAILED"
				j.Phase = "FEDERATED_V63_FAILED"
				j.Error = "FEDERATED_REGION_SCAN_FAILED"
				j.FinishedAt = utcNow()
			})
			return
		}

		regionsOK++
		totalDecoded += len(players)
		for _, p := range players {
			uid := strings.TrimSpace(p.GameUID)
			if uid == "" || strings.TrimSpace(p.Pseudo) == "" {
				continue
			}
			if p.ServerID == "" {
				p.ServerID = serverID
			}
			unique[uid] = p
		}

		accepted, ingestErr := collectorIngest(context.Background(), players, 0)
		if ingestErr != nil {
			slog.Error("FEDERATED_COLLECTOR_V63_SENTINEL", "jobId", jobID, "stage", "INGEST_ERROR", "serverId", serverID, "region", region, "error", ingestErr.Error())
			radarCollectorJobs.update(jobID, func(j *collectorJob) {
				j.Status = "FAILED"
				j.Phase = "FEDERATED_V63_FAILED"
				j.Error = "FEDERATED_INGEST_FAILED"
				j.FinishedAt = utcNow()
			})
			return
		}
		totalAccepted += accepted
		radarCollectorJobs.update(jobID, func(j *collectorJob) {
			j.PlayersSeen = totalDecoded
			j.Enriched = totalAccepted
		})
		slog.Info("FEDERATED_COLLECTOR_V63_SENTINEL", "jobId", jobID, "stage", "REGION_DONE", "serverId", serverID, "region", region, "decoded", len(players), "accepted", accepted, "unique", len(unique), "durationMs", time.Since(started).Milliseconds())
	}

	sample := make([]map[string]any, 0, 8)
	serverMismatch := 0
	for _, p := range unique {
		if strings.TrimPrefix(strings.TrimSpace(p.ServerID), "APS") != serverID {
			serverMismatch++
		}
		if len(sample) < 8 {
			item := map[string]any{
				"uid": p.GameUID,
				"pseudo": p.Pseudo,
				"serverId": p.ServerID,
			}
			if p.X != nil { item["x"] = *p.X }
			if p.Y != nil { item["y"] = *p.Y }
			sample = append(sample, item)
		}
	}

	player := map[string]any{
		"pseudo": "FEDERATED CANARY V6.3",
		"game_uid": "federated-canary-v63-" + serverID,
		"server_id": serverID,
		"regions": regionsOK,
		"decoded": totalDecoded,
		"uniqueUIDs": len(unique),
		"accepted": totalAccepted,
		"serverMismatch": serverMismatch,
		"sample": sample,
		"observed_at": utcNow(),
	}
	completeCollectorJob(jobID, player)
	slog.Info("FEDERATED_COLLECTOR_V63_SENTINEL", "jobId", jobID, "stage", "DONE", "serverId", serverID, "regions", regionsOK, "decoded", totalDecoded, "uniqueUIDs", len(unique), "accepted", totalAccepted, "serverMismatch", serverMismatch)
}

'''
    if s.count(helper_anchor) != 1:
        raise SystemExit(f'federated helper anchor: expected 1 match, got {s.count(helper_anchor)}')
    s = s.replace(helper_anchor, helper + helper_anchor, 1)
    JOBS.write_text(s, encoding='utf-8')

print('FEDERATED_COLLECTOR_CONNECTOR_V63=PATCHED')
print('FEDERATED_COLLECTOR_CANARY_QUERY=@federated:<serverId>')
print('FEDERATED_COLLECTOR_CANARY_REGIONS=9')
print('FEDERATED_COLLECTOR_CANARY_INGEST=YES')
print('FEDERATED_COLLECTOR_SERVER_EXPLORER_PROBE=PRESERVED')
