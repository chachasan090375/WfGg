#!/usr/bin/env python3
from __future__ import annotations
import argparse,importlib.util,json,sqlite3,sys,time,urllib.request
from pathlib import Path

def load_client(path:Path):
 sys.path.insert(0,str(path.parent));s=importlib.util.spec_from_file_location('guardian_client_replay',path);m=importlib.util.module_from_spec(s);sys.modules[s.name]=m;s.loader.exec_module(m);return m

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--source-db',type=Path,required=True);ap.add_argument('--candidate-url',required=True);ap.add_argument('--private-key',type=Path,required=True);ap.add_argument('--guardian-client',type=Path,required=True);ap.add_argument('--pairs',type=int,default=12);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args();gc=load_client(a.guardian_client);db=sqlite3.connect('file:'+str(a.source_db)+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
 rows=db.execute("select event_id,phase,verdict,severity,contract_id,reason_codes_json,payload_json,received_at from governance_events where verdict='PASS' order by received_at desc limit 1000").fetchall();db.close();by={}
 for r in rows:
  try:p=json.loads(r['payload_json']);aid=p.get('action_id')
  except:continue
  if aid:by.setdefault(aid,{})[r['phase']]=r
 pairs=[(aid,x) for aid,x in by.items() if 'PRE_ACTION' in x and 'POST_ACTION' in x][:max(1,min(a.pairs,100))];results=[];stamp=int(time.time())
 for i,(aid,pair) in enumerate(pairs):
  rid=f'sovereign-historical-replay-{stamp}-{i}'
  for phase in ('PRE_ACTION','POST_ACTION'):
   orig=pair[phase];event=json.loads(orig['payload_json']);event['event_id']=rid+('-pre' if phase=='PRE_ACTION' else '-post');event['action_id']=rid;event['run_id']=rid;body=json.dumps(event,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode();req=gc.signed_request('POST',a.candidate_url.rstrip('/')+'/v1/check',a.private_key,body)
   with urllib.request.urlopen(req,timeout=15) as rr:got=json.loads(rr.read())
   exp={'verdict':orig['verdict'],'severity':orig['severity'],'contract_id':orig['contract_id'],'reason_codes':sorted(json.loads(orig['reason_codes_json']))};act={'verdict':got.get('verdict'),'severity':got.get('severity'),'contract_id':got.get('subject_contract_id'),'reason_codes':sorted(got.get('reason_codes') or [])};results.append({'source_event_id':orig['event_id'],'phase':phase,'expected':exp,'actual':act,'same':exp==act})
 ok=bool(results) and all(x['same'] for x in results);out={'schema':'chacha.dev/sovereign-guardian-historical-verdict-parity/v1','status':'PASS' if ok else 'MISMATCH','source':'AUTHORITATIVE_D1_EXPORT_HISTORICAL_VERDICTS','replayed_event_count':len(results),'action_pair_count':len(pairs),'results':results,'live_remote_write_performed':False,'production_mutation':False,'production_cutover_authorized':False,'automatic_external_spend_eur':0,'observed_at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())};a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(out,indent=2)+'\n');print('CHACHA_DEV_SOVEREIGN_GUARDIAN_HISTORICAL_VERDICT_PARITY='+out['status']);print('REPLAYED_EVENTS='+str(len(results)));print('LIVE_REMOTE_WRITE=NO');return 0 if ok else 20
if __name__=='__main__':raise SystemExit(main())
