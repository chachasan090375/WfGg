#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,sys,urllib.request,urllib.error,os,re
from datetime import datetime,timezone
from pathlib import Path
from typing import Any

SCHEMA_IN='chacha.dev/dispatch-envelope/v1';SCHEMA_OUT='chacha.dev/task-result/v1';ADAPTER='context7-mcp-adapter';PROVIDER='context7-mcp';URL='https://mcp.context7.com/mcp'
EVIDENCE_ROOT=Path(os.environ.get('CHACHA_DEV_EVIDENCE_ROOT','/opt/chacha-dev/runtime/evidence'))
def now():return datetime.now(timezone.utc).isoformat()
def digest(b:bytes):return 'sha256:'+hashlib.sha256(b).hexdigest()
def safe(v:str):
 v=re.sub(r'[^A-Za-z0-9._-]+','-',str(v)).strip('.-')
 return v[:120] or 'unknown'
def materialize(req:dict[str,Any],label:str,payload:bytes):
 t=req.get('task') if isinstance(req.get('task'),dict) else {}
 p=EVIDENCE_ROOT/safe(req.get('project') or 'unknown')/safe(req.get('run_id') or 'no-run')/safe(t.get('id') or 'unknown')/(safe(label)+'.evidence')
 p.parent.mkdir(parents=True,exist_ok=True)
 tmp=p.with_name(p.name+'.tmp-'+str(os.getpid()))
 with tmp.open('wb') as f:
  f.write(payload);f.flush();os.fsync(f.fileno())
 os.chmod(tmp,0o640);os.replace(tmp,p)
 return str(p),digest(payload)
def emit(req:dict[str,Any],status:str,summary:str,evidence=None,code=0):
 t=req.get('task') if isinstance(req.get('task'),dict) else {}
 x={'schema':SCHEMA_OUT,'project':str(req.get('project') or 'unknown'),'task_id':str(t.get('id') or 'unknown'),'status':status,'producer':ADAPTER,'observed_at':now(),'summary':summary,'evidence':evidence or [],'verification':{'status':'UNVERIFIED','method':'none','verifier':'none','observed_at':now(),'notes':'External documentation evidence requires independent verification.'},'outputs':[{'type':o.get('type'),'id':o.get('id'),'status':'UNVERIFIED'} for o in t.get('outputs') or [] if isinstance(o,dict)]}
 print(json.dumps(x,ensure_ascii=False,separators=(',',':')));return code
def rpc(method:str,params:dict[str,Any],idv:int=1):
 body=json.dumps({'jsonrpc':'2.0','id':idv,'method':method,'params':params},separators=(',',':')).encode();req=urllib.request.Request(URL,data=body,headers={'Content-Type':'application/json','Accept':'application/json, text/event-stream','User-Agent':'ChaCha-DEV-Context7-Adapter/1.0'},method='POST')
 with urllib.request.urlopen(req,timeout=20) as r:raw=r.read(512000)
 text=raw.decode('utf-8','replace');items=[]
 for line in text.splitlines():
  if line.startswith('data: '):
   try:items.append(json.loads(line[6:]))
   except Exception:pass
 if not items:
  try:items=[json.loads(text)]
  except Exception:raise RuntimeError('MCP_RESPONSE_INVALID')
 return items[-1],raw
def main():
 try:req=json.load(sys.stdin)
 except Exception:return emit({'task':{'id':'unknown'}},'BLOCKED','INPUT_JSON_INVALID',code=2)
 if not isinstance(req,dict) or req.get('schema')!=SCHEMA_IN:return emit(req if isinstance(req,dict) else {},'BLOCKED','INPUT_SCHEMA_INVALID',code=2)
 t=req.get('task') or {};caps=set(str(x) for x in t.get('capabilities') or [])
 if t.get('permission')!='read':return emit(req,'BLOCKED','CONTEXT7_READ_PERMISSION_REQUIRED',code=2)
 if 'library-docs' not in caps:return emit(req,'BLOCKED','CONTEXT7_CAPABILITY_UNSUPPORTED',code=2)
 if not any(isinstance(x,dict) and x.get('provider')==PROVIDER and x.get('adapter')==ADAPTER for x in req.get('bindings') or []):return emit(req,'BLOCKED','CONTEXT7_BINDING_MISSING',code=2)
 try:x,raw=rpc('tools/list',{},2)
 except Exception as e:return emit(req,'FAILED','CONTEXT7_TOOLS_LIST_FAILED',[{'kind':'url','source':URL,'digest':digest(type(e).__name__.encode()),'details':{'error_class':type(e).__name__}}],1)
 tools=((x.get('result') or {}).get('tools') or []) if isinstance(x,dict) else []
 names=sorted(str(i.get('name')) for i in tools if isinstance(i,dict) and i.get('name'))
 required={'resolve-library-id','query-docs'}
 ok=required.issubset(set(names))
 source_path,source_digest=materialize(req,'context7-tools-list',raw)
 ev=[{'kind':'url-snapshot','source':source_path,'digest':source_digest,'details':{'origin':URL,'tool_names':names,'read_only_probe':True,'credentials_sent':False,'materialized_local_evidence':True}}]
 return emit(req,'OK' if ok else 'FAILED','CONTEXT7_MCP_READY' if ok else 'CONTEXT7_REQUIRED_TOOLS_MISSING',ev,0 if ok else 1)
if __name__=='__main__':raise SystemExit(main())
