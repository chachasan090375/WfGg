#!/usr/bin/env python3
from pathlib import Path
import shutil

ROOT = Path('/tmp/wfgg-radar')
CONNECTOR = ROOT / 'connector-go'
COLLECTOR = CONNECTOR / 'cmd/radar-connector/collector_jobs.go'
SRC = Path('.radar-release-src/v68-source/connector-go/cmd/radar-connector')


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected exactly 1 match, got {count}')
    return text.replace(old, new, 1)


def install_sources() -> None:
    for name in ('profile_isolation_v68.go', 'profile_isolation_v68_test.go'):
        src = SRC / name
        dst = CONNECTOR / 'cmd/radar-connector' / name
        if not src.is_file():
            raise SystemExit(f'V68_SOURCE_MISSING={src}')
        shutil.copyfile(src, dst)


def patch_collector() -> None:
    text = COLLECTOR.read_text(encoding='utf-8')
    if 'WFGG_RADAR_PROFILE_ISOLATION_JOB_V68' in text:
        print('RADAR_V68_COLLECTOR=ALREADY_PRESENT')
        return

    text = replace_once(
        text,
        '\tRegionFailures   []collectorRegionFailure `json:"regionFailures,omitempty"`\n',
        '\tRegionFailures   []collectorRegionFailure `json:"regionFailures,omitempty"`\n\t// WFGG_RADAR_PROFILE_ISOLATION_JOB_V68\n\tProfileStats     collectorProfileStatsV68 `json:"profileStats,omitempty"`\n',
        'profile stats field',
    )

    old = '''\tif len(uids) > 0 {\n\t\tprofileScanner, ok := s.game.(protocol.ProfileScanner)\n\t\tif !ok {\n\t\t\t_ = collectorFinishCycle(context.Background(), cycle.ID, "FAILED", "PROFILE_SCANNER_UNAVAILABLE")\n\t\t\tfail("PROFILE_SCANNER_UNAVAILABLE")\n\t\t\treturn\n\t\t}\n\t\tfor start := 0; start < len(uids); start += 50 {\n\t\t\tend := start + 50\n\t\t\tif end > len(uids) {\n\t\t\t\tend = len(uids)\n\t\t\t}\n\t\t\tplayers, err := profileScanner.ScanProfiles(ctx, token, uids[start:end])\n\t\t\tif err != nil {\n\t\t\t\t_ = collectorFinishCycle(context.Background(), cycle.ID, "FAILED", "PROFILE_BATCH_FAILED")\n\t\t\t\tfail("PROFILE_BATCH_FAILED", err)\n\t\t\t\treturn\n\t\t\t}\n\t\t\taccepted, err := collectorIngest(ctx, players, cycle.ID)\n\t\t\tif err != nil {\n\t\t\t\t_ = collectorFinishCycle(context.Background(), cycle.ID, "FAILED", "PROFILE_INGEST_FAILED")\n\t\t\t\tfail("PROFILE_INGEST_FAILED", err)\n\t\t\t\treturn\n\t\t\t}\n\t\t\tradarCollectorJobs.update(jobID, func(j *collectorJob) { j.Enriched += accepted })\n\t\t}\n\t}\n'''
    new = '''\tif len(uids) > 0 {\n\t\t// WFGG_RADAR_PROFILE_ISOLATION_V68: map evidence survives profile\n\t\t// failures. Failed/partial batches are bisected under a hard budget and\n\t\t// only aggregate failure codes are retained; no UID is exposed.\n\t\tprofileScanner, ok := s.game.(protocol.ProfileScanner)\n\t\tif !ok {\n\t\t\tstats := collectorProfileStatsV68{\n\t\t\t\tStatus: "UNAVAILABLE", Requested: len(uids), ProfilesUnresolved: len(uids),\n\t\t\t\tFailures: []collectorProfileFailureV68{{Scope: "SCANNER", BatchSize: len(uids), Code: "PROFILE_SCANNER_UNAVAILABLE"}},\n\t\t\t}\n\t\t\tradarCollectorJobs.update(jobID, func(j *collectorJob) { j.ProfileStats = stats })\n\t\t} else {\n\t\t\tstats := enrichProfilesIsolatedV68(ctx, profileScanner, token, uids, cycle.ID, collectorIngest)\n\t\t\tradarCollectorJobs.update(jobID, func(j *collectorJob) {\n\t\t\t\tj.ProfileStats = stats\n\t\t\t\tj.Enriched += stats.ProfilesAccepted\n\t\t\t})\n\t\t}\n\t}\n'''
    text = replace_once(text, old, new, 'profile enrichment loop')
    COLLECTOR.write_text(text, encoding='utf-8')
    print('RADAR_V68_COLLECTOR=PATCHED')


install_sources()
patch_collector()
print('RADAR_PROFILE_ISOLATION_V68=READY')
