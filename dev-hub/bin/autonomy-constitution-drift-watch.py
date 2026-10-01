#!/usr/bin/env python3
from __future__ import annotations
import argparse,json
from pathlib import Path
from typing import Any

def load(p:Path)->dict[str,Any]:
    x=json.loads(p.read_text(encoding='utf-8'))
    if not isinstance(x,dict):raise ValueError('JSON_OBJECT_REQUIRED:'+str(p))
    return x

def watch(policy:dict[str,Any],verification:dict[str,Any],previous:dict[str,Any]|None)->dict[str,Any]:
    if policy.get('schema')!='chacha.dev/autonomy-constitution-drift-watch-policy/v1':raise ValueError('POLICY_SCHEMA_MISMATCH')
    if verification.get('schema')!=policy.get('verification_schema'):raise ValueError('VERIFICATION_SCHEMA_MISMATCH')
    status='STABLE';reason='VERIFICATION_PASS'
    if verification.get('status')!='PASS':status='CRITICAL';reason='CONSTITUTION_VERIFICATION_BLOCKED'
    elif previous and previous.get('last_good_digest') and previous.get('last_good_digest')!=verification.get('constitution_digest'):status='REVIEW_REQUIRED';reason='CONSTITUTION_DIGEST_CHANGED'
    return {'schema':'chacha.dev/autonomy-constitution-drift-watch/v1','status':status,'reason':reason,'current_digest':verification.get('constitution_digest'),'last_good_digest':verification.get('constitution_digest') if verification.get('status')=='PASS' else (previous or {}).get('last_good_digest'),'blocked_clause_count':verification.get('blocked_count'),'constitution_mutation_authorized':False,'execution_authority':False,'automatic_external_spend_eur':0}

def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument('--policy',type=Path,required=True);ap.add_argument('--verification',type=Path,required=True);ap.add_argument('--previous',type=Path);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    try:
        out=watch(load(a.policy),load(a.verification),load(a.previous) if a.previous and a.previous.exists() else None);a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(out,indent=2,sort_keys=True)+'\n');print('CHACHA_DEV_AUTONOMY_CONSTITUTION_DRIFT_WATCH='+out['status']);print('MUTATION_AUTHORIZED=NO');return 20 if out['status']=='CRITICAL' else 0
    except Exception as e:print('CHACHA_DEV_AUTONOMY_CONSTITUTION_DRIFT_WATCH=BLOCK');print('REASON='+str(e));return 20
if __name__=='__main__':raise SystemExit(main())
