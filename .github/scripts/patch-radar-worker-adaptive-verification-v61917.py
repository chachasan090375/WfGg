#!/usr/bin/env python3
from pathlib import Path

WORKER = Path('/tmp/wfgg-radar/src/worker.js')
worker = WORKER.read_text(encoding='utf-8')
marker = '// WFGG_RADAR_AUTOPILOT_ADAPTIVE_VERIFICATION_WORKER_V61917'

if marker not in worker:
    old_helper = """// WFGG_RADAR_AUTOPILOT_WORKER_COVERAGE_PROPAGATION_V61915
function normalizeAutopilotStartOptionsV61915(body = {}) {
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
  return { initialSeed, fullCyclesPerCluster, coverageMode, maxClusters };
}
"""
    new_helper = """// WFGG_RADAR_AUTOPILOT_WORKER_COVERAGE_PROPAGATION_V61915
// WFGG_RADAR_AUTOPILOT_ADAPTIVE_VERIFICATION_WORKER_V61917
function normalizeAutopilotStartOptionsV61915(body = {}) {
  const initialSeed = String(body.initialSeed || '').trim();
  const coverageMode = body.coverageMode === true;
  const adaptiveVerification = body.adaptiveVerification === true;
  const requestedCycles = body.fullCyclesPerCluster == null ? (adaptiveVerification ? 1 : 3) : Number(body.fullCyclesPerCluster);
  const fullCyclesPerCluster = adaptiveVerification ? 1 : requestedCycles;
  const maxClusters = coverageMode ? 0 : (body.maxClusters == null ? 5 : Number(body.maxClusters));
  if (!Number.isInteger(requestedCycles) || requestedCycles < 1 || requestedCycles > 5) {
    throw Object.assign(new Error('AUTOPILOT_FULL_CYCLES_INVALID'), { status: 400 });
  }
  if (adaptiveVerification && requestedCycles !== 1) {
    throw Object.assign(new Error('AUTOPILOT_ADAPTIVE_FULL_CYCLES_CONFLICT_V61917'), { status: 400 });
  }
  if (!coverageMode && (!Number.isInteger(maxClusters) || maxClusters < 1 || maxClusters > 20)) {
    throw Object.assign(new Error('AUTOPILOT_MAX_CLUSTERS_INVALID'), { status: 400 });
  }
  return { initialSeed, fullCyclesPerCluster, adaptiveVerification, coverageMode, maxClusters };
}
"""
    if worker.count(old_helper) != 1:
        raise SystemExit(f'V61917_WORKER_HELPER_ANCHOR_COUNT={worker.count(old_helper)}')
    worker = worker.replace(old_helper, new_helper, 1)

    old_destruct = '        const { initialSeed, fullCyclesPerCluster, coverageMode, maxClusters } = normalizeAutopilotStartOptionsV61915(body);\n'
    new_destruct = '        const { initialSeed, fullCyclesPerCluster, adaptiveVerification, coverageMode, maxClusters } = normalizeAutopilotStartOptionsV61915(body);\n'
    if worker.count(old_destruct) != 1:
        raise SystemExit(f'V61917_WORKER_DESTRUCT_ANCHOR_COUNT={worker.count(old_destruct)}')
    worker = worker.replace(old_destruct, new_destruct, 1)

    options_anchor = """            initialSeed,
            fullCyclesPerCluster,
            coverageMode,
            maxClusters,
"""
    if worker.count(options_anchor) != 1:
        raise SystemExit(f'V61917_WORKER_OPTIONS_ANCHOR_COUNT={worker.count(options_anchor)}')
    worker = worker.replace(
        options_anchor,
        """            initialSeed,
            fullCyclesPerCluster,
            adaptiveVerification,
            coverageMode,
            maxClusters,
""",
        1,
    )

WORKER.write_text(worker, encoding='utf-8')
print('RADAR_V61917_WORKER_ADAPTIVE_VERIFICATION=READY')
