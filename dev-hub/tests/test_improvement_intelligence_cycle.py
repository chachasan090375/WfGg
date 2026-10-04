#!/usr/bin/env python3
import json,tempfile,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'dev-hub/bin'))
import agent_observation_bus as bus, improvement_intelligence_cycle as cyc
with tempfile.TemporaryDirectory() as td:
 rt=Path(td);pol=json.load(open(ROOT/'dev-hub/config/agent-observation-bus.v1.json'))
 e={'schema':'chacha.dev/agent-observation-event/v1','event_id':'verified-failure-1','event_type':'VERIFIED_FAILURE','source_id':'project-control','source_surface':'test','project_id':'chacha-dev-platform','subject_role':'run-controller','outcome':'FAILED','revision':'a'*40,'verification':'VERIFIED','evidence_refs':['receipt:1'],'capabilities':['run-controller'],'details':{'summary':'Repeated execution failure requires resilience improvement'}}
 out=bus.publish(e,pol,rt);assert out['event']['verification']=='VERIFIED',out
 receipt=cyc.run(ROOT,rt);assert receipt['status']=='PASS';assert receipt['improvement_candidate_count']>=1,receipt
 q=list((rt/'platform-evolution/reassessment-queue').glob('improvement-*.json'));assert q,q
 req=json.load(open(q[0]));assert req['production_authority'] is False and req['shadow_required'] is True
 print('test_verified_bus_signal_routes_to_governed_shadow_reassessment=PASS')
print('CHACHA_DEV_IMPROVEMENT_INTELLIGENCE_CYCLE_TEST=PASS')
