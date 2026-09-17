#!/usr/bin/env python3
from pathlib import Path
import shutil

ROOT = Path('/tmp/wfgg-radar')
CONNECTOR = ROOT / 'connector-go'
JOBS = CONNECTOR / 'cmd/radar-connector/collector_jobs.go'
SRC = Path('.radar-release-src/v618-source/connector-go/cmd/radar-connector')
DST = CONNECTOR / 'cmd/radar-connector'


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected exactly 1 match, got {count}')
    return text.replace(old, new, 1)


for name in ('profile_map_merge_v618.go', 'profile_map_merge_v618_test.go'):
    src = SRC / name
    if not src.is_file():
        raise SystemExit(f'V618_SOURCE_MISSING={src}')
    shutil.copyfile(src, DST / name)

text = JOBS.read_text(encoding='utf-8')
marker = 'WFGG_RADAR_MAP_PROFILE_MERGE_JOB_V618'
if marker in text:
    print('RADAR_V618_COLLECTOR=ALREADY_PRESENT')
    raise SystemExit(0)

# Keep the latest map observation for every UID seen in this cycle.
old_index = '''\tprofileUIDsV697 := make([]string, 0, 4096)\n\tprofileUIDSeenV697 := map[string]struct{}{}\n\n\tfor region := 0; region < 9; region++ {\n'''
new_index = '''\tprofileUIDsV697 := make([]string, 0, 4096)\n\tprofileUIDSeenV697 := map[string]struct{}{}\n\t// WFGG_RADAR_MAP_PROFILE_MERGE_JOB_V618\n\tmapPlayersV618 := map[string]protocol.Player{}\n\n\tfor region := 0; region < 9; region++ {\n'''
text = replace_once(text, old_index, new_index, 'map index init')

old_map_ingest = '''\t\tprofileUIDsV697 = appendProfileUIDsV697(profileUIDsV697, profileUIDSeenV697, players)\n\t\taccepted, err := collectorIngest(ctx, players, cycle.ID)\n'''
new_map_ingest = '''\t\tprofileUIDsV697 = appendProfileUIDsV697(profileUIDsV697, profileUIDSeenV697, players)\n\t\trememberMapPlayersV618(mapPlayersV618, players)\n\t\taccepted, err := collectorIngest(ctx, players, cycle.ID)\n'''
text = replace_once(text, old_map_ingest, new_map_ingest, 'map observation capture')

# Bulk profile enrichment uses a wrapper that restores omitted map fields before
# the row reaches Collector.
old_bulk = '''\t\t\tstats := enrichProfilesIsolatedV68(ctx, profileScanner, token, uids, cycle.ID, collectorIngest)\n'''
new_bulk = '''\t\t\tprofileIngestV618 := func(ingestCtx context.Context, profiles []protocol.Player, ingestCycleID int64) (int, error) {\n\t\t\t\treturn collectorIngest(ingestCtx, mergeProfileBatchV618(mapPlayersV618, profiles), ingestCycleID)\n\t\t\t}\n\t\t\tstats := enrichProfilesIsolatedV68(ctx, profileScanner, token, uids, cycle.ID, profileIngestV618)\n'''
text = replace_once(text, old_bulk, new_bulk, 'bulk profile ingest')

# The dedicated searched-player retry is another profile write path and must use
# the same sparse merge rule.
old_call = '''\t_ = s.refreshSearchTarget(ctx, token, query, cycle.ID, jobID)\n'''
new_call = '''\t_ = s.refreshSearchTarget(ctx, token, query, cycle.ID, jobID, mapPlayersV618)\n'''
text = replace_once(text, old_call, new_call, 'target retry call')

old_sig = '''func (s *server) refreshSearchTarget(ctx context.Context, token, query string, cycleID int64, jobID string) error {\n'''
new_sig = '''func (s *server) refreshSearchTarget(ctx context.Context, token, query string, cycleID int64, jobID string, mapPlayersV618 map[string]protocol.Player) error {\n'''
text = replace_once(text, old_sig, new_sig, 'target retry signature')

old_target_ingest = '''\t\tif scanErr == nil && len(players) > 0 {\n\t\t\taccepted, ingestErr := collectorIngest(ctx, players, cycleID)\n'''
new_target_ingest = '''\t\tif scanErr == nil && len(players) > 0 {\n\t\t\tplayers = mergeProfileBatchV618(mapPlayersV618, players)\n\t\t\taccepted, ingestErr := collectorIngest(ctx, players, cycleID)\n'''
text = replace_once(text, old_target_ingest, new_target_ingest, 'target retry ingest')

JOBS.write_text(text, encoding='utf-8')
print('RADAR_V618_MAP_PROFILE_MERGE=PATCHED')
print('RADAR_MAP_PROFILE_MERGE_V618=READY')
