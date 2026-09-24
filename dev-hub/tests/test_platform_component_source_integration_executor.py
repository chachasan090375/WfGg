#!/usr/bin/env python3
from __future__ import annotations
import importlib.util,json,tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BIN=ROOT/"dev-hub/bin"
spec=importlib.util.spec_from_file_location("platform_component_source_integration_executor",BIN/"platform-component-source-integration-executor.py")
assert spec and spec.loader
executor=importlib.util.module_from_spec(spec);spec.loader.exec_module(executor)

CAND="a"*40
INC="b"*40
QUAL="ChaCha DEV universal evolution coverage sync qualification"
SENTINEL="ChaCha DEV Sentinel technical assurance"
PLAN={
 "schema":"chacha.dev/platform-component-controlled-apply-plan/v1",
 "component_id":"central-orchestrator","candidate_owner":"branch-foundry",
 "candidate_revision":CAND,"incumbent_revision":INC,
 "candidate_artifact_ref":"git:candidate@"+CAND,
 "incumbent_artifact_ref":"git:incumbent@"+INC,
 "adapter_id":"branch-foundry-source-integrator-v1",
 "rollback_adapter_id":"branch-foundry-source-rollback-v1",
 "adapter_qualification_workflow_name":"ChaCha DEV source integration adapter qualification",
 "source_qualification_workflow_name":QUAL,
 "post_apply_exact_sha_gates_required":[QUAL,SENTINEL],
 "guardian_post_apply_assurance_required":True,
 "exact_revision_required":True,"rollback_required":True,
 "apply_mode":"SOURCE_RELEASE_CANDIDATE_INTEGRATION",
 "central_orchestrator_apply_required":True,
 "apply_execution_authorized_by_planner":False,
 "automatic_apply":False,"direct_runtime_mutation":False,
 "production_activation_allowed":False,"production_deployment_allowed":False,
 "merge_to_production_branch_allowed":False,
 "automatic_external_spend_eur":0
}
PLANNER={
 "schema":"chacha.dev/platform-component-controlled-apply-planner/v1",
 "status":"READY_FOR_CENTRAL_ORCHESTRATOR_APPLY",
 "controlled_apply_plan_ready":True,
 "apply_execution_authorized_by_planner":False,
 "approval_id":"platform-component-promotion:central-orchestrator:"+CAND,
 "approval_actor":"human-platform-owner",
 "technical_review_digest":"sha256:"+"c"*64,
 "apply_plan":PLAN
}
HANDOFF={
 "schema":"chacha.dev/platform-component-central-apply-handoff/v1",
 "handoff_id":"central-apply-"+CAND[:16],
 "actor":"central-orchestrator","apply_execution_authorized":True,
 "single_use":True,"source_candidate_integration_only":True,
 "component_id":"central-orchestrator","candidate_owner":"branch-foundry",
 "candidate_revision":CAND,"incumbent_revision":INC,
 "candidate_artifact_ref":"git:candidate@"+CAND,
 "incumbent_artifact_ref":"git:incumbent@"+INC,
 "adapter_id":"branch-foundry-source-integrator-v1",
 "controlled_apply_plan_digest":executor.digest(PLAN),
 "approval_id":PLANNER["approval_id"],"approval_actor":PLANNER["approval_actor"],
 "technical_review_digest":PLANNER["technical_review_digest"],
 "human_approval_verified":True,"rollback_required":True,
 "guardian_pre_post_required":True,"emergency_stop_required":True,
 "direct_runtime_mutation_authorized":False,
 "production_activation_authorized":False,
 "production_deployment_authorized":False,
 "merge_to_production_branch_authorized":False,
 "automatic_apply":False,"automatic_external_spend_eur":0
}
REGISTRY={
 "schema":"chacha.dev/platform-component-apply-adapter-registry/v1",
 "default_admission":"DENY",
 "principles":{
   "trusted_executable_root":"/opt/chacha-dev/adapters/platform-component",
   "fixed_operation_protocol":True,"shell_interpolation_forbidden":True,
   "single_use_central_handoff_required":True
 },
 "adapters":{
   "central-orchestrator":{
     "adapter_id":"branch-foundry-source-integrator-v1","status":"QUALIFIED",
     "candidate_owner":"branch-foundry",
     "apply_mode":"SOURCE_RELEASE_CANDIDATE_INTEGRATION",
     "reversible":True,"rollback_adapter_id":"branch-foundry-source-rollback-v1",
     "exact_revision_enforced":True,
     "executable":"/opt/chacha-dev/adapters/platform-component/branch-foundry-source-integrator/current/adapter",
     "direct_runtime_mutation":False,"production_activation":False,
     "production_deployment":False,"merge_to_production_branch":False,
     "automatic_apply":False,"automatic_external_spend_eur":0
   }
 }
}
RUNS={"workflow_runs":[
 {"name":QUAL,"head_sha":CAND,"status":"completed","conclusion":"success"},
 {"name":SENTINEL,"head_sha":CAND,"status":"completed","conclusion":"success"}
]}

