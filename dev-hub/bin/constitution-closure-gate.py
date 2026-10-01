#!/usr/bin/env python3
from __future__ import annotations
import argparse,json
from pathlib import Path
from typing import Any

def load(p:Path)->dict[str,Any]:
    x=json.loads(p.read_text(encoding='utf-8'))
    if not isinstance(x,dict):raise ValueError('JSON_OBJECT_REQUIRED')
    return x

def gate(policy:dict[str,Any],verification:dict[str,Any],watch:dict[str,Any])->dict[str,Any]:
    if policy.get('schema')!='chacha.dev/constitution-closure-gate-policy/v1':raise ValueError('POLICY_SCHEMA')
    blockers=[]
    if verification.get('schema')!=policy.get('required_verification_schema') or verification.get('status')!='PASS':blockers.append('CONSTITUTION_VERIFICATION_NOT_PASS')
    if int(verification.get('blocked_count') or 0)!=0:blockers.append('CONSTITUTION_BLOCKED_CLAUSES')
    if int(verification.get('passed_count') or 0)!=int(verification.get('clause_count') or -1) or int(verification.get('clause_count') or 0)<=0:blockers.append('CONSTITUTION_NOT_FULLY_VERIFIED')
    if watch.get('schema')!=policy.get('required_drift_watch_schema') or watch.get('status')!=policy.get('required_watch_status'):blockers.append('CONSTITUTION_WATCH_NOT_STABLE')
    if watch.get('current_digest')!=verification.get('constitution_digest'):blockers.append('CONSTITUTION_DIGEST_MISMATCH')
    if watch.get('constitution_mutation_authorized') is True or watch.get('execution_authority') is True:blockers.append('WATCH_HAS_MUTATION_AUTHORITY')
    return {'schema':'chacha.dev/constitution-closure-gate/v1','status':'PASS' if not blockers else 'HOLD','blockers':blockers,'constitution_digest':verification.get('constitution_digest'),'verified_clause_count':verification.get('passed_count'),'constitution_terminal_evidence_ready':not blockers,'execution_authority':False,'constitution_mutation_authorized':False,'automatic_external_spend_eur':0}

def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument('--policy',type=Path,required=True);ap.add_argument('--verification',type=Path,required=True);ap.add_argument('--watch',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    out=gate(load(a.policy),load(a.verification),load(a.watch));a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(out,indent=2)+'\n');print('CHACHA_DEV_CONSTITUTION_CLOSURE_GATE='+out['status']);print('MUTATION_AUTHORIZED=NO');return 0 if out['status']=='PASS' else 10
if __name__=='__main__':raise SystemExit(main())
