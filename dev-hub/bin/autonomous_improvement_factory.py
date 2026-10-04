#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path
from typing import Any

def load(p:Path)->dict[str,Any]:
    x=json.loads(p.read_text(encoding='utf-8')); assert isinstance(x,dict); return x

def save(p:Path,x:dict[str,Any]):
    p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')

def train_id(mechanism_id:str)->str:
    return 'update-'+hashlib.sha256(mechanism_id.encode()).hexdigest()[:16]

def build_queue(report:dict[str,Any],policy:dict[str,Any])->dict[str,Any]:
    rows=[]
    if report.get('schema')=='chacha.dev/improvement-intelligence-synthesis/v1':
        candidates=report.get('items') or []
        def eligible(m): return m.get('improvement_request_authorized') is True and m.get('recommendation')=='IMPROVEMENT_CANDIDATE'
    else:
        candidates=report.get('mechanisms') or []
        def eligible(m): return m.get('train_build_eligible') is True
    for m in candidates:
        if not eligible(m): continue
        mid=str(m.get('mechanism_id') or m.get('axis_id') or m.get('cluster_key') or '')
        if not mid: continue
        rows.append({
          'train_id':train_id(mid),'mechanism_id':mid,'title':m.get('title') or mid,
          'state':'VALUE_GATE_PASS','functional_summary':m.get('functional_summary') or ('Amélioration de '+str(m.get('capability') or mid)),
          'platform_value':m.get('platform_value') or {'global_value_score':m.get('global_value_score'),'dimensions':m.get('value_dimensions')},
          'source_origin':m.get('origin') or 'IMPROVEMENT_INTELLIGENCE_FABRIC','source_agents':m.get('source_agents') or [],
          'source_strategy':m.get('source_strategy') or 'STRATEGY_RESOLUTION_PENDING','license_spdx':m.get('license_spdx'),
          'source_code_copy_allowed':m.get('source_code_copy_allowed') is True,
          'provenance_verified':m.get('provenance_verified') is True,'target_component_id':m.get('target_component_id') or 'central-orchestrator',
          'candidate_owner':m.get('candidate_owner') or 'branch-foundry','dependencies':m.get('dependencies') or [],'conflicts':m.get('conflicts') or [],
          'build_route':policy.get('build_route') or [],'production_ready':False,'human_promotion_button_enabled':False,
          'central_orchestrator_handoff_required':True,'automatic_external_spend_eur':0
        })
    return {'schema':'chacha.dev/cockpit-update-center/v1','status':'PASS','items':rows,
            'batch_policy':policy.get('cockpit_update_center') or {},'production_authority':False,'automatic_external_spend_eur':0}

def reassessment_request(row:dict[str,Any])->dict[str,Any]:
    tid=str(row.get('train_id') or '')
    return {
      'schema':'chacha.dev/platform-component-reassessment-request/v1','request_id':'autonomous-improvement-'+tid,
      'component_id':str(row.get('target_component_id') or 'central-orchestrator'),
      'trigger_reasons':['AUTONOMOUS_IMPROVEMENT_FACTORY','TRAIN_ID:'+tid,'SOURCE:'+str(row.get('source_origin') or 'UNKNOWN')],
      'candidate_owner':str(row.get('candidate_owner') or 'branch-foundry'),'shadow_required':True,'pilot_required':True,
      'technology_watch_revalidation_required':True,'logician_falsification_required':True,
      'functional_summary':row.get('functional_summary'),'platform_value':row.get('platform_value'),
      'source_strategy':row.get('source_strategy'),'license_spdx':row.get('license_spdx'),'provenance_verified':row.get('provenance_verified') is True,
      'dependencies':row.get('dependencies') or [],'conflicts':row.get('conflicts') or [],
      'direct_component_mutation':False,'self_promotion':False,'permission_expansion':False,
      'architecture_council_final_authority':True,'automatic_external_spend_eur':0}

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--report',type=Path,required=True);ap.add_argument('--policy',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    out=build_queue(load(a.report),load(a.policy));save(a.output,out)
    print('CHACHA_DEV_AUTONOMOUS_IMPROVEMENT_FACTORY=PASS');print('TRAIN_REQUEST_COUNT='+str(len(out['items'])));print('PRODUCTION_AUTHORITY=NO');print('AUTOMATIC_EXTERNAL_SPEND_EUR=0')
if __name__=='__main__':main()
