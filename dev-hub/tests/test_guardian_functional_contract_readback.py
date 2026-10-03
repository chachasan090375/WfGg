#!/usr/bin/env python3
from pathlib import Path
root=Path(__file__).resolve().parents[2]
worker=(root/'dev-hub/guardian/worker.js').read_text()
client=(root/'dev-hub/bin/guardian-client.py').read_text()
for token in ['async function readbackFunctionalContractPin','chacha.dev/guardian-functional-contract-readback-request/v1','SELECT project_id,contract_id,contract_digest,contract_json,pinned_at FROM project_functional_contracts WHERE project_id=?1','authority:"guardian-external-worker",read_only:true,direct_mutation:false','/v1/functional-contracts/readback']:
    assert token in worker,token
scope=worker[worker.index('async function readbackFunctionalContractPin'):worker.index('async function functionalAcceptance')]
assert 'UPDATE project_functional_contracts' not in scope
assert 'INSERT INTO project_functional_contracts' not in scope
for token in ['def functional_contract_readback','functional-contract-readback','/v1/functional-contracts/readback','x.get("direct_mutation") is False']:
    assert token in client,token
print('CHACHA_DEV_GUARDIAN_FUNCTIONAL_CONTRACT_READBACK=PASS')
print('CHACHA_DEV_GUARDIAN_FUNCTIONAL_CONTRACT_READBACK_READ_ONLY=PASS')
print('CHACHA_DEV_AUTOMATIC_EXTERNAL_SPEND_EUR=0')
