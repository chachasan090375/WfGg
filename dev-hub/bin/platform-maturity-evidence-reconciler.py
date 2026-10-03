#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,subprocess
from pathlib import Path
from typing import Any

POLICY_SCHEMA='chacha.dev/platform-maturity-evidence-reconciler-policy/v1'
SCORECARD_SCHEMA='chacha.dev/platform-maturity-scorecard/v1'

def load(p:Path)->dict[str,Any]:
    x=json.loads(p.read_text(encoding='utf-8'))
    if not isinstance(x,dict): raise ValueError('JSON_OBJECT_REQUIRED:'+str(p))
    return x

def digest(p:Path)->str:return 'sha256:'+hashlib.sha256(p.read_bytes()).hexdigest()
def clamp(x:Any)->float:return max(0.0,min(100.0,float(x)))

def verify(policy:dict[str,Any],score:dict[str,Any])->tuple[list[dict[str,Any]],list[str]]:
    if policy.get('schema')!=POLICY_SCHEMA: raise ValueError('POLICY_SCHEMA_MISMATCH')
    if score.get('schema')!=SCORECARD_SCHEMA: raise ValueError('SCORECARD_SCHEMA_MISMATCH')
    rows=[];errors=[]
    for row in score.get('dimensions') or []:
        if not isinstance(row,dict): continue
        p=Path(str(row.get('evidence_path') or ''))
        ok=p.is_file() and digest(p)==str(row.get('evidence_digest') or '')
        rows.append({**row,'materialized':ok})
        if not ok:errors.append('EVIDENCE_NOT_MATERIALIZED:'+str(row.get('id')))
    if len(rows)<int(policy.get('minimum_dimensions') or 3):errors.append('INSUFFICIENT_DIMENSIONS')
    total=sum(float(r.get('weight') or 0) for r in rows)
    if total!=100:errors.append('WEIGHT_SUM_NOT_100')
    return rows,errors

def reconcile(policy:dict[str,Any],score:dict[str,Any])->dict[str,Any]:
    rows,errors=verify(policy,score)
    if score.get('status')!='PASS':errors.append('SCORECARD_NOT_PASS')
    weighted=round(sum(clamp(r.get('score'))*float(r.get('weight') or 0)/100 for r in rows),1)
    return {'schema':'chacha.dev/platform-maturity-reconciliation/v1',
      'status':'PASS' if not errors else 'BLOCK','target_percent':weighted,
      'dimensions':rows,'blockers':sorted(set(errors)),'apply_authorized':False,
      'execution_authority':False,'automatic_external_spend_eur':0}

def apply(repo:Path,policy:dict[str,Any],out:dict[str,Any])->dict[str,Any]:
    if out.get('status')!='PASS':raise ValueError('RECONCILIATION_NOT_PASS')
    ctl=repo/str(policy['progress_controller']);pol=repo/str(policy['progress_policy'])
    cp=subprocess.run(['python3',str(ctl),'--policy',str(pol),'set-maturity','--percent',str(round(float(out['target_percent']))),'--label',str(policy.get('maturity_label') or 'ChaCha DEV global')],capture_output=True,text=True)
    if cp.returncode:raise RuntimeError('PROGRESS_CONTROLLER_FAILED:'+cp.stderr[-400:])
    applied=json.loads(cp.stdout);return {**out,'apply_authorized':True,'applied':True,'progress_state':applied}

def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument('--repo-root',type=Path,required=True);ap.add_argument('--policy',type=Path,required=True);ap.add_argument('--scorecard',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--apply',action='store_true');a=ap.parse_args()
    try:
        pol=load(a.policy);score=load(a.scorecard);out=reconcile(pol,score)
        if a.apply:out=apply(a.repo_root.resolve(),pol,out)
        a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(out,indent=2,sort_keys=True)+'\n')
        print('CHACHA_DEV_PLATFORM_MATURITY_RECONCILER='+out['status']);print('TARGET_PERCENT='+str(out['target_percent']));print('APPLIED='+str(bool(out.get('applied'))).lower());return 0 if out['status']=='PASS' else 20
    except Exception as e:print('CHACHA_DEV_PLATFORM_MATURITY_RECONCILER=BLOCK');print('REASON='+str(e));return 20
if __name__=='__main__':raise SystemExit(main())
