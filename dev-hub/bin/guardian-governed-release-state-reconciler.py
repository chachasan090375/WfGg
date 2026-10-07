#!/usr/bin/env python3
from __future__ import annotations
from canonical_route_runtime import resolve_path as canonical_route_path, resolve_value as canonical_route_value
import sys
sys.dont_write_bytecode=True
import argparse,hashlib,json,subprocess,tempfile,time,urllib.request,sys
from pathlib import Path
from typing import Any

CURRENT=Path('/opt/chacha-dev/platform/current')
PLATFORM=Path('/opt/chacha-dev/platform')
RUNTIME=Path('/opt/chacha-dev/runtime')
HERE=Path(__file__).resolve().parent
if str(HERE) not in sys.path:sys.path.insert(0,str(HERE))
import promotion_transaction as ptx

def load(p:Path)->dict[str,Any]:
    x=json.loads(p.read_text(encoding='utf-8'))
    if not isinstance(x,dict): raise ValueError('JSON_ROOT_NOT_OBJECT:'+str(p))
    return x

def save(p:Path,x:dict[str,Any])->None:
    p.parent.mkdir(parents=True,exist_ok=True)
    tmp=p.with_suffix(p.suffix+'.tmp')
    tmp.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    tmp.replace(p)

def sha256_file(p:Path)->str:
    return 'sha256:'+hashlib.sha256(p.read_bytes()).hexdigest()

def iso()->str:return time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())

