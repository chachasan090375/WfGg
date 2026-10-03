#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,sqlite3,time
from pathlib import Path
SERVICES={
 'guardian':('/opt/chacha-dev/runtime/sovereign-state/shadow/guardian.db','guardian.db'),
 'sentinel':('/opt/chacha-dev/runtime/sovereign-state/shadow/sentinel/state.db','sentinel.db'),
 'assurance-exchange':('/opt/chacha-dev/runtime/sovereign-state/shadow/assurance-exchange/state.db','assurance_exchange.db'),
 'learning-relay':('/opt/chacha-dev/runtime/sovereign-state/shadow/learning-relay/state.db','learning_relay.db')}
def stable(v):return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False,default=str)
def dbview(p):
 db=sqlite3.connect('file:'+str(p)+'?mode=ro',uri=True);tables=[r[0] for r in db.execute("select name from sqlite_master where type='table' and name not like 'sqlite_%' and name not like '_sovereign_%' order by name")];out={}
 for t in tables:
  cols=[r[1] for r in db.execute(f'pragma table_info("{t}")')];rows=[dict(zip(cols,r)) for r in db.execute(f'select * from "{t}"')];rows.sort(key=stable);raw=stable(rows).encode();out[t]={'count':len(rows),'digest':'sha256:'+hashlib.sha256(raw).hexdigest()}
 db.close();return out
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--import-dir',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args();rows={};ok=True
 for service,(local,impname) in SERVICES.items():
  lp=Path(local);rp=a.import_dir/impname
  if not lp.is_file() or not rp.is_file(): rows[service]={'status':'MISSING','local':str(lp),'imported':str(rp)};ok=False;continue
  l,r=dbview(lp),dbview(rp);names=sorted(set(l)|set(r));diff={t:{'local':l.get(t),'imported':r.get(t),'same':l.get(t)==r.get(t)} for t in names};same=all(x['same'] for x in diff.values());ok &= same;rows[service]={'status':'PASS' if same else 'MISMATCH','tables':diff}
 out={'schema':'chacha.dev/sovereign-state-multi-service-parity/v1','status':'PASS' if ok else 'MISMATCH','services':rows,'production_cutover_authorized':False,'automatic_external_spend_eur':0,'observed_at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())};a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(out,indent=2)+'\n');print('CHACHA_DEV_SOVEREIGN_MULTI_SERVICE_PARITY='+out['status']);print('PRODUCTION_CUTOVER_AUTHORIZED=NO');return 0 if ok else 20
if __name__=='__main__':raise SystemExit(main())
