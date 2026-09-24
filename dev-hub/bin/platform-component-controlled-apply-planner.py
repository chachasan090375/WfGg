#!/usr/bin/env python3
from __future__ import annotations
import argparse,json
from datetime import datetime,timezone
from pathlib import Path
from typing import Any

SCHEMA="chacha.dev/platform-component-controlled-apply-planner/v1"

def load(p:Path)->dict[str,Any]:
    x=json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise ValueError("JSON_ROOT_NOT_OBJECT:"+str(p))
    return x

def save(p:Path,x:dict[str,Any])->None:
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")

def now_iso()->str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00","Z")

def validate_gate(gate:dict[str,Any])->tuple[bool,list[str]]:
    c=gate.get("controlled_apply_contract") if isinstance(gate.get("controlled_apply_contract"),dict) else {}
    post=set(str(x) for x in (c.get("post_apply_exact_sha_gates_required") or []) if str(x))
    qualification=str(c.get("qualification_workflow_name") or "")
    checks={
      "gate_schema":gate.get("schema")=="chacha.dev/platform-component-promotion-gate/v1",
      "gate_status":gate.get("status")=="PROMOTION_AUTHORIZED_FOR_CONTROLLED_APPLY",
      "human_approval_verified":gate.get("human_approval_verified") is True,
      "promotion_authorized":gate.get("promotion_authorized") is True,
      "controlled_apply_required":gate.get("controlled_apply_required") is True,
      "controlled_apply_contract_created":gate.get("controlled_apply_contract_created") is True,
      "contract_schema":c.get("schema")=="chacha.dev/platform-component-controlled-apply-contract/v1",
      "source_candidate_only":c.get("apply_mode")=="SOURCE_RELEASE_CANDIDATE_INTEGRATION" and c.get("source_candidate_integration_authorized") is True,
      "central_orchestrator_apply_required":c.get("central_orchestrator_apply_required") is True,
      "candidate_owner_adapter_required":c.get("candidate_owner_apply_adapter_required") is True,
      "automatic_apply_forbidden":c.get("automatic_apply") is False,
      "direct_runtime_mutation_forbidden":c.get("direct_runtime_mutation_authorized") is False,
      "production_activation_forbidden":c.get("production_activation_authorized") is False,
      "production_deployment_forbidden":c.get("production_deployment_authorized") is False,
      "production_merge_forbidden":c.get("merge_to_production_branch_authorized") is False,
      "exact_revision_required":c.get("exact_revision_required") is True,
      "rollback_required":c.get("rollback_required") is True,
      "candidate_revision_present":bool(str(c.get("candidate_revision") or "")),
      "incumbent_revision_present":bool(str(c.get("incumbent_revision") or "")),
      "candidate_artifact_present":bool(str(c.get("candidate_artifact_ref") or "")),
      "incumbent_artifact_present":bool(str(c.get("incumbent_artifact_ref") or "")),
      "qualification_workflow_present":bool(qualification),
      "post_apply_qualification_gate_present":bool(qualification) and qualification in post,
      "post_apply_sentinel_gate_present":"ChaCha DEV Sentinel technical assurance" in post,
      "approval_id_present":bool(str(c.get("approval_id") or "")),
      "approval_actor_present":bool(str(c.get("approval_actor") or "")),
      "approval_evidence_present":bool(str(c.get("approval_evidence") or "")),
      "technical_review_digest_present":bool(str(c.get("technical_review_digest") or "")),
      "guardian_post_apply_required":c.get("guardian_post_apply_assurance_required") is True,
      "zero_automatic_external_spend":float(c.get("automatic_external_spend_eur") or 0)==0,
    }
    return all(checks.values()),sorted(k for k,v in checks.items() if not v)

