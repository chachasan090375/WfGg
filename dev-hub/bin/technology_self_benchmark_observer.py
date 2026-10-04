#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path
from typing import Any

def load(p:Path)->dict[str,Any]:
    x=json.loads(p.read_text(encoding='utf-8'))
    if not isinstance(x,dict): raise ValueError('JSON_ROOT_NOT_OBJECT')
    return x

def save(p:Path,x:dict[str,Any])->None:
    p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')

def sig(x:dict[str,Any])->str:
    raw=json.dumps(x,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()
    return 'sha256:'+hashlib.sha256(raw).hexdigest()

def assess(dossier:dict[str,Any],policy:dict[str,Any])->dict[str,Any]:
    if dossier.get('schema')!='chacha.dev/external-mechanism-dossier/v1': raise ValueError('DOSSIER_SCHEMA_INVALID')
    t=policy['thresholds']; rows=[]; rejected=[]
    for m in dossier.get('mechanisms') or []:
        evidence=float(m.get('evidence_score') or 0); maturity=float(m.get('maturity_score') or 0)
        external=float(m.get('external_measured_score') or 0); internal=float(m.get('internal_measured_score') or 0)
        advantage=external-internal
        comparison_measured=m.get('comparison_measured') is True
        incompatible=bool(m.get('safety_incompatible') or m.get('permission_expansion_required') or m.get('automatic_paid_dependency_required'))
        reasons=[]
        if incompatible:
            cls='IGNORE'; reasons.append('GOVERNANCE_OR_COST_INCOMPATIBLE')
        elif not comparison_measured:
            cls='WATCH' if evidence>=40 else 'IGNORE'; reasons.append('LOCAL_COMPARATIVE_BENCHMARK_REQUIRED' if evidence>=40 else 'EXTERNAL_EVIDENCE_INSUFFICIENT')
        elif evidence>=t['minimum_evidence_score_for_pilot'] and maturity>=t['minimum_maturity_score'] and advantage>=t['minimum_advantage_points_for_pilot']:
            cls='PILOT_CANDIDATE'; reasons.append('STRONG_VERIFIED_ADVANTAGE')
        elif evidence>=t['minimum_evidence_score_for_benchmark'] and maturity>=t['minimum_maturity_score'] and advantage>=t['minimum_advantage_points']:
            cls='BENCHMARK'; reasons.append('VERIFIED_ADVANTAGE_REQUIRES_LOCAL_BENCHMARK')
        elif evidence>=40 and advantage>0:
            cls='WATCH'; reasons.append('PROMISING_BUT_NOT_PROVEN')
        else:
            cls='IGNORE'; reasons.append('NO_MATERIAL_VERIFIED_ADVANTAGE')
        row={"mechanism_id":m.get('mechanism_id'),"capability":m.get('capability'),"recommendation":cls,
             "evidence_score":evidence,"maturity_score":maturity,"external_measured_score":external,
             "internal_measured_score":internal,"advantage_points":advantage,"comparison_measured":comparison_measured,"reason_codes":reasons,
             "source_code_ingestion":False,"source_code_copy":False,"automatic_external_spend_eur":0}
        rows.append(row)
        if cls=='IGNORE': rejected.append({"mechanism_id":m.get('mechanism_id'),"evidence_signature":sig(m),"reason_codes":reasons,"reconsider_only_on_material_new_evidence":True})
    return {"schema":"chacha.dev/technology-self-benchmark-report/v1","status":"PASS","observer_role":"OUT_OF_BAND_ADVISORY",
            "mechanisms":rows,"negative_knowledge":rejected,"technology_watch_decision_authority":False,
            "logician_falsification_required":True,"architecture_council_review_required":True,
            "production_authority":False,"execution_authority":False,"foundry_execution_authorized":False,
            "guardian_preserved":True,"sentinel_preserved":True,"automatic_external_spend_eur":0}

def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument('--dossier',type=Path,required=True);ap.add_argument('--policy',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    out=assess(load(a.dossier),load(a.policy));save(a.output,out)
    print('CHACHA_DEV_TECHNOLOGY_SELF_BENCHMARK=PASS');print('MECHANISM_COUNT='+str(len(out['mechanisms'])));print('PRODUCTION_AUTHORITY=NO');print('SOURCE_CODE_COPY=NO');print('AUTOMATIC_EXTERNAL_SPEND_EUR=0');return 0
if __name__=='__main__': raise SystemExit(main())
