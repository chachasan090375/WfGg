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

# Centralize robust terminalization in the existing fail path. This avoids
# depending on the exact formatting of seven historical error call-sites.
if 'WFGG_RADAR_COLLECTOR_CYCLE_TERMINALIZATION_CALLSITE_V6198' not in text:
    fail_anchor = '''\t// WFGG_RADAR_FEDERATED_DIAGNOSTICS_V65
\tfail := func(code string, causes ...error) {
'''
    if text.count(fail_anchor) != 1:
        raise SystemExit(f'V6198_FAIL_CLOSURE_ANCHOR_COUNT={text.count(fail_anchor)}')
    fail_repl = '''\t// WFGG_RADAR_FEDERATED_DIAGNOSTICS_V65
\t// WFGG_RADAR_COLLECTOR_CYCLE_TERMINALIZATION_CALLSITE_V6198
\tvar cycleIDV6198 int64
\tvar ownsCycleV6198 bool
\tfail := func(code string, causes ...error) {
'''
    text = text.replace(fail_anchor, fail_repl, 1)

    cause_anchor = '''\t\tif len(causes) > 0 {
\t\t\tcause = causes[0]
\t\t}
\t\tradarCollectorJobs.update(jobID, func(j *collectorJob) {
'''
    if text.count(cause_anchor) != 1:
        raise SystemExit(f'V6198_CAUSE_ANCHOR_COUNT={text.count(cause_anchor)}')
    cause_repl = '''\t\tif len(causes) > 0 {
\t\t\tcause = causes[0]
\t\t}
\t\tif ownsCycleV6198 && cycleIDV6198 > 0 {
\t\t\tif terminalErr := collectorFinishCycleReliableV6198(cycleIDV6198, "FAILED", code); terminalErr != nil {
\t\t\t\tif cause != nil {
\t\t\t\t\tcause = fmt.Errorf("%v; %w", cause, terminalErr)
\t\t\t\t} else {
\t\t\t\t\tcause = terminalErr
\t\t\t\t}
\t\t\t\tcode = code + "_CYCLE_TERMINALIZATION_FAILED"
\t\t\t}
\t\t}
\t\tradarCollectorJobs.update(jobID, func(j *collectorJob) {
'''
    text = text.replace(cause_anchor, cause_repl, 1)

    ownership_anchor = '''\tradarCollectorJobs.update(jobID, func(j *collectorJob) { j.CycleID = cycle.ID; j.Joined = joined })

\tif joined {
'''
    if text.count(ownership_anchor) != 1:
        raise SystemExit(f'V6198_OWNERSHIP_ANCHOR_COUNT={text.count(ownership_anchor)}')
    ownership_repl = '''\tradarCollectorJobs.update(jobID, func(j *collectorJob) { j.CycleID = cycle.ID; j.Joined = joined })
\tcycleIDV6198 = cycle.ID
\townsCycleV6198 = !joined

\tif joined {
'''
    text = text.replace(ownership_anchor, ownership_repl, 1)

success_old = '''\tif err := collectorFinishCycle(ctx, cycle.ID, "SUCCESS", ""); err != nil {
\t\tfail("COLLECTOR_CYCLE_FINISH_FAILED", err)
\t\treturn
\t}'''
success_new = '''\tif err := collectorFinishCycleReliableV6198(cycle.ID, "SUCCESS", ""); err != nil {
\t\tfail("COLLECTOR_CYCLE_FINISH_FAILED", err)
\t\treturn
\t}'''
if success_old in text:
    text = text.replace(success_old, success_new, 1)
elif success_new not in text:
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
