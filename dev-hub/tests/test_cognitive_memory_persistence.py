from __future__ import annotations
import importlib.util,json,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def mod(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
store=mod('ams',ROOT/'bin/agent-memory-store.py');boot=mod('hmb',ROOT/'bin/historical-memory-bootstrap.py')
def record(**kw):
 x={'schema':'chacha.dev/agent-memory-record/v1','memory_id':'m1','memory_key':'k1','memory_type':'semantic','trust_state':'TRUSTED','evidence_count':3,'confidence':0.9,'content_digest':'sha256:'+'a'*64,'evidence_refs':['ev:1'],'observed_at':'2026-10-03T00:00:00Z'};x.update(kw);return x
def test_agent_store_round_trip():
 with tempfile.TemporaryDirectory() as d:
  db=Path(d)/'agent.db';store.put(db,record());x=store.get(db,'m1');assert x['memory_key']=='k1';assert x['content_digest']=='sha256:'+'a'*64;assert x['evidence_refs']==['ev:1']
def test_raw_content_is_forbidden():
 with tempfile.TemporaryDirectory() as d:
  try:store.put(Path(d)/'a.db',record(content='secret-ish raw text'));raise AssertionError('expected block')
  except ValueError as e:assert 'RAW_CONTENT_FORBIDDEN' in str(e)
def test_bootstrap_is_read_only_and_privacy_safe():
 snap={'schema':'chacha.dev/central-memory-assimilation/v1','snapshot_digest':'s1','items':[{'item_key':'abc','subject_kind':'agent','subject_id':'logicien','signal_key':'change:/x','state':'PROVISIONAL','evidence_count':1,'confidence':0.2,'latest_observed_at':'2026-10-03T00:00:00Z','evidence_digest':'b'*64}]}
 x=boot.bootstrap(snap);assert x['status']=='PASS' and x['writes_performed'] is False;assert x['records'][0]['namespace']=='agent:logicien';assert x['records'][0]['memory_type']=='episodic';assert x['records'][0]['raw_user_content'] is False
def test_bootstrap_maps_non_agent_to_central():
 snap={'schema':'chacha.dev/central-memory-assimilation/v1','snapshot_digest':'s1','items':[{'item_key':'abc','subject_kind':'architecture','subject_id':'a','signal_key':'reuse','state':'TRUSTED','evidence_count':3,'confidence':0.9,'evidence_digest':'c'*64}]};x=boot.bootstrap(snap);assert x['records'][0]['namespace']=='central';assert x['records'][0]['memory_type']=='procedural'
def test_policy_does_not_authorize_activation():
 p=json.load(open(ROOT/'config/cognitive-memory-fabric.v1.json'));assert p['persistence']['production_activation_authorized'] is False;assert p['historical_bootstrap']['writes_performed'] is False
def test_tiering_is_shadow_only_and_readback_bounded():
 p=json.load(open(ROOT/'config/cognitive-memory-fabric.v1.json'));t=p['tiering'];assert t['readback_adapter']=='nas-readback-adapter';assert t['restore_mode']=='DISPOSABLE_WORKSPACE_ONLY';assert t['active_memory_restore_authorized'] is False;assert t['production_activation_authorized'] is False
if __name__=='__main__':
 n=0
 for name,fn in sorted(globals().items()):
  if name.startswith('test_'):fn();print(name+'=PASS');n+=1
 print('CHACHA_DEV_COGNITIVE_MEMORY_PERSISTENCE=PASS');print('TEST_COUNT='+str(n));print('AUTOMATIC_EXTERNAL_SPEND_EUR=0')
