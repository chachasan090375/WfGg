#!/usr/bin/env python3
import importlib.util,json,tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
MOD=ROOT/'bin/guardian-governed-deploy-transaction.py'
spec=importlib.util.spec_from_file_location('gdt',MOD);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
POL=json.load(open(ROOT/'config/guardian-governed-deploy-transaction.v1.json'))
REV='a'*40;TREE='b'*40

def test_plan_is_non_mutating_and_bounded():
    x=m.plan(POL,REV,TREE)
    assert x['status']=='PREPARED_NOT_AUTHORIZED'
    assert x['scope']=='GUARDIAN_EXTERNAL_PLANE_ONLY'
    assert 'PLATFORM_CURRENT_SWITCH' in x['forbidden']
    assert x['automatic_external_spend_eur']==0

def test_bad_revision_blocks():
    try:m.plan(POL,'bad',TREE)
    except ValueError as e:assert 'REVISION_INVALID' in str(e)
    else:raise AssertionError('bad revision accepted')

def test_snapshot_and_restore_are_deterministic():
    with tempfile.TemporaryDirectory() as td:
        d=Path(td)
        (d/'worker-deployments.json').write_text('[{"id":"v1"}]\n')
        (d/'role_contracts.json').write_text('[{"results":[{"contract_id":"r1","kind":"role"}]}]\n')
        (d/'expected_components.json').write_text('[{"results":[{"component_id":"c1","role":"x"}]}]\n')
        man=m.snapshot_manifest(POL,d);assert man['status']=='PASS' and len(man['files'])==3
        out=d/'restore.sql';rec=m.build_restore(POL,d,out)
        text=out.read_text();assert 'DELETE FROM role_contracts;' in text
        assert "INSERT INTO expected_components" in text
        assert rec['restore_digest']==m.sha(out)
