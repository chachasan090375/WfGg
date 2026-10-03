#!/usr/bin/env python3
from __future__ import annotations
import argparse,datetime,json,subprocess,tempfile
from pathlib import Path

def run(cmd:list[str])->tuple[int,str,str]:
 p=subprocess.run(cmd,capture_output=True,text=True);return p.returncode,p.stdout,p.stderr

def pilot(router:Path,router_policy:Path,recovery:Path,recovery_policy:Path)->dict:
 td=Path(tempfile.mkdtemp(prefix='chacha-safe-remediation-pilot-'));incident=td/'incident.json';route=td/'route.json';state=td/'progress.json';recovery_out=td/'recovery.json'
 incident.write_text(json.dumps({'code':'PROGRESS_TERMINAL_STALE','severity':'BLOCK','destructive':False,'production_mutation':False,'automatic_external_spend_eur':0}))
 old=(datetime.datetime.now(datetime.timezone.utc)-datetime.timedelta(seconds=600)).isoformat().replace('+00:00','Z')
 state.write_text(json.dumps({'schema':'chacha.dev/platform-progress/v1','status':'ERROR','platform_maturity_percent':90,'active_work_percent':33,'headline':'pilot','active_operation':'pilot-op','modules':{},'updated_at':old}))
 rc,_,err=run(['python3',str(router),'--policy',str(router_policy),'--incident',str(incident),'--output',str(route)]);r=json.load(open(route)) if route.exists() else {}
 if rc or r.get('status')!='AUTO_ELIGIBLE':return {'schema':'chacha.dev/incident-safe-remediation-pilot/v1','status':'BLOCK','reason':'ROUTER_NOT_AUTO_ELIGIBLE','stderr':err[-200:]}
 rc,_,err=run(['python3',str(recovery),'--policy',str(recovery_policy),'--state',str(state),'--output',str(recovery_out),'--apply']);x=json.load(open(recovery_out)) if recovery_out.exists() else {};after=json.load(open(state))
 ok=rc==0 and x.get('applied') is True and after.get('status')=='IDLE' and after.get('platform_maturity_percent')==90
 return {'schema':'chacha.dev/incident-safe-remediation-pilot/v1','status':'PASS' if ok else 'BLOCK','safe_auto_remediation_proved':ok,'production_mutation':False,'destructive_operation':False,'automatic_external_spend_eur':0}

def main()->int:
 ap=argparse.ArgumentParser();ap.add_argument('--router',type=Path,required=True);ap.add_argument('--router-policy',type=Path,required=True);ap.add_argument('--recovery',type=Path,required=True);ap.add_argument('--recovery-policy',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
 out=pilot(a.router,a.router_policy,a.recovery,a.recovery_policy);a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(out,indent=2,sort_keys=True)+'\n');print('CHACHA_DEV_INCIDENT_SAFE_REMEDIATION_PILOT='+out['status']);print('PRODUCTION_MUTATION=NO');return 0 if out['status']=='PASS' else 20
if __name__=='__main__':raise SystemExit(main())
