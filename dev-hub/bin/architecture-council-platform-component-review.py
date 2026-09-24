#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,urllib.parse,urllib.request
from datetime import datetime,timezone
from pathlib import Path
from typing import Any
import technology_watch_runtime as tw

SCHEMA="chacha.dev/architecture-council-platform-component-review/v1"

def load(p:Path)->dict[str,Any]:
    x=json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise ValueError("JSON_ROOT_NOT_OBJECT:"+str(p))
    return x

def save(p:Path,x:dict[str,Any])->None:
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")

def now_iso()->str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00","Z")

def github_runs(repository:str,revision:str)->dict[str,Any]:
    q=urllib.parse.urlencode({"head_sha":revision,"per_page":100})
    req=urllib.request.Request(
      "https://api.github.com/repos/"+repository+"/actions/runs?"+q,
      headers={"User-Agent":"ChaCha-DEV-Platform-Council/1.0","Accept":"application/vnd.github+json"})
    with urllib.request.urlopen(req,timeout=20) as r:
        x=json.loads(r.read().decode("utf-8"))
    if not isinstance(x,dict):raise ValueError("GITHUB_RUNS_INVALID")
    return x

def workflow_success(runs:dict[str,Any],name:str,revision:str)->bool:
    return any(
      isinstance(x,dict) and x.get("name")==name and x.get("head_sha")==revision and
      x.get("status")=="completed" and x.get("conclusion")=="success"
      for x in (runs.get("workflow_runs") or [])
    )

