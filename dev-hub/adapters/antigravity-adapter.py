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
BACKEND=Path('/usr/local/bin/agy-dev')
ATTESTATION=Path('/opt/chacha-dev/runtime/provider-economics/antigravity-zero-cost.json')
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
        expiry=parse_time(x.get('valid_until'))
        if expiry is None or expiry<=datetime.now(timezone.utc):return False,'ZERO_COST_ATTESTATION_EXPIRED',x
    return True,'ZERO_COST_ATTESTED',x

def tree_digest(root:Path)->str:
    h=hashlib.sha256()
    if not root.is_dir():return 'sha256:'+h.hexdigest()
    for p in sorted((p for p in root.rglob('*') if p.is_file() and '.git' not in p.parts),key=lambda q:q.as_posix()):
        rel=p.relative_to(root).as_posix().encode();data=p.read_bytes();h.update(len(rel).to_bytes(8,'big'));h.update(rel);h.update(len(data).to_bytes(8,'big'));h.update(data)
    return 'sha256:'+h.hexdigest()
def provider_status(req):
    ok,reason,att=economics()
    if not ok:return emit(req,'BLOCKED',reason,[{'kind':'policy','source':str(ATTESTATION),'details':{'provider_invocation_started':False,'automatic_external_spend_eur':0}}],[],2)
    if not BACKEND.is_file():return emit(req,'FAILED','ANTIGRAVITY_BACKEND_MISSING',[],[],1)
    try:p=subprocess.run([str(BACKEND),'models'],stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=30)
    except Exception as exc:return emit(req,'FAILED','ANTIGRAVITY_PROVIDER_STATUS_ERROR:'+type(exc).__name__,[],[],1)
    raw=p.stdout.encode('utf-8','replace')
    if p.returncode!=0 or 'gemini-' not in p.stdout:return emit(req,'FAILED','ANTIGRAVITY_PROVIDER_UNAVAILABLE',[{'kind':'command','source':'agy-dev models','digest':sha(raw),'details':{'exit_code':p.returncode,'automatic_external_spend_eur':0}}],[],1)
    count=sum(1 for line in p.stdout.splitlines() if line.strip().startswith('gemini-'))
    return emit(req,'OK','ANTIGRAVITY_PROVIDER_STATUS_OK',[{'kind':'command','source':'agy-dev models','digest':sha(raw),'details':{'model_count':count,'cost_class':att.get('cost_class'),'automatic_external_spend_eur':0}}],[],0)

def execute_capability(req,task,capability,permission):
    ok,reason,att=economics()
    if not ok:return emit(req,'BLOCKED',reason,[{'kind':'policy','source':str(ATTESTATION),'details':{'provider_invocation_started':False,'automatic_external_spend_eur':0}}],[],2)
    raw_workspace=str(req.get('workspace') or '').strip();workspace=Path(raw_workspace) if raw_workspace else None
    if permission=='workspace-write':
        if workspace is None or not workspace.is_absolute() or not workspace.is_dir():return emit(req,'BLOCKED','GOVERNED_WORKSPACE_REQUIRED',[],[],2)
    before=tree_digest(workspace) if workspace else None
    meta=req.get('metadata') if isinstance(req.get('metadata'),dict) else {};intent=str(meta.get('intent_excerpt') or '')[:4000]
    description=str(task.get('description') or '')[:2000]
    prompt=('Execute this ChaCha DEV governed task. Work only inside the provided workspace. Do not deploy to production, do not purchase access, do not reveal secrets. '
            'Return a concise completion summary after the task.\nCAPABILITY: '+capability+'\nTASK: '+description+'\nFUNCTIONAL INTENT: '+intent)
    mode='accept-edits' if permission=='workspace-write' else 'plan'
    argv=[str(BACKEND),'--print',prompt,'--mode',mode,'--sandbox','--print-timeout','300s']
    if workspace:argv += ['--add-dir',str(workspace)]
    try:p=subprocess.run(argv,cwd=str(workspace) if workspace else None,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=330)
    except subprocess.TimeoutExpired:return emit(req,'FAILED','ANTIGRAVITY_TIMEOUT',[],[],1)
    except Exception as exc:return emit(req,'FAILED','ANTIGRAVITY_EXECUTION_ERROR:'+type(exc).__name__,[],[],1)
    after=tree_digest(workspace) if workspace else None
    if permission in {'read','plan'} and before is not None and after!=before:
        return emit(req,'FAILED','READ_ONLY_PROVIDER_MUTATION_DETECTED',[{'kind':'workspace','source':str(workspace),'details':{'before':before,'after':after}}],[],1)
    evidence=[{'kind':'provider-run','source':'agy-dev','digest':sha(p.stdout.encode('utf-8','replace')),
               'details':{'exit_code':p.returncode,'capability':capability,'permission':permission,'workspace_before':before,'workspace_after':after,
                          'cost_class':att.get('cost_class'),'automatic_external_spend_eur':0}}]
    if p.returncode!=0:return emit(req,'FAILED','ANTIGRAVITY_PROVIDER_EXECUTION_FAILED',evidence,[],1)
    outputs=[]
    for row in task.get('outputs') or []:
        if isinstance(row,dict) and row.get('type') and row.get('id'):outputs.append({'type':row['type'],'id':row['id'],'status':'OK'})
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
