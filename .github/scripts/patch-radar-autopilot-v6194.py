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
quality_marker = 'WFGG_RADAR_PARTIAL_CYCLE_QUALITY_MARKER_V6194'
if quality_marker not in jobs:
    old = '''\tradarCollectorJobs.update(jobID, func(j *collectorJob) { j.Phase = "FINALIZING" })
\tif err := collectorFinishCycle(ctx, cycle.ID, "SUCCESS", ""); err != nil {
'''
    if jobs.count(old) != 1:
        raise SystemExit(f'V6194_FINALIZE_ANCHOR_COUNT={jobs.count(old)}')
    new = '''\tradarCollectorJobs.update(jobID, func(j *collectorJob) { j.Phase = "FINALIZING" })
\t// WFGG_RADAR_PARTIAL_CYCLE_QUALITY_MARKER_V6194
\t// Keep valid observations, but mark a region-isolated cycle so V6.17 quality
\t// gating cannot accidentally use it as cluster-confirmation evidence.
\tfinishMarker := ""
\tif current, ok := radarCollectorJobs.get(jobID); ok && current.RegionsFailed > 0 {
\t\tfinishMarker = "PARTIAL_REGIONS"
\t}
\tif err := collectorFinishCycle(ctx, cycle.ID, "SUCCESS", finishMarker); err != nil {
'''
    jobs = jobs.replace(old, new, 1)
    JOBS.write_text(jobs, encoding='utf-8')
    print('RADAR_V6194_PARTIAL_QUALITY_MARKER=PATCHED')
else:
    print('RADAR_V6194_PARTIAL_QUALITY_MARKER=ALREADY_PRESENT')

print('RADAR_V6194_AUTOPILOT=READY')
