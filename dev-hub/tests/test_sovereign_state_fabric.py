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
 x=json.loads(receipt.read_text());assert x['status']=='PASS' and x['active_identity_count']==1 and x['role_contract_count']>=60 and x['table_count']>=19
 c=sqlite3.connect(db);assert c.execute('pragma journal_mode').fetchone()[0].lower()=='wal';c.close()
 subprocess.run([sys.executable,str(ROOT/'dev-hub/bin/sovereign-state-parity.py'),'--left',str(db),'--right',str(db)],check=True,stdout=subprocess.PIPE)
print('CHACHA_DEV_SOVEREIGN_STATE_FABRIC=PASS')
print('PRODUCTION_ACTIVATION=NO')
print('AUTOMATIC_EXTERNAL_SPEND_EUR=0')
M=json.loads((ROOT/'dev-hub/config/master-roadmap.v1.json').read_text())
assert M['priority_interrupt']['id']=='sovereign-state-d1-independence'
assert M['priority_interrupt']['resume_master_roadmap_after']=='SOVEREIGN_STATE_LOCAL_PRIMARY_HUMAN_CUTOVER_AND_STABILITY_PROOF'
w={x['id']:x for x in M['workstreams']}
assert w['sovereign-state-fabric']['state']=='CUTOVER_GATE_READY_PENDING_EXACT_SHA_QUALIFICATION_AND_HUMAN_APPROVAL'

SM=json.loads((ROOT/'dev-hub/config/sovereign-state-service-matrix.v1.json').read_text())
assert SM['state']=='SHADOW_ONLY' and SM['all_bind_loopback'] is True and SM['production_authority'] is False
assert [x['id'] for x in SM['services']]==['guardian','sentinel','assurance-exchange','learning-relay']
assert len({x['local_port'] for x in SM['services']})==4

assert M['priority_interrupt']['state']=='CUTOVER_TECHNICALLY_READY_PENDING_EXACT_SHA_QUALIFICATION_AND_HUMAN_APPROVAL'
