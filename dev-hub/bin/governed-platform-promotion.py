#!/usr/bin/env python3
from __future__ import annotations
import sys
sys.dont_write_bytecode=True
import argparse,hashlib,json,os,re,shlex,subprocess,sys,tempfile,time,urllib.parse,urllib.request
from pathlib import Path
from typing import Any

HERE=Path(__file__).resolve().parent
if str(HERE) not in sys.path:sys.path.insert(0,str(HERE))
import promotion_transaction as ptx
import promotion_cycle_evidence as pce
import exact_git_release as egr
import release_runtime_immutability as rri

SCHEMA='chacha.dev/governed-platform-promotion/v2'
ASSURANCE_SCHEMA='chacha.dev/promotion-bound-assurance/v1'
SHA_RE=re.compile(r'^[0-9a-f]{40}$')

def load(path:Path)->dict[str,Any]:
    x=json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(x,dict):raise ValueError('JSON_ROOT_NOT_OBJECT:'+str(path))
    return x

def atomic_json(path:Path,obj:dict[str,Any])->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix=path.name+'.',dir=str(path.parent))
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as f:
            json.dump(obj,f,indent=2,ensure_ascii=False);f.write('\n');f.flush();os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)

def digest(path:Path)->str:return 'sha256:'+hashlib.sha256(path.read_bytes()).hexdigest()
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
    if not str(meta.get('source_git_root') or '').strip():raise ValueError('SOURCE_GIT_ROOT_REQUIRED')
    rb=Path(str(meta.get('rollback_path') or ''))
    if not rb.is_dir():raise ValueError('ROLLBACK_PATH_REQUIRED')

def lease(runtime_root:Path,lease_token:str,promotion_id:str,candidate_revision:str,phase:str):
    return ptx.assert_owner(runtime_root,lease_token,promotion_id,candidate_revision,phase,renew=True)

def exact_release_verification(release_root:Path,meta:dict[str,Any])->dict[str,Any]:
    raw=str(meta.get('source_git_root') or '').strip()
    if not raw:raise ValueError('SOURCE_GIT_ROOT_REQUIRED_FOR_EXACT_RELEASE_VERIFICATION')
    source=Path(raw)
    out=egr.verify_release(release_root.resolve(),source,meta['candidate_revision'],meta['candidate_tree'])
    if out.get('status')!='PASS':
        reasons=','.join(out.get('reason_codes') or ['UNKNOWN'])
        raise ValueError('EXACT_GIT_RELEASE_VERIFICATION_FAILED:'+reasons)
    return out

def prepare(candidate_root:Path,runtime_root:Path,receipt:Path,promotion_id:str,lease_token:str)->dict[str,Any]:
    candidate_root=candidate_root.resolve();runtime_root=runtime_root.resolve()
    meta=load(candidate_root/'.release-preparation.json');validate_preparation(meta)
    lx=lease(runtime_root,lease_token,promotion_id,meta['candidate_revision'],'PREPARE')
    created=[];verified=[];outside=[];units=candidate_root/'dev-hub/systemd'
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
    out=ptx.bind_receipt(lx,{'schema':SCHEMA,'phase':'PREPARE','status':'PASS','candidate_revision':meta['candidate_revision'],
      'candidate_tree':meta['candidate_tree'],'created_runtime_paths':sorted(set(created)),'verified_runtime_paths':sorted(set(verified)),
      'external_existing_paths':sorted(set(outside)),'current_release_mutated':False})
    ptx.write_once_json(receipt,out);return out

def loopback_url(url:str)->bool:
    u=urllib.parse.urlparse(url);return u.scheme in ('http','https') and (u.hostname or '') in ('127.0.0.1','localhost','::1')