def fake_guardian(repo_root,phase,plan,handoff,status=None):
    return {"status":"PASS","verdict":"PASS","phase":phase,"result_status":status}

adapter_calls=[]
def fake_adapter(executable,operation,payload):
    adapter_calls.append((executable,operation,payload))
    if operation=="apply":
        return {
          "schema":"chacha.dev/platform-component-source-integration-receipt/v1",
          "status":"PASS","component_id":"central-orchestrator",
          "candidate_revision":CAND,"incumbent_revision":INC,
          "source_release_candidate_integrated":True,
          "rollback_token":"rollback-token-1",
          "direct_runtime_mutation":False,"production_activation":False,
          "production_deployment":False,"merge_to_production_branch":False,
          "automatic_external_spend_eur":0
        }
    assert operation=="rollback",operation
    return {
      "schema":"chacha.dev/platform-component-source-integration-rollback/v1",
      "status":"PASS","component_id":"central-orchestrator",
      "candidate_revision":CAND,"rollback_proven":True,
      "source_candidate_integration_reverted":True,
      "direct_runtime_mutation":False,"production_activation":False,
      "production_deployment":False,"merge_to_production_branch":False,
      "automatic_external_spend_eur":0
    }

consumed=[]
def fake_consumer(runtime_root,handoff):
    consumed.append(handoff["handoff_id"])
    return Path("/tmp/fake-consumption-"+str(len(consumed))+".json")

ok=executor.execute(
    PLANNER,HANDOFF,REGISTRY,ROOT,RUNS,
    adapter_provider=fake_adapter,guardian_provider=fake_guardian,
    handoff_consumer=fake_consumer,stop_provider=lambda:False
)
assert ok["status"]=="PASS_SOURCE_RELEASE_CANDIDATE_INTEGRATED",ok
assert ok["source_release_candidate_integrated"] is True,ok
assert ok["post_apply_exact_sha_gates_pass"] is True,ok
assert ok["guardian_post_apply_pass"] is True,ok
assert ok["rollback_attempted"] is False,ok
assert ok["production_activation_allowed"] is False,ok
assert ok["production_deployment_allowed"] is False,ok
assert ok["merge_to_production_branch_allowed"] is False,ok
assert ok["direct_runtime_mutation"] is False,ok
assert [x[1] for x in adapter_calls]==["apply"],adapter_calls
assert consumed==[HANDOFF["handoff_id"]],consumed

# Post-apply exact-SHA failure must rollback.
adapter_calls.clear();consumed.clear()
bad_runs={"workflow_runs":[RUNS["workflow_runs"][0]]}
rolled=executor.execute(
    PLANNER,HANDOFF,REGISTRY,ROOT,bad_runs,
    adapter_provider=fake_adapter,guardian_provider=fake_guardian,
    handoff_consumer=fake_consumer,stop_provider=lambda:False
)
assert rolled["status"]=="BLOCKED_ROLLED_BACK",rolled
assert rolled["source_release_candidate_integrated"] is False,rolled
assert rolled["rollback_attempted"] is True and rolled["rollback_proven"] is True,rolled
assert SENTINEL in rolled["missing_post_apply_gates"],rolled
assert [x[1] for x in adapter_calls]==["apply","rollback"],adapter_calls

# Central handoff is truly single-use.
with tempfile.TemporaryDirectory(prefix="source-integration-replay-") as td:
    root=Path(td)
    first=executor.consume_handoff(root,HANDOFF)
    assert first.is_file(),first
    try:
        executor.consume_handoff(root,HANDOFF)
    except RuntimeError as exc:
        assert "REPLAY_BLOCKED" in str(exc),exc
    else:
        raise AssertionError("single-use handoff replay was accepted")

# Handoff must be exactly bound to the plan and human approval lineage.
bad_handoff=json.loads(json.dumps(HANDOFF))
bad_handoff["controlled_apply_plan_digest"]="sha256:wrong"
v=executor.validate_inputs(PLANNER,bad_handoff,REGISTRY)
assert v["ok"] is False,v
assert "handoff_plan_digest_matches" in v["blockers"],v

bad_approval=json.loads(json.dumps(HANDOFF))
bad_approval["approval_actor"]="central-orchestrator"
v2=executor.validate_inputs(PLANNER,bad_approval,REGISTRY)
assert v2["ok"] is False,v2
assert "handoff_approval_actor_matches" in v2["blockers"],v2

