#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,re
from pathlib import Path
from typing import Any
SHA=re.compile(r'^[0-9a-f]{40}$')

def load(p:Path)->dict[str,Any]:
    x=json.loads(p.read_text(encoding='utf-8'))
    if not isinstance(x,dict):raise ValueError('JSON_OBJECT_REQUIRED:'+str(p))
    return x

def digest(p:Path)->str:return 'sha256:'+hashlib.sha256(p.read_bytes()).hexdigest()

def gate(policy:dict[str,Any],change:dict[str,Any],evidence:list[tuple[Path,dict[str,Any]]])->dict[str,Any]:
    if policy.get('schema')!='chacha.dev/foundry-shadow-graduation-gate-policy/v1':raise ValueError('POLICY_SCHEMA_MISMATCH')
    blockers=[];details=change.get('details') if isinstance(change.get('details'),dict) else {}
    if change.get('status')!=policy.get('required_change_set_status'):blockers.append('CHANGE_SET_NOT_PASS')
    rev=str(details.get('workspace_commit') or '');tree=str(details.get('workspace_tree') or '')
    if not SHA.fullmatch(rev):blockers.append('EXACT_CANDIDATE_REVISION_REQUIRED')
    if not SHA.fullmatch(tree):blockers.append('EXACT_CANDIDATE_TREE_REQUIRED')
    if not isinstance(details.get('rollback'),dict):blockers.append('ROLLBACK_REQUIRED')
    valid=[]
    for path,row in evidence:
        if row.get('status')=='PASS':valid.append({'path':str(path),'digest':digest(path),'schema':row.get('schema')})
    if len(valid)<int(policy.get('required_independent_evidence_count') or 2):blockers.append('INDEPENDENT_EVIDENCE_INSUFFICIENT')
    return {'schema':'chacha.dev/foundry-shadow-graduation-gate/v1','status':'PILOT_READY' if not blockers else 'HOLD','candidate_revision':rev,'candidate_tree':tree,'evidence':valid,'blockers':blockers,'pilot_execution_authorized':False,'promotion_authorized':False,'production_change_authorized':False,'automatic_external_spend_eur':0}

def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument('--policy',type=Path,required=True);ap.add_argument('--change-set',type=Path,required=True);ap.add_argument('--evidence',type=Path,action='append',default=[]);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    try:
        ev=[(p,load(p)) for p in a.evidence];out=gate(load(a.policy),load(a.change_set),ev);a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(out,indent=2,sort_keys=True)+'\n');print('CHACHA_DEV_FOUNDRY_SHADOW_GRADUATION_GATE='+out['status']);print('PILOT_EXECUTION_AUTHORIZED=NO');print('PROMOTION_AUTHORIZED=NO');return 0 if out['status']=='PILOT_READY' else 10
    except Exception as e:print('CHACHA_DEV_FOUNDRY_SHADOW_GRADUATION_GATE=BLOCK');print('REASON='+str(e));return 20
if __name__=='__main__':raise SystemExit(main())