def wait_ready(url:str,attempts:int,delay:float,timeout:float,receipt:Path,runtime_root:Path,promotion_id:str,lease_token:str,candidate_revision:str)->dict[str,Any]:
    if not loopback_url(url):raise ValueError('READINESS_URL_MUST_BE_LOOPBACK')
    lx=lease(runtime_root,lease_token,promotion_id,candidate_revision,'READINESS');errors=[]
    for i in range(1,attempts+1):
        try:
            with urllib.request.urlopen(url,timeout=timeout) as r:
                body=r.read();payload=json.loads(body or b'{}')
                if r.status==200 and payload.get('status')=='PASS':
                    lx=lease(runtime_root,lease_token,promotion_id,candidate_revision,'READINESS_PASS')
                    out=ptx.bind_receipt(lx,{'schema':SCHEMA,'phase':'READINESS','status':'PASS','candidate_revision':candidate_revision,'url':url,'attempt':i,'payload':payload})
                    ptx.write_once_json(receipt,out);return out
                errors.append('NON_PASS_RESPONSE')
        except Exception as e:errors.append(type(e).__name__)
        if i<attempts:time.sleep(delay)
    raise ValueError('READINESS_RETRIES_EXHAUSTED:'+','.join(errors[-5:]))

def canonical_emergency_state(release_root:Path)->tuple[Path,Path]:
    config_path=release_root/'dev-hub/config/emergency-stop.v1.json';cfg=load(config_path)
    if cfg.get('schema')!='chacha.dev/emergency-stop/v1':raise ValueError('EMERGENCY_STOP_CONFIG_SCHEMA_INVALID')
    raw=str(cfg.get('state_file') or '').strip();state=Path(raw)
    if not raw or not state.is_absolute():raise ValueError('EMERGENCY_STATE_PATH_MUST_BE_ABSOLUTE')
    if not state.is_file():raise ValueError('EMERGENCY_STATE_FILE_MISSING:'+str(state))
    return state,config_path

SOVEREIGN_UNITS={
  'assurance-exchange':'chacha-dev-sovereign-assurance-exchange.service',
  'sentinel':'chacha-dev-sovereign-sentinel.service',
  'learning-relay':'chacha-dev-sovereign-learning-relay.service',
  'guardian':'chacha-dev-sovereign-guardian.service'
}

def sovereign_runtime_refresh(runtime_root:Path)->dict[str,Any]:
    auth=runtime_root/'sovereign-state/authority.json'
    if not auth.is_file():return {'status':'PASS','mode':'D1_REMOTE','refreshed':False,'reason':'AUTHORITY_FILE_ABSENT_DEFAULT_REMOTE'}
    cfg=load(auth);mode=str(cfg.get('mode') or '')
    if mode!='LOCAL_SQLITE':return {'status':'PASS','mode':mode or 'D1_REMOTE','refreshed':False,'reason':'LOCAL_AUTHORITY_INACTIVE'}
    services=cfg.get('services') or {}
    if set(services)!=set(SOVEREIGN_UNITS):raise ValueError('SOVEREIGN_LOCAL_SERVICE_SET_INVALID')
    for svc in SOVEREIGN_UNITS:
        if not loopback_url(str(services.get(svc) or '')):raise ValueError('SOVEREIGN_LOCAL_ENDPOINT_NOT_LOOPBACK:'+svc)
    restarted=[]
    for svc,unit in SOVEREIGN_UNITS.items():
        p=subprocess.run(['/usr/bin/systemctl','restart',unit],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=45)
        if p.returncode!=0:raise ValueError('SOVEREIGN_SERVICE_RESTART_FAILED:'+svc+':'+(p.stderr or '')[-300:])
        restarted.append(unit)
    health={}
    for svc in SOVEREIGN_UNITS:
        url=str(services[svc]).rstrip('/')+'/__sovereign/healthz';last=''
        for i in range(1,31):
            try:
                with urllib.request.urlopen(url,timeout=4) as r:
                    x=json.loads(r.read() or b'{}')
                    if r.status==200 and x.get('status')=='ok' and x.get('state_backend')=='SQLITE_LOCAL':
                        health[svc]=x;break
                    last='NON_PASS_HEALTH'
            except Exception as e:last=type(e).__name__
            if i<30:time.sleep(.2)
        if svc not in health:raise ValueError('SOVEREIGN_SERVICE_HEALTH_FAILED:'+svc+':'+last)
    return {'status':'PASS','mode':'LOCAL_SQLITE','refreshed':True,'restarted_units':restarted,'health':health}

