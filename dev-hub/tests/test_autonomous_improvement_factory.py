from pathlib import Path
import importlib.util,json,tempfile
ROOT=Path(__file__).resolve().parents[1];BIN=ROOT/'bin';CFG=ROOT/'config'
def mod(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
obs=mod('obs',BIN/'technology_self_benchmark_observer.py');fac=mod('fac',BIN/'autonomous_improvement_factory.py')
policy=json.loads((CFG/'technology-self-benchmark-observer.v1.json').read_text())
def dossier(mech):return {'schema':'chacha.dev/external-mechanism-dossier/v1','origin':'TECHNOLOGY_TRUTH','mechanisms':[mech]}
base={'mechanism_id':'m1','capability':'orchestration','evidence_score':95,'maturity_score':90,'external_measured_score':95,'internal_measured_score':60,'comparison_measured':True,'global_value_score':90,'architecture_fit':True,'maintenance_debt_score':10,'value_dimensions':{'autonomy':20},'provenance_verified':True,'owned_implementation_feasible':True}
# Open source can be reused only with compatible license + obligations + provenance.
m={**base,'source_is_open_source':True,'source_code_available':True,'license_spdx':'Apache-2.0','license_compatible':True,'license_obligations_recorded':True}
r=obs.assess(dossier(m),policy)['mechanisms'][0];assert r['recommendation']=='PILOT_CANDIDATE' and r['source_strategy']=='OPEN_SOURCE_REUSE' and r['source_code_copy_allowed'] is True and r['train_build_eligible'] is True
print('test_compatible_open_source_reuse=PASS')
# Incompatible/unassessed license => rebuild, never blind-copy.
m2={**base,'source_is_open_source':True,'source_code_available':True,'license_spdx':'UNKNOWN','license_compatible':False,'license_obligations_recorded':False}
r2=obs.assess(dossier(m2),policy)['mechanisms'][0];assert r2['source_strategy']=='OWNED_REIMPLEMENTATION' and r2['source_code_copy_allowed'] is False
print('test_incompatible_license_rebuilds_mechanism=PASS')
# Novelty / no platform value never creates a train.
m3={**base,'global_value_score':10,'value_dimensions':{}}
r3=obs.assess(dossier(m3),policy)['mechanisms'][0];assert r3['recommendation']=='IGNORE' and r3['train_build_eligible'] is False
print('test_novelty_without_global_value_rejected=PASS')
# Factory produces shadow queue only, never production-ready by itself.
report=obs.assess(dossier(m),policy);q=fac.build_queue(report,json.loads((CFG/'autonomous-improvement-factory.v1.json').read_text()));assert len(q['items'])==1 and q['items'][0]['production_ready'] is False and q['production_authority'] is False
print('test_factory_build_queue_has_no_production_authority=PASS')
# Cockpit and Direct Operator expose update center, buttons go through governed BUILD intent.
ui=(ROOT/'direct-operator-ui/index.html').read_text();svc=(BIN/'direct-operator-service.py').read_text();
for token in ['🔄 Mises à jour','Reconstruire et installer toutes les mises à jour compatibles','Reconstruire et mettre en production','rebuildPromotionIntent','/api/v1/update-center']:
 assert token in ui or token in svc,token
assert 'direct current switch' not in ui.lower()
factory_policy=json.loads((CFG/'autonomous-improvement-factory.v1.json').read_text());assert factory_policy['cockpit_update_center']['recipe_first_default'] is True and factory_policy['cockpit_update_center']['qualified_train_default_state']=='RECIPE_ONLY'
print('test_cockpit_update_center_contract=PASS')
print('CHACHA_DEV_AUTONOMOUS_IMPROVEMENT_FACTORY_TESTS=5/5 PASS')
