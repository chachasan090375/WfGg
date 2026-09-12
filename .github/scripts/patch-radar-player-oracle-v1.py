#!/usr/bin/env python3
from pathlib import Path

p = Path('/tmp/wfgg-radar/connector-go/cmd/radar-connector/collector_jobs.go')
s = p.read_text(encoding='utf-8')
marker = 'PLAYER_ORACLE_TARGETED_UID_V1'
if marker in s:
    print('PLAYER_ORACLE_TARGETED_UID=ALREADY_PRESENT')
    raise SystemExit(0)

old_struct = '''\tStatus      string         `json:"status"`\n\tPhase       string         `json:"phase"`\n\tRegion      int            `json:"region"`\n'''
new_struct = '''\tStatus      string         `json:"status"`\n\tPhase       string         `json:"phase"`\n\tStrategy    string         `json:"strategy,omitempty"`\n\tRegion      int            `json:"region"`\n'''
if s.count(old_struct) != 1:
    raise SystemExit('PLAYER_ORACLE_STRUCT_ANCHOR_MISSING')
s = s.replace(old_struct, new_struct, 1)

old_start = '''\tradarCollectorJobs.update(jobID, func(j *collectorJob) { j.Status = "RUNNING"; j.Phase = "STARTING" })\n\tcycle, joined, err := collectorStartCycle(ctx, query)\n'''
new_start = '''\tradarCollectorJobs.update(jobID, func(j *collectorJob) { j.Status = "RUNNING"; j.Phase = "STARTING" })\n\n\t// PLAYER_ORACLE_TARGETED_UID_V1\n\t// Individual searches first resolve the stable UID from Collector and ask\n\t// Last War for that exact profile. The validated nine-region Broad Scan is\n\t// preserved unchanged as the fallback when the UID is unknown or the direct\n\t// profile path cannot refresh the target.\n\tif s.tryTargetedUIDSearch(ctx, token, query, jobID) {\n\t\treturn\n\t}\n\tradarCollectorJobs.update(jobID, func(j *collectorJob) { j.Strategy = "BROAD_SCAN_V4"; j.Phase = "STARTING_BROAD_SCAN" })\n\tcycle, joined, err := collectorStartCycle(ctx, query)\n'''
if s.count(old_start) != 1:
    raise SystemExit('PLAYER_ORACLE_START_ANCHOR_MISSING')
s = s.replace(old_start, new_start, 1)

anchor = '''var errPlayerNotFound = errors.New("COLLECTOR_PLAYER_NOT_FOUND")\n'''
helper = '''// tryTargetedUIDSearch is deliberately best-effort. Returning false means\n// "use Broad Scan", never "player does not exist". This keeps the frozen V4\n// map engine as a safety net while making known-player searches much faster.\nfunc (s *server) tryTargetedUIDSearch(ctx context.Context, token, query, jobID string) bool {\n\tplayer, err := collectorGetPlayer(ctx, query)\n\tif err != nil {\n\t\treturn false\n\t}\n\tuid := stringField(player, "game_uid", "gameUid")\n\tif uid == "" {\n\t\treturn false\n\t}\n\n\tradarCollectorJobs.update(jobID, func(j *collectorJob) {\n\t\tj.Strategy = "TARGETED_UID_PROFILE"\n\t\tj.Phase = "RESOLVED_UID"\n\t\tj.Candidates = 1\n\t\tj.Region = 0\n\t})\n\n\t// refreshSearchTarget already performs the validated direct ProfileScanner\n\t// call and, after PROFILE_TARGET_RETRY_V1, retries transient misses up to 3x.\n\tif err := s.refreshSearchTarget(ctx, token, query, 0, jobID); err != nil {\n\t\tradarCollectorJobs.update(jobID, func(j *collectorJob) {\n\t\t\tj.Phase = "TARGETED_FALLBACK"\n\t\t\tj.Error = ""\n\t\t})\n\t\treturn false\n\t}\n\n\trefreshed, err := collectorGetPlayer(ctx, uid)\n\tif err != nil {\n\t\trefreshed, err = collectorGetPlayer(ctx, query)\n\t}\n\tif err != nil {\n\t\treturn false\n\t}\n\tcompleteCollectorJob(jobID, refreshed)\n\treturn true\n}\n\n'''
if s.count(anchor) != 1:
    raise SystemExit('PLAYER_ORACLE_HELPER_ANCHOR_MISSING')
s = s.replace(anchor, helper + anchor, 1)

p.write_text(s, encoding='utf-8')
print('PLAYER_ORACLE_TARGETED_UID=PATCHED')
print('PLAYER_ORACLE_FALLBACK=BROAD_SCAN_V4')
