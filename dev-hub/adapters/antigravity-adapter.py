#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,os,re,subprocess,sys
from datetime import datetime,timezone
from pathlib import Path

INPUT_SCHEMA='chacha.dev/dispatch-envelope/v1'
OUTPUT_SCHEMA='chacha.dev/task-result/v1'
ATTEST_SCHEMA='chacha.dev/provider-zero-cost-attestation/v1'
ADAPTER_ID='antigravity-adapter'
PROVIDER_ID='antigravity'
BACKEND=Path('/usr/local/bin/agy')
ACCOUNT_HOME=Path('/opt/chacha-dev/runtime/provider-economics/antigravity-account-home')
ATTESTATION=Path('/opt/chacha-dev/runtime/provider-economics/antigravity-zero-cost.json')
EVIDENCE_ROOT=Path(os.environ.get('CHACHA_DEV_PROVIDER_EVIDENCE_ROOT','/opt/chacha-dev/runtime/evidence/provider-runs'))
GOVERNED_WORKSPACE_ROOT=Path('/opt/chacha-dev/runtime/projects')
MODEL_PREFERENCES=[('gemini-3.8-flash-medium','gemini models'),('claude-sonnet-4-6','claude and gpt models'),('gpt-oss-120b-medium','claude and gpt models')]
for _bin in (Path(__file__).resolve().parents[1]/'bin',Path('/opt/chacha-dev/platform/current/dev-hub/bin')):
    if _bin.is_dir() and str(_bin) not in sys.path:sys.path.insert(0,str(_bin))
try:import provider_quota_circuit as pqc
except Exception:pqc=None
ALLOWED_CAPABILITIES={'code-edit','code-review','documentation','translation','translation-quality-review'}
ALLOWED_PERMISSIONS={'read','plan','workspace-write'}

def now_iso():return datetime.now(timezone.utc).isoformat()
def sha(raw:bytes)->str:return 'sha256:'+hashlib.sha256(raw).hexdigest()
def load(path:Path):
    try:return json.loads(path.read_text(encoding='utf-8'))
    except Exception:return None

def emit(req,status,summary,evidence=None,outputs=None,code=0):
    task=req.get('task') if isinstance(req.get('task'),dict) else {}
    payload={'schema':OUTPUT_SCHEMA,'project':str(req.get('project') or 'unknown'),'task_id':str(task.get('id') or 'unknown'),
             'status':status,'producer':ADAPTER_ID,'observed_at':now_iso(),'summary':summary,'evidence':evidence or [],
             'verification':{'status':'UNVERIFIED','method':'none','verifier':'none','observed_at':now_iso(),'notes':'Independent verification required.'},
             'outputs':outputs or []}
    sys.stdout.write(json.dumps(payload,ensure_ascii=False,separators=(',',':'))+'\n');return code
def parse_time(value):
    try:return datetime.fromisoformat(str(value).replace('Z','+00:00'))
    except Exception:return None

def economics():
    x=load(ATTESTATION)
    if not isinstance(x,dict):return False,'ZERO_COST_ATTESTATION_MISSING',None
    if x.get('schema')!=ATTEST_SCHEMA or x.get('provider_id')!=PROVIDER_ID or x.get('status')!='PASS':
        return False,'ZERO_COST_ATTESTATION_INVALID',x
    try:spend=float(x.get('automatic_external_spend_eur'))
    except Exception:spend=-1
    if spend!=0:return False,'ZERO_COST_ATTESTATION_NONZERO_SPEND',x
    cost=str(x.get('cost_class') or '').lower()
    if cost not in {'free','owned','included','local','quota'}:return False,'COST_CLASS_NOT_AUTOMATIC_ZERO',x
    if cost=='quota':
        if x.get('quota_available') is not True:return False,'FREE_QUOTA_NOT_CONFIRMED',x
        if x.get('auth_mode')!='account-oauth' or x.get('baseline_quota_only') is not True:return False,'ACCOUNT_BASELINE_QUOTA_ATTESTATION_REQUIRED',x
        if x.get('overage_enabled') is not False:return False,'AI_CREDIT_OVERAGE_NOT_DISABLED',x
        expiry=parse_time(x.get('valid_until'))
        if expiry is None or expiry<=datetime.now(timezone.utc):return False,'ZERO_COST_ATTESTATION_EXPIRED',x
    return True,'ZERO_COST_ATTESTED',x