def build_review(policy:dict[str,Any],pilot:dict[str,Any],contract:dict[str,Any],
                 sentinel:dict[str,Any],watch:dict[str,Any],runs:dict[str,Any])->dict[str,Any]:
    review_policy=policy.get("platform_component_candidate_review") or {}
    candidate_revision=str(contract.get("candidate_revision") or "")
    incumbent_revision=str(contract.get("incumbent_revision") or "")
    qualification_workflow=str(contract.get("qualification_workflow_name") or "")
    pre=contract.get("pre_pilot_checks") if isinstance(contract.get("pre_pilot_checks"),dict) else {}
    required_pre=[
      "independent_verification","measurable_gain","no_material_regression",
      "permission_non_escalation","rollback_ready","exact_revision_evidence",
      "logician_falsification_pass","technology_watch_revalidation_pass","real_harness_available"
    ]
    incumbent=(pilot.get("results") or {}).get("INCUMBENT") or {}
    candidate=(pilot.get("results") or {}).get("CANDIDATE") or {}
    comparison=pilot.get("comparison") or {}
    mandatory_policy_flags=[
      "pilot_result_required","exact_candidate_and_incumbent_revision_required",
      "exact_candidate_and_incumbent_artifact_required","same_benchmark_contract_required",
      "isolated_ephemeral_capsules_required","guardian_pre_post_required",
      "sentinel_exact_revision_success_required","qualification_exact_revision_success_required",
      "technology_watch_fresh_required","logician_falsification_required",
      "permission_non_escalation_required","rollback_ready_required","measurable_gain_required",
      "no_material_regression_required","zero_automatic_external_spend_required",
      "incumbent_control_group_required","production_entrypoint_unchanged_required"
    ]
    checks={
      "policy_enabled":review_policy.get("enabled") is True,
      "review_policy_requirements_enabled":all(review_policy.get(k) is True for k in mandatory_policy_flags),
      "council_may_confirm_technical_admissibility":review_policy.get("architecture_council_may_confirm_technical_admissibility") is True,
      "central_orchestrator_final_decider":policy.get("central_orchestrator_is_final_decider") is True,
      "no_single_foundry_final_authority":policy.get("no_single_foundry_may_select_final_architecture") is True,
      "pilot_result_schema":pilot.get("schema")=="chacha.dev/platform-component-comparative-pilot-result/v1",
      "pilot_result_pass":pilot.get("status")=="PASS",
      "pilot_contract_schema":contract.get("schema")=="chacha.dev/platform-component-comparative-pilot-contract/v1",
      "contract_id_matches":pilot.get("contract_id")==contract.get("contract_id"),
      "dispatch_id_matches":pilot.get("dispatch_id")==contract.get("dispatch_id"),
      "component_id_matches":pilot.get("component_id")==contract.get("component_id"),
      "candidate_revision_matches":pilot.get("candidate_revision")==candidate_revision and bool(candidate_revision),
      "incumbent_revision_matches":pilot.get("incumbent_revision")==incumbent_revision and bool(incumbent_revision),
      "candidate_artifact_matches":candidate.get("artifact_ref")==contract.get("candidate_artifact_ref"),
      "incumbent_artifact_matches":incumbent.get("artifact_ref")==contract.get("incumbent_artifact_ref"),
      "same_benchmark_contract":pilot.get("same_benchmark_contract") is True and contract.get("same_benchmark_contract") is True,
      "isolated_ephemeral_capsules":pilot.get("isolated_ephemeral_capsules") is True and contract.get("isolated_ephemeral_capsules") is True,
      "production_entrypoint_unchanged":pilot.get("production_entrypoint_unchanged") is True and contract.get("production_entrypoint_unchanged") is True,
      "guardian_pre_pass":pilot.get("guardian_pre_pass") is True and bool(pilot.get("guardian_pre_receipt_digest")),
      "guardian_post_pass":pilot.get("guardian_post_pass") is True and bool(pilot.get("guardian_post_receipt_digest")),
      "sentinel_receipt_schema":sentinel.get("schema")=="chacha.dev/sentinel-exact-sha-receipt/v1",
      "sentinel_receipt_revision":sentinel.get("head_sha")==candidate_revision,
      "sentinel_receipt_success":sentinel.get("conclusion")=="success" and sentinel.get("exact_sha_verified") is True,
      "sentinel_exact_revision_workflow_success":workflow_success(runs,"ChaCha DEV Sentinel technical assurance",candidate_revision),
      "qualification_exact_revision_workflow_success":bool(qualification_workflow) and workflow_success(runs,qualification_workflow,candidate_revision),
      "technology_watch_fresh":watch.get("fresh") is True and watch.get("state")=="FRESH",
      "pre_pilot_checks_complete":all(pre.get(k) is True for k in required_pre),
      "logician_falsification":pre.get("logician_falsification_pass") is True,
      "permission_non_escalation":pre.get("permission_non_escalation") is True,
      "rollback_ready":pre.get("rollback_ready") is True,
      "measurable_gain_preverified":pre.get("measurable_gain") is True,
      "no_material_regression_preverified":pre.get("no_material_regression") is True,
      "both_pilot_variants_acceptance_pass":comparison.get("both_acceptance_pass") is True,
      "candidate_zero_external_spend":comparison.get("candidate_zero_external_spend") is True,
      "candidate_measurable_gain_observed":comparison.get("measurable_gain_observed") is True,
      "candidate_no_quality_regression":comparison.get("no_quality_regression") is True,
      "candidate_no_stability_regression":comparison.get("no_stability_regression") is True,
      "candidate_no_error_rate_regression":comparison.get("no_error_rate_regression") is True,
      "candidate_technically_admissible_from_pilot":comparison.get("candidate_technically_admissible_for_council_review") is True,
      "pilot_made_no_final_architecture_decision":comparison.get("final_architecture_decision_made") is False,
      "pilot_production_change_forbidden":pilot.get("production_change_authorized") is False and contract.get("production_change_authorized") is False,
      "pilot_promotion_forbidden":pilot.get("promotion_authorized") is False and contract.get("promotion_authorized") is False,
      "permission_expansion_forbidden":pilot.get("permission_expansion") is False and contract.get("permission_expansion") is False,
      "zero_automatic_external_spend":float(pilot.get("automatic_external_spend_eur") or 0)==0 and float(contract.get("automatic_external_spend_eur") or 0)==0,
      "auto_promotion_forbidden":review_policy.get("architecture_council_may_auto_promote") is False,
      "explicit_human_promotion_approval_required":review_policy.get("explicit_human_promotion_approval_required") is True
    }
    passed=all(checks.values())
    decision=("TECHNICALLY_ADMISSIBLE_AWAIT_EXPLICIT_HUMAN_PROMOTION_APPROVAL"
              if passed else "COUNCIL_REVIEW_BLOCKED_HOLD_INCUMBENT")
    return {
      "schema":SCHEMA,"generated_at":now_iso(),"review_authority":"architecture-council",
      "component_id":contract.get("component_id"),"candidate_owner":contract.get("candidate_owner"),
      "candidate_revision":candidate_revision,"incumbent_revision":incumbent_revision,
      "pilot_contract_id":contract.get("contract_id"),"pilot_run_id":pilot.get("run_id"),
      "checks":checks,"technical_review_passed":passed,
      "architecture_council_technical_admissibility":passed,
      "decision":decision,
      "next_action":"AWAIT_EXPLICIT_HUMAN_PROMOTION_APPROVAL" if passed else "REMEDIATE_AND_REVIEW",
      "incumbent_control_group":True,"human_explicit_promotion_approval_present":False,
      "explicit_human_promotion_approval_required":True,
      "production_activation_allowed":False,"promotion_allowed":False,
      "direct_mutation":False,"permission_expansion":False,
      "architecture_council_review_complete":passed,
      "central_orchestrator_may_apply_only_after_authorized_promotion":True,
      "automatic_external_spend_eur":0
    }

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--repo-root",type=Path,required=True)
    ap.add_argument("--pilot-result",type=Path,required=True)
    ap.add_argument("--pilot-contract",type=Path,required=True)
    ap.add_argument("--sentinel-receipt",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    ap.add_argument("--technology-watch-status",type=Path)
    ap.add_argument("--github-runs-json",type=Path)
    ap.add_argument("--repository")
    a=ap.parse_args()
    repo=a.repo_root.resolve()
    policy=load(repo/"dev-hub/config/architecture-decision-council.v1.json")
    pilot=load(a.pilot_result);contract=load(a.pilot_contract);sentinel=load(a.sentinel_receipt)
    watch=load(a.technology_watch_status) if a.technology_watch_status else tw.snapshot_status(repo)
    sentinel_policy=load(repo/"dev-hub/config/sentinel-runtime-policy.v1.json")
    repository=a.repository or str(sentinel_policy.get("github_repository") or "chachasan090375/WfGg")
    runs=load(a.github_runs_json) if a.github_runs_json else github_runs(repository,str(contract.get("candidate_revision") or ""))
    result=build_review(policy,pilot,contract,sentinel,watch,runs)
    save(a.output,result)
    print("CHACHA_DEV_PLATFORM_COMPONENT_COUNCIL_REVIEW="+("PASS" if result["technical_review_passed"] else "BLOCK"))
    print("TECHNICAL_ADMISSIBILITY="+("PASS" if result["architecture_council_technical_admissibility"] else "BLOCK"))
    print("HUMAN_PROMOTION_APPROVAL_PRESENT=NO")
    print("PRODUCTION_ACTIVATION_ALLOWED=NO")
    print("PROMOTION_ALLOWED=NO")
    print("INCUMBENT_CONTROL_GROUP=YES")
    print("CHACHA_DEV_PLATFORM_COMPONENT_COUNCIL_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
    return 0 if result["technical_review_passed"] else 20

if __name__=="__main__":raise SystemExit(main())
