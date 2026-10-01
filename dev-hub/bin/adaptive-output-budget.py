#!/usr/bin/env python3
from __future__ import annotations
import argparse,json
from pathlib import Path
from typing import Any

SCHEMA='chacha.dev/adaptive-output-budget-policy/v1'

def load(path:Path)->dict[str,Any]:
    x=json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(x,dict):raise ValueError('JSON_ROOT_NOT_OBJECT')
    return x

def decide(policy:dict[str,Any],task_class:str,model_id:str,requested:int)->dict[str,Any]:
    if policy.get('schema')!=SCHEMA:raise ValueError('POLICY_SCHEMA_INVALID')
    minimum=max(1,int(policy.get('minimum_tokens') or 1))
    task=max(minimum,int((policy.get('task_budgets') or {}).get(task_class) or policy.get('default_task_budget') or minimum))
    model=max(minimum,int((policy.get('model_caps') or {}).get(model_id) or task))
    req=max(minimum,int(requested or task))
    effective=min(req,task,model) if policy.get('never_expand_requested_budget') is True else min(task,model)
    return {'schema':'chacha.dev/adaptive-output-budget/v1','status':'PASS','task_class':task_class,'model_id':model_id,
            'requested_max_tokens':req,'task_budget':task,'model_cap':model,'effective_max_tokens':effective,
            'budget_reduced':effective<req,'routing_authority':'CHACHA_DEV','automatic_external_spend_eur':0}

def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument('--policy',type=Path,required=True);ap.add_argument('--task-class',required=True)
    ap.add_argument('--model-id',required=True);ap.add_argument('--requested-max-tokens',type=int,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    out=decide(load(a.policy),a.task_class,a.model_id,a.requested_max_tokens)
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(out,indent=2)+'\n')
    print('CHACHA_DEV_ADAPTIVE_OUTPUT_BUDGET=PASS');print('EFFECTIVE_MAX_TOKENS='+str(out['effective_max_tokens']))
    print('ROUTING_AUTHORITY=CHACHA_DEV');print('AUTOMATIC_EXTERNAL_SPEND_EUR=0');return 0

if __name__=='__main__':raise SystemExit(main())
