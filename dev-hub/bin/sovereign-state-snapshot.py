#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,os,sqlite3,subprocess,tempfile,time
from pathlib import Path

def sha(p:Path):
 h=hashlib.sha256();
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return 'sha256:'+h.hexdigest()
def snapshot(src:Path,dst:Path):
 dst.parent.mkdir(parents=True,exist_ok=True);s=sqlite3.connect('file:'+str(src)+'?mode=ro',uri=True,timeout=10);d=sqlite3.connect(dst)
 try:s.backup(d);d.commit()
 finally:d.close();s.close()
 c=sqlite3.connect('file:'+str(dst)+'?mode=ro',uri=True);r=c.execute('pragma integrity_check').fetchone();c.close()
 if not r or str(r[0]).lower()!='ok':raise RuntimeError('SQLITE_SNAPSHOT_INTEGRITY_FAILED')
 return sha(dst)
def envelope(task_id,adapter,workspace,meta):
 return {'schema':'chacha.dev/dispatch-envelope/v1','project':'chacha-dev','transition':'sovereign-state-shadow-backup','run_id':task_id,'wave':1,'task':{'id':task_id,'kind':'state-snapshot','description':'Sovereign State Fabric shadow backup.','owner_role':'knowledge-compiler-agent','permission':'workspace-write','outputs':[{'type':'artifact','id':task_id}],'verification':{'required':True,'mode':'machine'}},'bindings':[{'capability':'backup-store','provider':'nas' if adapter=='nas-ssh-adapter' else 'nas-readback','adapter':adapter,'fallback_used':False,'health_state':'HEALTHY'}],'policy_context':{'resource_class':'light','requires_storage_preflight':False,'human_approval_required':False,'approval_id':None,'timeout_seconds':60},'workspace':str(workspace),'metadata':meta}
def run(exe:Path,req,accept=set()):
 argv=[str(exe)] if os.access(exe,os.X_OK) else ['/usr/bin/python3',str(exe)];p=subprocess.run(argv,input=json.dumps(req).encode(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=60)
 if p.returncode:raise RuntimeError((p.stdout+p.stderr).decode(errors='replace')[-500:])
 x=json.loads(p.stdout);summary=str(x.get('summary') or '')
 if x.get('status')!='OK' and summary not in accept:raise RuntimeError('ADAPTER_NOT_OK:'+summary)
 return x
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--db',type=Path,required=True);ap.add_argument('--publish',type=Path,default=Path('/opt/chacha-dev/adapters/nas-ssh/current/nas-ssh-adapter'));ap.add_argument('--readback',type=Path,default=Path('/opt/chacha-dev/platform/current/dev-hub/adapters/nas-readback-adapter.py'));ap.add_argument('--remote-prefix',default='knowledge/sovereign-state-shadow');ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
 with tempfile.TemporaryDirectory(prefix='chacha-sovereign-state-') as td:
  w=Path(td);snap=w/'guardian.db';digest=snapshot(a.db,snap);remote=f"{a.remote_prefix.rstrip('/')}/{time.strftime('%Y%m%d',time.gmtime())}/{digest.split(':')[1][:24]}-guardian.db"
  put=run(a.publish,envelope('sovereign-put','nas-ssh-adapter',w,{'nas_storage':{'action':'put-file','local_path':'guardian.db','remote_path':remote,'reserve_mb':256}}),{'NAS_DESTINATION_ALREADY_EXISTS'})
  (w/'restore').mkdir();rb=run(a.readback,envelope('sovereign-read','nas-readback-adapter',w,{'nas_readback':{'action':'read-file','remote_path':remote,'local_path':'restore/guardian.db','expected_sha256':digest}}));rest=w/'restore/guardian.db'
  if sha(rest)!=digest:raise RuntimeError('READBACK_HASH_MISMATCH')
  c=sqlite3.connect('file:'+str(rest)+'?mode=ro',uri=True);chk=c.execute('pragma integrity_check').fetchone();c.close();
  if not chk or str(chk[0]).lower()!='ok':raise RuntimeError('READBACK_INTEGRITY_FAILED')
 out={'schema':'chacha.dev/sovereign-state-nas-snapshot/v1','status':'PASS','source':str(a.db),'snapshot_digest':digest,'remote':remote,'publish':put.get('summary'),'readback':rb.get('summary'),'sqlite_integrity':'OK','production_activation_authorized':False,'automatic_external_spend_eur':0}
 a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(out,indent=2)+'\n');print('CHACHA_DEV_SOVEREIGN_STATE_NAS_SNAPSHOT=PASS');print('PRODUCTION_ACTIVATION=NO')
if __name__=='__main__':raise SystemExit(main())
