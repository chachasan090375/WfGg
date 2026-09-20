#!/usr/bin/env python3
from pathlib import Path
import shutil

ROOT = Path('/tmp/wfgg-radar')
DST = ROOT / 'connector-go' / 'cmd' / 'radar-connector'
SRC = Path('.radar-release-src/v6199-source/connector-go/cmd/radar-connector')
AUTOPILOT = DST / 'server_autopilot_v6194.go'

for name in ('autopilot_targeted_history_v6199.go','autopilot_targeted_history_v6199_test.go'):
    src = SRC / name
    dst = DST / name
    if not src.is_file():
        raise SystemExit(f'V6199_SOURCE_MISSING={src}')
    shutil.copyfile(src, dst)

text = AUTOPILOT.read_text(encoding='utf-8')
marker = '// WFGG_RADAR_AUTOPILOT_TARGETED_HISTORY_QUALITY_V6199'
if marker not in text:
    anchor = '// WFGG_RADAR_COLLECTOR_CYCLE_TERMINALIZATION_V6198'
    if text.count(anchor) != 1:
        raise SystemExit(f'V6199_MARKER_ANCHOR_COUNT={text.count(anchor)}')
    text = text.replace(anchor, anchor + '\n' + marker, 1)

old = '''func autopilotExistingFullCycleIDsV6194(ctx context.Context, seed string) ([]int64, error) {
	seed = strings.TrimSpace(seed)
	if seed == "" {
		return nil, nil
	}
	dbPath := strings.TrimSpace(os.Getenv("WFGG_COLLECTOR_DB"))
	if dbPath == "" {
		dbPath = "/opt/wfgg-collector/data/collector.db"
	}
	history, err := runServerCycleHistoryV614(ctx, dbPath)
	if err != nil {
		return nil, err
	}
	quality, err := runCycleQualityMetaV617(ctx, dbPath)
	if err != nil {
		return nil, err
	}
	ids := []int64{}
	for _, cycle := range history.Cycles {
		meta, found := quality[cycle.CycleID]
		eligible, _ := cycleEligibleForClusterV617(cycle, meta, found)
		if !eligible {
			continue
		}
		if federatedTargetV617(meta.Query) != seed {
			continue
		}
		if !cycleContainsServerV617(cycle, seed) {
			continue
		}
		ids = append(ids, cycle.CycleID)
	}
	return ids, nil
}
'''
new = '''func autopilotExistingFullCycleIDsV6194(ctx context.Context, seed string) ([]int64, error) {
	seed = strings.TrimSpace(seed)
	if seed == "" {
		return nil, nil
	}
	dbPath := strings.TrimSpace(os.Getenv("WFGG_COLLECTOR_DB"))
	if dbPath == "" {
		dbPath = "/opt/wfgg-collector/data/collector.db"
	}
	// WFGG_RADAR_AUTOPILOT_TARGETED_HISTORY_CALLSITE_V6199
	return autopilotTargetedFullCycleIDsV6199(ctx, dbPath, seed)
}
'''
if 'WFGG_RADAR_AUTOPILOT_TARGETED_HISTORY_CALLSITE_V6199' not in text:
    if text.count(old) != 1:
        raise SystemExit(f'V6199_HISTORY_FUNCTION_ANCHOR_COUNT={text.count(old)}')
    text = text.replace(old, new, 1)

if 'autopilotVersionV6194                    = "v6.19.8"' in text:
    text = text.replace(
        'autopilotVersionV6194                    = "v6.19.8"',
        'autopilotVersionV6194                    = "v6.19.9"',
        1,
    )
elif 'autopilotVersionV6194                    = "v6.19.9"' not in text:
    raise SystemExit('V6199_AUTOPILOT_VERSION_ANCHOR_MISSING')

AUTOPILOT.write_text(text, encoding='utf-8')
print('RADAR_V6199_AUTOPILOT_TARGETED_HISTORY=READY')
