#!/usr/bin/env python3
from __future__ import annotations
import argparse,datetime,hashlib,json,os,subprocess,sys,uuid
from pathlib import Path
from typing import Any

SCHEMA='chacha.dev/ephemeral-branch-lifecycle/v1'

def iso(): return datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00','Z')
def load(p:Path,default=None):
    try:
        x=json.loads(p.read_text(encoding='utf-8')); return x if isinstance(x,dict) else ({} if default is None else default)
    except Exception:return {} if default is None else default
def save(p:Path,x:dict[str,Any]):
    p.parent.mkdir(parents=True,exist_ok=True); t=p.with_suffix(p.suffix+'.tmp')
    t.write_text(json.dumps(x,indent=2,ensure_ascii=False)+'\n',encoding='utf-8'); os.replace(t,p)
def run(argv:list[str],timeout=60):
    return subprocess.run([str(x) for x in argv],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=timeout)
def parse_ts(v:Any):
    try:return datetime.datetime.fromisoformat(str(v).replace('Z','+00:00')).astimezone(datetime.timezone.utc)
    except Exception:return None
def unit_for(branch_id:str)->str:
    return 'chacha-dev-branch@'+hashlib.sha256(branch_id.encode()).hexdigest()[:16]+'.service'
def unit_active(systemctl:Path,unit:str)->tuple[bool,bool,str]:
    try:
        p=run([systemctl,'is-active',unit],10); state=(p.stdout.strip() or p.stderr.strip() or 'unknown')[:120]
        return p.returncode==0 and state=='active',True,state
    except Exception as exc:return False,False,(type(exc).__name__+':'+str(exc))[:120]
def observe(runtime:Path,branch_cfg:dict[str,Any],systemctl:Path=Path('/usr/bin/systemctl'),now=None)->dict[str,Any]:
    stamp=now or datetime.datetime.now(datetime.timezone.utc); root=runtime/'capsules'; reg=load(root/'registry.json',{'capsules':[]})
    default_ttl=int(((branch_cfg.get('runtime_capsules') or {}).get('teardown_after_idle_seconds') or 900))
    cache_ttl=int(((branch_cfg.get('runtime_capsules') or {}).get('maximum_idle_cache_seconds') or 3600))
    rows=[]; issues=[]; referenced=set()
    for raw in reg.get('capsules') or []:
        if not isinstance(raw,dict):continue
        branch_id=str(raw.get('branch_id') or ''); unit=str(raw.get('unit') or unit_for(branch_id)); expected=unit_for(branch_id) if branch_id else ''
        workspace=Path(str(raw.get('workspace') or (root/hashlib.sha256(branch_id.encode()).hexdigest()[:16]))) if branch_id else root/'unknown'
        referenced.add(str(workspace.resolve()) if workspace.exists() else str(workspace))
        created=parse_ts(raw.get('created_at')); ttl=max(30,int(raw.get('ttl_seconds') or default_ttl)); age=int((stamp-created).total_seconds()) if created else None
        active,observed,runtime_state=unit_active(systemctl,unit) if unit else (False,False,'missing-unit')
        expired=bool(age is not None and age>ttl); state=str(raw.get('state') or '')
        row={'branch_id':branch_id,'unit':unit,'expected_unit':expected,'workspace':str(workspace),'workspace_exists':workspace.is_dir(),
             'state':state,'runtime_active':active,'runtime_observed':observed,'runtime_state':runtime_state,'ttl_seconds':ttl,
             'age_seconds':age,'ttl_expired':expired,'materialization_component_id':raw.get('materialization_component_id'),
             'owner_foundry':'branch-foundry','ephemeral':True}
        rows.append(row)
        if branch_id and unit!=expected:
            issues.append({'code':'EPHEMERAL_BRANCH_UNIT_MISMATCH','severity':'CRITICAL','subject':branch_id,'details':row})
        elif state=='ACTIVE' and not workspace.is_dir():
            issues.append({'code':'EPHEMERAL_BRANCH_WORKSPACE_MISSING','severity':'HIGH','subject':branch_id,'details':row})
        elif state=='ACTIVE' and expired and observed and not active:
            issues.append({'code':'EPHEMERAL_BRANCH_STALE','severity':'HIGH','subject':branch_id,'details':row})
        elif state=='ACTIVE' and expired and active:
            issues.append({'code':'EPHEMERAL_BRANCH_TTL_EXCEEDED_ACTIVE','severity':'HIGH','subject':branch_id,'details':row})
    residues=[]
    if root.is_dir():
        for d in root.iterdir():
            if not d.is_dir():continue
            key=str(d.resolve())
            if key in referenced:continue
            try:age=int(stamp.timestamp()-d.stat().st_mtime)
            except Exception:continue
            if age>cache_ttl:residues.append({'workspace':str(d),'age_seconds':age,'cache_ttl_seconds':cache_ttl})
    return {'schema':SCHEMA,'observed_at':iso(),'status':'PASS' if not issues else 'DRIFT','capsule_count':len(rows),
            'active_runtime_count':sum(1 for x in rows if x['runtime_active']),'issue_count':len(issues),'issues':issues,
            'branches':rows,'orphan_workspace_residues':residues,'orphan_workspace_residue_count':len(residues),
            'read_only':True,'automatic_external_spend_eur':0}
