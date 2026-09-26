#!/usr/bin/env python3
from __future__ import annotations
import importlib.util,json,sys,tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BIN=ROOT/'dev-hub/bin'
sys.path.insert(0,str(BIN))

def mod(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(spec);assert spec and spec.loader
    spec.loader.exec_module(m);return m

odr=mod('odr',BIN/'operator_directive_registry.py')
impact=mod('impact',BIN/'directive_impact_analyzer.py')
prop=mod('prop',BIN/'policy_propagation_engine.py')
vca=mod('vca',BIN/'version_coupling_audit.py')
canon=mod('canon',BIN/'canonical_component_registry.py')
gate=mod('gate',BIN/'universal-materialization-gate.py')

policy=json.load(open(ROOT/'dev-hub/config/operator-directives.v1.json'))
directives=odr.snapshot(policy)
assert directives['active_global_directive_count']>=9
required={'opdir-version-agnostic-runtime','opdir-universal-materialization',
          'opdir-canonical-inventory','opdir-universal-hygiene'}
assert required.issubset(set(directives['active_global_ids']))
canonical_policy=json.load(open(ROOT/'dev-hub/config/canonical-component-registry.v1.json'))
registry=canon.build_registry(ROOT,canonical_policy)
assert registry['birth_contract_complete'] is True
assert registry['active_global_directive_digest']==directives['active_global_digest']
assert registry['component_count']>=190
for row in registry['components']:
    controls=row['birth_contract']['controls']
    value=controls['operator_directives']['value']
    assert value['active_global_digest']==directives['active_global_digest']
    assert sorted(value['active_global_ids'])==sorted(directives['active_global_ids'])

catalog=json.load(open(ROOT/'dev-hub/config/operator-directive-sinks.v1.json'))
report=impact.analyze(ROOT,directives,catalog)
assert report['status']=='PASS',report
assert report['missing_target_count']==0,report
receipt=prop.verify(directives,report,registry)
assert receipt['status']=='VERIFIED',receipt
assert receipt['verified_component_count']==registry['component_count']
version_report=vca.audit(ROOT/'dev-hub')
assert version_report['status']=='PASS',version_report['blocking']
assert version_report['blocking_count']==0

manifest={
  'agent_id':'fixture-agent','governance_class':'FULL_AGENT','owner_foundry':'agent-foundry',
  'materialization_gate_required':True,'purpose':'fixture','scope':'PLATFORM',
  'automatic_external_spend_eur':0
}
view=gate.materialization_view(manifest)
verdict=gate.validate(view,manifest,canonical_policy,directives)
assert verdict['status']=='PASS',verdict
birth=verdict['birth_contract']
value=birth['controls']['operator_directives']['value']
assert value['active_global_digest']==directives['active_global_digest']
assert sorted(value['active_global_ids'])==sorted(directives['active_global_ids'])

for cfg in ('agent-foundry.v1.json','branch-foundry.v1.json','capability-foundry.v1.json','object-factory.v1.json'):
    text=(ROOT/'dev-hub/config'/cfg).read_text()
    assert 'canonical_component_registry_required' in text,cfg
    assert 'universal_materialization_gate_required' in text,cfg
    assert 'birth_contract_required' in text,cfg
print('CHACHA_DEV_OPERATOR_DIRECTIVE_REGISTRY=PASS')
print('CHACHA_DEV_DIRECTIVE_IMPACT_ANALYZER=PASS')
print('CHACHA_DEV_GLOBAL_POLICY_PROPAGATION=PASS')
print('CHACHA_DEV_EXISTING_COMPONENT_BACKFILL=PASS')
print('CHACHA_DEV_UNIVERSAL_MATERIALIZATION_GATE=PASS')
print('CHACHA_DEV_ALL_FOUNDRIES_USE_BIRTH_CONTRACT=PASS')
print('CHACHA_DEV_NO_ACTIVE_VERSION_MAJOR_COUPLING=PASS')
print('CHACHA_DEV_LEGACY_VERSION_REFERENCE_CLASSIFICATION=PASS')
print('CHACHA_DEV_AUTOMATIC_EXTERNAL_SPEND_EUR=0')
