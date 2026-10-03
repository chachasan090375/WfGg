#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,os,shutil,sqlite3,time
from pathlib import Path

def load(p):return json.loads(Path(p).read_text())
def sha(p):return 'sha256:'+hashlib.sha256(Path(p).read_bytes()).hexdigest()
def atomic_link(target:Path,link:Path):
 tmp=link.with_name(link.name+'.tmp-'+str(os.getpid()));
 try:tmp.unlink()
 except FileNotFoundError:pass
 tmp.symlink_to(target);os.replace(tmp,link)
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--repo-root',type=Path,required=True);ap.add_argument('--candidate-root',type=Path,required=True);ap.add_argument('--policy',type=Path,required=True);ap.add_argument('--revision',required=True);ap.add_argument('--runtime-root',type=Path);ap.add_argument('--apply',action='store_true');ap.add_argument('--output',type=Path,required=True);a=ap.parse_args();pol=load(a.policy);root=a.runtime_root or Path(pol['runtime_root'])
 if len(a.revision)!=40:raise SystemExit('EXACT_REVISION_REQUIRED')
 if (a.repo_root/'.git').exists() or (a.repo_root/'.git').is_file():
  import subprocess;head=subprocess.check_output(['git','-C',str(a.repo_root),'rev-parse','HEAD'],text=True).strip()
  if head!=a.revision:raise SystemExit('SOURCE_REVISION_MISMATCH')
 checks=[]
 for svc in pol['services']:
  w=a.repo_root/svc['worker'];db=a.candidate_root/svc['db_rel'];checks.append({'service':svc['id'],'worker_exists':w.is_file(),'db_exists':db.is_file(),'db_sha256':sha(db) if db.is_file() else None})
 if not all(x['worker_exists'] and x['db_exists'] for x in checks):raise SystemExit('STAGE_INPUT_MISSING')
 release=root/'releases'/a.revision
 status='DRY_RUN'
 if a.apply:
  if release.exists():shutil.rmtree(release)
  (release/'bin').mkdir(parents=True);(release/'lib').mkdir();(release/'workers').mkdir();(release/'state').mkdir()
  shutil.copy2(a.repo_root/'dev-hub/bin/d1-worker-local-runtime.mjs',release/'bin/d1-worker-local-runtime.mjs')
  shutil.copy2(a.repo_root/'dev-hub/lib/d1-sqlite-binding.mjs',release/'lib/d1-sqlite-binding.mjs')
  for svc in pol['services']:
   shutil.copy2(a.repo_root/svc['worker'],release/'workers'/(svc['id']+'.js'))
   shutil.copy2(a.candidate_root/svc['db_rel'],release/'state'/(svc['id']+'.db'))
   d=sqlite3.connect('file:'+str(release/'state'/(svc['id']+'.db'))+'?mode=ro',uri=True);chk=d.execute('pragma integrity_check').fetchone()[0];d.close()
   if str(chk).lower()!='ok':raise RuntimeError('STAGED_DB_INTEGRITY_FAILED:'+svc['id'])
  (release/'.revision').write_text(a.revision+'\n');atomic_link(release,root/'current');status='STAGED'
 out={'schema':'chacha.dev/sovereign-state-stage-runtime/v1','status':status,'revision':a.revision,'runtime_root':str(root),'release':str(release),'checks':checks,'authority_switched':False,'production_mutation':False,'automatic_external_spend_eur':0,'observed_at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())};a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(out,indent=2)+'\n');print('CHACHA_DEV_SOVEREIGN_STATE_STAGE='+status);print('AUTHORITY_SWITCHED=NO')
if __name__=='__main__':raise SystemExit(main())
