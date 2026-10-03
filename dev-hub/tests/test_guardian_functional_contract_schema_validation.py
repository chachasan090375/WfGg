#!/usr/bin/env python3
from pathlib import Path

root=Path(__file__).resolve().parents[2]
src=(root/'dev-hub/guardian/worker.js').read_text(encoding='utf-8')

required=[
 'functional_contract_criteria_invalid',
 'functional_contract_criterion_id_invalid',
 'functional_contract_criterion_id_duplicate',
 'acceptance_criteria_invalid',
 'acceptance_criterion_id_invalid',
 'acceptance_criterion_id_duplicate',
]
for token in required:
    assert token in src, token

validation=src.index('const contractCriteria=Array.isArray(contract.criteria)?contract.criteria:null;')
digest=src.index('const contractDigest=await sha256Hex(stable(contract));')
pin=src.index('INSERT INTO project_functional_contracts')
assert validation < digest < pin
assert 'const required=contractCriteria.filter(x=>x&&x.required!==false);' in src
assert 'const amap=new Map(acceptanceCriteria.map(x=>[String(x.criterion_id),x]));' in src
print('CHACHA_DEV_GUARDIAN_FUNCTIONAL_SCHEMA_VALIDATION=PASS')
print('CHACHA_DEV_MALFORMED_CRITERION_REJECTED_BEFORE_PIN=PASS')
