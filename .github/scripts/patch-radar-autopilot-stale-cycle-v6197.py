#!/usr/bin/env python3
from pathlib import Path
import shutil

ROOT = Path('/tmp/wfgg-radar')
CONNECTOR = ROOT / 'connector-go'
DST = CONNECTOR / 'cmd/radar-connector'
SRC = Path('.radar-release-src/v6197-source/connector-go/cmd/radar-connector')
COLLECTOR = DST / 'collector_jobs.go'
AUTOPILOT = DST / 'server_autopilot_v6194.go'

for name in ('collector_stale_cycle_v6197.go', 'collector_stale_cycle_v6197_test.go'):
    src = SRC / name
    dst = DST / name
    if not src.is_file():
        raise SystemExit(f'V6197_SOURCE_MISSING={src}')
    shutil.copyfile(src, dst)

text = COLLECTOR.read_text(encoding='utf-8')
marker = 'collectorStartCycleWithStaleRecoveryV6197(ctx, query)'
if marker not in text:
    old = 'cycle, joined, err := collectorStartCycle(ctx, query)'
    if text.count(old) != 1:
        raise SystemExit(f'V6197_COLLECTOR_START_ANCHOR_COUNT={text.count(old)}')
    new = '''cycle, joined, staleRecovered, err := collectorStartCycleWithStaleRecoveryV6197(ctx, query)
	if staleRecovered {
		radarCollectorJobs.update(jobID, func(j *collectorJob) { j.Phase = "STALE_CYCLE_RECOVERED" })
	}'''
    text = text.replace(old, new, 1)
    COLLECTOR.write_text(text, encoding='utf-8')
    print('RADAR_V6197_COLLECTOR_START=PATCHED')
else:
    print('RADAR_V6197_COLLECTOR_START=ALREADY_PRESENT')

text = AUTOPILOT.read_text(encoding='utf-8')
if 'WFGG_RADAR_AUTOPILOT_STALE_CYCLE_RECOVERY_V6197' not in text:
    anchor = '// WFGG_RADAR_AUTOPILOT_CONTINUE_NO_DATA_V6196'
    if text.count(anchor) != 1:
        raise SystemExit(f'V6197_AUTOPILOT_MARKER_ANCHOR_COUNT={text.count(anchor)}')
    text = text.replace(anchor, anchor + '\n// WFGG_RADAR_AUTOPILOT_STALE_CYCLE_RECOVERY_V6197', 1)
if 'autopilotVersionV6194                    = "v6.19.6"' in text:
    text = text.replace(
        'autopilotVersionV6194                    = "v6.19.6"',
        'autopilotVersionV6194                    = "v6.19.7"',
        1,
    )
elif 'autopilotVersionV6194                    = "v6.19.7"' not in text:
    raise SystemExit('V6197_AUTOPILOT_VERSION_ANCHOR_MISSING')
AUTOPILOT.write_text(text, encoding='utf-8')

print('RADAR_V6197_STALE_CYCLE_RECOVERY=READY')