def account_env():
    env=os.environ.copy();env.pop('GEMINI_API_KEY',None);env['HOME']=str(ACCOUNT_HOME);return env
def slash_probe(command:str):
    try:p=subprocess.run([str(BACKEND),'--print',command,'--output-format','json','--print-timeout','20s'],env=account_env(),stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=40)
    except Exception as exc:return None,'ACCOUNT_PROBE_ERROR:'+type(exc).__name__
    try:x=json.loads(p.stdout)
    except Exception:return None,'ACCOUNT_PROBE_JSON_INVALID'
    if p.returncode!=0 or x.get('status')!='SUCCESS' or x.get('num_turns')!=0 or ((x.get('usage') or {}).get('total_tokens') not in {0,None}):return x,'ACCOUNT_PROBE_FAILED'
    return x,None
def live_zero_cost_gate():
    cfg,err=slash_probe('/config')
    if err:return False,err,None
    conf=((cfg.get('command') or {}).get('data') or {}).get('config') or {}
    if conf.get('useG1Credits') is not False:return False,'AI_CREDIT_OVERAGE_NOT_DISABLED',None
    if str(conf.get('modelProvider') or ''):return False,'ACCOUNT_AUTH_NOT_ACTIVE',None
    usage,err=slash_probe('/usage')
    if err:return False,err,None
    groups={}
    for group in ((((usage.get('command') or {}).get('data') or {}).get('groups')) or []):
        name=str(group.get('name') or '').strip().casefold();vals=[];reset=None
        for bucket in group.get('buckets') or []:
            try:vals.append(float(bucket.get('remaining_fraction')))
            except Exception:continue
            if reset is None:reset=bucket.get('reset_time')
        if vals:groups[name]={'remaining_fraction':min(vals),'reset_time':reset}
    try:models=subprocess.run([str(BACKEND),'models'],env=account_env(),stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=30)
    except Exception as exc:return False,'ACCOUNT_MODELS_PROBE_ERROR:'+type(exc).__name__,None
    if models.returncode!=0:return False,'ACCOUNT_MODELS_PROBE_FAILED',None
    available={line.split('\t',1)[0].strip() for line in models.stdout.splitlines() if line.strip() and not line.startswith('Fetching ')}
    att=load(ATTESTATION) or {}
    try:minimum=float(att.get('minimum_remaining_fraction') or 0.01)
    except Exception:minimum=0.01
    blocked_models=[];eligible=[]
    for model,group_name in MODEL_PREFERENCES:
        if model not in available:continue
        row=groups.get(group_name) or {};remaining=row.get('remaining_fraction')
        circuit=pqc.blocked(PROVIDER_ID,model) if pqc is not None else None
        if circuit is not None:
            blocked_models.append({'model':model,'quota_group':group_name,'resume_at':circuit.get('resume_at')});continue
        if isinstance(remaining,(int,float)) and remaining>=minimum:
            eligible.append({'model':model,'quota_group':group_name,'remaining_fraction':remaining,'reset_time':row.get('reset_time')})
    if eligible:
        selected=eligible[0]
        return True,'ACCOUNT_BASELINE_QUOTA_AVAILABLE',{'selected_model':selected['model'],'selected_quota_group':selected['quota_group'],'remaining_fraction':selected['remaining_fraction'],'reset_time':selected.get('reset_time'),'eligible_models':[r['model'] for r in eligible],'quota_groups':groups,'blocked_models':blocked_models}
    resets=[]
    for row in groups.values():
        if isinstance(row,dict) and row.get('reset_time'):resets.append(str(row.get('reset_time')))
    resets += [str(r.get('resume_at')) for r in blocked_models if r.get('resume_at')]
    quota_seen=any(isinstance((groups.get(g) or {}).get('remaining_fraction'),(int,float)) for _,g in MODEL_PREFERENCES)
    if quota_seen:
        return False,'PROVIDER_MODEL_QUOTA_EXHAUSTED',{'provider':PROVIDER_ID,'model':'all-zero-cost-models','resume_at':sorted(resets)[0] if resets else None,'quota_groups':groups,'blocked_models':blocked_models,'automatic_paid_upgrade':False,'automatic_external_spend_eur':0}
    return False,'PROVIDER_ZERO_COST_MODEL_UNAVAILABLE',{'quota_groups':groups,'blocked_models':blocked_models,'automatic_external_spend_eur':0}