def refresh_living_whitepaper(release_root:Path,runtime_root:Path)->dict[str,Any]:
    script=release_root/'dev-hub/bin/living_whitepaper_generator.py'
    if not script.is_file():return {'status':'NOT_AVAILABLE','blocking':False}
    try:
        p=subprocess.run([sys.executable,str(script),'--repo-root',str(release_root),'--runtime-root',str(runtime_root)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=90,check=False)
        return {'status':'PASS' if p.returncode==0 else 'WARNING','blocking':False,'returncode':p.returncode,
                'stdout_tail':(p.stdout or '')[-1000:],'stderr_tail':(p.stderr or '')[-1000:]}
    except Exception as exc:
        return {'status':'WARNING','blocking':False,'reason':type(exc).__name__+':'+str(exc)[:300]}

def atomic_current_switch(current:Path,target:Path,lease_id:str)->None:
    current=current.absolute();target=target.resolve();tmp=current.with_name(current.name+'.promotion-'+lease_id)
    tmp.unlink(missing_ok=True);os.symlink(str(target),str(tmp),target_is_directory=True);os.replace(tmp,current)
    dfd=os.open(str(current.parent),os.O_DIRECTORY)
    try:os.fsync(dfd)
    finally:os.close(dfd)

RETRY_TERMINAL_METADATA_KEYS=(
  'rollback_reason','rolled_back_at','promotion_acceptance_status','promotion_final_verification','promotion_final_verified_at',
  'living_whitepaper_refresh','guardian_post_action','guardian_post_event_id','sentinel_post_activation_verdict',
  'sentinel_post_activation_receipt_id','direct_operator_status','release_retention_count','controlled_cycle_status',
  'controlled_cycle_next_state','controlled_cycle_before','controlled_cycle_after','controlled_cycle_run_id',
  'controlled_cycle_evidence_digest','autonomy_timer_status','autonomy_timer_enabled','first_automatic_timer_cycle_before',
  'first_automatic_timer_cycle_after','first_automatic_timer_cycle_status','first_automatic_timer_cycle_next_state',
  'first_automatic_timer_run_id','first_automatic_timer_cycle_evidence_digest','stop_available'
)

def reset_previous_terminal_attempt(meta:dict[str,Any])->None:
    for key in RETRY_TERMINAL_METADATA_KEYS:meta.pop(key,None)

def activate(release_root:Path,current:Path,runtime_root:Path,receipt:Path,promotion_id:str,lease_token:str)->dict[str,Any]:
    release_root=release_root.resolve();meta=load(release_root/'.release-preparation.json');validate_preparation(meta)
    lx=lease(runtime_root,lease_token,promotion_id,meta['candidate_revision'],'ACTIVATE')
    exact_git=exact_release_verification(release_root,meta)
    emergency,_=canonical_emergency_state(release_root)
    if load(emergency).get('active') is not False:raise ValueError('EMERGENCY_STOP_MUST_BE_CLEAR')
    rollback=Path(meta['rollback_path']).resolve();before=current.resolve(strict=True)
    release_count=sum(1 for p in release_root.parent.iterdir() if p.is_dir() and (p/'.revision').is_file())
    if release_count>3:raise ValueError('RELEASE_RETENTION_OVERAGE_PRE_ACTIVATION')
    if before not in {rollback,release_root}:raise ValueError('ACTIVE_CURRENT_NOT_ROLLBACK_OR_CANDIDATE')
    bytecode_guard=rri.ensure_python_release_guard(release_root)
    mutated=before!=release_root
    if mutated:atomic_current_switch(current,release_root,str(lx['lease_id']))
    if current.resolve(strict=True)!=release_root:raise ValueError('CURRENT_SWITCH_VERIFICATION_FAILED')
    try:
        sovereign=sovereign_runtime_refresh(runtime_root)
    except Exception as exc:
        if mutated:
            atomic_current_switch(current,rollback,str(lx['lease_id']))
            restore_error=None
            try:sovereign_runtime_refresh(runtime_root)
            except Exception as restore_exc:restore_error=str(restore_exc)
            if restore_error:raise ValueError('SOVEREIGN_RUNTIME_REFRESH_FAILED_ROLLBACK_DEGRADED:'+str(exc)+':RESTORE:'+restore_error)
            raise ValueError('SOVEREIGN_RUNTIME_REFRESH_FAILED_ROLLBACK_COMPLETE:'+str(exc))
        raise ValueError('SOVEREIGN_RUNTIME_REFRESH_FAILED:'+str(exc))
    now=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
    reset_previous_terminal_attempt(meta)
    meta.update({'activation_status':'ACTIVE','activated_at':now,'promotion_id':promotion_id,'promotion_lease_id':lx['lease_id'],
      'promotion_owner':lx['owner'],'current_switch_controller':'governed-platform-promotion','sovereign_runtime_refresh':sovereign,'automatic_external_spend_eur':0})
    atomic_json(release_root/'.release-preparation.json',meta)
    out=ptx.bind_receipt(lx,{'schema':SCHEMA,'phase':'ACTIVATE','status':'PASS','candidate_revision':meta['candidate_revision'],
      'candidate_tree':meta['candidate_tree'],'previous_release':str(before),'active_release':str(release_root),'current_release_mutated':mutated,
      'exact_git_release_verification':exact_git,'python_bytecode_guard':bytecode_guard,'sovereign_runtime_refresh':sovereign})
    ptx.write_once_json(receipt,out);return out

def seal_assurance(kind:str,source:Path,receipt:Path,runtime_root:Path,promotion_id:str,lease_token:str,candidate_revision:str)->dict[str,Any]:
    if kind not in {'guardian-post','sentinel-post'}:raise ValueError('ASSURANCE_KIND_INVALID')
    lx=lease(runtime_root,lease_token,promotion_id,candidate_revision,'SEAL_'+kind.upper().replace('-','_'));payload=load(source)
    if payload.get('verdict')!='PASS':raise ValueError('ASSURANCE_PASS_REQUIRED')
    if kind=='guardian-post' and payload.get('stop_recommended') is True:raise ValueError('GUARDIAN_STOP_RECOMMENDED')
    if kind=='sentinel-post' and payload.get('revision')!=candidate_revision:raise ValueError('SENTINEL_POST_EXACT_SHA_REQUIRED')
    out=ptx.bind_receipt(lx,{'schema':ASSURANCE_SCHEMA,'status':'PASS','kind':kind,'candidate_revision':candidate_revision,
      'source_path':str(source.resolve()),'source_digest':digest(source.resolve()),'payload':payload})
    ptx.write_once_json(receipt,out);return out

def require_bound_assurance(path:Path,kind:str,lx:dict[str,Any],candidate_revision:str,runtime_root:Path|None=None)->dict[str,Any]:
    x=load(path)
    if x.get('schema')!=ASSURANCE_SCHEMA or x.get('status')!='PASS' or x.get('kind')!=kind:raise ValueError('BOUND_ASSURANCE_INVALID:'+kind)
    if runtime_root is None:
        if x.get('candidate_revision')!=candidate_revision or x.get('promotion_lease_id')!=lx.get('lease_id'):raise ValueError('BOUND_ASSURANCE_SCOPE_MISMATCH:'+kind)
    else:
        ptx.require_receipt_binding(runtime_root.resolve(),x,lx,candidate_revision,'BOUND_ASSURANCE_'+kind.upper().replace('-','_'))
    p=x.get('payload') or {}
    if p.get('verdict')!='PASS':raise ValueError('BOUND_ASSURANCE_NON_PASS:'+kind)
    if kind=='sentinel-post' and p.get('revision')!=candidate_revision:raise ValueError('SENTINEL_POST_EXACT_SHA_REQUIRED')
    return x

def require_run(path:Path,label:str)->dict[str,Any]:
    x=load(path)
    if x.get('status')!='CONVERGED' or x.get('next_state')!='RESUME':raise ValueError(label+'_NOT_CONVERGED_RESUME')
    if x.get('direct_mutation_by_supervisor') is not False:raise ValueError(label+'_DIRECT_MUTATION_FORBIDDEN')
    if int(x.get('automatic_external_spend_eur',0))!=0:raise ValueError(label+'_NONZERO_EXTERNAL_SPEND')
    return x

def finalize(release_root:Path,current:Path,runtime_root:Path,receipt:Path,guardian_post:Path,sentinel_post:Path,readiness:Path,
             controlled_cycle_receipt:Path,timer_cycle_receipt:Path,release_count:int,promotion_id:str,lease_token:str)->dict[str,Any]:
    release_root=release_root.resolve();p=release_root/'.release-preparation.json';meta=load(p);validate_preparation(meta)
    lx=lease(runtime_root,lease_token,promotion_id,meta['candidate_revision'],'FINALIZE')
    if current.resolve()!=release_root:raise ValueError('ACTIVE_CURRENT_EXACT_REQUIRED')
    if meta.get('activation_status')!='ACTIVE':raise ValueError('ACTIVE_METADATA_REQUIRED')
    ptx.require_receipt_binding(runtime_root.resolve(),meta,lx,meta['candidate_revision'],'ACTIVE_METADATA')
    gp=require_bound_assurance(guardian_post,'guardian-post',lx,meta['candidate_revision'],runtime_root)
    sp=require_bound_assurance(sentinel_post,'sentinel-post',lx,meta['candidate_revision'],runtime_root)
    rd=load(readiness)
    if rd.get('status')!='PASS' or rd.get('phase')!='READINESS':raise ValueError('READINESS_BOUND_PASS_REQUIRED')
    ptx.require_receipt_binding(runtime_root.resolve(),rd,lx,meta['candidate_revision'],'READINESS')
    cr=pce.require(controlled_cycle_receipt,'CONTROLLED',lx,meta['candidate_revision'],runtime_root)
    tr=pce.require(timer_cycle_receipt,'TIMER',lx,meta['candidate_revision'],runtime_root)
    controlled_before=int(cr['counter_before']);controlled_after=int(cr['counter_after'])
    timer_before=int(tr['counter_before']);timer_after=int(tr['counter_after'])
    emergency,emergency_config=canonical_emergency_state(release_root);stop=load(emergency)
    if stop.get('active') is not False:raise ValueError('EMERGENCY_STOP_MUST_BE_CLEAR')
    if release_count>3:raise ValueError('RELEASE_RETENTION_OVERAGE')
    if timer_before<controlled_after:raise ValueError('AUTONOMY_CYCLE_ORDER_INVALID')
    if 'rollback_reason' in meta or 'rolled_back_at' in meta:raise ValueError('STALE_ROLLBACK_METADATA_FORBIDDEN')
    now=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime());sentinel_payload=sp['payload'];guardian_payload=gp['payload']
    whitepaper_refresh=refresh_living_whitepaper(release_root,runtime_root)
    meta.update({'living_whitepaper_refresh':whitepaper_refresh,'promotion_acceptance_status':'PASS','guardian_post_action':'PASS','guardian_post_event_id':guardian_payload.get('event_id'),
      'sentinel_post_activation_verdict':'PASS','sentinel_post_activation_receipt_id':sentinel_payload.get('receipt_id'),'direct_operator_status':'PASS',
      'release_retention_count':release_count,'controlled_cycle_status':'CONVERGED','controlled_cycle_next_state':'RESUME',
      'controlled_cycle_before':controlled_before,'controlled_cycle_after':controlled_after,'controlled_cycle_run_id':cr.get('run_id'),'controlled_cycle_evidence_digest':cr.get('binding_digest'),
      'autonomy_timer_status':'ACTIVE','autonomy_timer_enabled':True,'first_automatic_timer_cycle_before':timer_before,
      'first_automatic_timer_cycle_after':timer_after,'first_automatic_timer_cycle_status':'CONVERGED','first_automatic_timer_cycle_next_state':'RESUME',
      'emergency_stop_config':str(emergency_config),'emergency_stop_state':str(emergency),'first_automatic_timer_run_id':tr.get('run_id'),'first_automatic_timer_cycle_evidence_digest':tr.get('binding_digest'),
      'stop_available':True,'promotion_final_verification':'PASS','promotion_final_verified_at':now,'automatic_external_spend_eur':0})
    atomic_json(p,meta)
    out=ptx.bind_receipt(lx,{'schema':SCHEMA,'phase':'FINALIZE','status':'PASS','candidate_revision':meta['candidate_revision'],
      'promotion_acceptance_status':'PASS','promotion_final_verification':'PASS','current_release_mutated':False})
    ptx.write_once_json(receipt,out);ptx.release(runtime_root,lease_token,promotion_id,meta['candidate_revision'],'FINALIZED');return out

