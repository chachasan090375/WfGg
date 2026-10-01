#!/usr/bin/env python3
from __future__ import annotations
import argparse,json
from pathlib import Path
from typing import Any

def load(p:Path)->dict[str,Any]:
    x=json.loads(p.read_text(encoding='utf-8'))
    if not isinstance(x,dict):raise ValueError('JSON_OBJECT_REQUIRED:'+str(p))
    return x

def route(policy:dict[str,Any],incident:dict[str,Any])->dict[str,Any]:
    if policy.get('schema')!='chacha.dev/incident-safe-remediation-router-policy/v1':raise ValueError('POLICY_SCHEMA_MISMATCH')
    code=str(incident.get('code') or '');severity=str(incident.get('severity') or '').upper();target=(policy.get('safe_routes') or {}).get(code)
    blockers=[]
    if not target:blockers.append('NO_SAFE_ROUTE')
    if severity=='CRITICAL' and policy.get('critical_severity_requires_human') is True:blockers.append('CRITICAL_REQUIRES_HUMAN')
    if incident.get('destructive') is not False:blockers.append('DESTRUCTIVE_NOT_ALLOWED')
    if incident.get('production_mutation') is not False:blockers.append('PRODUCTION_MUTATION_NOT_ALLOWED')
    if float(incident.get('automatic_external_spend_eur') or 0)!=0:blockers.append('NONZERO_EXTERNAL_SPEND')
    return {'schema':'chacha.dev/incident-safe-remediation-route/v1','status':'AUTO_ELIGIBLE' if not blockers else 'HUMAN_BOUNDARY','incident_code':code,'target':target if not blockers else None,'blockers':sorted(set(blockers)),'router_executes_remediation':False,'production_mutation_authorized':False,'automatic_external_spend_eur':0}

def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument('--policy',type=Path,required=True);ap.add_argument('--incident',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    try:
        out=route(load(a.policy),load(a.incident));a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(out,indent=2,sort_keys=True)+'\n');print('CHACHA_DEV_INCIDENT_SAFE_REMEDIATION_ROUTER='+out['status']);print('EXECUTION_AUTHORITY=NO');return 0
    except Exception as e:print('CHACHA_DEV_INCIDENT_SAFE_REMEDIATION_ROUTER=BLOCK');print('REASON='+str(e));return 20
if __name__=='__main__':raise SystemExit(main())
