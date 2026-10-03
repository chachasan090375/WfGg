#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,time
from pathlib import Path
from typing import Any

def load(p:Path)->dict[str,Any]:
 x=json.loads(p.read_text(encoding='utf-8'))
 if not isinstance(x,dict):raise ValueError('JSON_ROOT_NOT_OBJECT')
 return x

def save(p:Path,x):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
def roles(h):return set(map(str,h.get('roles') or []))
def healthy(h):return str(h.get('health') or '').upper() in {'PASS','HEALTHY','READY'}

def requirements(target:dict[str,Any])->tuple[set[str],str]:
 fam=str(target.get('family') or '').lower();purpose=str(target.get('purpose') or 'compatibility_test').lower();hw=bool(target.get('hardware_specific'))
 if hw:return {f'physical-device:{fam}'},'PHYSICAL_DEVICE_REQUIRED'
 if fam=='linux':return ({'linux-build'} if purpose=='build' else {'linux-runtime'}),'LINUX_RUNNER'
 if fam=='web_runtime':return {'web-runtime'},'WEB_RUNTIME_RUNNER'
 if fam=='windows':return {'windows-vm'},'WINDOWS_VM'
 if fam=='freebsd_unix':return {'freebsd-unix-vm'},'FREEBSD_UNIX_VM'
 if fam=='android':
  if purpose=='build':return {'android-build'},'ANDROID_BUILD_RUNNER'
  if purpose in {'accelerated_emulator','emulator'}:return {'android-emulator-native-host'},'ANDROID_ACCELERATED_EMULATOR_HOST'
  return {'android-compat'},'ANDROID_COMPATIBILITY_RUNNER'
 if fam=='ios':return {'apple-native-ios'},'APPLE_NATIVE_IOS_RUNNER'
 if fam=='macos':return {'apple-native-macos'},'APPLE_NATIVE_MACOS_RUNNER'
 if fam=='embedded_linux':return {'embedded-linux-build'},'EMBEDDED_LINUX_RUNNER'
 return {f'target-family:{fam}'},'UNKNOWN_TARGET_FAMILY'

def plan(matrix:dict[str,Any],inventory:dict[str,Any],images:dict[str,Any],policy:dict[str,Any])->dict[str,Any]:
 hosts=[h for h in inventory.get('hosts') or [] if isinstance(h,dict) and healthy(h)]
 image_rows=images.get('images') or [];routes=[];gaps=[]
 for t in matrix.get('targets') or []:
  tid=str(t.get('target_id') or '');fam=str(t.get('family') or '').lower();req,label=requirements(t)
  candidates=[]
  for h in hosts:
   if req.issubset(roles(h)):candidates.append(h)
  # For generic x86 guest families, a QNAP KVM host can host the target after a verified image exists.
  if not candidates and fam in {'windows','freebsd_unix'}:
   generic=[h for h in hosts if 'qnap-kvm-host' in roles(h) and 'x86-guest-vm' in roles(h)]
   if generic:candidates=generic
  image_needed=fam in {'windows','linux','freebsd_unix','android'} and str(t.get('purpose') or '').lower()!='build'
  matching=[x for x in image_rows if isinstance(x,dict) and str(x.get('family') or '').lower()==fam and x.get('verified') is True and str(x.get('sha256') or '').startswith('sha256:')]
  if not candidates:
   gap={'target_id':tid,'family':fam,'kind':'RUNNER_CAPABILITY_MISSING','required_roles':sorted(req),'route_label':label,'automatic_paid_provisioning':False};gaps.append(gap);routes.append({'target_id':tid,'status':'BLOCKED_RUNNER_MISSING','required_roles':sorted(req)});continue
  chosen=sorted(candidates,key=lambda h:(int(h.get('preference') or 100),str(h.get('host_id'))))[0]
  if f'native:{fam}' in roles(chosen):image_needed=False
  if image_needed and not matching:
   gap={'target_id':tid,'family':fam,'kind':'VERIFIED_BASE_IMAGE_MISSING','host_id':chosen.get('host_id'),'required_sha256':True,'automatic_download_or_purchase':False};gaps.append(gap);routes.append({'target_id':tid,'status':'READY_HOST_IMAGE_REQUIRED','host_id':chosen.get('host_id'),'runner_type':chosen.get('type'),'required_roles':sorted(req),'image_required':True});continue
  routes.append({'target_id':tid,'status':'READY','host_id':chosen.get('host_id'),'runner_type':chosen.get('type'),'required_roles':sorted(req),'image_id':matching[0].get('image_id') if matching else None,'image_required':image_needed,'resource_admission_required':True})
 return {'schema':'chacha.dev/virtual-os-device-lab-plan/v1','status':'PASS' if not gaps else 'PARTIAL','matrix_id':matrix.get('matrix_id'),'routes':routes,'gaps':gaps,'host_count':len(hosts),'automatic_provisioning':False,'automatic_external_spend_eur':0,'execution_authority':False,'production_authority':False,'planned_at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())}

def main()->int:
 ap=argparse.ArgumentParser();ap.add_argument('--matrix',type=Path,required=True);ap.add_argument('--inventory',type=Path,required=True);ap.add_argument('--images',type=Path,default=Path('dev-hub/config/virtual-os-image-registry.v1.json'));ap.add_argument('--policy',type=Path,default=Path('dev-hub/config/virtual-os-device-lab.v1.json'));ap.add_argument('--output',type=Path,required=True);a=ap.parse_args();out=plan(load(a.matrix),load(a.inventory),load(a.images),load(a.policy));save(a.output,out);print('CHACHA_DEV_VIRTUAL_OS_DEVICE_LAB='+out['status']);print('GAPS='+str(len(out['gaps'])));print('AUTOMATIC_EXTERNAL_SPEND_EUR=0');return 0
if __name__=='__main__':raise SystemExit(main())