def file_sha(path:Path)->str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return 'sha256:'+h.hexdigest()
def tree_snapshot(root:Path)->dict[str,str]:
    out={}
    if not root.is_dir():return out
    for p in sorted((q for q in root.rglob('*') if q.is_file() and '.git' not in q.parts),key=lambda q:q.as_posix()):out[p.relative_to(root).as_posix()]=file_sha(p)
    return out
def snapshot_digest(snapshot:dict[str,str])->str:
    return sha(json.dumps(snapshot,sort_keys=True,separators=(',',':')).encode())
def tree_digest(root:Path)->str:return snapshot_digest(tree_snapshot(root))
def local_execution_receipt(req:dict,workspace:Path,before:dict[str,str],after:dict[str,str],provider_stdout:bytes,provider_stderr:bytes,quota:dict|None)->Path:
    task=req.get('task') if isinstance(req.get('task'),dict) else {};project=str(req.get('project') or 'unknown');run_id=str(req.get('run_id') or 'run');tid=str(task.get('id') or 'task')
    safe=lambda v:re.sub(r'[^A-Za-z0-9._-]+','_',v)[:160]
    added=sorted(set(after)-set(before));deleted=sorted(set(before)-set(after));modified=sorted(k for k in set(before)&set(after) if before[k]!=after[k])
    root=EVIDENCE_ROOT/safe(project)/safe(run_id);root.mkdir(parents=True,exist_ok=True);path=root/(safe(tid)+'.json')
    payload={'schema':'chacha.dev/provider-workspace-execution-receipt/v1','provider':PROVIDER_ID,'adapter':ADAPTER_ID,'project':project,'run_id':run_id,'task_id':tid,'observed_at':now_iso(),'workspace':str(workspace),'workspace_before':snapshot_digest(before),'workspace_after':snapshot_digest(after),'added':added,'modified':modified,'deleted':deleted,'changed_file_digests':{k:after[k] for k in added+modified},'provider_stdout_digest':sha(provider_stdout),'provider_stderr_digest':sha(provider_stderr),'auth_mode':'account-oauth','quota_remaining_fraction':(quota or {}).get('remaining_fraction'),'model':(quota or {}).get('selected_model'),'quota_group':(quota or {}).get('selected_quota_group'),'automatic_external_spend_eur':0}
    tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(payload,indent=2,ensure_ascii=False)+'\n',encoding='utf-8');os.chmod(tmp,0o640);os.replace(tmp,path);return path
def provider_status(req):
    ok,reason,att=economics()
    if not ok:return emit(req,'BLOCKED',reason,[{'kind':'policy','source':str(ATTESTATION),'details':{'provider_invocation_started':False,'automatic_external_spend_eur':0}}],[],2)
    if not BACKEND.is_file():return emit(req,'FAILED','ANTIGRAVITY_BACKEND_MISSING',[],[],1)
    model_id=str((att or {}).get('selected_model') or '')
    quota_group=str((att or {}).get('selected_quota_group') or '')
    if not model_id:return emit(req,'BLOCKED','ZERO_COST_ATTESTATION_MODEL_MISSING',[],[],2)
    circuit=pqc.blocked(PROVIDER_ID,model_id) if pqc is not None else None
    if circuit is not None:
        return emit(req,'BLOCKED','PROVIDER_MODEL_QUOTA_EXHAUSTED',[{'kind':'provider-quota-circuit','source':str(pqc.state_path()),'details':{'provider':PROVIDER_ID,'model':model_id,'resume_at':circuit.get('resume_at'),'provider_invocation_started':False,'automatic_paid_upgrade':False,'automatic_external_spend_eur':0}}],[],2)
    try:p=subprocess.run([str(BACKEND),'models'],env=account_env(),stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=30)
    except Exception as exc:return emit(req,'FAILED','ANTIGRAVITY_PROVIDER_STATUS_ERROR:'+type(exc).__name__,[],[],1)
    raw=p.stdout.encode('utf-8','replace')
    if p.returncode!=0:return emit(req,'FAILED','ANTIGRAVITY_PROVIDER_UNAVAILABLE',[{'kind':'command','source':'agy-account models','digest':sha(raw),'details':{'exit_code':p.returncode,'automatic_external_spend_eur':0}}],[],1)
    available={line.split('\t',1)[0].strip() for line in p.stdout.splitlines() if line.strip() and not line.startswith('Fetching ')}
    if model_id not in available:return emit(req,'BLOCKED','ATTESTED_MODEL_UNAVAILABLE',[{'kind':'command','source':'agy-account models','digest':sha(raw),'details':{'selected_model':model_id,'automatic_external_spend_eur':0}}],[],2)
    return emit(req,'OK','ANTIGRAVITY_PROVIDER_STATUS_OK',[{'kind':'command','source':'agy-account models','digest':sha(raw),'details':{'model_count':len(available),'selected_model':model_id,'selected_quota_group':quota_group,'cost_class':att.get('cost_class'),'auth_mode':'account-oauth','quota_remaining_fraction':att.get('quota_remaining_fraction'),'economics_attestation_fresh':True,'live_economics_recheck_required_before_generation':True,'automatic_external_spend_eur':0}}],[],0)

