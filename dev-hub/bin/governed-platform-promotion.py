#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,os,re,shlex,tempfile,time,urllib.parse,urllib.request
from pathlib import Path
from typing import Any

SCHEMA='chacha.dev/governed-platform-promotion/v1'
SHA_RE=re.compile(r'^[0-9a-f]{40}$')

def load(path:Path)->dict[str,Any]:
    x=json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(x,dict): raise ValueError('JSON_ROOT_NOT_OBJECT:'+str(path))
    return x

def atomic_json(path:Path,obj:dict[str,Any])->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix=path.name+'.',dir=str(path.parent))
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as f:
            json.dump(obj,f,indent=2,ensure_ascii=False);f.write('\n');f.flush();os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)

def inside(path:Path,root:Path)->bool:
    try:path.resolve().relative_to(root.resolve());return True
    except ValueError:return False

def unit_write_paths(text:str)->list[str]:
    out=[]
    for raw in text.splitlines():
        if not raw.startswith('ReadWritePaths='):continue
        for token in shlex.split(raw.split('=',1)[1]):
            token=token.lstrip('-+!')
            if token.startswith('/'):out.append(token)
    return out

def validate_preparation(meta:dict[str,Any])->None:
    if meta.get('human_production_approval_present') is not True:raise ValueError('HUMAN_PRODUCTION_APPROVAL_REQUIRED')
    if meta.get('platform_qualification')!='PASS':raise ValueError('PLATFORM_QUALIFICATION_PASS_REQUIRED')
    if meta.get('guardian_pre_action')!='PASS':raise ValueError('GUARDIAN_PRE_PASS_REQUIRED')
    if meta.get('sentinel_exact_revision')!='PASS':raise ValueError('SENTINEL_EXACT_SHA_PASS_REQUIRED')
    rev=str(meta.get('candidate_revision') or '');tree=str(meta.get('candidate_tree') or '')
    if not SHA_RE.fullmatch(rev) or not SHA_RE.fullmatch(tree):raise ValueError('EXACT_SHA_TREE_REQUIRED')
    rb=Path(str(meta.get('rollback_path') or ''))
    if not rb.is_dir():raise ValueError('ROLLBACK_PATH_REQUIRED')

def prepare(candidate_root:Path,runtime_root:Path,receipt:Path)->dict[str,Any]:
    candidate_root=candidate_root.resolve();runtime_root=runtime_root.resolve()
    meta=load(candidate_root/'.release-preparation.json');validate_preparation(meta)
    created=[];verified=[];outside=[]
    units=candidate_root/'dev-hub/systemd'
    for unit in sorted(units.glob('*.service')):
        for raw in unit_write_paths(unit.read_text(encoding='utf-8')):
            p=Path(raw)
            if inside(p,runtime_root):
                if not p.exists():p.mkdir(parents=True,exist_ok=True);created.append(str(p))
                if not p.is_dir():raise ValueError('RUNTIME_WRITE_PATH_NOT_DIRECTORY:'+str(p))
                verified.append(str(p))
            else:
                if not p.exists():raise ValueError('EXTERNAL_WRITE_PATH_MISSING:'+str(p))
                outside.append(str(p))
    out={'schema':SCHEMA,'phase':'PREPARE','status':'PASS','candidate_revision':meta['candidate_revision'],
         'candidate_tree':meta['candidate_tree'],'created_runtime_paths':sorted(set(created)),
         'verified_runtime_paths':sorted(set(verified)),'external_existing_paths':sorted(set(outside)),
         'current_release_mutated':False,'automatic_external_spend_eur':0}
    atomic_json(receipt,out);return out

def loopback_url(url:str)->bool:
    u=urllib.parse.urlparse(url)
    return u.scheme in ('http','https') and (u.hostname or '') in ('127.0.0.1','localhost','::1')

def wait_ready(url:str,attempts:int,delay:float,timeout:float,receipt:Path)->dict[str,Any]:
    if not loopback_url(url):raise ValueError('READINESS_URL_MUST_BE_LOOPBACK')
    errors=[]
    for i in range(1,attempts+1):
        try:
            with urllib.request.urlopen(url,timeout=timeout) as r:
                body=r.read();payload=json.loads(body or b'{}')
                if r.status==200 and payload.get('status')=='PASS':
                    out={'schema':SCHEMA,'phase':'READINESS','status':'PASS','url':url,'attempt':i,
                         'payload':payload,'automatic_external_spend_eur':0}
                    atomic_json(receipt,out);return out
                errors.append('NON_PASS_RESPONSE')
        except Exception as e: errors.append(type(e).__name__)
        if i<attempts:time.sleep(delay)
    raise ValueError('READINESS_RETRIES_EXHAUSTED:'+','.join(errors[-5:]))

def require_run(path:Path,label:str)->dict[str,Any]:
    x=load(path)
    if x.get('status')!='CONVERGED' or x.get('next_state')!='RESUME':raise ValueError(label+'_NOT_CONVERGED_RESUME')
    if x.get('direct_mutation_by_supervisor') is not False:raise ValueError(label+'_DIRECT_MUTATION_FORBIDDEN')
    if int(x.get('automatic_external_spend_eur',0))!=0:raise ValueError(label+'_NONZERO_EXTERNAL_SPEND')
    return x

