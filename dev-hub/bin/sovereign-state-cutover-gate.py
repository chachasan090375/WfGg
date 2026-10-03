#!/usr/bin/env python3
from __future__ import annotations
import argparse,json
from pathlib import Path

def load(p:Path):return json.loads(p.read_text())
def main():
 ap=argparse.ArgumentParser();
 for n in ['bootstrap','local-pilot','nas-snapshot','d1-import','parity','dual-parity']:ap.add_argument('--'+n.replace('_','-'),type=Path)
 ap.add_argument('--output',type=Path,required=True);a=ap.parse_args();checks={};blockers=[]
 expected={'bootstrap':'PASS','local_pilot':'PASS','nas_snapshot':'PASS','d1_import':'PASS','parity':'PASS','dual_parity':'PASS'}
 for k,want in expected.items():
  p=getattr(a,k,None)
  if not p or not p.is_file(): checks[k]='MISSING';blockers.append(k.upper()+'_MISSING');continue
  x=load(p);status=str(x.get('status') or 'UNKNOWN');checks[k]=status
  if status!=want:blockers.append(k.upper()+'_NOT_PASS')
 status='READY_FOR_HUMAN_CUTOVER_APPROVAL' if not blockers else 'HOLD'
 out={'schema':'chacha.dev/sovereign-state-cutover-gate/v1','status':status,'checks':checks,'blockers':blockers,'cutover_performed':False,'production_mutation':False,'human_approval_required':True,'automatic_external_spend_eur':0}
 a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(out,indent=2)+'\n');print('CHACHA_DEV_SOVEREIGN_STATE_CUTOVER_GATE='+status);print('CUTOVER_PERFORMED=NO');return 0 if status.startswith('READY_') else 20
if __name__=='__main__':raise SystemExit(main())
