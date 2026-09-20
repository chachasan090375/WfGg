#!/usr/bin/env python3
from pathlib import Path
import shutil

ROOT = Path('/tmp/wfgg-radar')
DST = ROOT / 'connector-go' / 'cmd' / 'radar-connector'
SRC = Path('.radar-release-src/v6198-source/connector-go/cmd/radar-connector')
COLLECTOR = DST / 'collector_jobs.go'
AUTOPILOT = DST / 'server_autopilot_v6194.go'

for name in ('collector_cycle_terminalization_v6198.go', 'collector_cycle_terminalization_v6198_test.go'):
    src = SRC / name
    dst = DST / name
    if not src.is_file():
        raise SystemExit(f'V6198_SOURCE_MISSING={src}')
    shutil.copyfile(src, dst)

text = COLLECTOR.read_text(encoding='utf-8')
marker = 'finishFailedV6198 := func('
if marker not in text:
    anchor = 'cycle, joined, staleRecovered, err := collectorStartCycleWithStaleRecoveryV6197(ctx, query)'
    if text.count(anchor) != 1:
        raise SystemExit(f'V6198_FAIL_HELPER_ANCHOR_COUNT={text.count(anchor)}')
    addition = '''// WFGG_RADAR_COLLECTOR_CYCLE_TERMINALIZATION_CALLSITE_V6198
	finishFailedV6198 := func(cycleID int64, code string, cause error) {
		if terminalErr := collectorFinishCycleReliableV6198(cycleID, "FAILED", code); terminalErr != nil {
			if cause != nil {
				fail(code+"_CYCLE_TERMINALIZATION_FAILED", fmt.Errorf("%v; %w", cause, terminalErr))
			} else {
				fail(code+"_CYCLE_TERMINALIZATION_FAILED", terminalErr)
			}
			return
		}
		if cause != nil {
			fail(code, cause)
		} else {
			fail(code)
		}
	}

	'''
    text = text.replace(anchor, addition + anchor, 1)

replacements = [
    (
        '''\t\t\t_ = collectorFinishCycle(context.Background(), cycle.ID, "FAILED", "MAP_INGEST_FAILED")
\t\t\tfail("MAP_INGEST_FAILED", err)''',
        '''\t\t\tfinishFailedV6198(cycle.ID, "MAP_INGEST_FAILED", err)'''
    ),
    (
        '''\t\t_ = collectorFinishCycle(context.Background(), cycle.ID, "FAILED", "MAP_ALL_REGIONS_FAILED")
\t\tfail("MAP_ALL_REGIONS_FAILED", errors.New("ALL_REGION_SCANS_FAILED"))''',
        '''\t\tfinishFailedV6198(cycle.ID, "MAP_ALL_REGIONS_FAILED", errors.New("ALL_REGION_SCANS_FAILED"))'''
    ),
]
for old, new in replacements:
    if old in text:
        text = text.replace(old, new, 1)
    elif new not in text:
        raise SystemExit('V6198_MAP_FAILURE_CALLSITE_ANCHOR_MISSING')

old_success = '''	if err := collectorFinishCycle(ctx, cycle.ID, "SUCCESS", ""); err != nil {
		fail("COLLECTOR_CYCLE_FINISH_FAILED", err)
		return
	}'''
new_success = '''	if err := collectorFinishCycleReliableV6198(cycle.ID, "SUCCESS", ""); err != nil {
		fail("COLLECTOR_CYCLE_FINISH_FAILED", err)
		return
	}'''
if old_success in text:
    text = text.replace(old_success, new_success, 1)
elif new_success not in text:
    raise SystemExit('V6198_SUCCESS_CALLSITE_ANCHOR_MISSING')

COLLECTOR.write_text(text, encoding='utf-8')

text = AUTOPILOT.read_text(encoding='utf-8')
if 'WFGG_RADAR_COLLECTOR_CYCLE_TERMINALIZATION_V6198' not in text:
    anchor = '// WFGG_RADAR_AUTOPILOT_STALE_CYCLE_RECOVERY_V6197'
    if text.count(anchor) != 1:
        raise SystemExit(f'V6198_AUTOPILOT_MARKER_ANCHOR_COUNT={text.count(anchor)}')
    text = text.replace(anchor, anchor + '\n// WFGG_RADAR_COLLECTOR_CYCLE_TERMINALIZATION_V6198', 1)
if 'autopilotVersionV6194                    = "v6.19.7"' in text:
    text = text.replace(
        'autopilotVersionV6194                    = "v6.19.7"',
        'autopilotVersionV6194                    = "v6.19.8"',
        1,
    )
elif 'autopilotVersionV6194                    = "v6.19.8"' not in text:
    raise SystemExit('V6198_AUTOPILOT_VERSION_ANCHOR_MISSING')
AUTOPILOT.write_text(text, encoding='utf-8')

print('RADAR_V6198_COLLECTOR_CYCLE_TERMINALIZATION=READY')