def finalize(release_root:Path,current:Path,guardian_post:Path,sentinel_post:Path,readiness:Path,
             controlled_run:Path,timer_run:Path,emergency:Path,release_count:int,
             controlled_before:int,controlled_after:int,timer_before:int,timer_after:int)->dict[str,Any]:
    release_root=release_root.resolve()
    if current.resolve()!=release_root:raise ValueError('ACTIVE_CURRENT_EXACT_REQUIRED')
    p=release_root/'.release-preparation.json';meta=load(p);validate_preparation(meta)
    if meta.get('activation_status')!='ACTIVE':raise ValueError('ACTIVE_METADATA_REQUIRED')
    gp=load(guardian_post)
    if gp.get('verdict')!='PASS':raise ValueError('GUARDIAN_POST_PASS_REQUIRED')
    sp=load(sentinel_post)
    if sp.get('verdict')!='PASS' or sp.get('revision')!=meta['candidate_revision']:raise ValueError('SENTINEL_POST_EXACT_SHA_REQUIRED')
    rd=load(readiness)
    if rd.get('status')!='PASS' or rd.get('phase')!='READINESS':raise ValueError('READINESS_PASS_REQUIRED')
    cr=require_run(controlled_run,'CONTROLLED_RUN');tr=require_run(timer_run,'TIMER_RUN')
    stop=load(emergency)
    if stop.get('active') is not False:raise ValueError('EMERGENCY_STOP_MUST_BE_CLEAR')
    if release_count>3:raise ValueError('RELEASE_RETENTION_OVERAGE')
    if not (controlled_after>controlled_before and timer_after>timer_before and timer_before>=controlled_after):
        raise ValueError('AUTONOMY_CYCLE_PROOF_INVALID')
    now=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
    meta.update({'promotion_acceptance_status':'PASS','guardian_post_action':'PASS',
      'guardian_post_event_id':gp.get('event_id'),'sentinel_post_activation_verdict':'PASS',
      'sentinel_post_activation_receipt_id':sp.get('receipt_id'),'direct_operator_status':'PASS',
      'release_retention_count':release_count,'controlled_cycle_status':'CONVERGED',
      'controlled_cycle_next_state':'RESUME','controlled_cycle_before':controlled_before,
      'controlled_cycle_after':controlled_after,'controlled_cycle_run_id':cr.get('run_id'),
      'autonomy_timer_status':'ACTIVE','autonomy_timer_enabled':True,
      'first_automatic_timer_cycle_before':timer_before,'first_automatic_timer_cycle_after':timer_after,
      'first_automatic_timer_cycle_status':'CONVERGED','first_automatic_timer_cycle_next_state':'RESUME',
      'first_automatic_timer_run_id':tr.get('run_id'),'stop_available':True,
      'promotion_final_verification':'PASS','promotion_final_verified_at':now,
      'automatic_external_spend_eur':0})
    atomic_json(p,meta)
    return {'schema':SCHEMA,'phase':'FINALIZE','status':'PASS','candidate_revision':meta['candidate_revision'],
            'promotion_acceptance_status':'PASS','current_release_mutated':False,'automatic_external_spend_eur':0}

def main()->int:
    ap=argparse.ArgumentParser();sub=ap.add_subparsers(dest='cmd',required=True)
    p=sub.add_parser('prepare');p.add_argument('--candidate-root',type=Path,required=True);p.add_argument('--runtime-root',type=Path,required=True);p.add_argument('--receipt',type=Path,required=True)
    p=sub.add_parser('wait-ready');p.add_argument('--url',required=True);p.add_argument('--attempts',type=int,default=15);p.add_argument('--delay',type=float,default=1);p.add_argument('--timeout',type=float,default=2);p.add_argument('--receipt',type=Path,required=True)
    p=sub.add_parser('finalize');p.add_argument('--release-root',type=Path,required=True);p.add_argument('--current',type=Path,required=True);p.add_argument('--guardian-post',type=Path,required=True);p.add_argument('--sentinel-post',type=Path,required=True);p.add_argument('--readiness',type=Path,required=True);p.add_argument('--controlled-run',type=Path,required=True);p.add_argument('--timer-run',type=Path,required=True);p.add_argument('--emergency-state',type=Path,required=True);p.add_argument('--release-count',type=int,required=True);p.add_argument('--controlled-before',type=int,required=True);p.add_argument('--controlled-after',type=int,required=True);p.add_argument('--timer-before',type=int,required=True);p.add_argument('--timer-after',type=int,required=True)
    a=ap.parse_args()
    try:
        if a.cmd=='prepare':out=prepare(a.candidate_root,a.runtime_root,a.receipt)
        elif a.cmd=='wait-ready':out=wait_ready(a.url,a.attempts,a.delay,a.timeout,a.receipt)
        else:out=finalize(a.release_root,a.current,a.guardian_post,a.sentinel_post,a.readiness,a.controlled_run,a.timer_run,a.emergency_state,a.release_count,a.controlled_before,a.controlled_after,a.timer_before,a.timer_after)
        print(json.dumps(out,ensure_ascii=False));return 0
    except Exception as e:
        print(json.dumps({'schema':SCHEMA,'status':'BLOCK','reason':str(e),'automatic_external_spend_eur':0},ensure_ascii=False));return 20
if __name__=='__main__':raise SystemExit(main())
