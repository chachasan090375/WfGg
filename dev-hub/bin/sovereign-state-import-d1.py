#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,sqlite3,tempfile,time
from pathlib import Path
REQUIRED={'guardian_identities','role_contracts','governance_events','guardian_alerts','action_leases','expected_components','coverage_heartbeats','dynamic_role_contracts','dynamic_component_contracts','task_contract_leases','remediation_directives','remediation_holds','project_functional_contracts','functional_acceptance_receipts','project_functional_events','project_assurance_identities','final_agent_reviews','action_lease_reconciliations'}
def sha(p:Path):return 'sha256:'+hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--sql-export',type=Path,required=True);ap.add_argument('--output-db',type=Path,required=True);ap.add_argument('--receipt',type=Path,required=True);a=ap.parse_args()
 text=a.sql_export.read_text(encoding='utf-8');a.output_db.parent.mkdir(parents=True,exist_ok=True)
 if a.output_db.exists():a.output_db.unlink()
 db=sqlite3.connect(a.output_db);db.executescript(text);db.commit();chk=db.execute('pragma integrity_check').fetchone();tables={r[0] for r in db.execute("select name from sqlite_master where type='table'")};missing=sorted(REQUIRED-tables);counts={t:db.execute(f'select count(*) from "{t}"').fetchone()[0] for t in sorted(REQUIRED & tables)};db.close()
 status='PASS' if chk and str(chk[0]).lower()=='ok' and not missing else 'BLOCK'
 out={'schema':'chacha.dev/sovereign-state-d1-import/v1','status':status,'source_export':str(a.sql_export),'source_sha256':sha(a.sql_export),'output_db':str(a.output_db),'output_sha256':sha(a.output_db),'missing_required_tables':missing,'row_counts':counts,'sqlite_integrity':str(chk[0]) if chk else None,'production_cutover_authorized':False,'automatic_external_spend_eur':0,'observed_at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())}
 a.receipt.parent.mkdir(parents=True,exist_ok=True);a.receipt.write_text(json.dumps(out,indent=2)+'\n');print('CHACHA_DEV_SOVEREIGN_D1_IMPORT='+status);print('PRODUCTION_CUTOVER_AUTHORIZED=NO');return 0 if status=='PASS' else 20
if __name__=='__main__':raise SystemExit(main())
