#!/usr/bin/env python3
import importlib.util,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
p=ROOT/'dev-hub/bin/technology_self_benchmark_observer.py';s=importlib.util.spec_from_file_location('o',p);o=importlib.util.module_from_spec(s);s.loader.exec_module(o)
policy=json.loads((ROOT/'dev-hub/config/technology-self-benchmark-observer.v1.json').read_text())
def dossier(mechs,origin='COMPETITIVE_WATCH'): return {'schema':'chacha.dev/external-mechanism-dossier/v1','origin':origin,'mechanisms':mechs}
def value(**kw):
 x={'global_value_score':85,'architecture_fit':True,'maintenance_debt_score':10,'value_dimensions':{'autonomy':15},'provenance_verified':True,'owned_implementation_feasible':True};x.update(kw);return x
def test_verified_better_pattern_is_benchmarked_not_adopted():
 r=o.assess(dossier([{**value(),'mechanism_id':'progress-ledger','capability':'anti-loop','evidence_score':80,'maturity_score':80,'external_measured_score':88,'internal_measured_score':70,'comparison_measured':True}]),policy)
 assert r['mechanisms'][0]['recommendation']=='BENCHMARK'; assert r['production_authority'] is False and r['foundry_execution_authorized'] is False
def test_strong_pattern_can_only_be_pilot_candidate():
 r=o.assess(dossier([{**value(),'mechanism_id':'out-of-band-watchdog','capability':'agent-safety','evidence_score':95,'maturity_score':90,'external_measured_score':95,'internal_measured_score':65,'comparison_measured':True}]),policy)
 assert r['mechanisms'][0]['recommendation']=='PILOT_CANDIDATE'; assert r['execution_authority'] is False
def test_worse_or_unproven_pattern_is_rejected_and_remembered():
 r=o.assess(dossier([{**value(),'mechanism_id':'fashionable-idea','capability':'routing','evidence_score':25,'maturity_score':30,'external_measured_score':60,'internal_measured_score':75,'comparison_measured':True}]),policy)
 assert r['mechanisms'][0]['recommendation']=='IGNORE'; assert len(r['negative_knowledge'])==1 and r['negative_knowledge'][0]['reconsider_only_on_material_new_evidence'] is True
def test_paid_dependency_is_forbidden_but_compatible_open_source_reuse_is_allowed():
 paid=o.assess(dossier([{**value(),'mechanism_id':'paid-only','capability':'memory','evidence_score':99,'maturity_score':99,'external_measured_score':99,'internal_measured_score':10,'comparison_measured':True,'automatic_paid_dependency_required':True}]),policy)['mechanisms'][0]
 assert paid['recommendation']=='IGNORE' and paid['source_code_copy'] is False
 oss=o.assess(dossier([{**value(),'mechanism_id':'oss','capability':'memory','evidence_score':99,'maturity_score':99,'external_measured_score':99,'internal_measured_score':10,'comparison_measured':True,'source_is_open_source':True,'source_code_available':True,'license_spdx':'Apache-2.0','license_compatible':True,'license_obligations_recorded':True}]),policy)['mechanisms'][0]
 assert oss['recommendation']=='PILOT_CANDIDATE' and oss['source_code_copy'] is True and oss['source_strategy']=='OPEN_SOURCE_REUSE'
def test_unmeasured_external_claim_stays_watch_only():
 r=o.assess(dossier([{**value(),'mechanism_id':'mission-ledger','capability':'long-horizon-planning','evidence_score':90,'maturity_score':90,'external_measured_score':95,'internal_measured_score':0,'comparison_measured':False}]),policy)
 assert r['mechanisms'][0]['recommendation']=='WATCH'; assert 'LOCAL_COMPARATIVE_BENCHMARK_REQUIRED' in r['mechanisms'][0]['reason_codes']
if __name__=='__main__':
 for n,v in sorted(globals().items()):
  if n.startswith('test_') and callable(v): v(); print(n+'=PASS')
 print('CHACHA_DEV_TECHNOLOGY_SELF_BENCHMARK_TESTS=5/5 PASS')
