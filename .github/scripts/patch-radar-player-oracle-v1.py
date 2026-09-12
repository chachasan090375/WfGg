#!/usr/bin/env python3
from pathlib import Path

p = Path('/tmp/wfgg-radar/connector-go/cmd/radar-connector/collector_jobs.go')
s = p.read_text(encoding='utf-8')
marker = 'PLAYER_ORACLE_TARGETED_UID_V1'
if marker in s:
    print('PLAYER_ORACLE_TARGETED_UID=ALREADY_PRESENT')
    raise SystemExit(0)

# Sentinel is deliberately observational: it must never choose the route itself.
# It records which priority was attempted and why a fallback happened.
old_import = '''\t"io"\n\t"net/http"\n'''
new_import = '''\t"io"\n\t"log/slog"\n\t"net/http"\n'''
if s.count(old_import) != 1:
    raise SystemExit('PLAYER_ORACLE_SENTINEL_IMPORT_ANCHOR_MISSING')
s = s.replace(old_import, new_import, 1)

old_struct = '''\tStatus      string         `json:"status"`\n\tPhase       string         `json:"phase"`\n\tRegion      int            `json:"region"`\n'''
new_struct = '''\tStatus      string         `json:"status"`\n\tPhase       string         `json:"phase"`\n\tStrategy    string         `json:"strategy,omitempty"`\n\tRegion      int            `json:"region"`\n'''
if s.count(old_struct) != 1:
    raise SystemExit('PLAYER_ORACLE_STRUCT_ANCHOR_MISSING')
s = s.replace(old_struct, new_struct, 1)

old_start = '''\tradarCollectorJobs.update(jobID, func(j *collectorJob) { j.Status = "RUNNING"; j.Phase = "STARTING" })\n\tcycle, joined, err := collectorStartCycle(ctx, query)\n'''
new_start = '''\tradarCollectorJobs.update(jobID, func(j *collectorJob) { j.Status = "RUNNING"; j.Phase = "STARTING" })\n\tsentinelOracle(jobID, "START", 1, "IDENTITY_INDEX_V1", "")\n\n\t// PLAYER_ORACLE_TARGETED_UID_V1\n\t// PLAYER_ORACLE_IDENTITY_INDEX_V1\n\t// Priority order for an individual search:\n\t//   P1 canonical Collector Identity Index resolves pseudo -> stable UID\n\t//   P2 direct Last War profile lookup for that UID\n\t//   P3 frozen Broad Scan V4 only if the targeted path is unavailable\n\tif s.tryTargetedUIDSearch(ctx, token, query, jobID) {\n\t\treturn\n\t}\n\tsentinelOracle(jobID, "BROAD_SCAN_SELECTED", 3, "BROAD_SCAN_V4", "targeted-path-unavailable")\n\tradarCollectorJobs.update(jobID, func(j *collectorJob) { j.Strategy = "BROAD_SCAN_V4"; j.Phase = "STARTING_BROAD_SCAN" })\n\tcycle, joined, err := collectorStartCycle(ctx, query)\n'''
if s.count(old_start) != 1:
    raise SystemExit('PLAYER_ORACLE_START_ANCHOR_MISSING')
s = s.replace(old_start, new_start, 1)

