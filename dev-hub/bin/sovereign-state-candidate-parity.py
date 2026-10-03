#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,sqlite3,time
from pathlib import Path
MAP={
 'guardian':('guardian.db','guardian/state.db'),
 'sentinel':('sentinel.db','sentinel/state.db'),
 'assurance-exchange':('assurance_exchange.db','assurance-exchange/state.db'),
 'learning-relay':('learning_relay.db','learning-relay/state.db')}
def digest(p):return 'sha256:'+hashlib.sha256(p.read_bytes()).hexdigest()
def view(p):
 db=sqlite3.connect('file:'+str(p)+'?mode=ro',uri=True);chk=db.execute('pragma integrity_check').fetchone()[0];tables={}
 for (t,) in db.execute("select name from sqlite_master where type='table' and name not like 'sqlite_%' order by name"):
  cols=[r[1] for r in db.execute(f'pragma table_info("{t}")')];rows=[dict(zip(cols,r)) for r in db.execute(f'select * from "{t}"')];rows.sort(key=lambda x:json.dumps(x,sort_keys=True,separators=(',',':'),default=str));raw=json.dumps(rows,sort_keys=True,separators=(',',':'),default=str).encode();tables[t]={'count':len(rows),'sha256':'sha256:'+hashlib.sha256(raw).hexdigest()}
 db.close();return {'integrity':chk,'file_sha256':digest(p),'tables':tables}
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--import-dir',type=Path,required=True);ap.add_argument('--candidate-root',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args();rows={};ok=True
 for s,(imp,can) in MAP.items():
  ip=a.import_dir/imp;cp=a.candidate_root/can
  if not ip.is_file() or not cp.is_file():rows[s]={'status':'MISSING'};ok=False;continue
  iv,cv=view(ip),view(cp);same=iv==cv;ok &= same;rows[s]={'status':'PASS' if same else 'MISMATCH','imported':iv,'candidate':cv}
 out={'schema':'chacha.dev/sovereign-state-candidate-parity/v1','status':'PASS' if ok else 'MISMATCH','services':rows,'production_cutover_authorized':False,'automatic_external_spend_eur':0,'observed_at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())};a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(out,indent=2)+'\n');print('CHACHA_DEV_SOVEREIGN_CANDIDATE_PARITY='+out['status']);print('PRODUCTION_CUTOVER_AUTHORIZED=NO');return 0 if ok else 20
if __name__=='__main__':raise SystemExit(main())
