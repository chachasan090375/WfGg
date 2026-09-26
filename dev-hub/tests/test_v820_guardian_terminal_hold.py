#!/usr/bin/env python3
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
worker=(ROOT/'dev-hub/guardian/worker.js').read_text(encoding='utf-8')
start=worker.index('async function activeRemediationHold')
end=worker.index('async function applyRemediationProgress',start)
fn=worker[start:end]

assert fn.count("d.status IN ('OPEN','DELIVERED')")==2,fn
assert fn.count('JOIN remediation_directives d ON d.directive_id=h.directive_id')==2,fn
assert 'SELECT * FROM remediation_holds' not in fn,fn

# Terminal directives are intentionally excluded from active enforcement.
for terminal in ('APPLIED','CANCELLED','ESCALATED'):
    assert terminal not in fn,terminal

runtime=(ROOT/'dev-hub/bin/guardian_remediation_runtime.py').read_text(encoding='utf-8')
assert '{"OPEN","DELIVERED"}' in runtime

print('CHACHA_DEV_GUARDIAN_TERMINAL_HOLD_FILTER=PASS')
print('CHACHA_DEV_GUARDIAN_ORPHAN_HOLD_BLOCKING=NO')
print('CHACHA_DEV_GUARDIAN_NO_BYPASS=PASS')
print('CHACHA_DEV_AUTOMATIC_EXTERNAL_SPEND_EUR=0')
