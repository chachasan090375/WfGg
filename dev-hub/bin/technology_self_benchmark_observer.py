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

def source_strategy(m:dict[str,Any])->tuple[str,bool,list[str]]:
    reasons=[]
    if m.get('internal_reuse_available') is True:
        return 'INTERNAL_REUSE',False,['INTERNAL_REUSE_AVAILABLE']
    oss=(m.get('source_is_open_source') is True and m.get('source_code_available') is True)
    license_ok=(m.get('license_compatible') is True and m.get('license_obligations_recorded') is True)
    provenance=m.get('provenance_verified') is True
    if oss and license_ok and provenance:
        return 'OPEN_SOURCE_REUSE',True,['OPEN_SOURCE_LICENSE_AND_PROVENANCE_PASS']
    if oss and not license_ok: reasons.append('OPEN_SOURCE_LICENSE_NOT_COMPATIBLE_OR_UNASSESSED')
    if oss and not provenance: reasons.append('OPEN_SOURCE_PROVENANCE_NOT_VERIFIED')
    if m.get('owned_implementation_feasible',True) is not False:
        return 'OWNED_REIMPLEMENTATION',False,reasons+['OWNED_IMPLEMENTATION_PREFERRED']
    if m.get('connector_fallback_available') is True:
        return 'CONNECTOR_FALLBACK',False,reasons+['OWNED_IMPLEMENTATION_NOT_REASONABLY_FEASIBLE']
    return 'NO_ADMISSIBLE_IMPLEMENTATION_PATH',False,reasons+['NO_ADMISSIBLE_IMPLEMENTATION_PATH']

def value_gate(m:dict[str,Any],policy:dict[str,Any])->tuple[bool,list[str]]:
    u=policy.get('utility_gate') or {}; reasons=[]
    score=float(m.get('global_value_score') or 0)
    if score<float(u.get('minimum_global_value_score') or 0): reasons.append('GLOBAL_VALUE_SCORE_TOO_LOW')
    if u.get('architecture_fit_required') and m.get('architecture_fit') is not True: reasons.append('ARCHITECTURE_FIT_REQUIRED')
    if m.get('duplicate_capability') is True and u.get('material_gain_required_for_duplicate_capability') and m.get('material_gain_over_existing') is not True:
        reasons.append('DUPLICATE_WITHOUT_MATERIAL_GAIN')
    if float(m.get('maintenance_debt_score') or 0)>float(u.get('maximum_maintenance_debt_score') or 100): reasons.append('MAINTENANCE_DEBT_TOO_HIGH')
    if not any(float(m.get('value_dimensions',{}).get(k) or 0)>0 for k in u.get('accepted_value_dimensions') or []):
        reasons.append('NO_MEASURABLE_PLATFORM_VALUE_DIMENSION')
    return not reasons,reasons

def assess(dossier:dict[str,Any],policy:dict[str,Any])->dict[str,Any]:
    if dossier.get('schema')!='chacha.dev/external-mechanism-dossier/v1': raise ValueError('DOSSIER_SCHEMA_INVALID')
    t=policy['thresholds']; rows=[]; rejected=[]
    origin=str(dossier.get('origin') or 'EXTERNAL').upper()
    for m in dossier.get('mechanisms') or []:
        evidence=float(m.get('evidence_score') or 0); maturity=float(m.get('maturity_score') or 0)
        external=float(m.get('external_measured_score') or 0); internal=float(m.get('internal_measured_score') or 0)
        advantage=external-internal; comparison_measured=m.get('comparison_measured') is True
        incompatible=bool(m.get('safety_incompatible') or m.get('permission_expansion_required') or m.get('automatic_paid_dependency_required'))
        utility_ok,utility_reasons=value_gate(m,policy); strategy,copy_allowed,strategy_reasons=source_strategy(m)
        reasons=[]
        if incompatible:
            cls='IGNORE'; reasons.append('GOVERNANCE_OR_COST_INCOMPATIBLE')
        elif not utility_ok:
            cls='IGNORE'; reasons+=utility_reasons
        elif strategy=='NO_ADMISSIBLE_IMPLEMENTATION_PATH':
            cls='WATCH'; reasons+=strategy_reasons
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
        reasons+=strategy_reasons
        build_eligible=(cls=='PILOT_CANDIDATE' and utility_ok and strategy!='NO_ADMISSIBLE_IMPLEMENTATION_PATH')
        row={
          'mechanism_id':m.get('mechanism_id'),'capability':m.get('capability'),'origin':origin,'recommendation':cls,
          'title':m.get('title'),'functional_summary':m.get('functional_summary'),'platform_value':m.get('platform_value') or m.get('value_dimensions'),
          'dependencies':m.get('dependencies') or [],'conflicts':m.get('conflicts') or [],'source_refs':m.get('source_refs') or [],
          'evidence_score':evidence,'maturity_score':maturity,'external_measured_score':external,'internal_measured_score':internal,
          'advantage_points':advantage,'comparison_measured':comparison_measured,'global_value_score':float(m.get('global_value_score') or 0),
          'utility_gate_pass':utility_ok,'source_strategy':strategy,'source_code_copy_allowed':copy_allowed,'source_code_copy':copy_allowed,
          'license_spdx':m.get('license_spdx'),'provenance_verified':m.get('provenance_verified') is True,
          'train_build_eligible':build_eligible,'improvement_request_authorized':build_eligible,'reason_codes':list(dict.fromkeys(reasons)),
          'automatic_external_spend_eur':0
        }
        rows.append(row)
        if cls=='IGNORE': rejected.append({'mechanism_id':m.get('mechanism_id'),'evidence_signature':sig(m),'reason_codes':row['reason_codes'],'reconsider_only_on_material_new_evidence':True})
    return {
      'schema':'chacha.dev/technology-self-benchmark-report/v1','status':'PASS','observer_role':'OUT_OF_BAND_ADVISORY',
      'mechanisms':rows,'negative_knowledge':rejected,'technology_watch_decision_authority':False,
      'observer_direct_build_authority':False,'central_orchestrator_improvement_handoff':True,
      'logician_falsification_required':True,'architecture_council_review_required':True,
      'production_authority':False,'execution_authority':False,'foundry_execution_authorized':False,'guardian_preserved':True,'sentinel_preserved':True,
      'automatic_external_spend_eur':0
    }

def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument('--dossier',type=Path,required=True);ap.add_argument('--policy',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    out=assess(load(a.dossier),load(a.policy));save(a.output,out)
    print('CHACHA_DEV_TECHNOLOGY_SELF_BENCHMARK=PASS');print('MECHANISM_COUNT='+str(len(out['mechanisms'])));print('OBSERVER_DIRECT_BUILD_AUTHORITY=NO');print('AUTOMATIC_EXTERNAL_SPEND_EUR=0');return 0
if __name__=='__main__': raise SystemExit(main())
