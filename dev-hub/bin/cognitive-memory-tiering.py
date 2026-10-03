from __future__ import annotations
import argparse, hashlib, json, os, sqlite3, subprocess, tempfile, time
from pathlib import Path
from typing import Any

DEFAULT_POLICY=Path('dev-hub/config/cognitive-memory-fabric.v1.json')
DEFAULT_PUBLISH=Path('/opt/chacha-dev/adapters/nas-ssh/current/nas-ssh-adapter')
DEFAULT_READBACK=Path('/opt/chacha-dev/platform/current/dev-hub/adapters/nas-readback-adapter.py')
ALLOWED_TRIGGERS={'INTERVAL','MISSION_ACCEPTED_COMPLETE','MEMORY_PROMOTED_TRUSTED','REUSABLE_ARCHITECTURE_CONSOLIDATED','AGENT_SPECIALIST_CORPUS_UPDATED'}

def now()->str:return time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
def sha(path:Path)->str:
 h=hashlib.sha256()
 with path.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return 'sha256:'+h.hexdigest()
def source_fingerprint(path:Path)->str:
 h=hashlib.sha256()
 for p in (path,Path(str(path)+'-wal')):
  if not p.is_file():continue
  h.update(p.name.encode());h.update(b'\0')
  with p.open('rb') as f:
   for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return 'sha256:'+h.hexdigest()
def load(path:Path)->dict[str,Any]:return json.loads(path.read_text())
def save(path:Path,obj:dict[str,Any])->None:
 path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_text(json.dumps(obj,indent=2,ensure_ascii=False)+'\n');os.replace(tmp,path)
def scan(policy:dict[str,Any],root:Path)->list[Path]:
 paths=list(root.rglob('*.db')) if root.exists() else []
 configured=Path(policy['persistence']['agent_store_root'])
 if root==configured:
  for raw in (policy.get('existing_sources') or {}).values():
   p=Path(str(raw))
   if p.suffix=='.db' and p.is_file():paths.append(p)
 return sorted({p.resolve() for p in paths if p.is_file()},key=str)
def plan(policy:dict[str,Any],trigger:str,root:Path,ledger:dict[str,Any])->dict[str,Any]:
 if trigger not in ALLOWED_TRIGGERS:raise ValueError('TRIGGER_NOT_ALLOWED')
 changed=[];observed={}
 for p in scan(policy,root):
  d=source_fingerprint(p);key=str(p);observed[key]=d
  if ledger.get('digests',{}).get(key)!=d:changed.append({'path':key,'digest':d,'bytes':p.stat().st_size})
 return {'schema':'chacha.dev/cognitive-memory-tiering-plan/v1','status':'PASS','trigger':trigger,'material_change':bool(changed),'changed':changed,'observed_digests':observed,
         'hot_purge_automatic':False,'hot_demote_automatic':False,'production_activation_authorized':bool(policy['tiering']['production_activation_authorized']),
         'automatic_external_spend_eur':0}
def envelope(task_id:str,permission:str,adapter:str,workspace:Path,meta:dict[str,Any])->dict[str,Any]:
 return {'schema':'chacha.dev/dispatch-envelope/v1','project':'chacha-dev','transition':'cognitive-memory-tiering-shadow','run_id':task_id,'wave':1,
 'task':{'id':task_id,'kind':'knowledge-event','description':'Cognitive memory tiering shadow operation.','owner_role':'knowledge-compiler-agent','permission':permission,
 'outputs':[{'type':'artifact','id':task_id}],'verification':{'required':True,'mode':'machine'}},
 'bindings':[{'capability':'backup-store','provider':'nas' if adapter=='nas-ssh-adapter' else 'nas-readback','adapter':adapter,'fallback_used':False,'health_state':'HEALTHY'}],
 'policy_context':{'resource_class':'light','requires_storage_preflight':False,'human_approval_required':False,'approval_id':None,'timeout_seconds':45},
 'workspace':str(workspace),'metadata':meta}
