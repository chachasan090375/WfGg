#!/usr/bin/env python3
from __future__ import annotations
import json,subprocess,tempfile,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];BIN=ROOT/'dev-hub/bin/creation-runtime-e2e-shadow.py'
def run(intent,req,targets):
 with tempfile.TemporaryDirectory(prefix='chacha-e2e-test-') as td:
  td=Path(td);out=td/'out.json';work=td/'work'
  cmd=[sys.executable,str(BIN),'--intent',str(ROOT/intent),'--infrastructure',str(ROOT/'dev-hub/evidence/infrastructure-feasibility-vps-observation-2026-10-03.json'),'--requirements',str(ROOT/req),'--resources',str(ROOT/'dev-hub/evidence/resource-host-pool-vps-observed-2026-10-03.json'),'--target-matrix',str(ROOT/targets),'--host-inventory',str(ROOT/'dev-hub/evidence/virtual-os-lab-host-inventory-observed-2026-10-03.json'),'--work-dir',str(work),'--output',str(out)]
  p=subprocess.run(cmd,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=60);assert p.returncode==0,(p.stdout,p.stderr);return json.loads(out.read_text()),[json.loads((work/f'{i:02d}-{name}.json').read_text()) for i,name in [(1,'feasibility'),(2,'composition'),(3,'recursive-specialization'),(4,'specialists'),(5,'execution-plan'),(6,'parallel-plan'),(7,'os-lab-plan')]]
def test_fit_project_reaches_shadow_plan_ready_and_parallel_modules():
 o,stages=run('dev-hub/fixtures/e2e-fit-api-backend-intent.v1.json','dev-hub/fixtures/e2e-fit-api-backend-requirements.v1.json','dev-hub/fixtures/e2e-fit-api-backend-targets.v1.json');assert o['status']=='SHADOW_PLAN_READY' and not o['blockers'];parallel=stages[5];assert any({x['task_id'] for x in w['assignments']}=={'implement:api','implement:backend'} for w in parallel['waves'])
def test_attached_artifact_survives_into_composition():
 o,stages=run('dev-hub/fixtures/e2e-fit-api-backend-intent.v1.json','dev-hub/fixtures/e2e-fit-api-backend-requirements.v1.json','dev-hub/fixtures/e2e-fit-api-backend-targets.v1.json');assert o['artifact_ref_count']==1;assert len(stages[1]['artifact_refs'])==1 and stages[1]['artifact_refs'][0]['execution_allowed'] is False
def test_non_fit_and_foundry_gaps_fail_closed():
 o,_=run('dev-hub/fixtures/solution-composer-mixed-request.v1.json','dev-hub/evidence/infrastructure-feasibility-reference-requirements-2026-10-03.json','dev-hub/fixtures/e2e-linux-only-targets.v1.json');assert o['status']=='BLOCKED';assert o['feasibility']=='NOT_FIT';assert o['foundry_gaps']==5;assert 'INFRASTRUCTURE_NOT_FIT' in o['blockers'] and 'FOUNDRY_GAPS_UNRESOLVED' in o['blockers']
def test_shadow_harness_never_executes_tasks_creates_vm_invokes_foundry_or_spends():
 o,_=run('dev-hub/fixtures/e2e-fit-api-backend-intent.v1.json','dev-hub/fixtures/e2e-fit-api-backend-requirements.v1.json','dev-hub/fixtures/e2e-fit-api-backend-targets.v1.json');assert o['task_execution_performed'] is False and o['vm_creation_performed'] is False and o['foundry_invoked'] is False and o['production_mutation'] is False and o['automatic_external_spend_eur']==0
def test_every_stage_emits_a_receipt():
 o,stages=run('dev-hub/fixtures/e2e-fit-api-backend-intent.v1.json','dev-hub/fixtures/e2e-fit-api-backend-requirements.v1.json','dev-hub/fixtures/e2e-fit-api-backend-targets.v1.json');assert len(o['receipts'])==7 and len(stages)==7
if __name__=='__main__':
 tests=[(n,v) for n,v in sorted(globals().items()) if n.startswith('test_') and callable(v)]
 for n,f in tests:f();print(n+'=PASS')
 print('CHACHA_DEV_CREATION_RUNTIME_E2E_SHADOW=PASS');print('TEST_COUNT='+str(len(tests)));print('TASK_EXECUTION=NO');print('PRODUCTION_MUTATION=NO');print('AUTOMATIC_EXTERNAL_SPEND_EUR=0')
