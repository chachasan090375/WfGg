from __future__ import annotations
import importlib.util,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
POLICY=json.load(open(ROOT/'config/cognitive-memory-fabric.v1.json',encoding='utf-8'))
def module(name,path):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
router=module('cmr',ROOT/'bin/cognitive-memory-router.py');curator=module('mc',ROOT/'bin/memory-curator.py')
def req(**kw):
    x={'schema':'chacha.dev/cognitive-memory-request/v1','operation':'READ','scope':'AGENT','memory_type':'semantic','agent_id':'logicien','privacy':{},'filtered_source':True};x.update(kw);return x
def test_agent_read_routes_hot_then_central():
    x=router.route(POLICY,req());assert x['status']=='PASS';assert x['sources'][0].endswith('/logicien.jsonl');assert 'central-memory-assimilation.json' in x['sources'][1]
def test_central_write_requires_trust_and_evidence():
    x=router.route(POLICY,req(operation='WRITE',scope='CENTRAL',agent_id='',trust_state='PROVISIONAL',evidence_count=1));assert x['status']=='HOLD';assert 'CENTRAL_TRUST_REQUIRED' in x['blockers']
def test_secret_is_blocked():assert router.route(POLICY,req(privacy={'contains_secret':True}))['status']=='HOLD'
def test_native_local_is_advisory_only():
    x=router.route(POLICY,req(cognitive_assist=True));assert x['cognitive_assist']=={'provider_id':'native-local','requested':True,'advisory_only':True,'activation_required':False}
def test_curator_dedup_and_quarantine():
    b={'schema':'chacha.dev/cognitive-memory-curation-batch/v1','records':[
      {'memory_id':'a','memory_key':'k','trust_state':'PROVISIONAL','confidence':0.7,'evidence_count':1,'privacy':{}},
      {'memory_id':'b','memory_key':'k','trust_state':'TRUSTED','confidence':0.9,'evidence_count':4,'privacy':{}},
      {'memory_id':'c','memory_key':'x','trust_state':'SUSPENDED','confidence':1,'evidence_count':9,'privacy':{}}]}
    x=curator.curate(POLICY,b);d={r['memory_id']:r['decision'] for r in x['decisions']};assert d['a']=='DROP_DUPLICATE_REFERENCE';assert d['b']=='RETAIN_HOT';assert d['c']=='QUARANTINE';assert x['hard_delete_performed'] is False
def test_authority_is_zero():
    assert all(v is False for v in POLICY['authority'].values());assert POLICY['automatic_external_spend_eur']==0
def test_reusable_architecture_memory_constitution():
    x=json.load(open(ROOT/'config/reusable-architecture-memory.v1.json'));r=x['decision_rules'];assert r['central_council_remains_final_decider'] is False;assert r['architecture_council_final_authority'] is False;assert r['architecture_council_recommendation_authority'] is True
if __name__=='__main__':
    n=0
    for name,fn in sorted(globals().items()):
        if name.startswith('test_'):fn();print(name+'=PASS');n+=1
    print('CHACHA_DEV_COGNITIVE_MEMORY_FABRIC_FOUNDATION=PASS');print('TEST_COUNT='+str(n));print('AUTOMATIC_EXTERNAL_SPEND_EUR=0')
