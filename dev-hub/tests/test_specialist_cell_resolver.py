#!/usr/bin/env python3
from __future__ import annotations
import importlib.util,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def load(rel):return json.loads((ROOT/rel).read_text())
def mod():
 p=ROOT/'dev-hub/bin/specialist-cell-resolver.py';s=importlib.util.spec_from_file_location('resolver',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
M=mod();D=load('dev-hub/config/domain-orchestration.v1.json');C=load('dev-hub/config/capability-registry.v1.json');P=load('dev-hub/config/specialist-cell-resolver.v1.json')

def graph():return {'project_id':'x','nodes':[
 {'node_id':'backend','domain_requirements':['development','data-backend','cybersecurity'],'capability_requirements':['code-edit','future-magic-capability']},
 {'node_id':'docs','domain_requirements':['documentation','translation'],'capability_requirements':['documentation']},
 {'node_id':'unknown','domain_requirements':['quantum-domain'],'capability_requirements':[]}
]}
def bydomain(o):return {(x['node_id'],x['domain_id']):x for x in o['specialist_cells']}

def test_existing_domains_reference_canonical_head_and_arm_without_cloning():
 o=M.resolve(graph(),D,C,P);r=bydomain(o);x=r[('backend','data-backend')];assert x['head']['orchestrator']==D['domains']['data-backend']['orchestrator'];assert x['head']['memory_namespace']=='specialist:domain:data-backend';assert x['cloned'] is False

def test_existing_capability_is_reused_before_foundry():
 o=M.resolve(graph(),D,C,P);rows=[x for x in o['reused_capabilities'] if x['node_id']=='backend' and x['capability_id']=='code-edit'];assert len(rows)==1 and rows[0]['resolution']=='REUSE' and rows[0]['materialize_new'] is False

def test_missing_capability_creates_planning_only_foundry_gap():
 o=M.resolve(graph(),D,C,P);g=next(x for x in o['foundry_gap_requests'] if x['requested_id']=='future-magic-capability');assert g['owner_foundry']=='capability-foundry';assert g['materialized'] is False;assert o['foundry_invoked'] is False

def test_missing_domain_creates_agent_foundry_gap_without_agent_explosion():
 o=M.resolve(graph(),D,C,P);g=next(x for x in o['foundry_gap_requests'] if x['requested_id']=='quantum-domain');assert g['owner_foundry']=='agent-foundry' and g['materialized'] is False

def test_security_and_ux_transversal_support_are_contextual():
 o=M.resolve(graph(),D,C,P);r=bydomain(o);assert 'bastion' in r[('backend','cybersecurity')]['transversal_support'];assert 'logician' in r[('backend','development')]['transversal_support'];assert o['release_gate_support']==['guardian','sentinel']

def test_capability_refs_are_deduplicated_per_node():
 g=graph();g['nodes'][0]['domain_requirements']=['development','development'];o=M.resolve(g,D,C,P);assert len([x for x in o['specialist_cells'] if x['node_id']=='backend' and x['domain_id']=='development'])==1

def test_v6_agent_foundry_first_rule_is_explicitly_superseded_here():
 assert D['principles']['agent_foundry_precedes_all_domain_execution'] is True
 assert P['rules']['agent_foundry_precedes_all_domain_execution'] is False
 assert P['rules']['reuse_before_foundry'] is True and P['rules']['foundry_only_for_missing_domains_or_capabilities'] is True

def test_no_execution_production_or_spend_authority():
 o=M.resolve(graph(),D,C,P);assert o['execution_authority'] is False and o['production_authority'] is False and o['automatic_external_spend_eur']==0;assert o['automatic_materialization'] is False

def test_birth_contract_is_shadow_and_umg_required():
 b=load('dev-hub/config/specialist-cell-resolver.birth.v1.json');assert b['materialization_gate_required'] is True;assert b['owner_foundry']=='branch-foundry';assert b['production_activation_authorized'] is False

if __name__=='__main__':
 tests=[(n,v) for n,v in sorted(globals().items()) if n.startswith('test_') and callable(v)]
 for n,f in tests:f();print(n+'=PASS')
 print('CHACHA_DEV_SPECIALIST_CELL_RESOLVER=PASS');print('TEST_COUNT='+str(len(tests)));print('FOUNDRY_INVOKED=NO');print('AUTOMATIC_EXTERNAL_SPEND_EUR=0')