def rollback(release_root:Path,current:Path,runtime_root:Path,receipt:Path,promotion_id:str,lease_token:str,reason:str)->dict[str,Any]:
    release_root=release_root.resolve();p=release_root/'.release-preparation.json';meta=load(p);validate_preparation(meta)
    lx=lease(runtime_root,lease_token,promotion_id,meta['candidate_revision'],'ROLLBACK');rollback_path=Path(meta['rollback_path']).resolve()
    before=current.resolve(strict=True)
    if before==release_root:atomic_current_switch(current,rollback_path,str(lx['lease_id']))
    elif before!=rollback_path:raise ValueError('ROLLBACK_CURRENT_SCOPE_MISMATCH')
    if current.resolve(strict=True)!=rollback_path:raise ValueError('ROLLBACK_SWITCH_VERIFICATION_FAILED')
    meta.update({'activation_status':'ROLLED_BACK','promotion_acceptance_status':'ROLLED_BACK','rolled_back_at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
      'rollback_reason':reason,'automatic_external_spend_eur':0});atomic_json(p,meta)
    out=ptx.bind_receipt(lx,{'schema':SCHEMA,'phase':'ROLLBACK','status':'PASS','candidate_revision':meta['candidate_revision'],
      'rollback_release':str(rollback_path),'rollback_reason':reason,'current_release_mutated':before==release_root})
    ptx.write_once_json(receipt,out);ptx.release(runtime_root,lease_token,promotion_id,meta['candidate_revision'],'ROLLED_BACK');return out