def execute_capability(req,task,capability,permission):
    ok,reason,att=economics()
    if not ok:return emit(req,'BLOCKED',reason,[{'kind':'policy','source':str(ATTESTATION),'details':{'provider_invocation_started':False,'automatic_external_spend_eur':0}}],[],2)
    live,live_reason,quota=live_zero_cost_gate()
    if not live:
        details={'provider':PROVIDER_ID,'provider_invocation_started':False,'automatic_paid_upgrade':False,'automatic_external_spend_eur':0,**(quota or {})}
        return emit(req,'BLOCKED',live_reason,[{'kind':'policy','source':'antigravity-account-live-gate','details':details}],[],2)
    model_id=str((quota or {}).get('selected_model') or '')
    if not model_id:return emit(req,'BLOCKED','PROVIDER_ZERO_COST_MODEL_UNAVAILABLE',[],[],2)
    raw_workspace=str(req.get('workspace') or '').strip();workspace=Path(raw_workspace) if raw_workspace else None
    if permission=='workspace-write':
        if workspace is None or not workspace.is_absolute() or not workspace.is_dir():return emit(req,'BLOCKED','GOVERNED_WORKSPACE_REQUIRED',[],[],2)
        try:workspace.resolve().relative_to(GOVERNED_WORKSPACE_ROOT.resolve())
        except Exception:return emit(req,'BLOCKED','GOVERNED_WORKSPACE_OUTSIDE_PROJECT_ROOT',[],[],2)
        if not (workspace/'.git/config').is_file():return emit(req,'BLOCKED','GOVERNED_WORKSPACE_GIT_BASELINE_REQUIRED',[],[],2)
        try:rem=subprocess.run(['git','-C',str(workspace),'remote'],stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=15)
        except Exception as exc:return emit(req,'BLOCKED','GOVERNED_WORKSPACE_GIT_VERIFY_ERROR:'+type(exc).__name__,[],[],2)
        if rem.returncode!=0 or rem.stdout.strip():return emit(req,'BLOCKED','GOVERNED_WORKSPACE_REMOTE_FORBIDDEN',[],[],2)
    before_snapshot=tree_snapshot(workspace) if workspace else {};before=snapshot_digest(before_snapshot) if workspace else None
    meta=req.get('metadata') if isinstance(req.get('metadata'),dict) else {};intent=str(meta.get('intent_excerpt') or '')[:4000]
    description=str(task.get('description') or '')[:2000]
    prompt=('Execute this ChaCha DEV governed task. Work only inside the provided workspace. Do not deploy to production, do not purchase access, do not reveal secrets. '
            'Return a concise completion summary after the task.\nCAPABILITY: '+capability+'\nTASK: '+description+'\nFUNCTIONAL INTENT: '+intent)
    mode='accept-edits' if permission=='workspace-write' else 'plan'
    policy_context=req.get('policy_context') if isinstance(req.get('policy_context'),dict) else {}
    governed_timeout=max(60,min(1800,int(policy_context.get('timeout_seconds') or 300)))
    provider_timeout=max(30,governed_timeout-60)
    adapter_timeout=min(governed_timeout-10,provider_timeout+30)
    argv=[str(BACKEND),'--print',prompt,'--mode',mode,'--sandbox','--print-timeout',str(provider_timeout)+'s','--model',model_id,'--output-format','json']
    if permission=='workspace-write':argv += ['--dangerously-skip-permissions']
    if workspace:argv += ['--add-dir',str(workspace)]
    try:p=subprocess.run(argv,cwd=str(workspace) if workspace else None,env=account_env(),stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=adapter_timeout)
    except subprocess.TimeoutExpired:return emit(req,'FAILED','ANTIGRAVITY_TIMEOUT',[],[],1)
    except Exception as exc:return emit(req,'FAILED','ANTIGRAVITY_EXECUTION_ERROR:'+type(exc).__name__,[],[],1)
    after_snapshot=tree_snapshot(workspace) if workspace else {};after=snapshot_digest(after_snapshot) if workspace else None
    if permission in {'read','plan'} and before is not None and after!=before:
        return emit(req,'FAILED','READ_ONLY_PROVIDER_MUTATION_DETECTED',[{'kind':'workspace','source':str(workspace),'details':{'before':before,'after':after}}],[],1)
    if p.returncode!=0:
        combined=(str(p.stdout or '')+'\n'+str(p.stderr or ''))
        circuit=pqc.observe_text(PROVIDER_ID,model_id,combined,'antigravity-adapter') if pqc is not None else None
        if circuit is not None:
            cp=pqc.state_path();ev=[]
            if cp.is_file():ev.append({'kind':'provider-quota-circuit','source':str(cp),'digest':file_sha(cp),'details':{'provider':PROVIDER_ID,'model':model_id,'resume_at':circuit.get('resume_at'),'provider_invocation_started':True,'automatic_paid_upgrade':False,'automatic_external_spend_eur':0}})
            return emit(req,'BLOCKED','PROVIDER_MODEL_QUOTA_EXHAUSTED',ev,[],2)
        return emit(req,'FAILED','ANTIGRAVITY_PROVIDER_EXECUTION_FAILED',[],[],1)
    if permission=='workspace-write' and before_snapshot==after_snapshot:
        return emit(req,'BLOCKED','WORKSPACE_WRITE_NO_MUTATION',[],[],2)
    receipt=local_execution_receipt(req,workspace,before_snapshot,after_snapshot,p.stdout.encode('utf-8','replace'),p.stderr.encode('utf-8','replace'),quota) if workspace else None
    evidence=[]
    if receipt is not None:evidence.append({'kind':'provider-execution-receipt','source':str(receipt),'digest':file_sha(receipt),'details':{'workspace':str(workspace),'model':model_id,'quota_group':quota.get('selected_quota_group'),'automatic_external_spend_eur':0}})
    changed=[k for k in sorted(after_snapshot) if before_snapshot.get(k)!=after_snapshot.get(k)]
    for rel in changed[:32]:
        target=workspace/rel;evidence.append({'kind':'workspace-artifact','source':str(target),'digest':after_snapshot[rel],'details':{'relative_path':rel,'workspace':str(workspace),'automatic_external_spend_eur':0}})
    outputs=[]
    for row in task.get('outputs') or []:
        if isinstance(row,dict) and row.get('type') and row.get('id'):outputs.append({'type':row['type'],'id':row['id'],'status':'UNVERIFIED'})
    return emit(req,'OK','ANTIGRAVITY_TASK_COMPLETED',evidence,outputs,0)

