#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,shutil,subprocess,time,urllib.request
from pathlib import Path

def load(p):return json.loads(Path(p).read_text())
def run(argv):
 p=subprocess.run(argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=30)
 if p.returncode:raise RuntimeError('COMMAND_FAILED:'+repr(argv)+':'+(p.stderr or p.stdout)[-500:])
 return p.stdout
def healthy(port):
 try:
  with urllib.request.urlopen(f'http://127.0.0.1:{port}/__sovereign/healthz',timeout=4) as r:return r.status==200 and json.loads(r.read()).get('status')=='ok'
 except Exception:return False
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--policy',type=Path,required=True);ap.add_argument('--stage-receipt',type=Path,required=True);ap.add_argument('--unit-dir',type=Path,required=True);ap.add_argument('--apply',action='store_true');ap.add_argument('--output',type=Path,required=True);a=ap.parse_args();pol=load(a.policy);stage=load(a.stage_receipt);blockers=[]
 if stage.get('status')!='STAGED':blockers.append('LOCAL_RUNTIME_NOT_STAGED')
 units=[]
 for s in pol['services']:
  u=a.unit_dir/f"chacha-dev-sovereign-{s['id']}.service";units.append((s,u))
  if not u.is_file():blockers.append('UNIT_MISSING:'+s['id'])
 status='DRY_RUN_READY' if not blockers else 'HOLD';started=[]
 if a.apply and not blockers:
  try:
   for s,u in units:shutil.copy2(u,Path('/etc/systemd/system')/u.name)
   run(['/usr/bin/systemctl','daemon-reload'])
   for s,u in units:
    run(['/usr/bin/systemctl','enable','--now',u.name]);started.append(u.name)
   bad=[s['id'] for s,_ in units if not healthy(s['port'])]
   if bad:raise RuntimeError('LOCAL_SERVICE_HEALTH_FAILED:'+','.join(bad))
   status='LOCAL_SERVICES_READY'
  except Exception:
   for n in reversed(started):subprocess.run(['/usr/bin/systemctl','disable','--now',n],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
   raise
 out={'schema':'chacha.dev/sovereign-state-local-services/v1','status':status,'blockers':blockers,'service_count':len(units),'services':[{'id':s['id'],'port':s['port'],'unit':u.name,'health':healthy(s['port']) if a.apply and not blockers else None} for s,u in units],'authority_switched':False,'production_traffic_redirected':False,'automatic_external_spend_eur':0,'observed_at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())};a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(out,indent=2)+'\n');print('CHACHA_DEV_SOVEREIGN_LOCAL_SERVICES='+status);print('AUTHORITY_SWITCHED=NO');return 0 if status in {'DRY_RUN_READY','LOCAL_SERVICES_READY'} else 20
if __name__=='__main__':raise SystemExit(main())
