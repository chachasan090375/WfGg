#!/usr/bin/env python3
from __future__ import annotations
import importlib.util,json,sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BIN=ROOT/"dev-hub/bin"
spec=importlib.util.spec_from_file_location("platform_component_controlled_apply_planner",BIN/"platform-component-controlled-apply-planner.py")
assert spec and spec.loader
planner=importlib.util.module_from_spec(spec);spec.loader.exec_module(planner)

contract={
  "schema":"chacha.dev/platform-component-controlled-apply-contract/v1",
  "component_id":"central-orchestrator",
  "candidate_owner":"branch-foundry",
  "candidate_revision":"abc","incumbent_revision":"def",
  "candidate_artifact_ref":"git:candidate@abc","incumbent_artifact_ref":"git:incumbent@def",
  "qualification_workflow_name":"ChaCha DEV universal evolution coverage sync qualification",
  "approval_id":"platform-component-promotion:central-orchestrator:abc",
  "approval_actor":"human-platform-owner",
  "approval_evidence":"architecture-council-platform-review:sha256:test",
  "technical_review_digest":"sha256:test",
  "apply_mode":"SOURCE_RELEASE_CANDIDATE_INTEGRATION",
  "source_candidate_integration_authorized":True,
  "direct_runtime_mutation_authorized":False,
  "production_activation_authorized":False,
  "production_deployment_authorized":False,
  "merge_to_production_branch_authorized":False,
  "automatic_apply":False,
  "central_orchestrator_apply_required":True,
  "candidate_owner_apply_adapter_required":True,
  "exact_revision_required":True,
  "rollback_required":True,
  "post_apply_exact_sha_gates_required":[
    "ChaCha DEV universal evolution coverage sync qualification",
    "ChaCha DEV Sentinel technical assurance"
  ],
  "guardian_post_apply_assurance_required":True,
  "automatic_external_spend_eur":0
}
gate={
  "schema":"chacha.dev/platform-component-promotion-gate/v1",
  "component_id":"central-orchestrator",
  "status":"PROMOTION_AUTHORIZED_FOR_CONTROLLED_APPLY",
  "human_approval_verified":True,
  "promotion_authorized":True,
  "controlled_apply_required":True,
  "controlled_apply_contract_created":True,
  "controlled_apply_contract":contract,
  "automatic_apply":False,
  "production_activation_allowed":False,
  "direct_runtime_mutation":False,
  "central_orchestrator_remains_apply_authority":True,
  "rollback_required":True,
  "automatic_external_spend_eur":0
}

# Default DENY canonical registry must not accidentally produce an executable plan.
registry_base=json.loads((ROOT/"dev-hub/config/platform-component-apply-adapter-registry.v1.json").read_text(encoding="utf-8"))
assert registry_base["schema"]=="chacha.dev/platform-component-apply-adapter-registry/v1",registry_base
assert registry_base["default_admission"]=="DENY",registry_base
assert registry_base["adapters"]=={},registry_base
awaiting=planner.evaluate(gate,registry_base)
assert awaiting["status"]=="AWAITING_APPLY_ADAPTER",awaiting
assert awaiting["controlled_apply_plan_ready"] is False,awaiting
assert awaiting["apply_execution_authorized_by_planner"] is False,awaiting
assert awaiting["apply_plan"] is None,awaiting
assert awaiting["automatic_apply"] is False,awaiting
assert awaiting["production_activation_allowed"] is False,awaiting

valid_adapter={
  "adapter_id":"branch-foundry-source-integrator-v1",
  "status":"QUALIFIED",
  "candidate_owner":"branch-foundry",
  "apply_mode":"SOURCE_RELEASE_CANDIDATE_INTEGRATION",
  "reversible":True,
  "rollback_adapter_id":"branch-foundry-source-rollback-v1",
  "exact_revision_enforced":True,
  "direct_runtime_mutation":False,
  "production_activation":False,
  "production_deployment":False,
  "merge_to_production_branch":False,
  "automatic_apply":False,
  "qualification_workflow_name":"ChaCha DEV controlled apply adapter qualification",
  "automatic_external_spend_eur":0
}
# A permissive/tampered registry is blocked before adapter selection.
bad_registry=json.loads(json.dumps(registry_base))
bad_registry["default_admission"]="ALLOW"
badreg=planner.evaluate(gate,bad_registry)
assert badreg["status"]=="BLOCKED",badreg
assert "APPLY_ADAPTER_REGISTRY_POLICY_INVALID" in badreg["blockers"],badreg

