#!/usr/bin/env python3
from __future__ import annotations
import json,subprocess,tempfile
from pathlib import Path

root=Path(__file__).resolve().parents[2]
worker=root/'dev-hub/guardian/worker.js'
src=worker.read_text(encoding='utf-8')
for token in [
 'functional_contract_criteria_invalid','functional_contract_criterion_id_invalid',
 'functional_contract_criterion_id_duplicate','functional_contract_criterion_id_ambiguous',
 'acceptance_criteria_invalid','acceptance_criterion_id_invalid','acceptance_criterion_id_duplicate',
 'legacy_pinned_contract_compatibility','legacy_pinned_criterion_aliases'
]:
    assert token in src,token
normalize=src.index('const normalizedContract=normalizeFunctionalContractCriteria(contract.criteria,exactPinnedContract);')
pin_insert=src.index('INSERT INTO project_functional_contracts')
assert normalize < pin_insert
with tempfile.TemporaryDirectory(prefix='guardian-functional-schema-') as td:
    module=Path(td)/'worker.mjs';module.write_text(src,encoding='utf-8')
    probe=Path(td)/'probe.mjs'
    probe.write_text(
        'import {normalizeFunctionalContractCriteria as n} from '+json.dumps(module.as_uri())+';\n'
        "function ok(v,label){if(!v){console.error('FAIL',label);process.exit(2)}console.log(label+'=PASS')}\n"
        "let x=n([{id:'legacy-only',required:true}],false);ok(!x.ok&&x.error==='functional_contract_criterion_id_invalid','NEW_LEGACY_REJECTED');\n"
        "x=n([{id:'legacy-only',required:true}],true);ok(x.ok&&x.criteria[0].criterion_id==='legacy-only'&&x.legacy_alias_count===1,'EXACT_PIN_LEGACY_ACCEPTED');\n"
        "x=n([{criterion_id:'canonical',required:true}],false);ok(x.ok&&x.legacy_alias_count===0,'CANONICAL_ACCEPTED');\n"
        "x=n([{criterion_id:'a',id:'b'}],true);ok(!x.ok&&x.error==='functional_contract_criterion_id_ambiguous','AMBIGUOUS_REJECTED');\n",
        encoding='utf-8')
    r=subprocess.run(['node',str(probe)],text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    assert r.returncode==0,(r.stdout,r.stderr)
    print(r.stdout.strip())
print('CHACHA_DEV_GUARDIAN_FUNCTIONAL_SCHEMA_VALIDATION=PASS')
print('CHACHA_DEV_NEW_MALFORMED_CRITERION_REJECTED_BEFORE_PIN=PASS')
print('CHACHA_DEV_EXACT_PIN_LEGACY_COMPATIBILITY=PASS')