anchor = '''var errPlayerNotFound = errors.New("COLLECTOR_PLAYER_NOT_FOUND")\n'''
helper = '''// PLAYER_ORACLE_SENTINEL_V1\n// Sentinel observes the routing decision without seeing or logging credentials.\n// Priority is explicit so a diagnostic can prove Identity Index always precedes\n// direct profile and Broad Scan for targeted searches.\nfunc sentinelOracle(jobID, stage string, priority int, strategy, reason string) {\n\tslog.Info("PLAYER_ORACLE_SENTINEL",\n\t\t"jobId", jobID,\n\t\t"stage", stage,\n\t\t"priority", priority,\n\t\t"strategy", strategy,\n\t\t"reason", reason,\n\t)\n}\n\nvar errIdentityAmbiguous = errors.New("COLLECTOR_IDENTITY_AMBIGUOUS")\n\ntype collectorIdentityResponse struct {\n\tOK         bool             `json:"ok"`\n\tResolved   bool             `json:"resolved"`\n\tAmbiguous  bool             `json:"ambiguous"`\n\tRoute      string           `json:"route"`\n\tIdentity   map[string]any   `json:"identity"`\n\tCandidates []map[string]any `json:"candidates"`\n}\n\n// collectorResolveIdentity is the canonical P1 resolver. Dynamic profile data\n// remains in Collector players, but identity resolution must come exclusively\n// from /identity/resolve so pseudo changes and collisions are handled safely.\nfunc collectorResolveIdentity(ctx context.Context, query string) (map[string]any, string, error) {\n\tvar r collectorIdentityResponse\n\tpath := "/identity/resolve?q=" + url.QueryEscape(strings.TrimSpace(query))\n\tif err := collectorJSON(ctx, http.MethodGet, path, nil, &r); err != nil {\n\t\treturn nil, "", err\n\t}\n\tif r.Ambiguous {\n\t\treturn nil, r.Route, errIdentityAmbiguous\n\t}\n\tif !r.Resolved || r.Identity == nil {\n\t\treturn nil, r.Route, errPlayerNotFound\n\t}\n\treturn r.Identity, r.Route, nil\n}\n\n// tryTargetedUIDSearch is deliberately best-effort. Returning false means\n// "use Broad Scan", never "player does not exist". This keeps the frozen V4\n// map engine as a safety net while making known-player searches much faster.\nfunc (s *server) tryTargetedUIDSearch(ctx context.Context, token, query, jobID string) bool {\n\tidentity, route, err := collectorResolveIdentity(ctx, query)\n\tif err != nil {\n\t\tif errors.Is(err, errIdentityAmbiguous) {\n\t\t\tsentinelOracle(jobID, "UID_INDEX_AMBIGUOUS", 1, "IDENTITY_INDEX_V1", route)\n\t\t} else {\n\t\t\tsentinelOracle(jobID, "UID_INDEX_MISS", 1, "IDENTITY_INDEX_V1", "identity-index-miss")\n\t\t}\n\t\treturn false\n\t}\n\tuid := stringField(identity, "game_uid", "gameUid")\n\tif uid == "" {\n\t\tsentinelOracle(jobID, "UID_MISSING", 1, "IDENTITY_INDEX_V1", "resolved-identity-has-no-uid")\n\t\treturn false\n\t}\n\n\tsentinelOracle(jobID, "UID_RESOLVED", 1, "IDENTITY_INDEX_V1", route)\n\tradarCollectorJobs.update(jobID, func(j *collectorJob) {\n\t\tj.Strategy = "TARGETED_UID_PROFILE"\n\t\tj.Phase = "RESOLVED_UID"\n\t\tj.Candidates = 1\n\t\tj.Region = 0\n\t})\n\n\t// PLAYER_ORACLE_TARGET_BUDGET_V1: a targeted lookup must be fast.\n\t// The native scanner has a much larger generic timeout and refreshSearchTarget\n\t// may retry three times; without a tighter parent deadline a single targeted\n\t// lookup can appear frozen for minutes. Give P2 a short total budget, then\n\t// hand control to the already validated Broad Scan V4 fallback.\n\ttargetCtx, cancel := context.WithTimeout(ctx, 12*time.Second)\n\tdefer cancel()\n\tsentinelOracle(jobID, "DIRECT_PROFILE_START", 2, "TARGETED_UID_PROFILE", "budget=12s")\n\t// Important: once P1 resolved identity, P2 operates only on the stable UID.\n\tif err := s.refreshSearchTarget(targetCtx, token, uid, 0, jobID); err != nil {\n\t\tsentinelOracle(jobID, "DIRECT_PROFILE_FAILED", 2, "TARGETED_UID_PROFILE", err.Error())\n\t\tradarCollectorJobs.update(jobID, func(j *collectorJob) {\n\t\t\tj.Phase = "TARGETED_FALLBACK"\n\t\t\tj.Error = ""\n\t\t})\n\t\treturn false\n\t}\n\n\trefreshed, err := collectorGetPlayer(ctx, uid)\n\tif err != nil {\n\t\trefreshed, err = collectorGetPlayer(ctx, query)\n\t}\n\tif err != nil {\n\t\tsentinelOracle(jobID, "DIRECT_PROFILE_RESULT_MISSING", 2, "TARGETED_UID_PROFILE", "collector-read-after-profile-failed")\n\t\treturn false\n\t}\n\tsentinelOracle(jobID, "DIRECT_PROFILE_SUCCESS", 2, "TARGETED_UID_PROFILE", "")\n\tcompleteCollectorJob(jobID, refreshed)\n\tsentinelOracle(jobID, "DONE", 2, "TARGETED_UID_PROFILE", "")\n\treturn true\n}\n\n'''
if s.count(anchor) != 1:
    raise SystemExit('PLAYER_ORACLE_HELPER_ANCHOR_MISSING')
s = s.replace(anchor, helper + anchor, 1)

p.write_text(s, encoding='utf-8')
print('PLAYER_ORACLE_TARGETED_UID=PATCHED')
print('PLAYER_ORACLE_SENTINEL=PATCHED')
print('PLAYER_ORACLE_IDENTITY_INDEX=/identity/resolve')
print('PLAYER_ORACLE_TARGET_BUDGET_SECONDS=12')
print('PLAYER_ORACLE_PRIORITY_ORDER=P1_IDENTITY_INDEX>P2_DIRECT_PROFILE>P3_BROAD_SCAN_V4')
print('PLAYER_ORACLE_FALLBACK=BROAD_SCAN_V4')
