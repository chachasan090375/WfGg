#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,os,time,urllib.request
from pathlib import Path

def load(p):return json.loads(Path(p).read_text())
def atomic_json(p:Path,x):
 p.parent.mkdir(parents=True,exist_ok=True);tmp=p.with_name(p.name+'.tmp-'+str(os.getpid()));tmp.write_text(json.dumps(x,indent=2)+'\n');os.replace(tmp,p)
def health(url):
 try:
  with urllib.request.urlopen(url,timeout=5) as r:return r.status==200 and json.loads(r.read()).get('status')=='ok'
 except Exception:return False
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--policy',type=Path,required=True);ap.add_argument('--stage-receipt',type=Path,required=True);ap.add_argument('--services-receipt',type=Path,required=True);ap.add_argument('--export-convergence',type=Path,required=True);ap.add_argument('--cutover-gate',type=Path,required=True);ap.add_argument('--authority-local',type=Path,required=True);ap.add_argument('--approval-id');ap.add_argument('--apply',action='store_true');ap.add_argument('--output',type=Path,required=True);a=ap.parse_args();p=load(a.policy);stage=load(a.stage_receipt);services=load(a.services_receipt);conv=load(a.export_convergence);gate=load(a.cutover_gate);auth=load(a.authority_local)
 blockers=[];bridge=''
 revfile=Path(p['platform_revision_file'])
 if revfile.is_file():bridge=revfile.read_text().strip()
 if bridge!=p['required_bridge_revision']:blockers.append('COMPAT_BRIDGE_NOT_ACTIVE')
 if stage.get('status')!='STAGED':blockers.append('LOCAL_RUNTIME_NOT_STAGED')
 if services.get('status')!='LOCAL_SERVICES_READY':blockers.append('LOCAL_SERVICES_NOT_READY')
 if conv.get('status')!='PASS':blockers.append('DOUBLE_EXPORT_CONVERGENCE_NOT_PASS')
 if gate.get('status')!='READY_FOR_HUMAN_CUTOVER_APPROVAL':blockers.append('CUTOVER_GATE_NOT_READY')
 for s in p['services']:
  if not health(f"http://127.0.0.1:{s['port']}/__sovereign/healthz"):blockers.append('LOCAL_HEALTH_NOT_PASS:'+s['id'])
 expected='sovereign-state-local-primary-cutover:'+stage.get('revision','')
 if a.apply and a.approval_id!=expected:blockers.append('EXACT_HUMAN_APPROVAL_ID_REQUIRED')
 status='READY_FOR_HUMAN_APPROVAL' if not blockers else 'HOLD'
 switched=False
 if a.apply and not blockers:
  atomic_json(Path(p['authority_file']),auth);switched=True;status='LOCAL_AUTHORITY_ACTIVE'
 out={'schema':'chacha.dev/sovereign-state-cutover/v1','status':status,'blockers':blockers,'bridge_revision':bridge,'required_bridge_revision':p['required_bridge_revision'],'candidate_revision':stage.get('revision'),'expected_approval_id':expected,'authority_switched':switched,'rollback_floor':p['rollback_floor'],'rollback_below_bridge_after_local_writes_forbidden':p['rollback_below_bridge_after_local_writes_forbidden'],'automatic_external_spend_eur':0,'observed_at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())};a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(out,indent=2)+'\n');print('CHACHA_DEV_SOVEREIGN_STATE_CUTOVER='+status);print('AUTHORITY_SWITCHED='+('YES' if switched else 'NO'));return 0 if status in {'READY_FOR_HUMAN_APPROVAL','LOCAL_AUTHORITY_ACTIVE'} else 20
if __name__=='__main__':raise SystemExit(main())