def main():
    try:req=json.load(sys.stdin)
    except Exception:return emit({},'BLOCKED','INPUT_JSON_INVALID',[],[],2)
    if req.get('schema')!=INPUT_SCHEMA:return emit(req,'BLOCKED','INPUT_SCHEMA_INVALID',[],[],2)
    task=req.get('task') if isinstance(req.get('task'),dict) else {};permission=str(task.get('permission') or '')
    caps=[str(x) for x in task.get('capabilities') or []]
    if permission not in ALLOWED_PERMISSIONS:return emit(req,'BLOCKED','ANTIGRAVITY_PERMISSION_DENIED',[],[],2)
    bindings=req.get('bindings') or []
    if not any(isinstance(x,dict) and x.get('provider')==PROVIDER_ID and x.get('adapter')==ADAPTER_ID for x in bindings):return emit(req,'BLOCKED','ANTIGRAVITY_BINDING_MISSING',[],[],2)
    meta=req.get('metadata') if isinstance(req.get('metadata'),dict) else {};ag=meta.get('antigravity') if isinstance(meta.get('antigravity'),dict) else {}
    if ag.get('action')=='provider-status':return provider_status(req)
    if len(caps)!=1 or caps[0] not in ALLOWED_CAPABILITIES:return emit(req,'BLOCKED','ANTIGRAVITY_CAPABILITY_DENIED',[],[],2)
    return execute_capability(req,task,caps[0],permission)

if __name__=='__main__':raise SystemExit(main())
