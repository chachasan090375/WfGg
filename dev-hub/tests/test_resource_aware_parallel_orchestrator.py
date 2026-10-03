#!/usr/bin/env python3
from __future__ import annotations
import importlib.util,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def load(rel):return json.loads((ROOT/rel).read_text())
def mod():
 p=ROOT/'dev-hub/bin/resource-aware-parallel-orchestrator.py';s=importlib.util.spec_from_file_location('r',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
M=mod();P=load('dev-hub/config/resource-aware-parallel-orchestrator.v1.json')
def host(cpu=4,ram=8,host_id='h1',roles=None,pressure=None):return {'host_id':host_id,'health':'PASS','roles':roles or ['build'],'usable_capacity':{'cpu_cores':cpu,'ram_gib':ram,'gpu_vram_gib':0,'storage_io_units':100,'network_mbps':1000},'pressure':pressure or {}}
def task(tid,deps=None,cpu=1,ram=1,mins=10,contract='STABLE',priority=0,roles=None,barrier=False):return {'task_id':tid,'depends_on':deps or [],'resources':{'cpu_cores':cpu,'ram_gib':ram},'estimated_minutes':mins,'interface_contract_state':contract,'priority':priority,'required_host_roles':roles or ['build'],'integration_barrier':barrier}
def plan(tasks,hosts):return M.plan({'project_id':'p','tasks':tasks},{'hosts':hosts},P)

def test_independent_api_backend_docs_run_same_wave_when_resources_fit():
 o=plan([task('api',cpu=1,ram=1),task('backend',cpu=1,ram=1),task('docs',cpu=.5,ram=.5)], [host(cpu=3,ram=4)])
 assert o['status']=='PASS';assert o['waves'][0]['parallel_task_count']==3;assert {x['task_id'] for x in o['waves'][0]['assignments']}=={'api','backend','docs'}

def test_dependency_and_integration_barrier_wait_for_prior_wave():
 o=plan([task('api'),task('backend'),task('integration',['api','backend'],barrier=True)], [host(cpu=4,ram=8)])
 assert len(o['waves'])==2;assert {x['task_id'] for x in o['waves'][0]['assignments']}=={'api','backend'};assert o['waves'][1]['assignments'][0]['task_id']=='integration';assert o['waves'][1]['assignments'][0]['integration_barrier'] is True

def test_resource_limit_serializes_without_fixed_worker_count():
 o=plan([task('a',cpu=1,ram=1),task('b',cpu=1,ram=1)], [host(cpu=1,ram=2)])
 assert [w['parallel_task_count'] for w in o['waves']]==[1,1];assert o['fixed_max_workers_used'] is False and o['adaptive_worker_count']==1

def test_unstable_interface_contract_fails_closed_for_that_task():
 o=plan([task('api',contract='UNSTABLE'),task('docs',cpu=.5,ram=.5)], [host()])
 assert o['status']=='PARTIAL';assert o['planned_task_count']==1;assert any(x['task_id']=='api' and x['reason']=='INTERFACE_CONTRACT_UNSTABLE' for x in o['remaining_tasks'])

def test_critical_path_wins_when_only_one_ready_task_fits():
 tasks=[task('short',cpu=1,ram=1,mins=2),task('critical',cpu=1,ram=1,mins=2),task('downstream',['critical'],cpu=1,ram=1,mins=20)]
 o=plan(tasks,[host(cpu=1,ram=2)]);assert o['waves'][0]['assignments'][0]['task_id']=='critical';assert o['critical_path_scores']['critical']>o['critical_path_scores']['short']

def test_multiple_hosts_expand_parallelism_and_respect_roles():
 tasks=[task('linux-a',roles=['linux']),task('linux-b',roles=['linux']),task('apple',roles=['apple'])]
 hosts=[host(cpu=1,ram=2,host_id='linux1',roles=['build','linux']),host(cpu=1,ram=2,host_id='linux2',roles=['build','linux']),host(cpu=1,ram=2,host_id='mac1',roles=['build','apple'])]
 o=plan(tasks,hosts);assert o['waves'][0]['parallel_task_count']==3;assert next(x for x in o['waves'][0]['assignments'] if x['task_id']=='apple')['host_id']=='mac1'

def test_live_pressure_reduces_effective_parallel_capacity():
 h=host(cpu=4,ram=8,pressure={'cpu_cores':.75,'ram_gib':.5});o=plan([task('a',cpu=1,ram=2),task('b',cpu=1,ram=2)],[h]);assert [w['parallel_task_count'] for w in o['waves']]==[1,1]

def test_oversized_task_is_resource_unfit_and_remains_unplanned():
 o=plan([task('gpu-ish',cpu=8,ram=32)], [host(cpu=4,ram=8)]);assert o['status']=='PARTIAL';assert o['planned_task_count']==0;assert o['resource_unfit'][0]['task_id']=='gpu-ish'

def test_missing_dependency_and_cycle_block_plan():
 o=plan([task('a',['missing'])],[host()]);assert o['status']=='BLOCKED' and any(x.startswith('DEPENDENCY_NOT_FOUND') for x in o['blockers'])
 o=plan([task('a',['b']),task('b',['a'])],[host()]);assert o['status']=='BLOCKED' and any(x.startswith('TASK_DAG_CYCLE') for x in o['blockers'])

def test_no_execution_production_or_spend_authority():
 o=plan([task('a')],[host()]);assert o['execution_authority'] is False and o['production_authority'] is False and o['automatic_external_spend_eur']==0;assert o['work_stealing_ready_queue'] is True and o['backpressure_enabled'] is True

def test_birth_contract_is_shadow_and_umg_required():
 b=load('dev-hub/config/resource-aware-parallel-orchestrator.birth.v1.json');assert b['materialization_gate_required'] is True;assert b['production_activation_authorized'] is False;assert b['owner_foundry']=='branch-foundry'
if __name__=='__main__':
 tests=[(n,v) for n,v in sorted(globals().items()) if n.startswith('test_') and callable(v)]
 for n,f in tests:f();print(n+'=PASS')
 print('CHACHA_DEV_RESOURCE_AWARE_PARALLEL_ORCHESTRATOR=PASS');print('TEST_COUNT='+str(len(tests)));print('EXECUTION_AUTHORITY=NO');print('AUTOMATIC_EXTERNAL_SPEND_EUR=0')
