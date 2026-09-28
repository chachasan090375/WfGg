#!/usr/bin/env python3
from __future__ import annotations
import argparse,json
from pathlib import Path
from typing import Any

def load(p:Path)->dict[str,Any]:
    x=json.loads(p.read_text(encoding='utf-8'))
    if not isinstance(x,dict): raise ValueError('JSON_ROOT_NOT_OBJECT:'+str(p))
    return x

def save(p:Path,x:dict[str,Any])->None:
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(x,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')


def issues_of(model:dict[str,Any])->list[dict[str,Any]]:
    reconciliation=model.get('reconciliation') if isinstance(model.get('reconciliation'),dict) else {}
    issues=reconciliation.get('issues') if isinstance(reconciliation.get('issues'),list) else []
    declared=int(reconciliation.get('issue_count') if reconciliation.get('issue_count') is not None else len(issues))
    if declared!=len(issues):
        raise ValueError('SELF_MODEL_ISSUE_CONTRACT_MISMATCH:'+str(declared)+':'+str(len(issues)))
    return [x for x in issues if isinstance(x,dict)]

def plan(self_model:dict[str,Any],policy:dict[str,Any])->dict[str,Any]:
    actions=[];unknown=[]
    mapping=policy.get('owner_actions') or {}
    try: issues=issues_of(self_model)
    except ValueError as exc:
        parts=str(exc).split(':')
        return {'schema':'chacha.dev/autonomy-supervision-plan/v1','status':'BLOCKED','next_state':'BLOCKED','actions':[],'unknown_issues':[{'code':'SELF_MODEL_ISSUE_CONTRACT_MISMATCH','details':str(exc)}],'issue_count':int(parts[1]) if len(parts)>1 and parts[1].isdigit() else 0,'direct_mutation_authority':False,'verification_required':True,'automatic_external_spend_eur':0}
    waits=[];human=[]
    for issue in issues:
        if not isinstance(issue,dict): continue
        cls=str(issue.get('class') or '')
        action=str(issue.get('recommended_action') or '')
        if cls=='EXTERNAL_DEPENDENCY':
            waits.append({'issue_code':issue.get('code'),'subject':issue.get('subject'),'owner':issue.get('owner'),'resume_at':(issue.get('details') or {}).get('resume_at'),'reason':action or issue.get('code'),'direct_mutation_by_supervisor':False})
            continue
        if cls=='HUMAN_BOUNDARY':
            human.append({'issue_code':issue.get('code'),'subject':issue.get('subject'),'owner':issue.get('owner'),'reason':action or issue.get('code'),'direct_mutation_by_supervisor':False})
            continue
        spec=mapping.get(action)
        if not isinstance(spec,dict):
            unknown.append({'code':issue.get('code'),'subject':issue.get('subject'),'recommended_action':action})
            continue
        actions.append({
          'issue_code':issue.get('code'),'subject':issue.get('subject'),
          'owner':spec.get('owner') or issue.get('owner'),'action':action,'mode':spec.get('mode'),
          'requires_human':bool(spec.get('requires_human')),'status':'PLANNED',
          'direct_mutation_by_supervisor':False
        })
    if unknown: status,next_state='BLOCKED','BLOCKED'
    elif human: status,next_state='AWAITING_HUMAN','AWAIT_HUMAN'
    elif actions: status,next_state='READY','DELEGATE'
    elif waits: status,next_state='WAITING_EXTERNAL','WAIT_EXTERNAL'
    else: status,next_state='CONVERGED','RESUME'
    return {'schema':'chacha.dev/autonomy-supervision-plan/v1','status':status,'next_state':next_state,
      'actions':actions,'external_waits':waits,'human_boundaries':human,'unknown_issues':unknown,'issue_count':len(actions)+len(waits)+len(human)+len(unknown),
      'direct_mutation_authority':False,'verification_required':True,'automatic_external_spend_eur':0}

def verify(before:dict[str,Any],after:dict[str,Any],execution:dict[str,Any],policy:dict[str,Any])->dict[str,Any]:
    try:
        before_issues=issues_of(before); after_issues=issues_of(after)
    except ValueError as exc:
        return {'schema':'chacha.dev/autonomy-supervision-verification/v1','status':'BLOCKED','next_state':'BLOCKED','resolved':[],'remaining':[],'failed_resolution_claims':[],'contract_error':str(exc),'verified_from_fresh_observation':False,'direct_mutation_authority':False,'automatic_external_spend_eur':0}
    before_keys={(x.get('code'),x.get('subject')) for x in before_issues}
    after_keys={(x.get('code'),x.get('subject')) for x in after_issues}
    executed={(x.get('issue_code'),x.get('subject')) for x in execution.get('actions') or [] if isinstance(x,dict) and x.get('status') in {'PASS','VERIFIED','SIMULATED_PASS'}}
    resolved=sorted([list(x) for x in (before_keys-after_keys) if x in executed])
    remaining=sorted([list(x) for x in after_keys])
    failed_claims=sorted([list(x) for x in executed if x in after_keys])
    if failed_claims: status='BLOCKED'; next_state='CLASSIFY'
    elif remaining: status='PARTIAL'; next_state='CLASSIFY'
    else: status='PASS'; next_state='RESUME'
    return {'schema':'chacha.dev/autonomy-supervision-verification/v1','status':status,'next_state':next_state,
      'resolved':resolved,'remaining':remaining,'failed_resolution_claims':failed_claims,
      'verified_from_fresh_observation':True,'direct_mutation_authority':False,'automatic_external_spend_eur':0}

def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument('--mode',choices=['plan','verify'],required=True);ap.add_argument('--policy',type=Path,required=True);ap.add_argument('--self-model',type=Path);ap.add_argument('--before',type=Path);ap.add_argument('--after',type=Path);ap.add_argument('--execution',type=Path);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args();p=load(a.policy)
    if a.mode=='plan':
        if not a.self_model: raise SystemExit('SELF_MODEL_REQUIRED')
        out=plan(load(a.self_model),p)
    else:
        if not (a.before and a.after and a.execution): raise SystemExit('BEFORE_AFTER_EXECUTION_REQUIRED')
        out=verify(load(a.before),load(a.after),load(a.execution),p)
    save(a.output,out);print('CHACHA_DEV_AUTONOMY_SUPERVISION='+out['status']);print('NEXT_STATE='+out['next_state']);print('AUTOMATIC_EXTERNAL_SPEND_EUR=0');return 0 if out['status']!='BLOCKED' else 2
if __name__=='__main__': raise SystemExit(main())
