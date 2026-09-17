#!/usr/bin/env python3
from pathlib import Path
import shutil

ROOT = Path('/tmp/wfgg-radar')
CONNECTOR = ROOT / 'connector-go'
COLLECTOR = CONNECTOR / 'cmd/radar-connector/collector_jobs.go'
V4 = CONNECTOR / 'native-template/player_scan_v4.go'
SRC = Path('.radar-release-src/v615-source/connector-go')


def copy_sources() -> None:
    pairs = [
        (SRC / 'internal/protocol/federated_target_v615.go', CONNECTOR / 'internal/protocol/federated_target_v615.go'),
        (SRC / 'internal/protocol/federated_target_v615_test.go', CONNECTOR / 'internal/protocol/federated_target_v615_test.go'),
        (SRC / 'cmd/radar-connector/federated_target_v615.go', CONNECTOR / 'cmd/radar-connector/federated_target_v615.go'),
        (SRC / 'cmd/radar-connector/federated_target_v615_test.go', CONNECTOR / 'cmd/radar-connector/federated_target_v615_test.go'),
    ]
    for src, dst in pairs:
        if not src.is_file():
            raise SystemExit(f'V615_SOURCE_MISSING={src}')
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)


def patch_collector() -> None:
    text = COLLECTOR.read_text(encoding='utf-8')
    marker = 'WFGG_RADAR_TARGETED_FEDERATED_SERVER_V615'
    if marker in text:
        print('RADAR_V615_COLLECTOR=ALREADY_PRESENT')
        return

    old = 'players, regionDiag, err := scanCollectorRegionV67(ctx, s.game, regionScanner, token, region)'
    new = '// WFGG_RADAR_TARGETED_FEDERATED_SERVER_V615\n\t\tplayers, regionDiag, err := scanCollectorRegionTargetV615(ctx, s.game, regionScanner, token, region, query)'
    if text.count(old) != 1:
        raise SystemExit(f'V615_COLLECTOR_SCAN_ANCHOR_COUNT={text.count(old)}')
    text = text.replace(old, new, 1)

    start_old = 'radarCollectorJobs.update(jobID, func(j *collectorJob) { j.Status = "RUNNING"; j.Phase = "STARTING" })'
    start_new = '''radarCollectorJobs.update(jobID, func(j *collectorJob) {
		j.Status = "RUNNING"
		j.Phase = "STARTING"
		if target, ok := federatedServerTargetV615(query); ok {
			j.ServerTarget = target
		}
	})'''
    if text.count(start_old) != 1:
        raise SystemExit(f'V615_COLLECTOR_START_ANCHOR_COUNT={text.count(start_old)}')
    text = text.replace(start_old, start_new, 1)
    COLLECTOR.write_text(text, encoding='utf-8')
    print('RADAR_V615_COLLECTOR=PATCHED')


def patch_native_map_target() -> None:
    text = V4.read_text(encoding='utf-8')
    marker = 'WFGG_RADAR_TARGET_SERVER_ID_V615'
    if marker in text:
        print('RADAR_V615_NATIVE=ALREADY_PRESENT')
        return

    old = '''\tserverID, err := strconv.Atoi(strings.TrimPrefix(strings.TrimSpace(fallbackServer), "APS"))
\tif err != nil || serverID <= 0 {
\t\treturn nil, errors.New("PLAYER_SCAN_SERVER_ID_INVALID")
\t}
'''
    new = '''\t// WFGG_RADAR_TARGET_SERVER_ID_V615: a federated Collector job may read a
\t// different server map while preserving the authenticated read-only session.
\t// The override is process-local because each region runs in its own helper.
\tscanServer := strings.TrimPrefix(strings.TrimSpace(fallbackServer), "APS")
\tif target := strings.TrimSpace(os.Getenv("WFGG_COLLECTOR_TARGET_SERVER_ID")); target != "" {
\t\tscanServer = strings.TrimPrefix(strings.TrimSpace(target), "APS")
\t}
\tserverID, err := strconv.Atoi(scanServer)
\tif err != nil || serverID <= 0 {
\t\treturn nil, errors.New("PLAYER_SCAN_SERVER_ID_INVALID")
\t}
'''
    if text.count(old) != 1:
        raise SystemExit(f'V615_NATIVE_SERVER_ANCHOR_COUNT={text.count(old)}')
    text = text.replace(old, new, 1)

    old_diag = 'diag.observe(obj, query, fallbackServer, observedAt, 0, 1000, fallbackServer)'
    new_diag = 'diag.observe(obj, query, scanServer, observedAt, 0, 1000, scanServer)'
    if text.count(old_diag) != 1:
        raise SystemExit(f'V615_NATIVE_DIAG_ANCHOR_COUNT={text.count(old_diag)}')
    text = text.replace(old_diag, new_diag, 1)

    old_collect = 'collectMapPlayersV3(obj, query, fallbackServer, observedAt, &out, seen, 0, 1000, fallbackServer)'
    new_collect = 'collectMapPlayersV3(obj, query, scanServer, observedAt, &out, seen, 0, 1000, scanServer)'
    if text.count(old_collect) != 1:
        raise SystemExit(f'V615_NATIVE_COLLECT_ANCHOR_COUNT={text.count(old_collect)}')
    text = text.replace(old_collect, new_collect, 1)

    V4.write_text(text, encoding='utf-8')
    print('RADAR_V615_NATIVE=PATCHED')


copy_sources()
patch_collector()
patch_native_map_target()
print('RADAR_TARGETED_FEDERATED_SERVER_V615=READY')
