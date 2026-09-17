#!/usr/bin/env python3
from pathlib import Path
import shutil

ROOT = Path('/tmp/wfgg-radar')
CONNECTOR = ROOT / 'connector-go'
COLLECTOR = CONNECTOR / 'cmd/radar-connector/collector_jobs.go'
PROFILE = CONNECTOR / 'cmd/radar-connector/profile_isolation_v68.go'
SRC = Path('.radar-release-src/v697-source/connector-go/cmd/radar-connector')


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected exactly 1 match, got {count}')
    return text.replace(old, new, 1)


def install_sources() -> None:
    for name in ('profile_universe_v697.go', 'profile_universe_v697_test.go'):
        src = SRC / name
        dst = CONNECTOR / 'cmd/radar-connector' / name
        if not src.is_file():
            raise SystemExit(f'V697_SOURCE_MISSING={src}')
        shutil.copyfile(src, dst)


def patch_collector() -> None:
    text = COLLECTOR.read_text(encoding='utf-8')
    marker = 'WFGG_RADAR_FULL_PROFILE_UNIVERSE_JOB_V697'
    if marker in text:
        print('RADAR_V697_COLLECTOR=ALREADY_PRESENT')
        return

    loop = '\tfor region := 0; region < 9; region++ {\n'
    injected = '''\t// WFGG_RADAR_FULL_PROFILE_UNIVERSE_JOB_V697\n\t// Keep the complete UID universe observed by this map cycle. The Collector\n\t// change feed is a delta and must not define profile population size.\n\tprofileUIDsV697 := make([]string, 0, 4096)\n\tprofileUIDSeenV697 := map[string]struct{}{}\n\n\tfor region := 0; region < 9; region++ {\n'''
    text = replace_once(text, loop, injected, 'region loop')

    ingest = '\t\taccepted, err := collectorIngest(ctx, players, cycle.ID)\n'
    ingest_with_uids = '''\t\tprofileUIDsV697 = appendProfileUIDsV697(profileUIDsV697, profileUIDSeenV697, players)\n\t\taccepted, err := collectorIngest(ctx, players, cycle.ID)\n'''
    text = replace_once(text, ingest, ingest_with_uids, 'map ingest')

    old_delta = '''\tuids, err := collectorChangedUIDs(ctx, cycle.ID)\n\tif err != nil {\n\t\t_ = collectorFinishCycle(context.Background(), cycle.ID, "FAILED", "DELTA_READ_FAILED")\n\t\tfail("DELTA_READ_FAILED", err)\n\t\treturn\n\t}\n'''
    new_population = '''\t// V6.9.7: enrich the complete current map population, not only rows whose\n\t// Collector state changed relative to a previous cycle.\n\tuids := append([]string(nil), profileUIDsV697...)\n'''
    text = replace_once(text, old_delta, new_population, 'delta candidate source')

    COLLECTOR.write_text(text, encoding='utf-8')
    print('RADAR_V697_COLLECTOR=PATCHED')


def patch_budget() -> None:
    text = PROFILE.read_text(encoding='utf-8')
    marker = 'WFGG_RADAR_PROFILE_DYNAMIC_BUDGET_V697'
    if marker in text:
        print('RADAR_V697_BUDGET=ALREADY_PRESENT')
        return

    init = '\tstats := collectorProfileStatsV68{Requested: len(clean)}\n'
    init_new = '''\tstats := collectorProfileStatsV68{Requested: len(clean)}\n\t// WFGG_RADAR_PROFILE_DYNAMIC_BUDGET_V697\n\tattemptBudgetV697 := profileAttemptBudgetV697(len(clean))\n'''
    text = replace_once(text, init, init_new, 'profile stats init')
    text = replace_once(
        text,
        '\t\tif stats.Attempts >= v68ProfileAttemptBudget {\n',
        '\t\tif stats.Attempts >= attemptBudgetV697 {\n',
        'attempt budget check',
    )
    PROFILE.write_text(text, encoding='utf-8')
    print('RADAR_V697_BUDGET=PATCHED')


install_sources()
patch_collector()
patch_budget()
print('RADAR_FULL_PROFILE_UNIVERSE_V697=READY')
