#!/usr/bin/env python3
from __future__ import annotations
import argparse,datetime,json,os,subprocess,sys,uuid
from pathlib import Path
from typing import Any

def iso(): return datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00','Z')
def load(p:Path,default=None):
    try:
        x=json.loads(p.read_text(encoding='utf-8')); return x if isinstance(x,dict) else ({} if default is None else default)
    except Exception:return {} if default is None else default
def save(p:Path,x:dict[str,Any]):
    p.parent.mkdir(parents=True,exist_ok=True); t=p.with_suffix(p.suffix+'.tmp')
    t.write_text(json.dumps(x,indent=2,ensure_ascii=False)+'\n',encoding='utf-8'); os.replace(t,p)
def run(argv:list[str],timeout=60):
    return subprocess.run(argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=timeout)
def active(systemctl:Path,unit:str)->bool:
    p=run([str(systemctl),'is-active',unit],10); return p.returncode==0 and p.stdout.strip()=='active'
def guardian(client:Path,policy:Path,event:Path,result:Path,payload:dict[str,Any])->tuple[bool,dict[str,Any]]:
    save(event,payload); p=run([sys.executable,str(client),'--policy',str(policy),'check','--event',str(event)],45)
    try:x=json.loads([z for z in p.stdout.splitlines() if z.strip()][-1])
    except Exception:x={'verdict':'UNAVAILABLE','stderr':p.stderr[-800:]}
    save(result,x); return p.returncode==0 and x.get('verdict') in {'PASS','WARNING'},x
def event(action_id:str,phase:str,unit:str,evidence:dict[str,Any])->dict[str,Any]:
    return {'schema':'chacha.dev/governance-action/v1','event_id':action_id+'-'+phase.lower(),'action_id':action_id,
      'phase':phase,'actor':'autonomous-recovery-agent','subject_role':'autonomous-recovery-agent',
      'action':'RESTART_SAFE_SERVICE','permission':'service-restart','project_id':'chacha-dev-platform',
      'evidence':evidence,'context':{'deadline_seconds':180,'service_unit':unit,'resource_class':'light'},
      'capabilities':['recovery-orchestration','health-checks'],'automatic_external_spend_eur':0}

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument('--repo-root',type=Path,required=True); ap.add_argument('--runtime-root',type=Path,default=Path('/opt/chacha-dev/runtime'))
    ap.add_argument('--policy',type=Path); ap.add_argument('--systemctl-bin',type=Path,default=Path('/usr/bin/systemctl'))
    ap.add_argument('--guardian-client',type=Path); ap.add_argument('--guardian-policy',type=Path)
    ap.add_argument('--recovery-orchestrator',type=Path); a=ap.parse_args()
    repo=a.repo_root.resolve(); runtime=a.runtime_root.resolve()
    policy=load(a.policy or repo/'dev-hub/config/recovery-orchestrator.v1.json')
    guardian_client=a.guardian_client or repo/'dev-hub/bin/guardian-client.py'
    guardian_policy=a.guardian_policy or repo/'dev-hub/config/guardian-runtime-policy.v1.json'
    recovery=a.recovery_orchestrator or repo/'dev-hub/bin/recovery-orchestrator.py'
    stop=load(runtime/'control/emergency-stop.json',{})
    root=runtime/'autonomous-recovery'; work=root/'work'/('recovery-'+uuid.uuid4().hex[:12]); work.mkdir(parents=True,exist_ok=True)
    report={'schema':'chacha.dev/autonomous-recovery-run/v1','observed_at':iso(),'status':'PASS','actions':[],
      'supervisor_direct_mutation':False,'automatic_external_spend_eur':0}
    if stop.get('active') is True:
        report.update({'status':'STOPPED','reason':'EMERGENCY_STOP_ACTIVE'}); save(root/'latest.json',report); save(work/'run.json',report); return 0
    safe=((policy.get('service_health') or {}).get('safe_restart') or [])
    for row in safe:
        if not isinstance(row,dict) or not row.get('unit'): continue
        unit=str(row['unit'])
        if active(a.systemctl_bin,unit): continue
        incident={'schema':'chacha.dev/recovery-incident/v1','incident_id':'svc-'+unit.replace('.','-'),
          'project_id':'chacha-dev-platform','service_unit':unit,'safe_service_restart_available':True,
          'rollback_available':False,'destructive_restore_required':False,'data_loss_possible':False,
          'security_boundary_change':False,'automatic_external_spend_eur':0}
        ip=work/(unit.replace('/','_')+'.incident.json'); dp=work/(unit.replace('/','_')+'.decision.json'); save(ip,incident)
        d=run([sys.executable,str(recovery),'--incident',str(ip),'--policy',str(a.policy or repo/'dev-hub/config/recovery-orchestrator.v1.json'),'--output',str(dp)],60)
        decision=load(dp,{})
        if d.returncode!=0 or decision.get('action')!='RESTART_SAFE_SERVICE' or decision.get('autonomous') is not True:
            report['status']='BLOCKED'; report['actions'].append({'unit':unit,'status':'BLOCKED','reason':'RECOVERY_DECISION_NOT_AUTONOMOUS'}); continue
        evidence={'service_allowlisted':True,'health_failed':True,'emergency_stop_inactive':True,
          'decision_digest':'sha256:'+__import__('hashlib').sha256(dp.read_bytes()).hexdigest(),'automatic_external_spend_eur':0}
        aid='safe-service-recovery-'+uuid.uuid4().hex[:12]
        ok,pre=guardian(guardian_client,guardian_policy,work/(aid+'-pre.json'),work/(aid+'-pre-result.json'),event(aid,'PRE_ACTION',unit,evidence))
        if not ok:
            report['status']='BLOCKED'; report['actions'].append({'unit':unit,'status':'BLOCKED','reason':'GUARDIAN_PRE_BLOCK','guardian':pre}); continue
        restart=run([str(a.systemctl_bin),'restart',unit],120)
        healthy=restart.returncode==0 and active(a.systemctl_bin,unit)
        post_evidence={**evidence,'restart_returncode':restart.returncode,'restart_succeeded':healthy}
        post_ok,post=guardian(guardian_client,guardian_policy,work/(aid+'-post.json'),work/(aid+'-post-result.json'),event(aid,'POST_ACTION',unit,post_evidence))
        status='VERIFIED' if healthy and post_ok else 'BLOCKED'
        if status!='VERIFIED': report['status']='BLOCKED'
        report['actions'].append({'unit':unit,'status':status,'owner':'autonomous-recovery-agent',
          'guardian_pre':pre.get('verdict'),'guardian_post':post.get('verdict'),'restart_returncode':restart.returncode,
          'verified_active_after_restart':healthy,'direct_mutation_by_supervisor':False})
    save(work/'run.json',report); save(root/'latest.json',report)
    print('CHACHA_DEV_AUTONOMOUS_RECOVERY='+report['status'])
    print('RECOVERY_ACTIONS='+str(len(report['actions'])))
    print('AUTOMATIC_EXTERNAL_SPEND_EUR=0')
    return 0 if report['status'] in {'PASS','STOPPED'} or all(x.get('status')=='VERIFIED' for x in report['actions']) else 20

if __name__=='__main__': raise SystemExit(main())
