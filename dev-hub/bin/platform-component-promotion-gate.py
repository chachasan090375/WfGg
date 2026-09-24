#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,subprocess,sys
from datetime import datetime,timezone
from pathlib import Path
from typing import Any

SCHEMA="chacha.dev/platform-component-promotion-gate/v1"
SYSTEM_ACTORS={
 "central-orchestrator","guardian","sentinel","curator","bastion","intendant",
 "logician","ergonomist","architecture-council","branch-foundry","capability-foundry",
 "platform-component-pilot-runner"
}

def load(p:Path)->dict[str,Any]:
    x=json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise ValueError("JSON_ROOT_NOT_OBJECT:"+str(p))
    return x
def save(p:Path,x:dict[str,Any])->None:
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
def now_iso()->str:return datetime.now(timezone.utc).isoformat().replace("+00:00","Z")

def evaluate(review:dict[str,Any],status:dict[str,Any],state:dict[str,Any],ledger:dict[str,Any])->dict[str,Any]:
    req=review.get("approval_request") if isinstance(review.get("approval_request"),dict) else {}
    approval_id=str(req.get("approval_id") or "")
    ledger_approval=((ledger.get("approvals") or {}).get(approval_id) or {}) if approval_id else {}
    state_approval=((((state.get("state") or {}).get("approvals") or {}).get(approval_id) or {})
                    if approval_id else {})
    actor=str(ledger_approval.get("actor") or "")
    evidence=str(ledger_approval.get("evidence") or "")
    expected_evidence=str(req.get("evidence") or "")
    status_details=status.get("details") if isinstance(status.get("details"),dict) else {}
    integrity=status_details.get("integrity") if isinstance(status_details.get("integrity"),dict) else {}

    checks={
      "council_schema":review.get("schema")=="chacha.dev/architecture-council-platform-component-review/v1",
      "council_technical_review_passed":review.get("technical_review_passed") is True,
      "council_technical_admissibility":review.get("architecture_council_technical_admissibility") is True,
      "council_still_holds_incumbent":review.get("promotion_allowed") is False and review.get("production_activation_allowed") is False,
      "human_approval_request_created":review.get("human_approval_request_created") is True,
      "approval_request_schema":req.get("schema")=="chacha.dev/protected-human-approval-request/v1",
      "approval_request_project":req.get("project")=="chacha-dev-platform",
      "approval_request_operation":req.get("operation")=="record-approval",
      "approval_request_actor_real_human":req.get("actor_requirement")=="real-human",
      "approval_synthesis_forbidden":req.get("agent_or_api_approval_synthesis_forbidden") is True,
      "review_digest_bound":bool(review.get("technical_review_digest")) and req.get("technical_review_digest")==review.get("technical_review_digest"),
      "approval_evidence_bound":bool(expected_evidence) and expected_evidence=="architecture-council-platform-review:"+str(review.get("technical_review_digest") or ""),
      "project_control_status_ready":status.get("status")=="READY",
      "project_control_profile_platform":status_details.get("control_profile")=="platform",
      "project_control_lifecycle_unmanaged":status_details.get("lifecycle_managed") is False,
      "project_control_human_boundary_protected":status_details.get("protected_human_approval_boundary") is True,
      "project_control_no_pending_transactions":int(status_details.get("pending_transactions") or 0)==0,
      "project_control_journal_chain_ok":integrity.get("JOURNAL_CHAIN")=="OK",
      "state_schema":state.get("schema")=="chacha.dev/control-plane-state/v1",
      "state_project":state.get("project")=="chacha-dev-platform",
      "state_profile_platform":str((((state.get("state") or {}).get("identity") or {}).get("control_profile") or ""))=="platform",
      "state_bootstrap_marker":bool((((state.get("state") or {}).get("evidence") or {}).get("control_plane_ledger_initialized") is True),
      "ledger_schema":ledger.get("schema")=="chacha.dev/evidence-ledger/v1",
      "ledger_project":ledger.get("project")=="chacha-dev-platform",
      "approval_id_present":bool(approval_id),
      "ledger_approval_status":ledger_approval.get("status")=="APPROVED",
      "ledger_approval_actor_present":bool(actor),
      "ledger_approval_actor_human":bool(actor) and actor not in SYSTEM_ACTORS,
      "ledger_approval_evidence_exact":bool(expected_evidence) and evidence==expected_evidence,
      "state_approval_status":state_approval.get("status")=="APPROVED",
      "state_approval_actor_matches":bool(actor) and state_approval.get("actor")==actor,
      "state_approval_evidence_matches":bool(expected_evidence) and state_approval.get("evidence")==expected_evidence,
      "candidate_revision_bound":bool(req.get("candidate_revision")) and req.get("candidate_revision")==review.get("candidate_revision"),
      "incumbent_revision_bound":bool(req.get("incumbent_revision")) and req.get("incumbent_revision")==review.get("incumbent_revision"),
      "automatic_external_spend_zero":float(req.get("automatic_external_spend_eur") or 0)==0 and float(review.get("automatic_external_spend_eur") or 0)==0,
    }
    core_ready=all(v for k,v in checks.items() if not k.startswith("ledger_approval_") and not k.startswith("state_approval_"))
    approval_ready=all(checks[k] for k in checks if k.startswith("ledger_approval_") or k.startswith("state_approval_"))
    approval_record_present=bool(ledger_approval or state_approval)
    if not core_ready:
        gate_status="BLOCKED"
    elif not approval_record_present:
        gate_status="AWAITING_HUMAN_APPROVAL"
    elif not approval_ready:
        gate_status="BLOCKED"
    else:
        gate_status="PROMOTION_AUTHORIZED_FOR_CONTROLLED_APPLY"
    blockers=sorted(k for k,v in checks.items() if not v)
    return {
      "schema":SCHEMA,"generated_at":now_iso(),"component_id":review.get("component_id"),
      "candidate_revision":review.get("candidate_revision"),"incumbent_revision":review.get("incumbent_revision"),
      "approval_id":approval_id,"approval_actor":actor or None,
      "status":gate_status,"checks":checks,"blockers":blockers,
      "human_approval_record_present":approval_record_present,
      "human_approval_verified":approval_ready and core_ready,
      "promotion_authorized":gate_status=="PROMOTION_AUTHORIZED_FOR_CONTROLLED_APPLY",
      "controlled_apply_required":True,"automatic_apply":False,
      "production_activation_allowed":False,
      "production_deployment_requires_separate_controlled_handoff":True,
      "direct_runtime_mutation":False,"permission_expansion":False,
      "central_orchestrator_remains_apply_authority":True,
      "rollback_required":True,"automatic_external_spend_eur":0
    }

def project_paths(policy:dict[str,Any],project:str)->tuple[Path,Path]:
    runtime=policy.get("runtime") or {}
    return (Path(str(runtime.get("state_root","/opt/chacha-dev/runtime/state")))/project/"state.json",
            Path(str(runtime.get("evidence_root","/opt/chacha-dev/runtime/evidence")))/project/"ledger.json")

def live_status(repo_root:Path,policy_path:Path,project:str)->dict[str,Any]:
    script=repo_root/"dev-hub/bin/project-control.py"
    p=subprocess.run([sys.executable,str(script),"--repo-root",str(repo_root),"--policy",str(policy_path),
                      "--json","status","--project",project],
                     stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=60)
    if not p.stdout.strip():raise RuntimeError("PROJECT_CONTROL_STATUS_EMPTY:"+p.stderr[-500:])
    value=json.loads(p.stdout)
    if not isinstance(value,dict):raise RuntimeError("PROJECT_CONTROL_STATUS_INVALID")
    return value

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--repo-root",type=Path,required=True)
    ap.add_argument("--council-review",type=Path,required=True)
    ap.add_argument("--project",default="chacha-dev-platform")
    ap.add_argument("--project-control-policy",type=Path)
    ap.add_argument("--output",type=Path,required=True)
    a=ap.parse_args()
    root=a.repo_root.resolve()
    policy_path=a.project_control_policy or (root/"dev-hub/config/project-control.v1.json")
    policy=load(policy_path)
    state_path,ledger_path=project_paths(policy,a.project)
    result=evaluate(load(a.council_review),live_status(root,policy_path,a.project),load(state_path),load(ledger_path))
    save(a.output,result)
    print("CHACHA_DEV_PLATFORM_COMPONENT_PROMOTION_GATE="+result["status"])
    print("HUMAN_APPROVAL_VERIFIED="+("YES" if result["human_approval_verified"] else "NO"))
    print("PROMOTION_AUTHORIZED="+("YES" if result["promotion_authorized"] else "NO"))
    print("AUTOMATIC_APPLY=NO")
    print("PRODUCTION_ACTIVATION_ALLOWED=NO")
    print("CHACHA_DEV_PLATFORM_COMPONENT_PROMOTION_GATE_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
    return 0 if result["status"] in {"AWAITING_HUMAN_APPROVAL","PROMOTION_AUTHORIZED_FOR_CONTROLLED_APPLY"} else 20

if __name__=="__main__":raise SystemExit(main())