registry=json.loads(json.dumps(registry_base))
registry["adapters"]["central-orchestrator"]=valid_adapter
ready=planner.evaluate(gate,registry)
assert ready["status"]=="READY_FOR_CENTRAL_ORCHESTRATOR_APPLY",ready
assert ready["controlled_apply_plan_ready"] is True,ready
assert ready["apply_execution_authorized_by_planner"] is False,ready
plan=ready["apply_plan"]
assert plan["candidate_revision"]=="abc" and plan["incumbent_revision"]=="def",plan
assert plan["candidate_artifact_ref"]=="git:candidate@abc",plan
assert plan["adapter_id"]=="branch-foundry-source-integrator-v1",plan
assert plan["rollback_adapter_id"]=="branch-foundry-source-rollback-v1",plan
assert plan["central_orchestrator_apply_required"] is True,plan
assert plan["apply_execution_authorized_by_planner"] is False,plan
assert plan["automatic_apply"] is False,plan
assert plan["direct_runtime_mutation"] is False,plan
assert plan["production_activation_allowed"] is False,plan
assert plan["production_deployment_allowed"] is False,plan
assert plan["merge_to_production_branch_allowed"] is False,plan
assert set(plan["post_apply_exact_sha_gates_required"])=={
 "ChaCha DEV universal evolution coverage sync qualification",
 "ChaCha DEV Sentinel technical assurance"
},plan

# Owner mismatch is a hard block.
bad_owner=json.loads(json.dumps(registry))
bad_owner["adapters"]["central-orchestrator"]["candidate_owner"]="capability-foundry"
blocked=planner.evaluate(gate,bad_owner)
assert blocked["status"]=="BLOCKED",blocked
assert "adapter_owner_matches" in blocked["blockers"],blocked

# Any runtime mutation capability is forbidden in this source-integration stage.
bad_runtime=json.loads(json.dumps(registry))
bad_runtime["adapters"]["central-orchestrator"]["direct_runtime_mutation"]=True
blocked2=planner.evaluate(gate,bad_runtime)
assert blocked2["status"]=="BLOCKED",blocked2
assert "direct_runtime_mutation_forbidden" in blocked2["blockers"],blocked2

# A weakened promotion gate must fail closed.
bad_gate=json.loads(json.dumps(gate))
bad_gate["human_approval_verified"]=False
blocked3=planner.evaluate(bad_gate,registry)
assert blocked3["status"]=="BLOCKED",blocked3
assert "PROMOTION_GATE_INVALID" in blocked3["blockers"],blocked3

# Planner itself is a governed core component and cannot deploy/promote.
guardian=json.loads((ROOT/"dev-hub/config/guardian-coverage-manifest.v1.json").read_text(encoding="utf-8"))
assert any(x.get("component_id")=="platform-component-controlled-apply-planner" for x in guardian.get("expected_components") or []),guardian
assert guardian["d1_write_budget"]["expected_max_component_heartbeat_writes_per_day"]==len(guardian["expected_components"])*12*24

core=json.loads((ROOT/"dev-hub/config/technology-core-watch.v1.json").read_text(encoding="utf-8"))
crow=next(x for x in core["components"] if x["id"]=="platform-component-controlled-apply-planner")
assert crow["class"]=="verification" and crow["criticality"]=="critical",crow

roles=json.loads((ROOT/"dev-hub/config/guardian-role-contracts.v1.json").read_text(encoding="utf-8"))
role=next(x for x in roles["contracts"] if x["contract_id"]=="role:platform-component-controlled-apply-planner")
assert set(role["allowed_permissions"])=={"read","plan","workspace-write"},role
assert {"PRODUCTION_DEPLOY","PROMOTE_COMPONENT","MODIFY_GUARDIAN_CONTRACTS","EXPAND_PERMISSIONS","MUTATE_RUNTIME"}<=set(role["forbidden_actions"]),role

print("CHACHA_DEV_PLATFORM_COMPONENT_CONTROLLED_APPLY_PLANNER=PASS")
print("CHACHA_DEV_PLATFORM_COMPONENT_APPLY_ADAPTER_DEFAULT=DENY")
print("CHACHA_DEV_PLATFORM_COMPONENT_APPLY_NO_ADAPTER=AWAIT")
print("CHACHA_DEV_PLATFORM_COMPONENT_APPLY_INVALID_REGISTRY=BLOCKED")
print("CHACHA_DEV_PLATFORM_COMPONENT_APPLY_VALID_ADAPTER=PLAN_READY")
print("CHACHA_DEV_PLATFORM_COMPONENT_APPLY_EXECUTION_AUTHORIZED_BY_PLANNER=NO")
print("CHACHA_DEV_PLATFORM_COMPONENT_APPLY_RUNTIME_MUTATION=NO")
print("CHACHA_DEV_PLATFORM_COMPONENT_APPLY_PRODUCTION_ACTIVATION=NO")
print("CHACHA_DEV_PLATFORM_COMPONENT_APPLY_PRODUCTION_DEPLOYMENT=NO")
print("CHACHA_DEV_PLATFORM_COMPONENT_APPLY_PRODUCTION_MERGE=NO")
print("CHACHA_DEV_PLATFORM_COMPONENT_APPLY_GUARDIAN_COVERAGE=PASS")
print("CHACHA_DEV_PLATFORM_COMPONENT_APPLY_CORE_WATCH=PASS")
print("CHACHA_DEV_PLATFORM_COMPONENT_APPLY_GUARDIAN_ROLE=PASS")
print("CHACHA_DEV_PLATFORM_COMPONENT_APPLY_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
