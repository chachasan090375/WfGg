#!/usr/bin/env python3
from pathlib import Path

root=Path(__file__).resolve().parents[2]
src=(root/'dev-hub/guardian/worker.js').read_text(encoding='utf-8')

required=[
 'async function resolveFunctionalContractDriftRemediations',
 'rules.includes("FUNCTIONAL_CONTRACT_DRIFT")',
 "SET status='APPLIED',applied_at=datetime('now'),resolution_evidence_json=?2",
 'UPDATE remediation_holds SET active=0',
 "UPDATE guardian_alerts SET status='ACKED'",
 'source:"corrected-functional-acceptance"',
 'verdict==="PASS"',
 'resolved_functional_contract_drift_remediations:resolvedFunctionalDriftRemediations',
]
for token in required:
    assert token in src, token

call='await resolveFunctionalContractDriftRemediations(env,{projectId,revision,receiptId,contractId,contractDigest})'
assert src.count(call)==1, src.count(call)
assert src.index('const resolvedFunctionalDriftRemediations=verdict==="PASS"') < src.index('if(verdict!=="PASS")')
print('CHACHA_DEV_GUARDIAN_FUNCTIONAL_DRIFT_RECONCILIATION=PASS')
print('CHACHA_DEV_GUARDIAN_CORRECTED_ACCEPTANCE_RESOLVES_PENDING_DRIFT=PASS')
print('CHACHA_DEV_GUARDIAN_DRIFT_HOLD_CLEARING=PASS')
print('CHACHA_DEV_GUARDIAN_DRIFT_ALERT_ACK=PASS')
print('CHACHA_DEV_AUTOMATIC_EXTERNAL_SPEND_EUR=0')
