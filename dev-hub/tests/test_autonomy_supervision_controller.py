#!/usr/bin/env python3
import importlib.util,json,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]; BIN=ROOT/'dev-hub/bin'; CFG=ROOT/'dev-hub/config'
def loadmod(name,p):
 s=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
sup=loadmod('autsup',BIN/'autonomy-supervision-controller.py')
policy=json.load(open(CFG/'autonomy-supervision.v1.json'))
self_model={'reconciliation':{'issue_count':3,'issues':[
 {'code':'FLEET_MISSING','subject':'a','owner':'agent-fleet-observatory','recommended_action':'BACKFILL_FLEET_FROM_CANONICAL_REGISTRY'},
 {'code':'FLEET_MISSING','subject':'b','owner':'agent-fleet-observatory','recommended_action':'BACKFILL_FLEET_FROM_CANONICAL_REGISTRY'},
 {'code':'RELEASE_OVERAGE','subject':'releases','owner':'intendant','recommended_action':'RECONCILE_RELEASE_RETENTION'}]}}
p=sup.plan(self_model,policy);assert p['status']=='READY' and p['next_state']=='DELEGATE' and len(p['actions'])==3,p
bad={'reconciliation':{'issue_count':2,'issues':[]}}
b=sup.plan(bad,policy);assert b['status']=='BLOCKED' and b['unknown_issues'][0]['code']=='SELF_MODEL_ISSUE_CONTRACT_MISMATCH',b
unknown={'reconciliation':{'issue_count':1,'issues':[{'code':'NEW_UNKNOWN','subject':'x','recommended_action':'MAGIC'}]}}
u=sup.plan(unknown,policy);assert u['status']=='BLOCKED',u
execution={'actions':[{'issue_code':'FLEET_MISSING','subject':'a','status':'VERIFIED'},{'issue_code':'FLEET_MISSING','subject':'b','status':'VERIFIED'},{'issue_code':'RELEASE_OVERAGE','subject':'releases','status':'PREPARED'}]}
after={'reconciliation':{'issue_count':1,'issues':[{'code':'RELEASE_OVERAGE','subject':'releases'}]}}
v=sup.verify(self_model,after,execution,policy);assert v['status']=='PARTIAL' and v['next_state']=='CLASSIFY',v
assert len(v['resolved'])==2 and v['remaining']==[['RELEASE_OVERAGE','releases']],v
print('CHACHA_DEV_AUTONOMY_SUPERVISION_CONTRACT=PASS')
print('CHACHA_DEV_AUTONOMY_FALSE_CONVERGENCE_BLOCK=PASS')
print('CHACHA_DEV_AUTONOMY_UNKNOWN_ISSUE_FAIL_CLOSED=PASS')
print('CHACHA_DEV_AUTONOMY_FRESH_OBSERVATION_REQUIRED=PASS')
external={'reconciliation':{'issue_count':1,'issues':[{'code':'PROVIDER_QUOTA','subject':'antigravity','class':'EXTERNAL_DEPENDENCY','owner':'provider-health','recommended_action':'RETRY_WHEN_AVAILABLE','details':{'resume_at':'2026-10-04T17:53:18Z'}}]}}
ep=sup.plan(external,policy);assert ep['status']=='WAITING_EXTERNAL' and ep['next_state']=='WAIT_EXTERNAL' and len(ep['external_waits'])==1,ep
human={'reconciliation':{'issue_count':1,'issues':[{'code':'PRODUCTION_PROMOTION','subject':'candidate','class':'HUMAN_BOUNDARY','owner':'release-lifecycle','recommended_action':'EXPLICIT_HUMAN_APPROVAL'}]}}
hp=sup.plan(human,policy);assert hp['status']=='AWAITING_HUMAN' and hp['next_state']=='AWAIT_HUMAN' and len(hp['human_boundaries'])==1,hp
print('CHACHA_DEV_AUTONOMY_EXTERNAL_WAIT=PASS')
print('CHACHA_DEV_AUTONOMY_HUMAN_BOUNDARY=PASS')
