#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, sqlite3
from pathlib import Path
CRITICAL=['guardian_identities','role_contracts','dynamic_role_contracts','dynamic_component_contracts','action_leases','task_contract_leases','remediation_directives','remediation_holds','guardian_alerts','project_functional_contracts','functional_acceptance_receipts','project_assurance_identities','final_agent_reviews','expected_components','coverage_heartbeats']
def stable(v):return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False,default=str)
def table_digest(db:sqlite3.Connection,t:str):
 cols=[r[1] for r in db.execute(f'PRAGMA table_info("{t}")')]
 if not cols:return {'present':False,'count':0,'digest':None}
 rows=[dict(zip(cols,r)) for r in db.execute(f'SELECT * FROM "{t}"')]
 rows.sort(key=stable); raw=stable(rows).encode();return {'present':True,'count':len(rows),'digest':'sha256:'+hashlib.sha256(raw).hexdigest()}
def compare(a:Path,b:Path):
 da=sqlite3.connect(f'file:{a}?mode=ro',uri=True);db=sqlite3.connect(f'file:{b}?mode=ro',uri=True)
 out={};ok=True
 for t in CRITICAL:
  x,y=table_digest(da,t),table_digest(db,t);same=x==y;ok&=same;out[t]={'left':x,'right':y,'same':same}
 da.close();db.close();return ok,out
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--left',type=Path,required=True);ap.add_argument('--right',type=Path,required=True);ap.add_argument('--output',type=Path);a=ap.parse_args();ok,tables=compare(a.left,a.right)
 out={'schema':'chacha.dev/sovereign-state-parity/v1','status':'PASS' if ok else 'MISMATCH','critical_tables':tables,'production_cutover_authorized':False,'automatic_external_spend_eur':0}
 if a.output:a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(out,indent=2)+'\n')
 print('CHACHA_DEV_SOVEREIGN_STATE_PARITY='+out['status']);print('PRODUCTION_CUTOVER_AUTHORIZED=NO');return 0 if ok else 20
if __name__=='__main__':raise SystemExit(main())
