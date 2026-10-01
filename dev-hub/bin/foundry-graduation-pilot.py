#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,subprocess,tempfile
from pathlib import Path

def pilot(gate:Path,policy:Path,change:Path,evidence:list[Path])->dict:
 td=Path(tempfile.mkdtemp(prefix='chacha-foundry-graduation-pilot-'));out=td/'gate.json';cmd=['python3',str(gate),'--policy',str(policy),'--change-set',str(change),'--output',str(out)]
 for p in evidence:cmd.extend(['--evidence',str(p)])
 cp=subprocess.run(cmd,capture_output=True,text=True);x=json.load(open(out)) if out.exists() else {}
 ok=cp.returncode==0 and x.get('status')=='PILOT_READY' and x.get('pilot_execution_authorized') is False and x.get('promotion_authorized') is False
 return {'schema':'chacha.dev/foundry-graduation-pilot/v1','status':'PASS' if ok else 'BLOCK','gate_status':x.get('status'),'candidate_revision':x.get('candidate_revision'),'pilot_execution_performed':False,'promotion_performed':False,'production_mutation':False,'automatic_external_spend_eur':0}

def main()->int:
 ap=argparse.ArgumentParser();ap.add_argument('--gate',type=Path,required=True);ap.add_argument('--policy',type=Path,required=True);ap.add_argument('--change-set',type=Path,required=True);ap.add_argument('--evidence',type=Path,action='append',default=[]);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args();o=pilot(a.gate,a.policy,a.change_set,a.evidence);a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(o,indent=2,sort_keys=True)+'\n');print('CHACHA_DEV_FOUNDRY_GRADUATION_PILOT='+o['status']);print('PROMOTION_PERFORMED=NO');return 0 if o['status']=='PASS' else 20
if __name__=='__main__':raise SystemExit(main())