# Adapter executable must stay under the trusted root.
outside=json.loads(json.dumps(REGISTRY))
outside["adapters"]["central-orchestrator"]["executable"]="/tmp/untrusted-adapter"
v3=executor.validate_inputs(PLANNER,HANDOFF,outside)
assert v3["ok"] is False,v3
assert "adapter_executable_under_trusted_root" in v3["blockers"],v3

# Emergency Stop blocks before adapter invocation.
try:
    executor.execute(
      PLANNER,HANDOFF,REGISTRY,ROOT,RUNS,
      adapter_provider=fake_adapter,guardian_provider=fake_guardian,
      handoff_consumer=fake_consumer,stop_provider=lambda:True
    )
except RuntimeError as exc:
    assert "EMERGENCY_STOP_ACTIVE" in str(exc),exc
else:
    raise AssertionError("emergency stop did not block source integration")

# Executor itself is governed and watched.
guardian=json.loads((ROOT/"dev-hub/config/guardian-coverage-manifest.v1.json").read_text(encoding="utf-8"))
assert any(x.get("component_id")=="platform-component-source-integration-executor" for x in guardian.get("expected_components") or []),guardian
assert guardian["d1_write_budget"]["expected_max_component_heartbeat_writes_per_day"]==len(guardian["expected_components"])*12*24

core=json.loads((ROOT/"dev-hub/config/technology-core-watch.v1.json").read_text(encoding="utf-8"))
crow=next(x for x in core["components"] if x["id"]=="platform-component-source-integration-executor")
assert crow["class"]=="execution" and crow["criticality"]=="critical",crow

roles=json.loads((ROOT/"dev-hub/config/guardian-role-contracts.v1.json").read_text(encoding="utf-8"))
role=next(x for x in roles["contracts"] if x["contract_id"]=="role:platform-component-source-integration-executor")
assert {"INTEGRATE_RELEASE_CANDIDATE_SOURCE","ROLLBACK_RELEASE_CANDIDATE_SOURCE"}<=set(role["allowed_actions"]),role
assert {"PRODUCTION_DEPLOY","PROMOTE_COMPONENT","MERGE_PRODUCTION_BRANCH","EXPAND_PERMISSIONS","MUTATE_RUNTIME"}<=set(role["forbidden_actions"]),role

source=(BIN/"platform-component-source-integration-executor.py").read_text(encoding="utf-8")
assert "shell=False" in source
assert "os.system" not in source
assert "subprocess.run([executable,operation]" in source
assert "CENTRAL_APPLY_HANDOFF_REPLAY_BLOCKED" in source

print("CHACHA_DEV_PLATFORM_COMPONENT_SOURCE_INTEGRATION_EXECUTOR=PASS")
print("CHACHA_DEV_PLATFORM_COMPONENT_SOURCE_INTEGRATION_CENTRAL_HANDOFF=REQUIRED")
print("CHACHA_DEV_PLATFORM_COMPONENT_SOURCE_INTEGRATION_SINGLE_USE=YES")
print("CHACHA_DEV_PLATFORM_COMPONENT_SOURCE_INTEGRATION_TRUSTED_ADAPTER_ROOT=ENFORCED")
print("CHACHA_DEV_PLATFORM_COMPONENT_SOURCE_INTEGRATION_POST_GATES=EXACT_SHA")
print("CHACHA_DEV_PLATFORM_COMPONENT_SOURCE_INTEGRATION_POST_GATE_FAILURE=ROLLBACK")
print("CHACHA_DEV_PLATFORM_COMPONENT_SOURCE_INTEGRATION_EMERGENCY_STOP=ENFORCED")
print("CHACHA_DEV_PLATFORM_COMPONENT_SOURCE_INTEGRATION_RUNTIME_MUTATION=NO")
print("CHACHA_DEV_PLATFORM_COMPONENT_SOURCE_INTEGRATION_PRODUCTION_ACTIVATION=NO")
print("CHACHA_DEV_PLATFORM_COMPONENT_SOURCE_INTEGRATION_PRODUCTION_DEPLOYMENT=NO")
print("CHACHA_DEV_PLATFORM_COMPONENT_SOURCE_INTEGRATION_PRODUCTION_MERGE=NO")
print("CHACHA_DEV_PLATFORM_COMPONENT_SOURCE_INTEGRATION_GUARDIAN_COVERAGE=PASS")
print("CHACHA_DEV_PLATFORM_COMPONENT_SOURCE_INTEGRATION_CORE_WATCH=PASS")
print("CHACHA_DEV_PLATFORM_COMPONENT_SOURCE_INTEGRATION_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
