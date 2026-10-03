#!/usr/bin/env python3
from pathlib import Path

root=Path(__file__).resolve().parents[2]
src=(root/'dev-hub/guardian/worker.js').read_text(encoding='utf-8')

required=[
 'async function resolveFunctionalContractDriftRemediations',
 'async function applyFunctionalRemediation',
 'explicit_apply_authorization_required',
 'const resolvedFunctionalDriftRemediations=0;',
 'Evaluation is side-effect free with respect to remediation/holds/alerts.',
 'Remediation application is a separate, explicitly authorized lifecycle event.',
 'UPDATE remediation_holds SET active=0',
 "UPDATE guardian_alerts SET status='ACKED'",
 'source:"corrected-functional-acceptance"',
]
for token in required:
    assert token in src, token

call='await resolveFunctionalContractDriftRemediations(env,{projectId:String(row.project_id),revision:String(row.revision),receiptId,contractId:String(row.contract_id),contractDigest:String(row.contract_digest)})'
assert src.count(call)==1, src.count(call)
assert src.index(call) > src.index('async function applyFunctionalRemediation')
print('CHACHA_DEV_GUARDIAN_FUNCTIONAL_DRIFT_RECONCILIATION=PASS')
print('CHACHA_DEV_GUARDIAN_FUNCTIONAL_REMEDIATION_EXPLICIT_APPLY=PASS')
print('CHACHA_DEV_AUTOMATIC_EXTERNAL_SPEND_EUR=0')
