#!/usr/bin/env python3
from pathlib import Path

ROOT = Path('/tmp/wfgg-radar')
WORKER = ROOT / 'src/worker.js'
AUTOPILOT = ROOT / 'connector-go/cmd/radar-connector/server_autopilot_v6194.go'
UI = ROOT / 'public/live-radar.html'

worker = WORKER.read_text(encoding='utf-8')
marker = '// WFGG_RADAR_AUTOPILOT_WORKER_COVERAGE_PROPAGATION_V61915'
if marker not in worker:
    old = """        const initialSeed = String(body.initialSeed || '').trim();
        const fullCyclesPerCluster = body.fullCyclesPerCluster == null ? 3 : Number(body.fullCyclesPerCluster);
        const maxClusters = body.maxClusters == null ? 5 : Number(body.maxClusters);
        if (!Number.isInteger(fullCyclesPerCluster) || fullCyclesPerCluster < 1 || fullCyclesPerCluster > 5) {
          throw Object.assign(new Error('AUTOPILOT_FULL_CYCLES_INVALID'), { status: 400 });
        }
        if (!Number.isInteger(maxClusters) || maxClusters < 1 || maxClusters > 20) {
          throw Object.assign(new Error('AUTOPILOT_MAX_CLUSTERS_INVALID'), { status: 400 });
        }
"""
    new = """        // WFGG_RADAR_AUTOPILOT_WORKER_COVERAGE_PROPAGATION_V61915
        const initialSeed = String(body.initialSeed || '').trim();
        const fullCyclesPerCluster = body.fullCyclesPerCluster == null ? 3 : Number(body.fullCyclesPerCluster);
        const coverageMode = body.coverageMode === true;
        const maxClusters = coverageMode ? 0 : (body.maxClusters == null ? 5 : Number(body.maxClusters));
        if (!Number.isInteger(fullCyclesPerCluster) || fullCyclesPerCluster < 1 || fullCyclesPerCluster > 5) {
          throw Object.assign(new Error('AUTOPILOT_FULL_CYCLES_INVALID'), { status: 400 });
        }
        if (!coverageMode && (!Number.isInteger(maxClusters) || maxClusters < 1 || maxClusters > 20)) {
          throw Object.assign(new Error('AUTOPILOT_MAX_CLUSTERS_INVALID'), { status: 400 });
        }
"""
    if worker.count(old) != 1:
        raise SystemExit(f'V61915_WORKER_PARSE_ANCHOR_COUNT={worker.count(old)}')
    worker = worker.replace(old, new, 1)

    old_options = """            initialSeed,
            fullCyclesPerCluster,
            maxClusters,
            partialRetryLimit: 5,
"""
    new_options = """            initialSeed,
            fullCyclesPerCluster,
            coverageMode,
            maxClusters,
            partialRetryLimit: 5,
"""
    if worker.count(old_options) != 1:
        raise SystemExit(f'V61915_WORKER_OPTIONS_ANCHOR_COUNT={worker.count(old_options)}')
    worker = worker.replace(old_options, new_options, 1)

WORKER.write_text(worker, encoding='utf-8')

autopilot = AUTOPILOT.read_text(encoding='utf-8')
old_version = 'autopilotVersionV6194                    = "v6.19.14"'
new_version = 'autopilotVersionV6194                    = "v6.19.15"'
if old_version in autopilot:
    autopilot = autopilot.replace(old_version, new_version, 1)
elif new_version not in autopilot:
    raise SystemExit('V61915_CONNECTOR_VERSION_ANCHOR_MISSING')
AUTOPILOT.write_text(autopilot, encoding='utf-8')

ui = UI.read_text(encoding='utf-8')
ui_marker = 'WFGG_RADAR_AUTOPILOT_WORKER_COVERAGE_PROPAGATION_UI_V61915'
if ui_marker not in ui:
    anchor = '<!-- WFGG_RADAR_AUTOPILOT_COVERAGE_COMPLETION_UI_V61914 -->'
    if ui.count(anchor) != 1:
        raise SystemExit(f'V61915_UI_MARKER_ANCHOR_COUNT={ui.count(anchor)}')
    ui = ui.replace(anchor, anchor + '\n  <!-- ' + ui_marker + ' -->', 1)
    old_title = '<span id="autopilotTitle" class="federated-title">AUTOPILOT V6.19.14 · ARRÊTÉ</span>'
    new_title = '<span id="autopilotTitle" class="federated-title">AUTOPILOT V6.19.15 · ARRÊTÉ</span>'
    if ui.count(old_title) != 1:
        raise SystemExit(f'V61915_UI_TITLE_ANCHOR_COUNT={ui.count(old_title)}')
    ui = ui.replace(old_title, new_title, 1)

UI.write_text(ui, encoding='utf-8')
print('RADAR_V61915_WORKER_COVERAGE_PROPAGATION=READY')
