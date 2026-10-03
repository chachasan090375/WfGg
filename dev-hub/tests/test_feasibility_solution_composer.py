#!/usr/bin/env python3
from __future__ import annotations
import importlib.util,json,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]

def mod(name,rel):
 p=ROOT/rel;s=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
A=mod('feas',Path('dev-hub/bin/infrastructure-feasibility-auditor.py'))
C=mod('composer',Path('dev-hub/bin/solution-composer.py'))
R=mod('recursive',Path('dev-hub/bin/recursive-specialization-router.py'))
FP=json.loads((ROOT/'dev-hub/config/infrastructure-feasibility.v1.json').read_text())
SP=json.loads((ROOT/'dev-hub/config/solution-composer.v1.json').read_text())
RF=json.loads((ROOT/'dev-hub/config/specialization-fabric.v2.json').read_text())
D=json.loads((ROOT/'dev-hub/config/deliverable-specialization.v1.json').read_text())
AR=json.loads((ROOT/'dev-hub/config/application-archetype-specialization.v1.json').read_text())

def infra(**kw):
 x={'infrastructure_id':'fixture','cpu_cores':8,'ram_gib':16,'gpu_vram_gib':0,'storage_free_gib':200,'storage_iops':2000,'network_mbps':1000,'latency_ms':10,'os_families':['linux'],'runtimes':['python','node'],'virtualization':['containers'],'device_access':[],'availability':'single-host'};x.update(kw);return x

def req(**kw):
 x={'requirements_id':'r','cpu_cores':3,'ram_gib':6,'gpu_vram_gib':0,'storage_free_gib':40,'storage_iops':500,'network_mbps':100,'os_families':['linux'],'runtimes':['python'],'virtualization':['containers'],'device_access':[]};x.update(kw);return x

def intent():return {'project_id':'retail-suite','deliverable_class':'application','archetype':'business_management','classification_confidence':.98,'global_constraints':{'security':'strict','external_spend':0,'language':'fr'},'modules':[
 {'name':'Gestion','kind':'management','owns_data':['stores','users'],'reuse_candidates':['identity-api']},
 {'name':'Formation ludique','kind':'game','constraints':{'fps_floor':60},'depends_on':['Gestion'],'reuse_candidates':['identity-api'],'interfaces':[{'target':'Gestion','kind':'api','contract':'user-and-progress-v1'}]},
 {'name':'Documentation','kind':'documentation','reuse_candidates':['identity-api']},
 {'name':'Reporting','kind':'reporting','depends_on':['Gestion']}
]}

def test_fit_uses_safety_reserve():
 out=A.audit(infra(),req(),FP);assert out['verdict']=='FIT',out;assert out['usable_capacity']['ram_gib']==11.2

def test_runtime_alias_python3_satisfies_python_requirement():
 out=A.audit(infra(runtimes=["python3","node"]),req(runtimes=["python"]),FP);assert out["verdict"]=="FIT",out


def test_fit_with_constraints_is_not_hard_block():
 out=A.audit(infra(latency_ms=80),req(max_latency_ms=30),FP);assert out['verdict']=='FIT_WITH_CONSTRAINTS';assert out['execution_on_current_infrastructure_allowed'] is True

def test_not_fit_proposes_minimum_and_recommended_target():
 out=A.audit(infra(cpu_cores=2,ram_gib=2),req(cpu_cores=4,ram_gib=8,os_families=['linux','macos']),FP)
 assert out['verdict']=='NOT_FIT';assert out['execution_on_current_infrastructure_allowed'] is False
 target=out['target_infrastructure_architecture'];assert target['minimum_profile']['ram_gib']>=11.42 and target['recommended_profile']['ram_gib']>target['minimum_profile']['ram_gib']
 assert any(x['dimension']=='os_families' for x in target['missing_components']);assert target['cost_boundary']=='NO_AUTOMATIC_EXTERNAL_SPEND'

def test_composer_requires_feasibility_evidence():
 out=C.compose(intent(),{},SP);assert out['status']=='BLOCKED';assert 'INFRASTRUCTURE_FEASIBILITY_REPORT_REQUIRED' in out['blockers']

def test_composer_designs_on_current_fit_infrastructure():
 f=A.audit(infra(),req(),FP);out=C.compose(intent(),f,SP);assert out['status']=='DESIGN_READY';assert out['execution_blocked'] is False;assert out['design_infrastructure']=='current_infrastructure'

def test_not_fit_still_conceptualizes_against_target_but_blocks_execution():
 f=A.audit(infra(cpu_cores=2,ram_gib=2),req(cpu_cores=6,ram_gib=10),FP);out=C.compose(intent(),f,SP)
 assert out['status']=='DESIGN_READY_EXECUTION_BLOCKED_INFRASTRUCTURE';assert out['execution_blocked'] is True;assert out['target_infrastructure_architecture']

def test_solution_graph_reclassifies_heterogeneous_modules_and_reuses_shared_component():
 f=A.audit(infra(),req(),FP);out=C.compose(intent(),f,SP);g=out['solution_graph'];r=R.resolve(g,RF,D,AR);assert r['status']=='PASS',r['blockers']
 rows={x['node_id']:x for x in r['nodes']};assert rows['formation-ludique']['classification']['archetype']=='game_realtime';assert rows['documentation']['classification']['deliverable_class']=='document';assert rows['reporting']['classification']['deliverable_class']=='data_artifact'
 assert set(r['shared_component_reuse']['identity-api'])=={'gestion','formation-ludique','documentation'}

def test_interfaces_dependencies_and_data_ownership_are_explicit():
 f=A.audit(infra(),req(),FP);out=C.compose(intent(),f,SP);rows={x['node_id']:x for x in out['solution_graph']['nodes']}
 assert rows['formation-ludique']['dependencies']==['gestion'];assert rows['gestion']['data_ownership']==['stores','users'];assert out['interfaces'][0]['contract']=='user-and-progress-v1'

def test_no_execution_or_production_authority_and_no_spend():
 f=A.audit(infra(),req(),FP);out=C.compose(intent(),f,SP);assert out['execution_authority'] is False and out['production_authority'] is False and out['automatic_external_spend_eur']==0
 assert SP['architecture_council_recommendation_only'] is True and SP['logician_challenge_required_before_release_plan'] is True

def test_birth_contracts_require_umg_and_shadow():
 for rel in ['dev-hub/config/infrastructure-feasibility-auditor.birth.v1.json','dev-hub/config/solution-composer.birth.v1.json']:
  b=json.loads((ROOT/rel).read_text());assert b['materialization_gate_required'] is True;assert b['governance_class']=='CORE_PLATFORM_COMPONENT';assert b['owner_foundry']=='branch-foundry';assert b['production_activation_authorized'] is False

if __name__=='__main__':
 tests=[(n,v) for n,v in sorted(globals().items()) if n.startswith('test_') and callable(v)]
 for n,f in tests:f();print(n+'=PASS')
 print('CHACHA_DEV_FEASIBILITY_SOLUTION_COMPOSER=PASS');print('TEST_COUNT='+str(len(tests)));print('PRODUCTION_ACTIVATION=NO');print('AUTOMATIC_EXTERNAL_SPEND_EUR=0')
