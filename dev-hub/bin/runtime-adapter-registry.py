#!/usr/bin/env python3
from __future__ import annotations
import argparse,copy,hashlib,json,os,tempfile
from datetime import datetime,timezone
from pathlib import Path
from typing import Any

BASE_SCHEMA='chacha.dev/provider-adapters/v1'
STATE_SCHEMA='chacha.dev/runtime-adapter-state/v1'
REPORT_SCHEMA='chacha.dev/runtime-adapter-registry-reconciliation/v1'
RUNTIME_STATES={'CONTRACT_OK','PILOT','ENABLED','DEGRADED','DISABLED'}

def now_iso()->str:return datetime.now(timezone.utc).isoformat()
def load(path:Path)->dict[str,Any]:
    x=json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(x,dict):raise ValueError('JSON_ROOT_NOT_OBJECT:'+str(path))
    return x
def atomic(path:Path,x:dict[str,Any])->None:
    path.parent.mkdir(parents=True,exist_ok=True);fd,tmp=tempfile.mkstemp(prefix=path.name+'.',suffix='.tmp',dir=str(path.parent))
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as f:json.dump(x,f,indent=2,ensure_ascii=False);f.write('\n');f.flush();os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)
def digest_obj(x:Any)->str:
    raw=json.dumps(x,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode();return 'sha256:'+hashlib.sha256(raw).hexdigest()
def digest_file(path:Path)->str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return 'sha256:'+h.hexdigest()
def empty_state()->dict[str,Any]:return {'schema':STATE_SCHEMA,'version':'1.0.0','adapters':{},'history':[],'updated_at':now_iso(),'automatic_external_spend_eur':0}
def read_state(path:Path)->dict[str,Any]:
    if not path.is_file():return empty_state()
    x=load(path)
    if x.get('schema')!=STATE_SCHEMA:raise ValueError('RUNTIME_ADAPTER_STATE_SCHEMA_INVALID')
    if not isinstance(x.get('adapters'),dict):raise ValueError('RUNTIME_ADAPTER_STATE_ADAPTERS_INVALID')
    return x
def contract_view(base:dict[str,Any],adapter:str)->dict[str,Any]:
    a=(base.get('adapters') or {}).get(adapter)
    providers={k:v for k,v in (base.get('providers') or {}).items() if isinstance(v,dict) and v.get('adapter')==adapter}
    if not isinstance(a,dict):return {}
    return {'adapter':adapter,'supports':a.get('supports') or [],'providers':providers}
def contract_digest(base:dict[str,Any],adapter:str)->str:return digest_obj(contract_view(base,adapter))
def desired_source(base_path:Path,adapter:str)->tuple[str|None,str|None]:
    policy=base_path.parent/'adapter-provisioning.v1.json'
    if not policy.is_file():return None,None
    try:cfg=load(policy)
    except Exception:return None,None
    spec=(cfg.get('adapters') or {}).get(adapter)
    if not isinstance(spec,dict) or not spec.get('source'):return None,None
    root=base_path.resolve().parents[2];src=(root/str(spec['source'])).resolve()
    if not src.is_file():return str(spec.get('version') or ''),None
    return str(spec.get('version') or ''),digest_file(src)
def reconcile(base:dict[str,Any],state:dict[str,Any],base_path:Path|None=None)->tuple[dict[str,Any],dict[str,Any]]:
    if base.get('schema')!=BASE_SCHEMA:raise ValueError('PROVIDER_ADAPTER_SCHEMA_INVALID')
    effective=copy.deepcopy(base);rows=[]
    for adapter,row in sorted((state.get('adapters') or {}).items()):
        blockers=[];base_entry=(base.get('adapters') or {}).get(adapter)
        if not isinstance(row,dict):blockers.append('STATE_ROW_INVALID')
        if not isinstance(base_entry,dict):blockers.append('BASE_ADAPTER_MISSING')
        expected=contract_digest(base,adapter) if isinstance(base_entry,dict) else None
        if isinstance(row,dict) and row.get('contract_digest')!=expected:blockers.append('CONTRACT_DIGEST_MISMATCH')
        desired_version,desired_digest=desired_source(base_path,adapter) if base_path is not None else (None,None)
        if desired_digest is not None and isinstance(row,dict):
            if row.get('source_digest')!=desired_digest:blockers.append('SOURCE_DIGEST_MISMATCH')
            if desired_version and row.get('source_version')!=desired_version:blockers.append('SOURCE_VERSION_MISMATCH')
        status=str((row or {}).get('status') or '')
        if status not in RUNTIME_STATES:blockers.append('RUNTIME_STATUS_INVALID')
        executable=(row or {}).get('executable')
        ed=(row or {}).get('executable_digest')
        if status in {'PILOT','ENABLED','DEGRADED'}:
            p=Path(str(executable or ''))
            if not p.is_absolute() or not p.is_file() or not os.access(p,os.X_OK):blockers.append('EXECUTABLE_UNAVAILABLE')
            elif not isinstance(ed,str) or ed!=digest_file(p):blockers.append('EXECUTABLE_DIGEST_MISMATCH')
        if not blockers:
            effective['adapters'][adapter]['status']=status
            effective['adapters'][adapter]['executable']=executable
        rows.append({'adapter':adapter,'status':'APPLIED' if not blockers else 'QUARANTINED','runtime_status':status,'blockers':blockers,'desired_source_version':desired_version,'desired_source_digest':desired_digest,'runtime_source_version':(row or {}).get('source_version'),'runtime_source_digest':(row or {}).get('source_digest')})
    # Base registry entries can also drift from their immutable provisioning source.
    # A static ENABLED flag is not execution authority when the installed executable
    # no longer matches the source+version contract. Quarantine only the effective
    # runtime view; the release config remains immutable and the governed remediator
    # can then re-provision the exact source and record a runtime overlay receipt.
    state_ids=set((state.get('adapters') or {}).keys())
    for adapter,base_entry in sorted((base.get('adapters') or {}).items()):
        if adapter in state_ids or not isinstance(base_entry,dict):continue
        status=str(base_entry.get('status') or '')
        if status not in {'PILOT','ENABLED','DEGRADED'}:continue
        provider_rows=[v for v in (base.get('providers') or {}).values() if isinstance(v,dict) and v.get('adapter')==adapter]
        if not any(str(v.get('execution') or '')=='vps' for v in provider_rows):continue
        desired_version,desired_digest=desired_source(base_path,adapter) if base_path is not None else (None,None)
        if desired_digest is None:continue
        executable=base_entry.get('executable');actual_digest=None;blockers=[]
        ep=Path(str(executable or ''))
        if not ep.is_absolute() or not ep.is_file() or not os.access(ep,os.X_OK):blockers.append('BASE_EXECUTABLE_UNAVAILABLE')
        else:
            actual_digest=digest_file(ep)
            if actual_digest!=desired_digest:blockers.append('BASE_EXECUTABLE_SOURCE_DIGEST_MISMATCH')
        if blockers:
            effective['adapters'][adapter]['status']='CONTRACT_OK'
            rows.append({'adapter':adapter,'status':'QUARANTINED','runtime_status':status,'blockers':blockers,'desired_source_version':desired_version,'desired_source_digest':desired_digest,'runtime_source_version':None,'runtime_source_digest':actual_digest})
    report={'schema':REPORT_SCHEMA,'observed_at':now_iso(),'status':'PASS' if not any(r['status']=='QUARANTINED' for r in rows) else 'DEGRADED','rows':rows,'applied_count':sum(r['status']=='APPLIED' for r in rows),'quarantined_count':sum(r['status']=='QUARANTINED' for r in rows),'automatic_external_spend_eur':0}
    return effective,report
def persist(base_path:Path,state_path:Path,adapter:str,status:str,executable:str|None,executable_digest:str|None,evidence_refs:list[str])->dict[str,Any]:
    base=load(base_path);state=read_state(state_path)
    if adapter not in (base.get('adapters') or {}):raise ValueError('BASE_ADAPTER_MISSING:'+adapter)
    if status not in RUNTIME_STATES:raise ValueError('RUNTIME_STATUS_INVALID:'+status)
    if status in {'PILOT','ENABLED','DEGRADED'}:
        p=Path(str(executable or ''))
        if not p.is_absolute() or not p.is_file() or not os.access(p,os.X_OK):raise ValueError('EXECUTABLE_UNAVAILABLE')
        actual=digest_file(p)
        if executable_digest and executable_digest!=actual:raise ValueError('EXECUTABLE_DIGEST_MISMATCH')
        executable_digest=actual
    source_version,source_digest=desired_source(base_path,adapter)
    row={'adapter':adapter,'status':status,'executable':executable,'executable_digest':executable_digest,'contract_digest':contract_digest(base,adapter),'source_version':source_version,'source_digest':source_digest,'evidence_refs':list(evidence_refs),'updated_at':now_iso(),'automatic_external_spend_eur':0}
    state['adapters'][adapter]=row;state.setdefault('history',[]).append({'event':'STATE_SET','adapter':adapter,'status':status,'at':now_iso(),'contract_digest':row['contract_digest']});state['updated_at']=now_iso();atomic(state_path,state);return row

def main()->int:
    ap=argparse.ArgumentParser();sub=ap.add_subparsers(dest='cmd',required=True)
    e=sub.add_parser('effective');e.add_argument('--base',type=Path,required=True);e.add_argument('--state',type=Path,required=True);e.add_argument('--output',type=Path,required=True);e.add_argument('--report',type=Path,required=True)
    s=sub.add_parser('set');s.add_argument('--base',type=Path,required=True);s.add_argument('--state',type=Path,required=True);s.add_argument('--adapter',required=True);s.add_argument('--status',required=True);s.add_argument('--executable');s.add_argument('--executable-digest');s.add_argument('--evidence-ref',action='append',default=[]);s.add_argument('--output',type=Path,required=True)
    a=ap.parse_args()
    if a.cmd=='effective':
        base=load(a.base);state=read_state(a.state);effective,report=reconcile(base,state,a.base.resolve());atomic(a.output,effective);atomic(a.report,report);print('CHACHA_DEV_RUNTIME_ADAPTER_REGISTRY='+report['status']);return 0 if report['status'] in {'PASS','DEGRADED'} else 2
    row=persist(a.base,a.state,a.adapter,a.status,a.executable,a.executable_digest,a.evidence_ref);atomic(a.output,{'schema':'chacha.dev/runtime-adapter-state-receipt/v1','status':'PASS','row':row,'automatic_external_spend_eur':0});print('CHACHA_DEV_RUNTIME_ADAPTER_STATE=PASS');return 0
if __name__=='__main__':raise SystemExit(main())
