#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,os
from pathlib import Path
from typing import Any

SCHEMA='chacha.dev/native-local-resource-admission-policy/v1'

def load(path:Path)->dict[str,Any]:
    x=json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(x,dict):raise ValueError('JSON_ROOT_NOT_OBJECT')
    return x

def mem_available_mb()->int:
    for line in Path('/proc/meminfo').read_text().splitlines():
        if line.startswith('MemAvailable:'):return int(line.split()[1])//1024
    raise RuntimeError('MEMAVAILABLE_MISSING')

def disk_free_mb(path:Path)->int:
    probe=path
    while not probe.exists() and probe!=probe.parent:probe=probe.parent
    st=os.statvfs(probe);return (st.f_bavail*st.f_frsize)//(1024*1024)

def snapshot(runtime_policy:dict[str,Any])->dict[str,Any]:
    model=Path(str(runtime_policy['model_artifact']));target=model.parent
    return {'available_memory_mb':mem_available_mb(),'free_disk_mb':disk_free_mb(target),
            'cpu_count':os.cpu_count() or 1,'load1':os.getloadavg()[0]}

def decide(policy:dict[str,Any],runtime:dict[str,Any],snap:dict[str,Any])->dict[str,Any]:
    if policy.get('schema')!=SCHEMA:raise ValueError('POLICY_SCHEMA_INVALID')
    res=runtime.get('resources') or {};limits=runtime.get('limits') or {};reasons=[]
    mem_need=max(int(policy['minimum_available_memory_mb']),int(res['memory_required_mb'])+int(policy['minimum_free_memory_after_load_mb']))
    if int(snap['available_memory_mb'])<mem_need:reasons.append('MEMORY_HEADROOM_INSUFFICIENT')
    disk_need=int(res['disk_required_mb'])+int(policy['minimum_free_disk_after_install_mb'])
    if int(snap['free_disk_mb'])<disk_need:reasons.append('DISK_HEADROOM_INSUFFICIENT')
    cpus=max(1,int(snap['cpu_count']))
    if policy.get('cpu_threads_must_fit') and int(limits['threads'])>cpus:reasons.append('THREADS_EXCEED_CPU_COUNT')
    if int(limits['parallel_slots'])>int(policy['maximum_parallel_slots']):reasons.append('PARALLEL_SLOTS_EXCEED_POLICY')
    if float(snap['load1'])/cpus>float(policy['maximum_load_per_cpu']):reasons.append('CPU_LOAD_TOO_HIGH')
    return {'schema':'chacha.dev/native-local-resource-admission/v1','status':'PASS' if not reasons else 'BLOCK',
            'reasons':reasons,'snapshot':snap,'memory_required_with_headroom_mb':mem_need,
            'disk_required_with_headroom_mb':disk_need,'fallback_required':bool(reasons),
            'production_activation_authorized':False,'automatic_external_spend_eur':0}

def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument('--repo-root',type=Path,required=True);ap.add_argument('--policy',type=Path,required=True)
    ap.add_argument('--snapshot',type=Path);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    pol=load(a.policy);runtime=load(a.repo_root/str(pol['runtime_policy']))
    snap=load(a.snapshot) if a.snapshot else snapshot(runtime);out=decide(pol,runtime,snap)
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(out,indent=2)+'\n')
    print('CHACHA_DEV_NATIVE_LOCAL_RESOURCE_ADMISSION='+out['status']);print('FALLBACK_REQUIRED='+str(out['fallback_required']).lower())
    print('PRODUCTION_ACTIVATION_AUTHORIZED=NO');print('AUTOMATIC_EXTERNAL_SPEND_EUR=0');return 0 if out['status']=='PASS' else 20

if __name__=='__main__':raise SystemExit(main())
