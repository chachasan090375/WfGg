#!/usr/bin/env python3
from pathlib import Path
import shutil

ROOT = Path('/tmp/wfgg-radar')
CONNECTOR = ROOT / 'connector-go'
MAIN = CONNECTOR / 'cmd/radar-connector/main.go'
COLLECTOR = CONNECTOR / 'cmd/radar-connector/collector_jobs.go'
SRC = Path('.radar-release-src/v6191-source/connector-go/cmd/radar-connector')


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected exactly 1 match, got {count}')
    return text.replace(old, new, 1)


def install_sources() -> None:
    for name in ('profile_refresh_v6191.go', 'profile_refresh_v6191_test.go'):
        src = SRC / name
        dst = CONNECTOR / 'cmd/radar-connector' / name
        if not src.is_file():
            raise SystemExit(f'V6191_SOURCE_MISSING={src}')
        shutil.copyfile(src, dst)



def patch_profile_only_job() -> None:
    text = COLLECTOR.read_text(encoding='utf-8')
    marker = 'WFGG_RADAR_PROFILE_ONLY_JOB_V6191'
    if marker in text:
        print('RADAR_V6191_PROFILE_ONLY_JOB=ALREADY_PRESENT')
        return
    old = '''\tradarCollectorJobs.update(jobID, func(j *collectorJob) {
\t\tj.Status = "RUNNING"
\t\tj.Phase = "STARTING"
\t\tif target, ok := federatedServerTargetV615(query); ok {
\t\t\tj.ServerTarget = target
\t\t}
\t})
\tcycle, joined, err := collectorStartCycle(ctx, query)
'''
    new = '''\tradarCollectorJobs.update(jobID, func(j *collectorJob) { j.Status = "RUNNING"; j.Phase = "STARTING" })\n\n\t// WFGG_RADAR_PROFILE_ONLY_JOB_V6191\n\t// Explicit @profile:<uid> uses only get.user.info.multi. It does not start\n\t// a map sweep or a Collector cycle, so cluster evidence is untouched.\n\tif uid, ok := profileOnlyUIDV6191(query); ok {\n\t\tradarCollectorJobs.update(jobID, func(j *collectorJob) {\n\t\t\tj.Phase = "PROFILE_ONLY"\n\t\t\tj.Candidates = 1\n\t\t})\n\t\tplayer, refreshErr := s.runTargetProfileRefreshV6191(ctx, token, uid)\n\t\tif refreshErr != nil {\n\t\t\tfail("PROFILE_TARGET_REFRESH_FAILED", refreshErr)\n\t\t\treturn\n\t\t}\n\t\tradarCollectorJobs.update(jobID, func(j *collectorJob) { j.Enriched = 1 })\n\t\tcompleteCollectorJob(jobID, playerMapV6191(player))\n\t\treturn\n\t}\n\n\tcycle, joined, err := collectorStartCycle(ctx, query)\n'''
    text = replace_once(text, old, new, 'profile-only collector job')
    COLLECTOR.write_text(text, encoding='utf-8')
    print('RADAR_V6191_PROFILE_ONLY_JOB=PATCHED')

def patch_route() -> None:
    text = MAIN.read_text(encoding='utf-8')
    marker = 'WFGG_RADAR_TARGET_PROFILE_REFRESH_ROUTE_V6191'
    if marker in text:
        print('RADAR_V6191_PROFILE_ROUTE=ALREADY_PRESENT')
        return
    anchor = '	mux.HandleFunc("GET /v1/collector/search/status", s.signed(s.collectorSearchStatus))\n'
    replacement = anchor + '	// WFGG_RADAR_TARGET_PROFILE_REFRESH_ROUTE_V6191\n	mux.HandleFunc("POST /v1/collector/profile/refresh", s.signed(s.profileRefreshV6191))\n'
    text = replace_once(text, anchor, replacement, 'profile refresh route')
    MAIN.write_text(text, encoding='utf-8')
    print('RADAR_V6191_PROFILE_ROUTE=PATCHED')


install_sources()
patch_profile_only_job()
patch_route()
print('RADAR_TARGET_PROFILE_REFRESH_V6191=READY')
