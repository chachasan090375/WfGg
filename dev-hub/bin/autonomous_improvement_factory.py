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
    for m in report.get('mechanisms') or []:
        if m.get('train_build_eligible') is not True: continue
        mid=str(m.get('mechanism_id') or '')
        rows.append({
          'train_id':train_id(mid),'mechanism_id':mid,'title':m.get('title') or mid,
          'state':'VALUE_GATE_PASS','functional_summary':m.get('functional_summary') or ('Amélioration de '+str(m.get('capability') or mid)),
          'platform_value':m.get('platform_value') or {'global_value_score':m.get('global_value_score')},
          'source_origin':m.get('origin'),'source_strategy':m.get('source_strategy'),'license_spdx':m.get('license_spdx'),
          'provenance_verified':m.get('provenance_verified') is True,'dependencies':m.get('dependencies') or [],'conflicts':m.get('conflicts') or [],
          'build_route':policy.get('build_route') or [],'production_ready':False,'human_promotion_button_enabled':False,
          'automatic_external_spend_eur':0
        })
    return {'schema':'chacha.dev/cockpit-update-center/v1','status':'PASS','items':rows,
            'batch_policy':policy.get('cockpit_update_center') or {},'production_authority':False,'automatic_external_spend_eur':0}

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--report',type=Path,required=True);ap.add_argument('--policy',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    out=build_queue(load(a.report),load(a.policy));save(a.output,out)
    print('CHACHA_DEV_AUTONOMOUS_IMPROVEMENT_FACTORY=PASS');print('TRAIN_REQUEST_COUNT='+str(len(out['items'])));print('PRODUCTION_AUTHORITY=NO');print('AUTOMATIC_EXTERNAL_SPEND_EUR=0')
if __name__=='__main__':main()
