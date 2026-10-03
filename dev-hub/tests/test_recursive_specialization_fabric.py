#!/usr/bin/env python3
from __future__ import annotations
import importlib.util,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]

def loadj(rel): return json.loads((ROOT/rel).read_text())
def loadmod():
 p=ROOT/'dev-hub/bin/recursive-specialization-router.py';s=importlib.util.spec_from_file_location('rsf',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
M=loadmod();F=loadj('dev-hub/config/specialization-fabric.v2.json');D=loadj('dev-hub/config/deliverable-specialization.v1.json');A=loadj('dev-hub/config/application-archetype-specialization.v1.json')

def base_graph():
 return {"schema":"chacha.dev/recursive-specialization-graph/v1","project_id":"mixed-management-suite","nodes":[
  {"node_id":"root","node_kind":"project","classification":{"deliverable_class":"application","archetype":"business_management","confidence":0.98},"constraints_local":{"security":"strict","language":"fr","external_spend":0},"domain_requirements":["product","development"],"dependencies":[]},
  {"node_id":"management","parent_id":"root","node_kind":"module","classification":{"deliverable_class":"application","archetype":"business_management","confidence":0.97},"constraints_local":{"audit":"required"},"domain_requirements":["data-backend","cybersecurity","data-backend"],"shared_component_refs":["identity-api"],"dependencies":[]},
  {"node_id":"training-game","parent_id":"root","node_kind":"module","classification":{"deliverable_class":"application","archetype":"game_realtime","confidence":0.96},"constraints_local":{"fps_floor":60},"domain_requirements":["development","graphics","animation"],"shared_component_refs":["identity-api"],"dependencies":["management"]},
  {"node_id":"game-animation","parent_id":"training-game","node_kind":"submodule","classification":{"deliverable_class":"animation_motion","subtype":"ui_animation","confidence":0.92},"domain_requirements":["animation","graphics"],"dependencies":[]},
  {"node_id":"documentation","parent_id":"root","node_kind":"module","classification":{"deliverable_class":"document","subtype":"manual","confidence":0.95},"domain_requirements":["documentation","translation","publication"],"shared_component_refs":["identity-api"],"dependencies":[]},
  {"node_id":"reporting","parent_id":"root","node_kind":"module","classification":{"deliverable_class":"data_artifact","subtype":"dashboard","confidence":0.94},"domain_requirements":["data-backend","ui-layout"],"dependencies":["management"]}
 ]}

def resolve(g): return M.resolve(g,F,D,A)

def byid(out): return {x['node_id']:x for x in out['nodes']}

def test_mixed_application_modules_reclassify_independently():
 out=resolve(base_graph()); assert out['status']=='PASS',out['blockers'];r=byid(out)
 assert r['management']['classification']['archetype']=='business_management'
 assert r['training-game']['classification']['archetype']=='game_realtime'
 assert r['documentation']['classification']['deliverable_class']=='document'
 assert r['reporting']['classification']['deliverable_class']=='data_artifact'
 assert r['game-animation']['classification']['deliverable_class']=='animation_motion'

def test_nested_reclassification_and_constraint_inheritance():
 out=resolve(base_graph());r=byid(out)
 assert r['game-animation']['constraints_effective']['security']=='strict'
 assert r['game-animation']['constraints_effective']['language']=='fr'
 assert r['training-game']['constraints_effective']['fps_floor']==60

def test_shared_component_is_referenced_once_not_cloned():
 out=resolve(base_graph()); assert set(out['shared_component_reuse']['identity-api'])=={'management','training-game','documentation'}
 assert len({x['node_id'] for x in out['nodes']})==out['node_count']

def test_duplicate_domain_arm_refs_are_deduplicated_locally():
 out=resolve(base_graph());r=byid(out);domains=[x['domain'] for x in r['management']['specialist_cells']]
 assert domains==['data-backend','cybersecurity']
 assert all(x['model']=='CANONICAL_HEAD_PLUS_ARM_REFERENCE' for x in r['management']['specialist_cells'])

def test_non_overridable_parent_constraint_cannot_be_changed():
 g=base_graph(); row=next(x for x in g['nodes'] if x['node_id']=='training-game');row['constraint_overrides']={'security':'relaxed'}
 out=resolve(g);assert out['status']=='BLOCKED';assert any('NON_OVERRIDABLE_CONSTRAINT' in x for x in out['blockers'])

def test_uncertain_and_unknown_classification_routes_shadow():
 g=base_graph();g['nodes'].append({"node_id":"rare","parent_id":"root","node_kind":"module","classification":{"deliverable_class":"quantum_hologram","confidence":0.4},"dependencies":[]})
 out=resolve(g);r=byid(out);assert r['rare']['classification_state']=='SHADOW_UNCERTAIN';assert any('UNKNOWN_DELIVERABLE_CLASS' in x for x in out['warnings'])

def test_mixed_composite_deliverable_is_supported():
 g=base_graph();g['nodes'][0]['classification']={"deliverable_class":"mixed_composite","subtype":"multi_deliverable_project","confidence":0.99}
 assert resolve(g)['status']=='PASS'

def test_dependency_cycle_blocks():
 g=base_graph();next(x for x in g['nodes'] if x['node_id']=='management')['dependencies']=['reporting']
 out=resolve(g);assert out['status']=='BLOCKED';assert any(x.startswith('DEPENDENCY_CYCLE:') for x in out['blockers'])

def test_recursive_depth_guard_blocks_runaway_decomposition():
 g={"schema":"chacha.dev/recursive-specialization-graph/v1","project_id":"deep","nodes":[]}
 parent=None
 for i in range(11):
  n={"node_id":f'n{i}',"parent_id":parent,"node_kind":"module" if i else "project","classification":{"deliverable_class":"application","archetype":"business_management","confidence":.9},"dependencies":[]};g['nodes'].append(n);parent=n['node_id']
 out=resolve(g);assert out['status']=='BLOCKED';assert 'RECURSIVE_DEPTH_LIMIT_EXCEEDED' in out['blockers']

def test_old_six_application_archetypes_are_preserved():
 expected={'game_realtime','business_management','system_infrastructure','consumer_application','data_ai_automation','creative_media_interactive'}
 assert expected.issubset(set(A['archetypes']))

def test_no_execution_authority_or_spend():
 out=resolve(base_graph());assert out['execution_authority'] is False and out['production_activation'] is False and out['automatic_external_spend_eur']==0
 assert all(x['authority']['execution'] is False and x['authority']['production'] is False for x in out['nodes'])
 assert F['governance']['universal_materialization_gate'] is True and F['governance']['canonical_component_registry'] is True

def test_birth_contract_is_governed_core_component_shadow_only():
 b=loadj('dev-hub/config/recursive-specialization-router.birth.v1.json')
 assert b['component_id']=='recursive-specialization-router';assert b['materialization_gate_required'] is True;assert b['governance_class']=='CORE_PLATFORM_COMPONENT';assert b['owner_foundry']=='branch-foundry';assert b['production_activation_authorized'] is False;assert b['automatic_external_spend_eur']==0

if __name__=='__main__':
 tests=[(n,v) for n,v in sorted(globals().items()) if n.startswith('test_') and callable(v)]
 for n,f in tests:f();print(n+'=PASS')
 print('CHACHA_DEV_RECURSIVE_SPECIALIZATION_FABRIC=PASS');print('TEST_COUNT='+str(len(tests)));print('PRODUCTION_ACTIVATION=NO');print('AUTOMATIC_EXTERNAL_SPEND_EUR=0')
