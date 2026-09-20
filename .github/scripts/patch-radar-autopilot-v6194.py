#!/usr/bin/env python3
from pathlib import Path
import shutil

ROOT = Path('/tmp/wfgg-radar')
MAIN = ROOT / 'connector-go/cmd/radar-connector/main.go'
JOBS = ROOT / 'connector-go/cmd/radar-connector/collector_jobs.go'
SRC = Path('.radar-release-src/v6194-source/connector-go/cmd/radar-connector')
DST = ROOT / 'connector-go/cmd/radar-connector'

for name in ('server_autopilot_v6194.go', 'server_autopilot_v6194_test.go'):
    src = SRC / name
    dst = DST / name
    if not src.is_file():
        raise SystemExit(f'V6194_SOURCE_MISSING={src}')
    shutil.copyfile(src, dst)

text = MAIN.read_text(encoding='utf-8')
marker = 'WFGG_RADAR_AUTOPILOT_ROUTE_V6194'
if marker not in text:
    anchor = '\t// WFGG_RADAR_SEED_SCOUT_ROUTE_V6193\n\t'
    pos = text.find(anchor)
    if pos < 0:
        raise SystemExit('V6194_ROUTE_ANCHOR_MISSING')
    line_end = text.find('\n', pos + len(anchor))
    line2_end = text.find('\n', line_end + 1)
    if line_end < 0 or line2_end < 0:
        raise SystemExit('V6194_ROUTE_BLOCK_INVALID')
    addition = (
        '\t// WFGG_RADAR_AUTOPILOT_ROUTE_V6194\n'
        '\tmux.HandleFunc("POST /v1/collector/autopilot/start", s.signed(s.serverAutopilotStartV6194))\n'
        '\tmux.HandleFunc("GET /v1/collector/autopilot/status", s.signed(s.serverAutopilotStatusV6194))\n'
        '\tmux.HandleFunc("POST /v1/collector/autopilot/stop", s.signed(s.serverAutopilotStopV6194))\n'
    )
    text = text[:line2_end+1] + addition + text[line2_end+1:]
    MAIN.write_text(text, encoding='utf-8')
    print('RADAR_V6194_AUTOPILOT_ROUTE=PATCHED')
else:
    print('RADAR_V6194_AUTOPILOT_ROUTE=ALREADY_PRESENT')

jobs = JOBS.read_text(encoding='utf-8')
# V6.17 already persists region-isolated cycles with a non-empty error marker,
# which is exactly the quality invariant Autopilot requires. Reuse that
# established gate instead of introducing a second partial-cycle semantic.
if 'WFGG_RADAR_PARTIAL_CYCLE_MARKER_V617' not in jobs:
    raise SystemExit('V6194_REQUIRES_V617_PARTIAL_QUALITY_MARKER')
print('RADAR_V6194_PARTIAL_QUALITY_MARKER=V617_REUSED')

print('RADAR_V6194_AUTOPILOT=READY')
