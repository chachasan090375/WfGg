#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,os,sys
from datetime import datetime,timezone
from pathlib import Path
from typing import Any

INPUT_SCHEMA='chacha.dev/dispatch-envelope/v1'
OUTPUT_SCHEMA='chacha.dev/task-result/v1'
ADAPTER_ID='workspace-file-adapter'
PROVIDER_ID='workspace-file-runtime'
PROJECT_ROOT=Path(os.environ.get('CHACHA_DEV_PROJECT_ROOT','/opt/chacha-dev/runtime/projects'))

def now_iso()->str:return datetime.now(timezone.utc).isoformat()
def sha256_file(path:Path)->str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return 'sha256:'+h.hexdigest()
def result(req:dict[str,Any],status:str,summary:str,evidence=None,outputs=None)->dict[str,Any]:
    task=req.get('task') if isinstance(req.get('task'),dict) else {}
    return {'schema':OUTPUT_SCHEMA,'project':str(req.get('project') or 'unknown'),'task_id':str(task.get('id') or 'unknown'),'status':status,'producer':ADAPTER_ID,'observed_at':now_iso(),'summary':summary,'evidence':evidence or [],'verification':{'status':'UNVERIFIED','method':'none','verifier':'pending-independent-verifier','observed_at':now_iso(),'notes':'Workspace mutation result requires independent verification.'},'outputs':outputs or []}
def emit(x:dict[str,Any],code:int=0)->int:
    print(json.dumps(x,ensure_ascii=False,separators=(',',':')));return code
def blocked(req:dict[str,Any],reason:str)->int:
    return emit(result(req,'BLOCKED',reason,[{'kind':'report','source':'workspace-file-adapter-policy','digest':'sha256:'+hashlib.sha256(reason.encode()).hexdigest(),'details':{'reason':reason}}]),2)
def binding_ok(req:dict[str,Any])->bool:
    return any(isinstance(x,dict) and x.get('provider')==PROVIDER_ID and x.get('adapter')==ADAPTER_ID and x.get('health_state')=='HEALTHY' for x in (req.get('bindings') or []))
def validate_workspace(req:dict[str,Any])->tuple[Path|None,str|None]:
    raw=str(req.get('workspace') or '').strip();project=str(req.get('project') or '').strip()
    if not raw:return None,'WORKSPACE_REQUIRED'
    p=Path(raw)
    if not p.is_absolute():return None,'WORKSPACE_MUST_BE_ABSOLUTE'
    try:r=p.resolve(strict=False);r.relative_to(PROJECT_ROOT.resolve())
    except Exception:return None,'WORKSPACE_OUTSIDE_GOVERNED_ROOT'
    if project and project not in r.parts:return None,'WORKSPACE_PROJECT_MISMATCH'
    return r,None
def safe_relative(value:str)->tuple[Path|None,str|None]:
    raw=value.strip().replace('\\','/')
    if not raw:return None,'WORKSPACE_FILE_PATH_MISSING'
    p=Path(raw)
    if p.is_absolute() or '..' in p.parts:return None,'WORKSPACE_FILE_PATH_UNSAFE'
    if len(p.parts)>8:return None,'WORKSPACE_FILE_PATH_TOO_DEEP'
    return p,None

def main()->int:
    try:req=json.load(sys.stdin)
    except Exception:return emit({'schema':OUTPUT_SCHEMA,'project':'unknown','task_id':'unknown','status':'BLOCKED','producer':ADAPTER_ID,'observed_at':now_iso(),'summary':'INPUT_JSON_INVALID','evidence':[],'verification':{'status':'UNVERIFIED','method':'none','verifier':'none','observed_at':now_iso(),'notes':'Invalid input.'},'outputs':[]},2)
    if req.get('schema')!=INPUT_SCHEMA:return blocked(req,'INPUT_SCHEMA_INVALID')
    task=req.get('task') if isinstance(req.get('task'),dict) else {}
    meta=req.get('metadata') if isinstance(req.get('metadata'),dict) else {}
    action=(meta.get('workspace_file') or {}).get('action') if isinstance(meta.get('workspace_file'),dict) else None
    if action=='status':
        if task.get('permission')!='read':return blocked(req,'WORKSPACE_FILE_STATUS_PERMISSION_REQUIRED:read')
        if not binding_ok(req):return blocked(req,'WORKSPACE_FILE_BINDING_NOT_HEALTHY')
        ev=[{'kind':'report','source':'workspace-file-adapter','digest':'sha256:'+hashlib.sha256(b'workspace-file-adapter-v1').hexdigest(),'details':{'provider':PROVIDER_ID,'write_scope':'governed-project-workspace-only','automatic_external_spend_eur':0}}]
        return emit(result(req,'OK','WORKSPACE_FILE_RUNTIME_READY',ev,task.get('outputs') or []),0)
    if task.get('permission')!='workspace-write':return blocked(req,'WORKSPACE_FILE_WRITE_PERMISSION_REQUIRED:workspace-write')
    if not binding_ok(req):return blocked(req,'WORKSPACE_FILE_BINDING_NOT_HEALTHY')
    spec=meta.get('workspace_file') if isinstance(meta.get('workspace_file'),dict) else {}
    if spec.get('action')!='write-text':return blocked(req,'WORKSPACE_FILE_ACTION_REQUIRED:write-text')
    rel,err=safe_relative(str(spec.get('path') or ''))
    if err:return blocked(req,err)
    content=spec.get('content')
    if not isinstance(content,str):return blocked(req,'WORKSPACE_FILE_CONTENT_MISSING')
    if len(content.encode('utf-8'))>64*1024:return blocked(req,'WORKSPACE_FILE_CONTENT_TOO_LARGE')
    workspace,err=validate_workspace(req)
    if err:return blocked(req,err)
    workspace.mkdir(parents=True,exist_ok=True)
    target=(workspace/rel).resolve(strict=False)
    try:target.relative_to(workspace.resolve())
    except Exception:return blocked(req,'WORKSPACE_FILE_TARGET_OUTSIDE_WORKSPACE')
    if target.exists() and target.is_symlink():return blocked(req,'WORKSPACE_FILE_SYMLINK_TARGET_FORBIDDEN')
    target.parent.mkdir(parents=True,exist_ok=True)
    try:target.parent.resolve().relative_to(workspace.resolve())
    except Exception:return blocked(req,'WORKSPACE_FILE_PARENT_OUTSIDE_WORKSPACE')
    tmp=target.with_name(target.name+'.tmp-'+str(os.getpid()))
    tmp.write_text(content,encoding='utf-8');os.chmod(tmp,0o640);os.replace(tmp,target)
    ev=[{'kind':'artifact','source':str(target),'digest':sha256_file(target),'details':{'relative_path':str(rel),'bytes':target.stat().st_size,'workspace':str(workspace),'automatic_external_spend_eur':0}}]
    outputs=[{'type':x.get('type'),'id':x.get('id'),'status':'UNVERIFIED','path':str(target)} for x in (task.get('outputs') or []) if isinstance(x,dict)]
    return emit(result(req,'OK','WORKSPACE_FILE_WRITTEN',ev,outputs),0)

if __name__=='__main__':raise SystemExit(main())