def supersede_expired_active_base(current:Path,runtime_root:Path,successor_approval:Path,guardian_event:Path,guardian_result:Path,receipt:Path)->dict[str,Any]:
    if receipt.exists():raise ValueError('IMMUTABLE_RECEIPT_ALREADY_EXISTS:'+str(receipt))
    current=current.resolve(strict=True);runtime_root=runtime_root.resolve()
    revision=(current/'.revision').read_text(encoding='utf-8').strip()
    tree=(current/'.tree').read_text(encoding='utf-8').strip()
    meta=load(current/'.release-preparation.json')
    if meta.get('activation_status') not in {'ACTIVE','ACTIVATED'}:raise ValueError('ACTIVE_BASE_METADATA_REQUIRED')
    if str(meta.get('candidate_revision') or '')!=revision:raise ValueError('ACTIVE_BASE_REVISION_MISMATCH')
    if str(meta.get('candidate_tree') or '')!=tree:raise ValueError('ACTIVE_BASE_TREE_MISMATCH')
    lx=ptx.public_status(runtime_root)
    if lx.get('status')!='EXPIRED':raise ValueError('EXPIRED_PROMOTION_LEASE_REQUIRED')
    if lx.get('candidate_revision')!=revision:raise ValueError('EXPIRED_LEASE_ACTIVE_BASE_MISMATCH')
    approval=load(successor_approval.resolve())
    if approval.get('schema')!='chacha.dev/production-approval/v1':raise ValueError('SUCCESSOR_APPROVAL_SCHEMA_INVALID')
    if approval.get('scope')!='platform-promotion-release-slot-reservation' or approval.get('approved') is not True:raise ValueError('SUCCESSOR_HUMAN_APPROVAL_REQUIRED')
    successor_revision=str(approval.get('revision') or '');successor_tree=str(approval.get('tree') or '')
    if not SHA_RE.fullmatch(successor_revision) or not SHA_RE.fullmatch(successor_tree):raise ValueError('SUCCESSOR_EXACT_SHA_TREE_REQUIRED')
    if successor_revision==revision:raise ValueError('SUCCESSOR_MUST_DIFFER_FROM_ACTIVE_BASE')
    event=load(guardian_event.resolve());result=load(guardian_result.resolve());evidence=event.get('evidence') or {}
    if event.get('schema')!='chacha.dev/governance-action/v1' or event.get('phase')!='PRE_ACTION':raise ValueError('SUPERSESSION_GUARDIAN_EVENT_INVALID')
    if event.get('actor')!='governed-platform-promotion' or event.get('subject_role')!='governed-platform-promotion':raise ValueError('SUPERSESSION_GUARDIAN_ACTOR_INVALID')
    if event.get('action')!='RECOVER_PROMOTION_LEASE' or event.get('permission')!='production-deploy':raise ValueError('SUPERSESSION_GUARDIAN_ACTION_INVALID')
    if evidence.get('human_approval') is not True or str(evidence.get('active_base_revision') or '')!=revision or str(evidence.get('successor_revision') or '')!=successor_revision or str(evidence.get('recovery_outcome') or '')!='SUPERSEDED':raise ValueError('SUPERSESSION_GUARDIAN_EVIDENCE_INVALID')
    if str(result.get('action_id') or '')!=str(event.get('action_id') or '') or str(result.get('verdict') or '')!='PASS' or result.get('stop_recommended') is True:raise ValueError('SUPERSESSION_GUARDIAN_PASS_REQUIRED')
    old_lease_id=str(lx.get('lease_id') or '');promotion_id=str(lx.get('promotion_id') or '');owner=str(lx.get('owner') or '')
    rec=ptx.recover(runtime_root,promotion_id,owner,revision,old_lease_id,300)
    released=ptx.release(runtime_root,str(rec.get('lease_token') or ''),promotion_id,revision,'SUPERSEDED')
    out={'schema':SCHEMA,'phase':'SUPERSEDE_EXPIRED','status':'PASS','active_base_revision':revision,'active_base_tree':tree,'active_base_release':str(current),'successor_revision':successor_revision,'successor_tree':successor_tree,'expired_lease_id':old_lease_id,'recovered_lease_id':rec.get('lease_id'),'promotion_id':promotion_id,'terminal_status':released.get('terminal_status'),'current_release_mutated':False,'release_deleted':False,'guardian_action_id':result.get('action_id'),'automatic_external_spend_eur':0}
    ptx.write_once_json(receipt,out);return out