def guardian(client:Path,policy:Path,event:Path,result:Path,payload:dict[str,Any]):
    save(event,payload); p=run([sys.executable,client,'--policy',policy,'check','--event',event],45)
    try:x=json.loads([z for z in p.stdout.splitlines() if z.strip()][-1])
    except Exception:x={'verdict':'UNAVAILABLE','stderr':p.stderr[-800:]}
    save(result,x); return p.returncode==0 and x.get('verdict') in {'PASS','WARNING'},x
def gov_event(action_id:str,phase:str,branch:dict[str,Any],evidence:dict[str,Any]):
    project=str(branch.get('branch_id') or '').split(':',1)[0] or 'chacha-dev-platform'
    return {'schema':'chacha.dev/governance-action/v1','event_id':action_id+'-'+phase.lower(),'action_id':action_id,'phase':phase,
      'actor':'branch-foundry-lifecycle','subject_role':'branch-foundry-lifecycle','action':'RETIRE_EPHEMERAL_BRANCH','permission':'ephemeral-runtime-retire',
      'project_id':project,'evidence':evidence,'context':{'deadline_seconds':300,'resource_class':'light','branch_id':branch.get('branch_id')},
      'capabilities':['branch-lifecycle','ephemeral-runtime-retirement'],'automatic_external_spend_eur':0}
