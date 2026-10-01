#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,re
from pathlib import Path
from typing import Any
SHA=re.compile(r'^[0-9a-f]{40}$')

def load(p:Path)->dict[str,Any]:
    x=json.loads(p.read_text(encoding='utf-8'))
    if not isinstance(x,dict):raise ValueError('JSON_OBJECT_REQUIRED:'+str(p))
    return x

def rehearse(policy:dict[str,Any],ready:dict[str,Any],expected_revision:str)->dict[str,Any]:
    if policy.get('schema')!='chacha.dev/ha-standby-rehearsal-policy/v1':raise ValueError('POLICY_SCHEMA_MISMATCH')
    blockers=[]
    if not SHA.fullmatch(expected_revision):blockers.append('EXACT_REVISION_REQUIRED')
    if ready.get('status')!=policy.get('required_readiness_status'):blockers.append('READINESS_NOT_PASS')
    if ready.get('state')!=policy.get('required_readiness_state'):blockers.append('READINESS_STATE_MISMATCH')
    if ready.get('platform_revision')!=expected_revision:blockers.append('PLATFORM_REVISION_MISMATCH')
    if ready.get('single_writer_enforced') is not True:blockers.append('SINGLE_WRITER_NOT_ENFORCED')
    if ready.get('fencing_ready') is not True:blockers.append('FENCING_NOT_READY')
    if ready.get('rollback_ready') is not True:blockers.append('ROLLBACK_NOT_READY')
    if ready.get('bastion_failover_state')!='RESERVED_INACTIVE':blockers.append('BASTION_FAILOVER_NOT_RESERVED')
    if ready.get('failover_authorized') is not False:blockers.append('FAILOVER_MUST_REMAIN_UNAUTHORIZED')
    steps=['verify-primary-health','verify-standby-checkpoint','verify-fencing','verify-single-writer','simulate-primary-loss','simulate-standby-readiness','simulate-rollback-path','assert-no-writer-switch']
    return {'schema':'chacha.dev/ha-standby-rehearsal/v1','status':'PASS' if not blockers else 'BLOCK','platform_revision':expected_revision,'primary_node_id':ready.get('primary_node_id'),'standby_node_id':ready.get('standby_node_id'),'simulated_steps':steps,'blockers':blockers,'writer_switch_performed':False,'failover_performed':False,'production_activation_authorized':False,'automatic_external_spend_eur':0}

def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument('--policy',type=Path,required=True);ap.add_argument('--readiness',type=Path,required=True);ap.add_argument('--expected-revision',required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    try:
        out=rehearse(load(a.policy),load(a.readiness),a.expected_revision);a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(out,indent=2,sort_keys=True)+'\n');print('CHACHA_DEV_HA_STANDBY_REHEARSAL='+out['status']);print('FAILOVER_PERFORMED=NO');print('WRITER_SWITCH_PERFORMED=NO');return 0 if out['status']=='PASS' else 20
    except Exception as e:print('CHACHA_DEV_HA_STANDBY_REHEARSAL=BLOCK');print('REASON='+str(e));return 20
if __name__=='__main__':raise SystemExit(main())
