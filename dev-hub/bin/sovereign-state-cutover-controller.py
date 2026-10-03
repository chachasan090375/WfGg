#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,os,shutil,sqlite3,subprocess,time,urllib.request
from pathlib import Path
SERVICES={'guardian':8871,'sentinel':8872,'assurance-exchange':8873,'learning-relay':8874}
UNITS={k:'chacha-dev-sovereign-'+k+'.service' for k in SERVICES}
ROOT=Path('/opt/chacha-dev/runtime/sovereign-state')
AUTH=ROOT/'authority.json'
STOP=Path('/opt/chacha-dev/runtime/control/emergency-stop.json')

def load(p:Path):return json.loads(p.read_text())
def save_atomic(p:Path,x):
 p.parent.mkdir(parents=True,exist_ok=True);t=p.with_suffix(p.suffix+'.tmp');t.write_text(json.dumps(x,indent=2)+'\n');os.replace(t,p)
def run(*cmd):
 p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=30)
 if p.returncode:raise RuntimeError('COMMAND_FAILED:'+cmd[0]+':'+p.stderr[-300:])
 return p.stdout
def integrity(p:Path):
 c=sqlite3.connect('file:'+str(p)+'?mode=ro',uri=True);x=c.execute('pragma integrity_check').fetchone();c.close();return bool(x and str(x[0]).lower()=='ok')
def backup(src:Path,dst:Path):
 dst.parent.mkdir(parents=True,exist_ok=True);tmp=dst.with_suffix('.new');tmp.unlink(missing_ok=True)
 s=sqlite3.connect('file:'+str(src)+'?mode=ro',uri=True);d=sqlite3.connect(tmp)
 try:s.backup(d);d.commit()
 finally:d.close();s.close()
 if not integrity(tmp):raise RuntimeError('PRIMARY_SQLITE_INTEGRITY_FAILED:'+dst.name)
 os.replace(tmp,dst)
def health(name,port):
 with urllib.request.urlopen(f'http://127.0.0.1:{port}/__sovereign/healthz',timeout=4) as r:x=json.loads(r.read())
 if r.status!=200 or x.get('status')!='ok' or x.get('state_backend')!='SQLITE_LOCAL':raise RuntimeError('LOCAL_HEALTH_FAILED:'+name)
 return x
def approval_ok(p:Path,revision:str):
 x=load(p)
 return x.get('schema')=='chacha.dev/sovereign-state-human-cutover-approval/v1' and x.get('status')=='APPROVED' and x.get('revision')==revision and x.get('scope')=='LOCAL_SQLITE_PRIMARY'
def current_rev():
 p=Path('/opt/chacha-dev/platform/current/.revision');return p.read_text().strip() if p.is_file() else ''
def stop_clear():
 try:return load(STOP).get('active') is False
 except:return False
def install_units(repo:Path):
 for unit in UNITS.values():shutil.copy2(repo/'dev-hub/systemd'/unit,Path('/etc/systemd/system')/unit)
 run('/usr/bin/systemctl','daemon-reload')
def start_units():
 for unit in UNITS.values():run('/usr/bin/systemctl','enable','--now',unit)
def stop_units():
 for unit in UNITS.values():subprocess.run(['/usr/bin/systemctl','disable','--now',unit],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
def main():
 ap=argparse.ArgumentParser();ap.add_argument('mode',choices=['dry-run','activate','rollback']);ap.add_argument('--repo-root',type=Path,required=True);ap.add_argument('--revision',required=True);ap.add_argument('--approval',type=Path);ap.add_argument('--candidate-root',type=Path,default=ROOT/'candidate');ap.add_argument('--receipt',type=Path,required=True);a=ap.parse_args()
 checks={'revision_current':current_rev()==a.revision,'stop_clear':stop_clear(),'approval':bool(a.approval and a.approval.is_file() and approval_ok(a.approval,a.revision))}
 for name in SERVICES:checks['candidate_'+name]=integrity(a.candidate_root/name/'state.db')
 if a.mode=='dry-run':
  out={'schema':'chacha.dev/sovereign-state-cutover-controller/v1','status':'READY' if all(v for k,v in checks.items() if k!='approval') else 'HOLD','mode':'DRY_RUN','checks':checks,'production_mutation':False,'authority_change':False,'automatic_external_spend_eur':0};save_atomic(a.receipt,out);print(json.dumps(out));return 0 if out['status']=='READY' else 20
 if not all(checks.values()):raise SystemExit('SOVEREIGN_CUTOVER_BLOCKED:'+json.dumps(checks,sort_keys=True))
 if a.mode=='rollback':
  save_atomic(AUTH,load(a.repo_root/'dev-hub/config/sovereign-state-authority.remote.v1.json'));stop_units();out={'schema':'chacha.dev/sovereign-state-cutover-controller/v1','status':'ROLLED_BACK','mode':'D1_REMOTE','checks':checks,'automatic_external_spend_eur':0};save_atomic(a.receipt,out);print(json.dumps(out));return 0
 try:
  for name in SERVICES:backup(a.candidate_root/name/'state.db',ROOT/'primary'/(name+'.db'))
  install_units(a.repo_root);start_units();hs={name:health(name,port) for name,port in SERVICES.items()}
  save_atomic(AUTH,load(a.repo_root/'dev-hub/config/sovereign-state-authority.local.v1.json'))
  # Consumers are release-bound. Restart the pull timer/service only after authority switch.
  subprocess.run(['/usr/bin/systemctl','restart','chacha-dev-central-learning-relay-pull.timer'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
  out={'schema':'chacha.dev/sovereign-state-cutover-controller/v1','status':'ACTIVE','mode':'LOCAL_SQLITE','checks':checks,'health':hs,'rollback':'D1_REMOTE','automatic_external_spend_eur':0};save_atomic(a.receipt,out);print(json.dumps(out));return 0
 except Exception as e:
  save_atomic(AUTH,load(a.repo_root/'dev-hub/config/sovereign-state-authority.remote.v1.json'));stop_units();save_atomic(a.receipt,{'schema':'chacha.dev/sovereign-state-cutover-controller/v1','status':'ROLLED_BACK_ON_FAILURE','reason':str(e),'automatic_external_spend_eur':0});raise
if __name__=='__main__':raise SystemExit(main())
