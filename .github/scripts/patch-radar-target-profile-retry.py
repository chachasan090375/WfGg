#!/usr/bin/env python3
from pathlib import Path

p = Path('/tmp/wfgg-radar/connector-go/cmd/radar-connector/collector_jobs.go')
s = p.read_text(encoding='utf-8')
marker = 'PROFILE_TARGET_RETRY_V1'
if marker in s:
    print('RADAR_TARGET_PROFILE_RETRY=ALREADY_PRESENT')
    raise SystemExit(0)

old_join = '''\t\tif err := s.refreshSearchTarget(ctx, token, query, 0, jobID); err != nil && !errors.Is(err, errPlayerNotFound) {\n\t\t\tfail("COLLECTOR_TARGET_REFRESH_FAILED")\n\t\t\treturn\n\t\t}\n'''
new_join = '''\t\t// PROFILE_TARGET_RETRY_V1: a joined SEARCH must still refresh its own\n\t\t// target, but a transient profile miss must not discard the valid map row.\n\t\t_ = s.refreshSearchTarget(ctx, token, query, 0, jobID)\n'''
if s.count(old_join) != 1:
    raise SystemExit('TARGET_RETRY_JOIN_ANCHOR_MISSING')
s = s.replace(old_join, new_join, 1)

old_final = '''\tradarCollectorJobs.update(jobID, func(j *collectorJob) { j.Phase = "FINALIZING" })\n'''
new_final = '''\t// Give the searched player a dedicated retry pass after bulk enrichment.\n\t// Bulk @profile batches are intentionally best-effort and can occasionally\n\t// return zero rows for one UID even though the player exists on the map.\n\t_ = s.refreshSearchTarget(ctx, token, query, cycle.ID, jobID)\n\n\tradarCollectorJobs.update(jobID, func(j *collectorJob) { j.Phase = "FINALIZING" })\n'''
if s.count(old_final) != 1:
    raise SystemExit('TARGET_RETRY_FINAL_ANCHOR_MISSING')
s = s.replace(old_final, new_final, 1)

old_fn = '''func (s *server) refreshSearchTarget(ctx context.Context, token, query string, cycleID int64, jobID string) error {\n\tplayer, err := collectorGetPlayer(ctx, query)\n\tif err != nil { return errPlayerNotFound }\n\tuid := stringField(player, "game_uid", "gameUid")\n\tif uid == "" { return errPlayerNotFound }\n\tprofileScanner, ok := s.game.(protocol.ProfileScanner)\n\tif !ok { return errors.New("PROFILE_SCANNER_UNAVAILABLE") }\n\tradarCollectorJobs.update(jobID, func(j *collectorJob) { j.Phase = "ENRICHING"; j.Candidates = 1 })\n\tplayers, err := profileScanner.ScanProfiles(ctx, token, []string{uid})\n\tif err != nil { return err }\n\taccepted, err := collectorIngest(ctx, players, cycleID)\n\tif err != nil { return err }\n\tradarCollectorJobs.update(jobID, func(j *collectorJob) { j.Enriched += accepted })\n\treturn nil\n}\n'''
new_fn = '''func (s *server) refreshSearchTarget(ctx context.Context, token, query string, cycleID int64, jobID string) error {\n\tplayer, err := collectorGetPlayer(ctx, query)\n\tif err != nil { return errPlayerNotFound }\n\tuid := stringField(player, "game_uid", "gameUid")\n\tif uid == "" { return errPlayerNotFound }\n\tprofileScanner, ok := s.game.(protocol.ProfileScanner)\n\tif !ok { return errors.New("PROFILE_SCANNER_UNAVAILABLE") }\n\tradarCollectorJobs.update(jobID, func(j *collectorJob) {\n\t\tj.Phase = "ENRICHING"\n\t\tif j.Candidates < 1 { j.Candidates = 1 }\n\t})\n\tvar lastErr error\n\tfor attempt := 0; attempt < 3; attempt++ {\n\t\tplayers, scanErr := profileScanner.ScanProfiles(ctx, token, []string{uid})\n\t\tif scanErr == nil && len(players) > 0 {\n\t\t\taccepted, ingestErr := collectorIngest(ctx, players, cycleID)\n\t\t\tif ingestErr != nil { return ingestErr }\n\t\t\tradarCollectorJobs.update(jobID, func(j *collectorJob) { j.Enriched += accepted })\n\t\t\tif accepted > 0 { return nil }\n\t\t\tlastErr = errors.New("PROFILE_TARGET_NOT_ACCEPTED")\n\t\t} else if scanErr != nil {\n\t\t\tlastErr = scanErr\n\t\t} else {\n\t\t\tlastErr = errors.New("PROFILE_TARGET_NOT_RETURNED")\n\t\t}\n\t\tselect {\n\t\tcase <-ctx.Done():\n\t\t\treturn ctx.Err()\n\t\tcase <-time.After(time.Duration(attempt+1) * 350 * time.Millisecond):\n\t\t}\n\t}\n\treturn lastErr\n}\n'''
if s.count(old_fn) != 1:
    raise SystemExit('TARGET_RETRY_FUNCTION_ANCHOR_MISSING')
s = s.replace(old_fn, new_fn, 1)

p.write_text(s, encoding='utf-8')
print('RADAR_TARGET_PROFILE_RETRY=PATCHED')
print('RADAR_TARGET_PROFILE_RETRY_ATTEMPTS=3')