def main()->int:
    ap=argparse.ArgumentParser();sub=ap.add_subparsers(dest='cmd',required=True)
    a=sub.add_parser('lease-acquire');a.add_argument('--runtime-root',type=Path,required=True);a.add_argument('--promotion-id',required=True);a.add_argument('--owner',required=True);a.add_argument('--candidate-revision',required=True);a.add_argument('--ttl-seconds',type=int,default=1800)
    a=sub.add_parser('lease-recover');a.add_argument('--runtime-root',type=Path,required=True);a.add_argument('--promotion-id',required=True);a.add_argument('--owner',required=True);a.add_argument('--candidate-revision',required=True);a.add_argument('--previous-lease-id',required=True);a.add_argument('--ttl-seconds',type=int,default=1800)
    a=sub.add_parser('lease-status');a.add_argument('--runtime-root',type=Path,required=True)
    p=sub.add_parser('prepare');p.add_argument('--candidate-root',type=Path,required=True);p.add_argument('--runtime-root',type=Path,required=True);p.add_argument('--receipt',type=Path,required=True);p.add_argument('--promotion-id',required=True);p.add_argument('--lease-token',required=True)
    p=sub.add_parser('wait-ready');p.add_argument('--url',required=True);p.add_argument('--attempts',type=int,default=15);p.add_argument('--delay',type=float,default=1);p.add_argument('--timeout',type=float,default=2);p.add_argument('--receipt',type=Path,required=True);p.add_argument('--runtime-root',type=Path,required=True);p.add_argument('--promotion-id',required=True);p.add_argument('--lease-token',required=True);p.add_argument('--candidate-revision',required=True)
    p=sub.add_parser('activate');p.add_argument('--release-root',type=Path,required=True);p.add_argument('--current',type=Path,required=True);p.add_argument('--runtime-root',type=Path,required=True);p.add_argument('--receipt',type=Path,required=True);p.add_argument('--promotion-id',required=True);p.add_argument('--lease-token',required=True)
    p=sub.add_parser('seal-assurance');p.add_argument('--kind',choices=['guardian-post','sentinel-post'],required=True);p.add_argument('--source',type=Path,required=True);p.add_argument('--receipt',type=Path,required=True);p.add_argument('--runtime-root',type=Path,required=True);p.add_argument('--promotion-id',required=True);p.add_argument('--lease-token',required=True);p.add_argument('--candidate-revision',required=True)
    p=sub.add_parser('finalize');p.add_argument('--release-root',type=Path,required=True);p.add_argument('--current',type=Path,required=True);p.add_argument('--runtime-root',type=Path,required=True);p.add_argument('--receipt',type=Path,required=True);p.add_argument('--guardian-post',type=Path,required=True);p.add_argument('--sentinel-post',type=Path,required=True);p.add_argument('--readiness',type=Path,required=True);p.add_argument('--controlled-cycle-receipt',type=Path,required=True);p.add_argument('--timer-cycle-receipt',type=Path,required=True);p.add_argument('--release-count',type=int,required=True);p.add_argument('--promotion-id',required=True);p.add_argument('--lease-token',required=True)
    p=sub.add_parser('rollback');p.add_argument('--release-root',type=Path,required=True);p.add_argument('--current',type=Path,required=True);p.add_argument('--runtime-root',type=Path,required=True);p.add_argument('--receipt',type=Path,required=True);p.add_argument('--promotion-id',required=True);p.add_argument('--lease-token',required=True);p.add_argument('--reason',required=True)
    p=sub.add_parser('supersede-expired');p.add_argument('--current',type=Path,required=True);p.add_argument('--runtime-root',type=Path,required=True);p.add_argument('--successor-approval',type=Path,required=True);p.add_argument('--guardian-event',type=Path,required=True);p.add_argument('--guardian-result',type=Path,required=True);p.add_argument('--receipt',type=Path,required=True)
    a=ap.parse_args()
    try:
        if a.cmd=='lease-acquire':out=ptx.acquire(a.runtime_root,a.promotion_id,a.owner,a.candidate_revision,a.ttl_seconds)
        elif a.cmd=='lease-recover':out=ptx.recover(a.runtime_root,a.promotion_id,a.owner,a.candidate_revision,a.previous_lease_id,a.ttl_seconds)
        elif a.cmd=='lease-status':out=ptx.public_status(a.runtime_root)
        elif a.cmd=='prepare':out=prepare(a.candidate_root,a.runtime_root,a.receipt,a.promotion_id,a.lease_token)
        elif a.cmd=='wait-ready':out=wait_ready(a.url,a.attempts,a.delay,a.timeout,a.receipt,a.runtime_root,a.promotion_id,a.lease_token,a.candidate_revision)
        elif a.cmd=='activate':out=activate(a.release_root,a.current,a.runtime_root,a.receipt,a.promotion_id,a.lease_token)
        elif a.cmd=='seal-assurance':out=seal_assurance(a.kind,a.source,a.receipt,a.runtime_root,a.promotion_id,a.lease_token,a.candidate_revision)
        elif a.cmd=='rollback':out=rollback(a.release_root,a.current,a.runtime_root,a.receipt,a.promotion_id,a.lease_token,a.reason)
        elif a.cmd=='supersede-expired':out=supersede_expired_active_base(a.current,a.runtime_root,a.successor_approval,a.guardian_event,a.guardian_result,a.receipt)
        else:out=finalize(a.release_root,a.current,a.runtime_root,a.receipt,a.guardian_post,a.sentinel_post,a.readiness,a.controlled_cycle_receipt,a.timer_cycle_receipt,a.release_count,a.promotion_id,a.lease_token)
        print(json.dumps(out,ensure_ascii=False));return 0
    except Exception as e:
        print(json.dumps({'schema':SCHEMA,'status':'BLOCK','reason':str(e),'automatic_external_spend_eur':0},ensure_ascii=False));return 20
if __name__=='__main__':raise SystemExit(main())
