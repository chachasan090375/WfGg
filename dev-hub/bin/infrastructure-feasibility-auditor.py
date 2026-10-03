#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,time
from pathlib import Path
from typing import Any
SCHEMA="chacha.dev/infrastructure-feasibility-report/v1"

def load(p:Path)->dict[str,Any]:
 x=json.loads(p.read_text());
 if not isinstance(x,dict):raise ValueError('JSON_ROOT_NOT_OBJECT')
 return x

def save(p:Path,x):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,indent=2,ensure_ascii=False)+'\n')
def n(x,k):return float(x.get(k) or 0)
def norm_values(key:str,values)->set[str]:
 vals=set(map(str,values or []))
 if key=="runtimes":
  if "python3" in vals:vals.add("python")
  if "nodejs" in vals:vals.add("node")
 return vals

def audit(infra:dict[str,Any],req:dict[str,Any],policy:dict[str,Any])->dict[str,Any]:
 reserve=policy['safety_reserve'];usable={
  'cpu_cores':n(infra,'cpu_cores')*(1-float(reserve['cpu_fraction'])),
  'ram_gib':n(infra,'ram_gib')*(1-float(reserve['ram_fraction'])),
  'storage_free_gib':n(infra,'storage_free_gib')*(1-float(reserve['storage_fraction'])),
  'gpu_vram_gib':n(infra,'gpu_vram_gib'), 'storage_iops':n(infra,'storage_iops'),'network_mbps':n(infra,'network_mbps')}
 hard=[];soft=[]
 numeric=['cpu_cores','ram_gib','storage_free_gib','gpu_vram_gib','storage_iops','network_mbps']
 for k in numeric:
  need=n(req,k)
  if need and usable.get(k,0)<need: hard.append({'dimension':k,'required':need,'usable':round(usable.get(k,0),3)})
 max_latency=float(req.get('max_latency_ms') or 0)
 if max_latency and n(infra,'latency_ms')>max_latency:soft.append({'dimension':'latency_ms','required_max':max_latency,'observed':n(infra,'latency_ms')})
 for k in ['os_families','runtimes','virtualization','device_access']:
  needs=norm_values(k,req.get(k));have=norm_values(k,infra.get(k));missing=sorted(needs-have)
  if missing: hard.append({'dimension':k,'missing':missing})
 if req.get('availability') and str(infra.get('availability') or '') not in set(req.get('acceptable_availability') or [req['availability']]): soft.append({'dimension':'availability','required':req['availability'],'observed':infra.get('availability')})
 verdict='NOT_FIT' if hard else 'FIT_WITH_CONSTRAINTS' if soft else 'FIT'
 target=None
 if verdict=='NOT_FIT':
  reserve_by={'cpu_cores':float(reserve['cpu_fraction']),'ram_gib':float(reserve['ram_fraction']),'storage_free_gib':float(reserve['storage_fraction'])}
  minimum={}
  for k in numeric:
   raw_need=n(req,k)/(1-reserve_by[k]) if k in reserve_by and n(req,k)>0 else n(req,k)
   minimum[k]=round(max(raw_need,n(infra,k)),2)
  recommended={k:round(max(minimum[k]*1.25,n(infra,k)),2) for k in numeric}
  target={'minimum_profile':minimum,'recommended_profile':recommended,'missing_components':hard,'placement_policy':'select zero-incremental-cost existing hosts first; add runner only when a required platform/device class is unavailable','migration_path':['preserve current production','provision isolated target runner','qualify target capabilities','bind only after Guardian/Sentinel and human approval if material'],'cost_boundary':'NO_AUTOMATIC_EXTERNAL_SPEND','risks':['capacity mismatch until target is provisioned','platform-specific runners may be required']}
 return {'schema':SCHEMA,'status':'PASS','verdict':verdict,'infrastructure_id':infra.get('infrastructure_id'),'requirements_id':req.get('requirements_id'),'usable_capacity':usable,'hard_gaps':hard,'constraints':soft,'target_infrastructure_architecture':target,'execution_on_current_infrastructure_allowed':verdict!='NOT_FIT','automatic_external_spend_eur':0,'production_authority':False,'observed_at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())}

def main()->int:
 ap=argparse.ArgumentParser();ap.add_argument('--infrastructure',type=Path,required=True);ap.add_argument('--requirements',type=Path,required=True);ap.add_argument('--policy',type=Path,default=Path('dev-hub/config/infrastructure-feasibility.v1.json'));ap.add_argument('--output',type=Path,required=True);a=ap.parse_args();out=audit(load(a.infrastructure),load(a.requirements),load(a.policy));save(a.output,out);print('CHACHA_DEV_INFRASTRUCTURE_FEASIBILITY='+out['verdict']);print('AUTOMATIC_EXTERNAL_SPEND_EUR=0');return 0
if __name__=='__main__':raise SystemExit(main())
