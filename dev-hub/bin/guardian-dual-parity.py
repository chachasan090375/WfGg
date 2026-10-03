#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys,urllib.request,urllib.error
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import guardian_client as gc
KEYS=('verdict','severity','reason_codes','actor_contract_id','subject_contract_id','remediation_required','remediation_applied','remediation_escalated','stop_recommended')
def request(url,key,event):
 body=json.dumps(event,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode();req=gc.signed_request('POST',url.rstrip('/')+'/v1/check',key,body)
 try:
  with urllib.request.urlopen(req,timeout=20) as r:return r.status,json.loads(r.read())
 except urllib.error.HTTPError as e:
  try:return e.code,json.loads(e.read())
  except Exception:return e.code,{'error':'unparseable'}
def norm(x):
 out={k:x.get(k) for k in KEYS};out['reason_codes']=sorted(out.get('reason_codes') or []);return out
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--left-url',required=True);ap.add_argument('--right-url',required=True);ap.add_argument('--private-key',type=Path,required=True);ap.add_argument('--event',type=Path,action='append',required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args();rows=[];ok=True
 for p in a.event:
  event=json.loads(p.read_text());ls,l=request(a.left_url,a.private_key,event);rs,r=request(a.right_url,a.private_key,event);same=ls==rs==200 and norm(l)==norm(r);ok&=same;rows.append({'event_id':event.get('event_id'),'left_status':ls,'right_status':rs,'left':norm(l),'right':norm(r),'same':same})
 out={'schema':'chacha.dev/guardian-dual-parity/v1','status':'PASS' if ok else 'MISMATCH','events':rows,'production_cutover_authorized':False,'automatic_external_spend_eur':0};a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(out,indent=2)+'\n');print('CHACHA_DEV_GUARDIAN_DUAL_PARITY='+out['status']);print('PRODUCTION_CUTOVER_AUTHORIZED=NO');return 0 if ok else 20
if __name__=='__main__':raise SystemExit(main())
