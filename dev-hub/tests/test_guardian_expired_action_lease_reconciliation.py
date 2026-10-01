#!/usr/bin/env python3
from pathlib import Path
import json, subprocess, tempfile

ROOT=Path(__file__).resolve().parents[2]
WORKER=ROOT/"dev-hub/guardian/worker.js"
CLIENT=ROOT/"dev-hub/bin/guardian-client.py"
ROLES=ROOT/"dev-hub/config/guardian-role-contracts.v1.json"
COVERAGE=ROOT/"dev-hub/config/guardian-coverage-manifest.v1.json"
MIGRATION=ROOT/"dev-hub/guardian/migrations/0011_action_lease_reconciliations.sql"
WORKFLOW=ROOT/".github/workflows/dev-hub-platform-qualification.yml"

def test_static_contract():
    worker=WORKER.read_text(encoding="utf-8")
    client=CLIENT.read_text(encoding="utf-8")
    migration=MIGRATION.read_text(encoding="utf-8")
    assert "/v1/action-leases/reconcile-expired" in worker
    assert "action_lease_reconciliations" in worker and "action_lease_reconciliations" in migration
    assert "post_action_fabricated:false" in worker
    assert "original_action_reexecuted:false" in worker
    assert "canonical_emergency_stop_mutated:false" in worker
    assert "platform_release_mutated:false" in worker
    assert "reconcile-action-state" in client

def test_role_and_coverage():
    roles=json.load(open(ROLES,encoding="utf-8"))
    role=next(x for x in roles["contracts"] if x["contract_id"]=="role:guardian-action-state-reconciler")
    assert role["allowed_actions"]==["RECONCILE_ACTION_STATE"]
    assert "destructive-operation" not in role["allowed_permissions"]
    assert "production-deploy" not in role["allowed_permissions"]
    assert "EXECUTE_PLATFORM_RETIREMENT" in role["forbidden_actions"]
    assert "REPLAY_ORIGINAL_ACTION" in role["forbidden_actions"]
    coverage=json.load(open(COVERAGE,encoding="utf-8"))
    row=next(x for x in coverage["expected_components"] if x["component_id"]=="guardian-action-state-reconciler")
    assert row["criticality"]=="CRITICAL"
    assert row["proof"]["file"]=="dev-hub/bin/guardian-action-state-reconciler.py"
    assert row["proof"]["marker"]=="CHACHA_DEV_GUARDIAN_ACTION_STATE_RECONCILER=PASS"

def test_validator_cases():
    source=WORKER.read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory(prefix="guardian-lease-reconcile-") as td:
        module=Path(td)/"worker.mjs"; module.write_text(source,encoding="utf-8")
        probe=Path(td)/"probe.mjs"
        probe.write_text(f'''import {{validateExpiredActionReconciliation as validate}} from {json.dumps(module.as_uri())};
const role={{allowed_actions_json:'["RECONCILE_ACTION_STATE"]'}};
const row={{action_id:'a1',status:'EXPIRED',actor:'platform-hygiene-executor',subject_role:'platform-hygiene-executor',action:'EXECUTE_PLATFORM_RETIREMENT',permission:'destructive-operation',project_id:'chacha-dev-platform',run_id:''}};
const alert={{status:'OPEN',reason_codes_json:'["POST_ACTION_MISSING"]'}};
const rem={{status:'DELIVERED',required_action:'RECONCILE_ACTION_STATE'}};
''',encoding="utf-8")
        probe.write_text(probe.read_text(encoding="utf-8")+'''const base={schema:'chacha.dev/action-lease-reconciliation-request/v1',reconciler_actor:'guardian-action-state-reconciler',action_id:'a1',source_alert_id:'lease-expired-a1',remediation_directive_id:'remed-lease-expired-a1',evidence_digest:'sha256:'+('a'.repeat(64)),original_identity:{actor:'platform-hygiene-executor',subject_role:'platform-hygiene-executor',action:'EXECUTE_PLATFORM_RETIREMENT',permission:'destructive-operation',project_id:'chacha-dev-platform',run_id:''},evidence:{final_state_verified:true,original_action_outcome:'COMPLETED',action_reexecuted:false,human_approval_verified:true,sources:[{digest:'sha256:'+('b'.repeat(64))}]}};
function expect(ok,label){if(!ok){console.error('FAIL',label);process.exit(2)}console.log(label+'=PASS')}
expect(validate(base,row,alert,rem,role).ok,'VALID_EXPIRED_LEASE');
expect(!validate(base,{...row,status:'OPEN'},alert,rem,role).ok,'OPEN_LEASE_BLOCKED');
expect(validate({...base,original_identity:{...base.original_identity,actor:'other'}},row,alert,rem,role).reason.startsWith('ORIGINAL_ACTION_IDENTITY_DRIFT'),'IDENTITY_DRIFT_BLOCKED');
expect(validate({...base,evidence:{...base.evidence,action_reexecuted:true}},row,alert,rem,role).reason==='ACTION_REPLAY_FORBIDDEN','ACTION_REPLAY_BLOCKED');
expect(validate({...base,evidence:{...base.evidence,human_approval_verified:false}},row,alert,rem,role).reason==='DESTRUCTIVE_HUMAN_APPROVAL_EVIDENCE_MISSING','HUMAN_APPROVAL_REQUIRED');
expect(!validate(base,row,alert,rem,{allowed_actions_json:'[]'}).ok,'UNAUTHORIZED_ROLE_BLOCKED');
''',encoding="utf-8")
        r=subprocess.run(["node",str(probe)],text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        assert r.returncode==0,(r.stdout,r.stderr)
        print(r.stdout.strip())

def test_platform_qualification_includes_reconciliation():
    workflow=WORKFLOW.read_text(encoding="utf-8")
    assert "test_guardian_expired_action_lease_reconciliation.py" in workflow

if __name__=="__main__":
    tests=[v for k,v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for test in tests:
        test(); print(test.__name__+"=PASS")
    print("CHACHA_DEV_GUARDIAN_EXPIRED_ACTION_LEASE_RECONCILIATION=PASS")
    print("TEST_COUNT="+str(len(tests)))
    print("AUTOMATIC_EXTERNAL_SPEND_EUR=0")