def guardian(client:Path,policy:Path,event:dict[str,Any])->dict[str,Any]:
    with tempfile.NamedTemporaryFile(prefix='chacha-release-state-',suffix='.json',mode='w',encoding='utf-8',delete=False) as f:
        json.dump(event,f,separators=(',',':')); ep=Path(f.name)
    try:
        r=subprocess.run(['python3',str(client),'--policy',str(policy),'check','--event',str(ep)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=30,check=False)
    finally: ep.unlink(missing_ok=True)
    if r.returncode!=0: raise RuntimeError('GUARDIAN_BLOCKED:'+(r.stdout or r.stderr)[-1400:])
    x=json.loads(r.stdout)
    if x.get('verdict')!='PASS' or x.get('stop_recommended') is True: raise RuntimeError('GUARDIAN_VERDICT_BLOCK:'+str(x))
    return x

def direct_health(url:str)->dict[str,Any]:
    with urllib.request.urlopen(url,timeout=4) as r:
        x=json.loads(r.read().decode('utf-8'))
    if x.get('status')!='PASS': raise RuntimeError('DIRECT_OPERATOR_HEALTH_NOT_PASS')
    return x

def active_attestation(platform:Path,runtime:Path,health_url:str)->dict[str,Any]:
    current=platform/'current'
    active=current.resolve(strict=True)
    releases=(platform/'releases').resolve()
    if releases not in active.parents: raise RuntimeError('ACTIVE_RELEASE_OUTSIDE_RELEASES_ROOT')
    revision=(active/'.revision').read_text(encoding='utf-8').strip()
    tree=(active/'.tree').read_text(encoding='utf-8').strip()
    prep_path=active/'.release-preparation.json'; prep=load(prep_path)
    if prep.get('candidate_revision')!=revision: raise RuntimeError('CANDIDATE_REVISION_MISMATCH')
    if prep.get('candidate_tree')!=tree: raise RuntimeError('CANDIDATE_TREE_MISMATCH')
    if prep.get('human_production_approval_present') is not True: raise RuntimeError('HUMAN_PRODUCTION_APPROVAL_MISSING')
    if prep.get('guardian_pre_action')!='PASS': raise RuntimeError('GUARDIAN_PRE_ACTION_MISSING')
    if prep.get('sentinel_exact_revision')!='PASS': raise RuntimeError('SENTINEL_EXACT_REVISION_MISSING')
    if float(prep.get('automatic_external_spend_eur') or 0)!=0: raise RuntimeError('AUTOMATIC_EXTERNAL_SPEND_NONZERO')
    stop=load(runtime/'control/emergency-stop.json')
    if stop.get('active') is True: raise RuntimeError('EMERGENCY_STOP_ACTIVE')
    health=direct_health(health_url)
    return {'active':active,'revision':revision,'tree':tree,'prep_path':prep_path,'prep':prep,
            'prep_digest_before':sha256_file(prep_path),'direct_health':health}

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument('--platform-root',type=Path,default=PLATFORM);ap.add_argument('--runtime-root',type=Path,default=RUNTIME)
    ap.add_argument('--guardian-client',type=Path,default=canonical_route_path("intendant.authority", "guardian_client"))
    ap.add_argument('--guardian-policy',type=Path,default=canonical_route_path("intendant.authority", "guardian_policy"))
    ap.add_argument('--core-reconciler',type=Path,default=CURRENT/'dev-hub/bin/release_state_reconciler.py')
    ap.add_argument('--health-url',default='chacha-route://internal.127.0.0.1_8792_healthz')
    ap.add_argument('--output',type=Path,default=RUNTIME/'release-state-reconciliation/latest.json')
    a=ap.parse_args(); platform=a.platform_root.resolve();runtime=a.runtime_root.resolve()
    att=active_attestation(platform,runtime,a.health_url)
    declared=str(att['prep'].get('activation_status') or '')
    tx=ptx.public_status(runtime)
    if declared not in {'ACTIVE','ACTIVATED'} and tx.get('status') in {'ACTIVE','EXPIRED'}:
        raise RuntimeError('PROMOTION_TRANSACTION_BLOCKS_RECONCILIATION:'+str(tx.get('promotion_id') or 'unknown'))
    if declared in {'ACTIVE','ACTIVATED'}:
        out={'schema':'chacha.dev/governed-release-state-reconciliation/v1','status':'PASS','mode':'NOOP_ALREADY_ACTIVE',
             'revision':att['revision'],'tree':att['tree'],'active_release':str(att['active']),'applied':False,'automatic_external_spend_eur':0}
        save(a.output,out);print('CHACHA_DEV_GOVERNED_RELEASE_STATE_RECONCILIATION=PASS');print('MODE=NOOP_ALREADY_ACTIVE');return 0
    stamp=time.strftime('%Y%m%dT%H%M%SZ',time.gmtime()); aid='release-state-reconciliation-'+stamp
    evidence={'active_current_exact':True,'active_release':str(att['active']),'revision':att['revision'],'tree':att['tree'],
              'qualified_release_metadata':True,'human_production_approval_present':True,'guardian_pre_action':'PASS',
              'sentinel_exact_revision':'PASS','direct_operator_health':'PASS','emergency_stop_clear':True,'promotion_transaction_state':tx.get('status'),
              'current_symlink_mutation':False,'release_deletion':False,'automatic_external_spend_eur':0}
    base={'schema':'chacha.dev/governance-action/v1','action_id':aid,'actor':'release-state-reconciler','subject_role':'release-state-reconciler',
          'action':'RECONCILE_ACTIVE_RELEASE_METADATA','task_kind':'release-state-reconciliation','permission':'workspace-write',
          'project_id':'chacha-dev-platform','run_id':aid,'adapters':[],
          'context':{'resource_class':'light','human_approval_required':False,'storage_preflight_required':False,'deadline_seconds':120},
          'automatic_external_spend_eur':0}
    pre=guardian(a.guardian_client,a.guardian_policy,{**base,'event_id':aid+'-pre','phase':'PRE_ACTION','evidence':evidence})
    gates=runtime/'release-gates'; proof_path=gates/('release-state-'+att['revision']+'-install-pass.json')
    proof={'schema':'chacha.dev/platform-install-pass/v1','status':'PASS','revision':att['revision'],'tree':att['tree'],
           'release':str(att['active']),'direct_operator_health':'PASS','guardian_realtime':'PASS',
           'guardian_event_id':pre.get('event_id'),'guardian_action_id':pre.get('action_id'),'current_target_verified':True,
           'qualified_release_metadata':True,'installed_at':iso(),'automatic_external_spend_eur':0}
    save(proof_path,proof)
    rec_out=runtime/'release-state-reconciliation'/('reconcile-'+stamp+'.json')
    p=subprocess.run(['python3',str(a.core_reconciler),'--platform-root',str(platform),'--release-gates',str(gates),
                      '--runtime-root',str(runtime),'--output',str(rec_out),'--apply'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=30,check=False)
    if p.returncode!=0: raise RuntimeError('CORE_RECONCILER_FAILED:'+(p.stderr or p.stdout)[-1400:])
    rec=load(rec_out)
    after_active=(platform/'current').resolve(strict=True)
    after_rev=(after_active/'.revision').read_text(encoding='utf-8').strip();after_tree=(after_active/'.tree').read_text(encoding='utf-8').strip()
    after_prep=load(after_active/'.release-preparation.json')
    if after_active!=att['active'] or after_rev!=att['revision'] or after_tree!=att['tree']: raise RuntimeError('ACTIVE_IDENTITY_CHANGED')
    if after_prep.get('activation_status')!='ACTIVE': raise RuntimeError('ACTIVATION_STATUS_NOT_RECONCILED')
    allowed={'activation_status','activated_at','activation_evidence'}
    for k,v in att['prep'].items():
        if k not in allowed and after_prep.get(k)!=v: raise RuntimeError('UNAUTHORIZED_PREPARATION_MUTATION:'+k)
    post_ev={**base,'event_id':aid+'-post','phase':'POST_ACTION','evidence':{**evidence,'result_status':'PASS','applied':bool(rec.get('applied')),
             'install_proof':str(proof_path),'install_proof_digest':sha256_file(proof_path),'active_identity_unchanged':True,
             'activation_status_after':'ACTIVE'}}
    post=guardian(a.guardian_client,a.guardian_policy,post_ev)
    out={'schema':'chacha.dev/governed-release-state-reconciliation/v1','status':'PASS','mode':'APPLIED' if rec.get('applied') else 'VERIFIED_NO_CHANGE',
         'revision':att['revision'],'tree':att['tree'],'active_release':str(att['active']),'declared_before':declared,'applied':bool(rec.get('applied')),
         'install_proof':str(proof_path),'guardian_pre_event_id':pre.get('event_id'),'guardian_post_event_id':post.get('event_id'),
         'current_symlink_mutation':False,'release_deletion':False,'automatic_external_spend_eur':0}
    save(a.output,out)
    print('CHACHA_DEV_GOVERNED_RELEASE_STATE_RECONCILIATION=PASS');print('MODE='+out['mode']);print('REVISION='+att['revision']);print('AUTOMATIC_EXTERNAL_SPEND_EUR=0')
    return 0
if __name__=='__main__': raise SystemExit(main())
