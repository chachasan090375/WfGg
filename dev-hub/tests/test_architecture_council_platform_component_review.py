#!/usr/bin/env python3
from __future__ import annotations
import importlib.util,json,sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BIN=ROOT/"dev-hub/bin"
sys.path.insert(0,str(BIN))
spec=importlib.util.spec_from_file_location(
    "architecture_council_platform_component_review",
    BIN/"architecture-council-platform-component-review.py")
assert spec and spec.loader
review=importlib.util.module_from_spec(spec)
spec.loader.exec_module(review)

policy=json.loads((ROOT/"dev-hub/config/architecture-decision-council.v1.json").read_text(encoding="utf-8"))
rp=policy["platform_component_candidate_review"]
assert rp["enabled"] is True
assert rp["architecture_council_may_auto_promote"] is False
assert rp["explicit_human_promotion_approval_required"] is True
assert rp["default_action_without_human_approval"]=="HOLD_INCUMBENT"

checks={
 "independent_verification":True,
 "measurable_gain":True,
 "no_material_regression":True,
 "permission_non_escalation":True,
 "rollback_ready":True,
 "exact_revision_evidence":True,
 "logician_falsification_pass":True,
 "technology_watch_revalidation_pass":True,
 "real_harness_available":True
}
contract={
 "schema":"chacha.dev/platform-component-comparative-pilot-contract/v1",
 "contract_id":"pcp-1","dispatch_id":"d1","component_id":"central-orchestrator",
 "candidate_owner":"branch-foundry","harness_id":"h1",
 "qualification_workflow_name":"ChaCha DEV universal evolution coverage sync qualification",
 "incumbent_artifact_ref":"git:incumbent@def","candidate_artifact_ref":"git:candidate@abc",
 "incumbent_revision":"def","candidate_revision":"abc",
 "pre_pilot_checks":checks,"pre_pilot_evidence_refs":["e:1","e:2"],
 "same_benchmark_contract":True,"isolated_ephemeral_capsules":True,
 "production_entrypoint_unchanged":True,
 "pilot_execution_authorized":True,"production_change_authorized":False,
 "promotion_authorized":False,"permission_expansion":False,
 "automatic_external_spend_eur":0
}
pilot={
 "schema":"chacha.dev/platform-component-comparative-pilot-result/v1",
 "status":"PASS","run_id":"run-1","contract_id":"pcp-1","dispatch_id":"d1",
 "component_id":"central-orchestrator","incumbent_revision":"def","candidate_revision":"abc",
 "same_benchmark_contract":True,"isolated_ephemeral_capsules":True,
 "production_entrypoint_unchanged":True,
 "sentinel_exact_sha_receipt_digest":"sha256:s",
 "guardian_pre_pass":True,"guardian_pre_receipt_digest":"sha256:gpre",
 "guardian_post_pass":True,"guardian_post_receipt_digest":"sha256:gpost",
 "results":{
   "INCUMBENT":{"artifact_ref":"git:incumbent@def","acceptance_pass":True,
     "quality_score":97,"stability_score":98,"error_rate":0,"latency_ms":30,
     "memory_mb":72,"external_spend_eur":0},
   "CANDIDATE":{"artifact_ref":"git:candidate@abc","acceptance_pass":True,
     "quality_score":99,"stability_score":99,"error_rate":0,"latency_ms":20,
     "memory_mb":64,"external_spend_eur":0}
 },
 "comparison":{
   "both_acceptance_pass":True,"candidate_zero_external_spend":True,
   "no_quality_regression":True,"no_stability_regression":True,
   "no_error_rate_regression":True,"measurable_gain_observed":True,
   "candidate_technically_admissible_for_council_review":True,
   "final_architecture_decision_made":False,"promotion_authorized":False
 },
 "council_handoff_required":True,"production_change_authorized":False,
 "promotion_authorized":False,"permission_expansion":False,
 "automatic_external_spend_eur":0
}
sentinel={
 "schema":"chacha.dev/sentinel-exact-sha-receipt/v1",
 "workflow_name":"ChaCha DEV Sentinel technical assurance","head_sha":"abc",
 "conclusion":"success","exact_sha_verified":True,"run_id":123
}
watch={"state":"FRESH","fresh":True}
runs={"workflow_runs":[
 {"name":"ChaCha DEV Sentinel technical assurance","head_sha":"abc",
  "status":"completed","conclusion":"success"},
 {"name":"ChaCha DEV universal evolution coverage sync qualification","head_sha":"abc",
  "status":"completed","conclusion":"success"}
]}

ok=review.build_review(policy,pilot,contract,sentinel,watch,runs)
assert ok["technical_review_passed"] is True,ok
assert ok["architecture_council_technical_admissibility"] is True,ok
assert ok["decision"]=="TECHNICALLY_ADMISSIBLE_AWAIT_EXPLICIT_HUMAN_PROMOTION_APPROVAL",ok
assert ok["next_action"]=="AWAIT_EXPLICIT_HUMAN_PROMOTION_APPROVAL",ok
assert ok["production_activation_allowed"] is False,ok
assert ok["promotion_allowed"] is False,ok
assert ok["human_explicit_promotion_approval_present"] is False,ok
assert ok["incumbent_control_group"] is True,ok

missing_runs={"workflow_runs":[runs["workflow_runs"][0]]}
blocked=review.build_review(policy,pilot,contract,sentinel,watch,missing_runs)
assert blocked["technical_review_passed"] is False,blocked
assert blocked["checks"]["qualification_exact_revision_workflow_success"] is False,blocked
assert blocked["decision"]=="COUNCIL_REVIEW_BLOCKED_HOLD_INCUMBENT",blocked

bad_pilot=json.loads(json.dumps(pilot))
bad_pilot["production_change_authorized"]=True
bad=review.build_review(policy,bad_pilot,contract,sentinel,watch,runs)
assert bad["technical_review_passed"] is False,bad
assert bad["checks"]["pilot_production_change_forbidden"] is False,bad

weak_policy=json.loads(json.dumps(policy))
weak_policy["platform_component_candidate_review"]["rollback_ready_required"]=False
weak=review.build_review(weak_policy,pilot,contract,sentinel,watch,runs)
assert weak["technical_review_passed"] is False,weak
assert weak["checks"]["review_policy_requirements_enabled"] is False,weak

print("CHACHA_DEV_PLATFORM_COMPONENT_COUNCIL_REVIEW=PASS")
print("CHACHA_DEV_PLATFORM_COMPONENT_COUNCIL_EXACT_SHA_GATES=PASS")
print("CHACHA_DEV_PLATFORM_COMPONENT_COUNCIL_POLICY_FAIL_CLOSED=PASS")
print("CHACHA_DEV_PLATFORM_COMPONENT_COUNCIL_HOLD_INCUMBENT=YES")
print("CHACHA_DEV_PLATFORM_COMPONENT_COUNCIL_HUMAN_PROMOTION_APPROVAL_REQUIRED=YES")
print("CHACHA_DEV_PLATFORM_COMPONENT_COUNCIL_PRODUCTION_ACTIVATION=NO")
print("CHACHA_DEV_PLATFORM_COMPONENT_COUNCIL_PROMOTION=NO")
print("CHACHA_DEV_PLATFORM_COMPONENT_COUNCIL_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
