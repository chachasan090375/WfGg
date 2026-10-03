#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path
from typing import Any

def load(p:Path)->dict[str,Any]:
    x=json.loads(p.read_text(encoding='utf-8'))
    if not isinstance(x,dict):raise ValueError('JSON_OBJECT_REQUIRED')
    return x

def digest_obj(x:Any)->str:
    raw=json.dumps(x,sort_keys=True,separators=(',',':')).encode();return 'sha256:'+hashlib.sha256(raw).hexdigest()

def bundle(policy:dict[str,Any],learning:dict[str,Any],selfe:dict[str,Any],constitution:dict[str,Any])->dict[str,Any]:
    if policy.get('schema')!='chacha.dev/autonomy-terminal-evidence-bundle-policy/v1':raise ValueError('POLICY_SCHEMA')
    rows={'learning':learning,'self_evolution':selfe,'constitution':constitution};req=policy.get('required_schemas') or {};blockers=[]
    ready_fields={'learning':'learning_terminal_evidence_ready','self_evolution':'self_evolution_terminal_evidence_ready','constitution':'constitution_terminal_evidence_ready'}
    for name,row in rows.items():
        expected=req.get(name);allowed=set(expected if isinstance(expected,list) else [expected])
        if row.get('schema') not in allowed:blockers.append(name.upper()+'_SCHEMA_MISMATCH')
        if row.get('status')!=policy.get('required_status'):blockers.append(name.upper()+'_NOT_PASS')
        if row.get(ready_fields[name]) is not True:blockers.append(name.upper()+'_NOT_TERMINAL_READY')
        if row.get('execution_authority') is True:blockers.append(name.upper()+'_EXECUTION_AUTHORITY')
    evidence={name:digest_obj(row) for name,row in rows.items()}
    return {'schema':'chacha.dev/autonomy-terminal-evidence-bundle/v1','status':'PASS' if not blockers else 'HOLD','blockers':blockers,'terminal_gaps_ready':['learning','self-evolution','constitution'] if not blockers else [],'evidence_digests':evidence,'execution_authority':False,'production_mutation':False,'automatic_external_spend_eur':0}

def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument('--policy',type=Path,required=True);ap.add_argument('--learning',type=Path,required=True);ap.add_argument('--self-evolution',type=Path,required=True);ap.add_argument('--constitution',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    out=bundle(load(a.policy),load(a.learning),load(a.self_evolution),load(a.constitution));a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(out,indent=2)+'\n');print('CHACHA_DEV_AUTONOMY_TERMINAL_EVIDENCE_BUNDLE='+out['status']);print('PRODUCTION_MUTATION=NO');return 0 if out['status']=='PASS' else 10
if __name__=='__main__':raise SystemExit(main())