def run_adapter(exe:Path,req:dict[str,Any],accepted_summaries:set[str]|None=None)->dict[str,Any]:
 argv=[str(exe)] if os.access(exe,os.X_OK) else ['/usr/bin/python3',str(exe)]
 p=subprocess.run(argv,input=json.dumps(req).encode(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=60,check=False)
 if p.returncode!=0:
  detail=p.stdout.decode('utf-8','replace').strip() or p.stderr.decode('utf-8','replace').strip()
  raise RuntimeError('ADAPTER_FAILED:'+detail[:400])
 out=json.loads(p.stdout)
 if out.get('status')!='OK' and str(out.get('summary') or '') not in set(accepted_summaries or set()):raise RuntimeError('ADAPTER_NOT_OK:'+str(out.get('summary')))
 return out
def sqlite_snapshot(src:Path,dest:Path)->str:
 source=sqlite3.connect('file:'+str(src)+'?mode=ro',uri=True,timeout=10)
 target=sqlite3.connect(dest)
 try:source.backup(target);target.commit()
 finally:target.close();source.close()
 check=sqlite3.connect('file:'+str(dest)+'?mode=ro',uri=True).execute('PRAGMA integrity_check').fetchone()
 if not check or str(check[0]).lower()!='ok':raise RuntimeError('SQLITE_SNAPSHOT_INTEGRITY_FAILED')
 return sha(dest)
def verify_restored_sqlite(path:Path,expected:str)->None:
 if sha(path)!=expected:raise RuntimeError('READBACK_HASH_MISMATCH')
 db=sqlite3.connect('file:'+str(path)+'?mode=ro',uri=True);row=db.execute('PRAGMA integrity_check').fetchone();db.close()
 if not row or str(row[0]).lower()!='ok':raise RuntimeError('READBACK_SQLITE_INTEGRITY_FAILED')
def readback_probe(readback:Path,row:dict[str,Any])->dict[str,Any]:
 digest=str(row['snapshot_digest']);remote=str(row['remote']);name=Path(str(row.get('source') or 'memory.db')).name
 with tempfile.TemporaryDirectory(prefix='chacha-cmf-restore-probe-') as td:
  wd=Path(td);(wd/'restore').mkdir();dest='restore/'+name
  rb=envelope('cmf-probe-'+digest[-12:],'workspace-write','nas-readback-adapter',wd,{'nas_readback':{'action':'read-file','remote_path':remote,'local_path':dest,'expected_sha256':digest}})
  out=run_adapter(readback,rb);verify_restored_sqlite(wd/dest,digest)
 return {'status':'PASS','remote':remote,'snapshot_digest':digest,'readback':out.get('summary'),'workspace_disposed':True}
def shadow_execute(policy:dict[str,Any],plan_doc:dict[str,Any],ledger_path:Path,ledger:dict[str,Any],publish:Path,readback:Path)->dict[str,Any]:
 if policy['tiering']['production_activation_authorized']:raise RuntimeError('PRODUCTION_ACTIVATION_FORBIDDEN_IN_SHADOW_RUNNER')
 results=[];prefix=policy['tiering']['shadow_remote_prefix'].rstrip('/')
 for item in plan_doc['changed']:
  src=Path(item['path']);name=src.name
  with tempfile.TemporaryDirectory(prefix='chacha-cmf-tiering-') as td:
   wd=Path(td);local=wd/name;snapshot_digest=sqlite_snapshot(src,local)
   remote=f"{prefix}/{time.strftime('%Y%m%d',time.gmtime())}/{snapshot_digest.split(':',1)[1][:20]}-{name}"
   put=envelope('cmf-tier-'+snapshot_digest[-12:]+'-put','workspace-write','nas-ssh-adapter',wd,{'nas_storage':{'action':'put-file','local_path':name,'remote_path':remote,'reserve_mb':1024}})
   put_out=run_adapter(publish,put,{'NAS_DESTINATION_ALREADY_EXISTS'})
   (wd/'restore').mkdir();dest='restore/'+name
   rb=envelope('cmf-tier-'+snapshot_digest[-12:]+'-read','workspace-write','nas-readback-adapter',wd,{'nas_readback':{'action':'read-file','remote_path':remote,'local_path':dest,'expected_sha256':snapshot_digest}})
   rb_out=run_adapter(readback,rb);verify_restored_sqlite(wd/dest,snapshot_digest)
   results.append({'source':str(src),'source_fingerprint':item['digest'],'snapshot_digest':snapshot_digest,'remote':remote,'publish':put_out.get('summary'),'readback':rb_out.get('summary'),'sqlite_integrity':'OK'})
 cycle=int(ledger.get('cycle_count') or 0)+1
 archive_index=list(ledger.get('archive_index') or [])+results
 if len(archive_index)>256:archive_index=archive_index[-256:]
 probe_every=max(1,int(policy['tiering'].get('restore_probe_interval_cycles') or 8))
 probe={'status':'NOT_DUE','cycle':cycle,'interval_cycles':probe_every}
 if cycle%probe_every==0:
  probe=readback_probe(readback,archive_index[-1]) if archive_index else {'status':'SKIPPED_NO_ARCHIVE','cycle':cycle,'interval_cycles':probe_every}
 new_ledger={'schema':'chacha.dev/cognitive-memory-tiering-ledger/v1','updated_at':now(),'cycle_count':cycle,
             'digests':dict(plan_doc.get('observed_digests') or {}),'last_results':results,'archive_index':archive_index,'last_restore_probe':probe}
 save(ledger_path,new_ledger)
 return {'schema':'chacha.dev/cognitive-memory-tiering-result/v1','status':'PASS','trigger':plan_doc['trigger'],'cycle':cycle,'material_change':plan_doc['material_change'],'archived':len(results),'results':results,'restore_probe':probe,
         'hot_purge_performed':False,'hot_demote_performed':False,'automatic_external_spend_eur':0}

def main()->int:
 ap=argparse.ArgumentParser();ap.add_argument('--policy',type=Path,default=DEFAULT_POLICY);ap.add_argument('--trigger',default='INTERVAL');ap.add_argument('--agent-root',type=Path);ap.add_argument('--ledger',type=Path);ap.add_argument('--shadow-execute',action='store_true');ap.add_argument('--publish-adapter',type=Path,default=DEFAULT_PUBLISH);ap.add_argument('--readback-adapter',type=Path,default=DEFAULT_READBACK);a=ap.parse_args()
 policy=load(a.policy);root=(a.agent_root or Path(policy['persistence']['agent_store_root'])).resolve();ledger_path=a.ledger or Path(policy['tiering']['tiering_ledger']);ledger=load(ledger_path) if ledger_path.exists() else {'digests':{}}
 p=plan(policy,a.trigger,root,ledger)
 if not a.shadow_execute:print(json.dumps(p,ensure_ascii=False));return 0
 print(json.dumps(shadow_execute(policy,p,ledger_path,ledger,a.publish_adapter,a.readback_adapter),ensure_ascii=False));return 0
if __name__=='__main__':raise SystemExit(main())
