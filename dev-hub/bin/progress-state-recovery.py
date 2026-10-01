#!/usr/bin/env python3
from __future__ import annotations
import argparse,datetime,json,os
from pathlib import Path
from typing import Any

POLICY_SCHEMA='chacha.dev/progress-state-recovery-policy/v1'
STATE_SCHEMA='chacha.dev/platform-progress/v1'

def load(p:Path)->dict[str,Any]:
    x=json.loads(p.read_text(encoding='utf-8'))
    if not isinstance(x,dict):raise ValueError('JSON_OBJECT_REQUIRED:'+str(p))
    return x

def age_seconds(v:Any)->float:
    try:t=datetime.datetime.fromisoformat(str(v).replace('Z','+00:00')).astimezone(datetime.timezone.utc)
    except Exception:return float('inf')
    return max(0.0,(datetime.datetime.now(datetime.timezone.utc)-t).total_seconds())

def atomic(p:Path,x:dict[str,Any])->None:
    p.parent.mkdir(parents=True,exist_ok=True);tmp=p.with_suffix(p.suffix+'.tmp');tmp.write_text(json.dumps(x,indent=2,ensure_ascii=False,sort_keys=True)+'\n');os.replace(tmp,p)

def plan(policy:dict[str,Any],state:dict[str,Any],inactive:dict[str,Any]|None=None)->dict[str,Any]:
    if policy.get('schema')!=POLICY_SCHEMA:raise ValueError('POLICY_SCHEMA_MISMATCH')
    if state.get('schema')!=STATE_SCHEMA:raise ValueError('STATE_SCHEMA_MISMATCH')
    status=str(state.get('status') or 'IDLE');age=age_seconds(state.get('updated_at'));action='NOOP';reason='STATE_CURRENT'
    terminal=set(policy.get('terminal_statuses') or [])
    if status in terminal and age>=float(policy.get('recover_terminal_after_seconds') or 120):action='ARCHIVE_AND_RESET';reason='TERMINAL_DISPLAY_EXPIRED'
    elif status in {'RUNNING','WAITING'} and inactive and inactive.get('operation_id')==state.get('active_operation') and inactive.get('operation_active') is False:action='ARCHIVE_AND_RESET';reason='EXTERNAL_OPERATION_INACTIVE'
    return {'schema':'chacha.dev/progress-state-recovery-plan/v1','status':'PASS','action':action,'reason':reason,'source_status':status,'age_seconds':round(age,1),'execution_authority':False,'automatic_external_spend_eur':0}

def recovered(state:dict[str,Any],why:str)->dict[str,Any]:
    last={'id':state.get('active_operation'),'status':state.get('status'),'percent':state.get('active_work_percent'),'headline':state.get('headline'),'updated_at':state.get('updated_at'),'recovery_reason':why}
    out=dict(state);out.update({'status':'IDLE','active_work_percent':0,'headline':'ChaCha est prêt ✨','active_operation':None,'last_operation':last,'updated_at':datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00','Z'),'execution_authority':False,'automatic_external_spend_eur':0})
    for row in (out.get('modules') or {}).values():
        if isinstance(row,dict):row.update({'percent':0,'state':'IDLE','detail':'En attente','updated_at':out['updated_at']})
    return out

def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument('--policy',type=Path,required=True);ap.add_argument('--state',type=Path,required=True);ap.add_argument('--inactive-evidence',type=Path);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--apply',action='store_true');a=ap.parse_args()
    try:
        pol=load(a.policy);state=load(a.state);inactive=load(a.inactive_evidence) if a.inactive_evidence else None;p=plan(pol,state,inactive)
        out={'plan':p,'applied':False}
        if a.apply and p['action']=='ARCHIVE_AND_RESET':
            new=recovered(state,p['reason']);atomic(a.state,new);out.update({'applied':True,'state':new})
        a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(out,indent=2,sort_keys=True)+'\n')
        print('CHACHA_DEV_PROGRESS_STATE_RECOVERY=PASS');print('ACTION='+p['action']);print('APPLIED='+str(out['applied']).lower());return 0
    except Exception as e:print('CHACHA_DEV_PROGRESS_STATE_RECOVERY=BLOCK');print('REASON='+str(e));return 20
if __name__=='__main__':raise SystemExit(main())
