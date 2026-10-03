#!/usr/bin/env python3
import json,sqlite3,subprocess,tempfile,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
CFG=json.loads((ROOT/'dev-hub/config/sovereign-state-fabric.v1.json').read_text())
BIRTH=json.loads((ROOT/'dev-hub/config/sovereign-state-fabric.birth.v1.json').read_text())
assert CFG['state']=='SHADOW_LOCAL'
assert CFG['rules']['reuse_same_guardian_worker_source'] is True
assert CFG['rules']['no_guardian_logic_fork'] is True
assert CFG['rules']['local_primary_survives_d1_quota_exhaustion'] is True
assert CFG['rules']['production_activation_authorized'] is False
assert BIRTH['materialization_gate_required'] is True and BIRTH['production_activation_authorized'] is False
with tempfile.TemporaryDirectory() as td:
 td=Path(td);db=td/'g.db';receipt=td/'r.json'
 subprocess.run([sys.executable,str(ROOT/'dev-hub/bin/sovereign-state-bootstrap.py'),'--db',str(db),'--migrations',str(ROOT/'dev-hub/guardian/migrations'),'--identity',str(ROOT/'dev-hub/config/worker-learning-central-identity.v1.json'),'--contracts',str(ROOT/'dev-hub/config/guardian-role-contracts.v1.json'),'--receipt',str(receipt)],check=True,stdout=subprocess.PIPE)
 x=json.loads(receipt.read_text())
 migrations=sorted(p.name for p in (ROOT/'dev-hub/guardian/migrations').glob('*.sql'))
 assert x['status']=='PASS' and x['active_identity_count']==1 and x['role_contract_count']>=60
 assert x['migrations_applied']==migrations,(x['migrations_applied'],migrations)
 c0=sqlite3.connect(db);tables={r[0] for r in c0.execute("select name from sqlite_master where type='table' and name not like 'sqlite_%'")};c0.close()
 required={'guardian_identities','role_contracts','governance_events','guardian_alerts','action_leases','expected_components','dynamic_role_contracts','dynamic_component_contracts','task_contract_leases','remediation_directives','functional_acceptance_receipts','project_assurance_identities','final_agent_reviews'}
 assert required<=tables,required-tables
 assert x['table_count']==len(tables),(x['table_count'],len(tables))
 c=sqlite3.connect(db);assert c.execute('pragma journal_mode').fetchone()[0].lower()=='wal';c.close()
 subprocess.run([sys.executable,str(ROOT/'dev-hub/bin/sovereign-state-parity.py'),'--left',str(db),'--right',str(db)],check=True,stdout=subprocess.PIPE)
print('CHACHA_DEV_SOVEREIGN_STATE_FABRIC=PASS')
print('PRODUCTION_ACTIVATION=NO')
print('AUTOMATIC_EXTERNAL_SPEND_EUR=0')
print('HOTFIX_BASELINE_AWARE=YES')