def reconcile(repo:Path,runtime:Path,systemctl:Path,guardian_client:Path,guardian_policy:Path,gate:Path,gate_policy:Path,dynamic_registry:Path)->dict[str,Any]:
    branch_cfg=load(repo/'dev-hub/config/branch-foundry.v1.json',{}); before=observe(runtime,branch_cfg,systemctl); root=runtime/'capsules'
    registry_path=root/'registry.json'; registry=load(registry_path,{'schema':'chacha.dev/runtime-capsule-registry/v1','capsules':[]})
    report_root=runtime/'branch-foundry-lifecycle'; work=report_root/'work'/('lifecycle-'+uuid.uuid4().hex[:12]); work.mkdir(parents=True,exist_ok=True)
    out={'schema':'chacha.dev/ephemeral-branch-lifecycle-run/v1','observed_at':iso(),'status':'PASS','actions':[],
         'workspace_deletion_performed':False,'active_runtime_termination_performed':False,'automatic_external_spend_eur':0}
    stop=load(runtime/'control/emergency-stop.json',{})
    if stop.get('active') is True:
        out.update({'status':'STOPPED','reason':'EMERGENCY_STOP_ACTIVE'});save(work/'run.json',out);save(report_root/'latest.json',out);return out
    stale={str(x.get('subject')):x for x in before.get('issues') or [] if x.get('code')=='EPHEMERAL_BRANCH_STALE'}
    rows=list(registry.get('capsules') or [])
    for row in rows:
        branch_id=str((row or {}).get('branch_id') or '')
        issue=stale.get(branch_id)
        if not issue:continue
        details=issue.get('details') or {}; cid=str((row or {}).get('materialization_component_id') or '')
        evidence={'branch_id':branch_id,'ephemeral_runtime':True,'ttl_expired':True,'runtime_inactive':True,
          'workspace_deleted':False,'persistent_state_preserved':True,'emergency_stop_inactive':True,
          'legacy_without_component_id':not bool(cid),'automatic_external_spend_eur':0}
        aid='retire-ephemeral-'+hashlib.sha256((branch_id+iso()).encode()).hexdigest()[:12]
        ok,pre=guardian(guardian_client,guardian_policy,work/(aid+'-pre.json'),work/(aid+'-pre-result.json'),gov_event(aid,'PRE_ACTION',row,evidence))
        if not ok:
            out['status']='BLOCKED';out['actions'].append({'branch_id':branch_id,'status':'BLOCKED','reason':'GUARDIAN_PRE_BLOCK','guardian':pre});continue
        canonical='LEGACY_NO_DYNAMIC_COMPONENT_RECORD'; receipt=None
        if cid:
            receipt_path=work/(aid+'-materialization-retire.json')
            p=run([sys.executable,gate,'--mode','retire','--component-id',cid,'--policy',gate_policy,
                   '--dynamic-registry',dynamic_registry,'--output',receipt_path],60)
            receipt=load(receipt_path,{})
            if p.returncode!=0 or receipt.get('status')!='PASS':
                out['status']='BLOCKED';out['actions'].append({'branch_id':branch_id,'status':'BLOCKED','reason':'MATERIALIZATION_RETIRE_FAILED','receipt':receipt});continue
            canonical=str(receipt.get('component_state') or 'RETIRED')
        row['state']='RETIRED';row['retired_at']=iso();row['retirement_reason']='TTL_EXPIRED_RUNTIME_INACTIVE'
        row['workspace_preserved_for_hygiene']=True;row['materialization_gate_status']=canonical
        save(registry_path,{**registry,'capsules':rows})
        post_evidence={**evidence,'registry_state_retired':True,'canonical_retirement':canonical,'workspace_preserved_for_hygiene':True}
        post_ok,post=guardian(guardian_client,guardian_policy,work/(aid+'-post.json'),work/(aid+'-post-result.json'),gov_event(aid,'POST_ACTION',row,post_evidence))
        status='VERIFIED' if post_ok else 'BLOCKED'
        if not post_ok:out['status']='BLOCKED'
        out['actions'].append({'branch_id':branch_id,'status':status,'owner':'branch-foundry','canonical_retirement':canonical,
          'legacy_without_component_id':not bool(cid),'workspace_preserved':True,'guardian_pre':pre.get('verdict'),'guardian_post':post.get('verdict')})
    after=observe(runtime,branch_cfg,systemctl);out['before_issue_count']=before.get('issue_count');out['after_issue_count']=after.get('issue_count')
    out['remaining_issues']=after.get('issues') or [];save(work/'run.json',out);save(report_root/'latest.json',out);return out

def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument('--mode',choices=['observe','reconcile'],default='observe')
    ap.add_argument('--repo-root',type=Path,required=True);ap.add_argument('--runtime-root',type=Path,default=Path('/opt/chacha-dev/runtime'))
    ap.add_argument('--systemctl-bin',type=Path,default=Path('/usr/bin/systemctl'));ap.add_argument('--guardian-client',type=Path);ap.add_argument('--guardian-policy',type=Path)
    ap.add_argument('--materialization-gate',type=Path);ap.add_argument('--materialization-policy',type=Path);ap.add_argument('--dynamic-registry',type=Path)
    ap.add_argument('--output',type=Path);a=ap.parse_args();repo=a.repo_root.resolve();runtime=a.runtime_root.resolve()
    if a.mode=='observe':out=observe(runtime,load(repo/'dev-hub/config/branch-foundry.v1.json',{}),a.systemctl_bin)
    else:
        out=reconcile(repo,runtime,a.systemctl_bin,a.guardian_client or repo/'dev-hub/bin/guardian-client.py',a.guardian_policy or repo/'dev-hub/config/guardian-runtime-policy.v1.json',
          a.materialization_gate or repo/'dev-hub/bin/universal-materialization-gate.py',a.materialization_policy or repo/'dev-hub/config/canonical-component-registry.v1.json',
          a.dynamic_registry or runtime/'canonical-registry/dynamic-components.json')
    if a.output:save(a.output,out)
    print('CHACHA_DEV_EPHEMERAL_BRANCH_LIFECYCLE='+str(out.get('status')))
    print('ISSUE_COUNT='+str(out.get('issue_count',out.get('after_issue_count',0))))
    print('AUTOMATIC_EXTERNAL_SPEND_EUR=0')
    return 0 if out.get('status') in {'PASS','STOPPED'} else 20
if __name__=='__main__':raise SystemExit(main())
