#!/usr/bin/env python3
from __future__ import annotations
import importlib.util,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def load(rel):return json.loads((ROOT/rel).read_text())
def mod():
 p=ROOT/'dev-hub/bin/execution-planner.py';s=importlib.util.spec_from_file_location('e',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
M=mod();P=load('dev-hub/config/execution-planner.v1.json')
def composition(blocked=False):return {'project_id':'clean','execution_blocked':blocked,'solution_graph':{'nodes':[
 {'node_id':'root','node_kind':'project','classification':{'deliverable_class':'application'},'dependencies':[]},
 {'node_id':'api','parent_id':'root','node_kind':'module','classification':{'deliverable_class':'application'},'dependencies':[]},
 {'node_id':'backend','parent_id':'root','node_kind':'module','classification':{'deliverable_class':'application'},'dependencies':[]},
 {'node_id':'reporting','parent_id':'root','node_kind':'module','classification':{'deliverable_class':'data_artifact'},'dependencies':['backend']}
]},'interfaces':[{'source':'api','target':'backend','kind':'api','contract':'users-v1'}]}
def specialists(gaps=None):return {'reused_capabilities':[
 {'node_id':'api','capability_id':'code-edit'},{'node_id':'backend','capability_id':'code-edit'},{'node_id':'reporting','capability_id':'data-model-review'}],
 'specialist_cells':[{'node_id':'api','domain_id':'development'},{'node_id':'backend','domain_id':'development'},{'node_id':'backend','domain_id':'data-backend'},{'node_id':'reporting','domain_id':'data-backend'}],
 'foundry_gap_requests':gaps or []}

def byid(o):return {x['task_id']:x for x in o['task_graph']['tasks']}
def test_interface_contract_precedes_both_module_implementations():
 o=M.compile_plan(composition(),specialists(),P);r=byid(o);cid=next(x for x in r if x.startswith('contract:api:backend'))
 assert cid in r['implement:api']['depends_on'] and cid in r['implement:backend']['depends_on'];assert r[cid]['task_kind']=='INTERFACE_CONTRACT'
def test_hard_module_dependency_is_preserved():
 o=M.compile_plan(composition(),specialists(),P);r=byid(o);assert 'implement:backend' in r['implement:reporting']['depends_on']
def test_integration_and_verification_are_barriers():
 o=M.compile_plan(composition(),specialists(),P);r=byid(o);assert r['integration:project']['integration_barrier'] is True;assert set(r['integration:project']['depends_on'])=={'implement:api','implement:backend','implement:reporting'};assert r['verification:project']['depends_on']==['integration:project'] and r['verification:project']['integration_barrier'] is True
def test_each_task_has_exactly_one_runtime_capability():
 o=M.compile_plan(composition(),specialists(),P);assert o['one_runtime_capability_per_task'] is True;assert all(len(x['capabilities'])==1 and x['runtime_capability']==x['capabilities'][0] for x in o['task_graph']['tasks'])
def test_clean_plan_is_execution_ready_but_planner_does_not_execute():
 o=M.compile_plan(composition(),specialists(),P);assert o['status']=='PASS' and o['execution_allowed'] is True;assert o['foundry_invoked'] is False and o['execution_authority'] is False
def test_foundry_gap_blocks_execution_without_invoking_foundry():
 gaps=[{'node_id':'api','kind':'CAPABILITY','requested_id':'missing-cap','state':'FOUNDRY_GAP_REQUEST'}];o=M.compile_plan(composition(),specialists(gaps),P);assert o['status']=='BLOCKED';assert 'FOUNDRY_GAPS_UNRESOLVED' in o['blockers'];assert o['foundry_invoked'] is False
def test_not_fit_feasibility_blocks_execution_even_with_clean_specialists():
 o=M.compile_plan(composition(True),specialists(),P);assert 'INFRASTRUCTURE_FEASIBILITY_BLOCKS_EXECUTION' in o['blockers'] and o['execution_allowed'] is False
def test_resource_profiles_grow_with_specialist_cell_count():
 o=M.compile_plan(composition(),specialists(),P);r=byid(o);assert r['implement:backend']['resources']['ram_gib']>r['implement:api']['resources']['ram_gib']
def test_no_production_authority_or_external_spend():
 o=M.compile_plan(composition(),specialists(),P);assert o['production_authority'] is False and o['automatic_external_spend_eur']==0
def test_birth_contract_is_shadow_and_umg_required():
 b=load('dev-hub/config/execution-planner.birth.v1.json');assert b['materialization_gate_required'] is True and b['production_activation_authorized'] is False and b['owner_foundry']=='branch-foundry'
if __name__=='__main__':
 tests=[(n,v) for n,v in sorted(globals().items()) if n.startswith('test_') and callable(v)]
 for n,f in tests:f();print(n+'=PASS')
 print('CHACHA_DEV_EXECUTION_PLANNER=PASS');print('TEST_COUNT='+str(len(tests)));print('EXECUTION_AUTHORITY=NO');print('AUTOMATIC_EXTERNAL_SPEND_EUR=0')
