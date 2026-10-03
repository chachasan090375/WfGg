#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,sqlite3,time
from pathlib import Path
SERVICES={
 'guardian':{'export':'chacha-dev-guardian.sql','required':{'guardian_identities','role_contracts','governance_events','guardian_alerts','action_leases','expected_components','coverage_heartbeats','dynamic_role_contracts','dynamic_component_contracts','task_contract_leases','remediation_directives','remediation_holds','project_functional_contracts','functional_acceptance_receipts','project_functional_events','project_assurance_identities','final_agent_reviews','action_lease_reconciliations'}},
 'sentinel':{'export':'chacha-dev-sentinel.sql','required':{'sentinel_identities','technical_release_receipts','sentinel_directives','project_assurance_identities','project_technical_events','final_agent_reviews','technical_workflow_attestations'}},
 'assurance-exchange':{'export':'chacha-dev-assurance-exchange.sql','required':{'exchange_identities','assurance_observations','assurance_correlations','peripheral_project_events','project_assurance_identities','specialist_review_refs','final_review_refs'}},
 'learning-relay':{'export':'chacha-dev-learning-relay.sql','required':{'identities','learning_deltas'}}
}
def digest(p):return 'sha256:'+hashlib.sha256(p.read_bytes()).hexdigest()
def one(service,src,dst):
 if dst.exists():dst.unlink()
 db=sqlite3.connect(dst);db.executescript(src.read_text(encoding='utf-8'));db.commit();chk=db.execute('pragma integrity_check').fetchone();tables={r[0] for r in db.execute("select name from sqlite_master where type='table'")};req=SERVICES[service]['required'];missing=sorted(req-tables);counts={t:db.execute(f'select count(*) from "{t}"').fetchone()[0] for t in sorted(req&tables)};db.close();status='PASS' if chk and str(chk[0]).lower()=='ok' and not missing else 'BLOCK';return {'status':status,'source':str(src),'source_sha256':digest(src),'db':str(dst),'db_sha256':digest(dst),'missing_required_tables':missing,'row_counts':counts,'sqlite_integrity':chk[0] if chk else None}
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--export-dir',type=Path,required=True);ap.add_argument('--output-dir',type=Path,required=True);ap.add_argument('--receipt',type=Path,required=True);a=ap.parse_args();a.output_dir.mkdir(parents=True,exist_ok=True);rows={};ok=True
 for service,cfg in SERVICES.items():
  src=a.export_dir/cfg['export'];dst=a.output_dir/(service.replace('-','_')+'.db')
  if not src.is_file():rows[service]={'status':'MISSING','source':str(src)};ok=False;continue
  rows[service]=one(service,src,dst);ok &= rows[service]['status']=='PASS'
 out={'schema':'chacha.dev/sovereign-state-multi-service-import/v1','status':'PASS' if ok else 'BLOCK','services':rows,'production_cutover_authorized':False,'automatic_external_spend_eur':0,'observed_at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())};a.receipt.parent.mkdir(parents=True,exist_ok=True);a.receipt.write_text(json.dumps(out,indent=2)+'\n');print('CHACHA_DEV_SOVEREIGN_MULTI_SERVICE_IMPORT='+out['status']);print('PRODUCTION_CUTOVER_AUTHORIZED=NO');return 0 if ok else 20
if __name__=='__main__':raise SystemExit(main())
