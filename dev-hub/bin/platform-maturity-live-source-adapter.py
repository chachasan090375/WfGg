#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path
from typing import Any

def load(p:Path)->dict[str,Any]:
    x=json.loads(p.read_text(encoding='utf-8'))
    if not isinstance(x,dict):raise ValueError('JSON_OBJECT_REQUIRED:'+str(p))
    return x

def digest(p:Path)->str:return 'sha256:'+hashlib.sha256(p.read_bytes()).hexdigest()
def gap_score(road:dict[str,Any],gid:str)->float:
    for g in road.get('gaps') or []:
        if isinstance(g,dict) and g.get('id')==gid:return float(g.get('progress') or 0)
    return 0.0

def build(policy:dict[str,Any],road_path:Path,const_path:Path,ha_path:Path)->dict[str,Any]:
    if policy.get('schema')!='chacha.dev/platform-maturity-live-source-adapter-policy/v1':raise ValueError('POLICY_SCHEMA_MISMATCH')
    road,const,ha=load(road_path),load(const_path),load(ha_path)
    if road.get('schema')!='chacha.dev/autonomy-gap-roadmap/v1' or road.get('reassessment_source')!='LIVE_POLICY_EVIDENCE':raise ValueError('LIVE_ROADMAP_REQUIRED')
    if const.get('status')!=policy.get('constitution_required_status'):raise ValueError('CONSTITUTION_NOT_STABLE')
    if ha.get('status')!=policy.get('ha_required_status'):raise ValueError('HA_REHEARSAL_NOT_PASS')
    w=policy.get('weights') or {};dims=[
      {'id':'autonomy-roadmap','score':float(road.get('score_percent') or 0),'weight':float(w.get('autonomy_roadmap') or 0),'evidence_path':str(road_path.resolve()),'evidence_digest':digest(road_path)},
      {'id':'constitutional-governance','score':100.0,'weight':float(w.get('constitutional_governance') or 0),'evidence_path':str(const_path.resolve()),'evidence_digest':digest(const_path)},
      {'id':'resilience','score':gap_score(road,'resilience-ha'),'weight':float(w.get('resilience') or 0),'evidence_path':str(ha_path.resolve()),'evidence_digest':digest(ha_path)}]
    if sum(d['weight'] for d in dims)!=100:raise ValueError('WEIGHT_SUM_NOT_100')
    return {'schema':policy.get('scorecard_schema'),'status':'PASS','dimensions':dims,'source_roadmap_score':road.get('score_percent'),'adapter_execution_authority':False,'automatic_external_spend_eur':0}

def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument('--policy',type=Path,required=True);ap.add_argument('--roadmap',type=Path,required=True);ap.add_argument('--constitution-watch',type=Path,required=True);ap.add_argument('--ha-rehearsal',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    try:
        out=build(load(a.policy),a.roadmap,a.constitution_watch,a.ha_rehearsal);a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(out,indent=2,sort_keys=True)+'\n');print('CHACHA_DEV_PLATFORM_MATURITY_LIVE_ADAPTER=PASS');print('ROADMAP_SCORE='+str(out['source_roadmap_score']));print('EXECUTION_AUTHORITY=NO');return 0
    except Exception as e:print('CHACHA_DEV_PLATFORM_MATURITY_LIVE_ADAPTER=BLOCK');print('REASON='+str(e));return 20
if __name__=='__main__':raise SystemExit(main())