def evaluate(gate:dict[str,Any],registry:dict[str,Any])->dict[str,Any]:
    gate_ok,gate_blockers=validate_gate(gate)
    principles=registry.get("principles") if isinstance(registry.get("principles"),dict) else {}
    required_registry_principles=[
      "source_release_candidate_only",
      "exact_candidate_and_incumbent_revision_required",
      "exact_candidate_and_incumbent_artifact_required",
      "candidate_owner_adapter_required",
      "reversible_apply_required",
      "rollback_adapter_required",
      "direct_runtime_mutation_forbidden",
      "production_activation_forbidden",
      "production_deployment_forbidden",
      "merge_to_production_branch_forbidden",
      "post_apply_exact_sha_qualification_required",
      "guardian_post_apply_assurance_required",
      "sentinel_post_apply_exact_sha_required",
      "central_orchestrator_apply_authority",
      "automatic_apply_forbidden"
    ]
    registry_checks={
      "registry_schema":registry.get("schema")=="chacha.dev/platform-component-apply-adapter-registry/v1",
      "default_admission_deny":registry.get("default_admission")=="DENY",
      "required_principles":all(principles.get(k) is True for k in required_registry_principles),
      "registry_zero_automatic_external_spend":float(principles.get("automatic_external_spend_eur") or 0)==0,
    }
    registry_ok=all(registry_checks.values())
    c=gate.get("controlled_apply_contract") if isinstance(gate.get("controlled_apply_contract"),dict) else {}
    cid=str(c.get("component_id") or gate.get("component_id") or "")
    owner=str(c.get("candidate_owner") or "")
    base={
      "schema":SCHEMA,"generated_at":now_iso(),"component_id":cid,
      "candidate_owner":owner,"candidate_revision":c.get("candidate_revision"),
      "incumbent_revision":c.get("incumbent_revision"),
      "candidate_artifact_ref":c.get("candidate_artifact_ref"),
      "incumbent_artifact_ref":c.get("incumbent_artifact_ref"),
      "approval_id":c.get("approval_id"),"approval_actor":c.get("approval_actor"),
      "technical_review_digest":c.get("technical_review_digest"),
      "apply_mode":"SOURCE_RELEASE_CANDIDATE_INTEGRATION",
      "automatic_apply":False,"direct_runtime_mutation":False,
      "production_activation_allowed":False,"production_deployment_allowed":False,
      "merge_to_production_branch_allowed":False,"permission_expansion":False,
      "central_orchestrator_apply_required":True,"rollback_required":True,
      "automatic_external_spend_eur":0
    }
    if not gate_ok:
        return {**base,"status":"BLOCKED","blockers":["PROMOTION_GATE_INVALID",*gate_blockers],
                "apply_adapter_found":False,"controlled_apply_plan_ready":False,
                "apply_execution_authorized_by_planner":False,"apply_plan":None}
    if not registry_ok:
        return {**base,"status":"BLOCKED",
                "blockers":["APPLY_ADAPTER_REGISTRY_POLICY_INVALID",*sorted(k for k,v in registry_checks.items() if not v)],
                "apply_adapter_found":False,"controlled_apply_plan_ready":False,
                "apply_execution_authorized_by_planner":False,"apply_plan":None}

    adapters=registry.get("adapters") if isinstance(registry.get("adapters"),dict) else {}
    adapter=adapters.get(cid)
    if not isinstance(adapter,dict):
        return {**base,"status":"AWAITING_APPLY_ADAPTER","blockers":["APPLY_ADAPTER_NOT_REGISTERED"],
                "apply_adapter_found":False,"controlled_apply_plan_ready":False,
                "apply_execution_authorized_by_planner":False,"apply_plan":None}

    adapter_checks={
      "adapter_id_present":bool(str(adapter.get("adapter_id") or "")),
      "adapter_status_qualified":str(adapter.get("status") or "")=="QUALIFIED",
      "adapter_owner_matches":str(adapter.get("candidate_owner") or "")==owner and bool(owner),
      "adapter_mode_matches":adapter.get("apply_mode")=="SOURCE_RELEASE_CANDIDATE_INTEGRATION",
      "adapter_reversible":adapter.get("reversible") is True,
      "rollback_adapter_present":bool(str(adapter.get("rollback_adapter_id") or "")),
      "exact_revision_enforced":adapter.get("exact_revision_enforced") is True,
      "direct_runtime_mutation_forbidden":adapter.get("direct_runtime_mutation") is False,
      "production_activation_forbidden":adapter.get("production_activation") is False,
      "production_deployment_forbidden":adapter.get("production_deployment") is False,
      "production_merge_forbidden":adapter.get("merge_to_production_branch") is False,
      "automatic_apply_forbidden":adapter.get("automatic_apply") is False,
      "adapter_qualification_workflow_present":bool(str(adapter.get("qualification_workflow_name") or "")),
      "zero_automatic_external_spend":float(adapter.get("automatic_external_spend_eur") or 0)==0,
    }
    adapter_blockers=sorted(k for k,v in adapter_checks.items() if not v)
    if adapter_blockers:
        return {**base,"status":"BLOCKED","blockers":adapter_blockers,
                "apply_adapter_found":True,"adapter_id":adapter.get("adapter_id"),
                "controlled_apply_plan_ready":False,
                "apply_execution_authorized_by_planner":False,"apply_plan":None}

    plan={
      "schema":"chacha.dev/platform-component-controlled-apply-plan/v1",
      "component_id":cid,"candidate_owner":owner,
      "candidate_revision":c.get("candidate_revision"),"incumbent_revision":c.get("incumbent_revision"),
      "candidate_artifact_ref":c.get("candidate_artifact_ref"),"incumbent_artifact_ref":c.get("incumbent_artifact_ref"),
      "adapter_id":adapter.get("adapter_id"),"rollback_adapter_id":adapter.get("rollback_adapter_id"),
      "adapter_qualification_workflow_name":adapter.get("qualification_workflow_name"),
      "source_qualification_workflow_name":c.get("qualification_workflow_name"),
      "post_apply_exact_sha_gates_required":list(c.get("post_apply_exact_sha_gates_required") or []),
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
    return {**base,"status":"READY_FOR_CENTRAL_ORCHESTRATOR_APPLY","blockers":[],
            "apply_adapter_found":True,"adapter_id":adapter.get("adapter_id"),
            "controlled_apply_plan_ready":True,
            "apply_execution_authorized_by_planner":False,"apply_plan":plan}

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--promotion-gate",type=Path,required=True)
    ap.add_argument("--adapter-registry",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    a=ap.parse_args()
    result=evaluate(load(a.promotion_gate),load(a.adapter_registry))
    save(a.output,result)
    print("CHACHA_DEV_PLATFORM_COMPONENT_CONTROLLED_APPLY_PLANNER="+result["status"])
    print("CONTROLLED_APPLY_PLAN_READY="+("YES" if result["controlled_apply_plan_ready"] else "NO"))
    print("APPLY_EXECUTION_AUTHORIZED_BY_PLANNER=NO")
    print("AUTOMATIC_APPLY=NO")
    print("PRODUCTION_ACTIVATION_ALLOWED=NO")
    print("CHACHA_DEV_PLATFORM_COMPONENT_CONTROLLED_APPLY_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
    return 0 if result["status"] in {"AWAITING_APPLY_ADAPTER","READY_FOR_CENTRAL_ORCHESTRATOR_APPLY"} else 20

if __name__=="__main__":raise SystemExit(main())
