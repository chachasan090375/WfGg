#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json
from datetime import datetime,timezone
from pathlib import Path
from typing import Any
import technology_watch_runtime as tw

SCHEMA="chacha.dev/architecture-council-agent-candidate-review/v1"

def load(p:Path)->dict[str,Any]:
    x=json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise ValueError("JSON_ROOT_NOT_OBJECT:"+str(p))
    return x
def save(p:Path,x:dict[str,Any])->None:
    p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
def now_iso()->str:return datetime.now(timezone.utc).isoformat().replace("+00:00","Z")
def sha256(p:Path)->str:return "sha256:"+hashlib.sha256(p.read_bytes()).hexdigest()

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--repo-root",type=Path,required=True)
    ap.add_argument("--runtime-root",type=Path,required=True)
    ap.add_argument("--readiness",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    ap.add_argument("--technology-watch-status",type=Path)
    a=ap.parse_args()
    repo=a.repo_root.resolve();runtime=a.runtime_root.resolve()
    policy_path=repo/"dev-hub/config/architecture-decision-council.v1.json"
    manifest_path=repo/"dev-hub/candidates/acceptance-engineer/v661/candidate-manifest.json"
    incumbent=repo/"dev-hub/bin/acceptance-engine.py"
    readiness=load(a.readiness);policy=load(policy_path);manifest=load(manifest_path)
    review_policy=policy.get("agent_candidate_review") or {}
    watch=load(a.technology_watch_status) if a.technology_watch_status else tw.snapshot_status(repo)
    checks={
      "council_policy_enabled":review_policy.get("enabled") is True,
      "central_orchestrator_final_decider":policy.get("central_orchestrator_is_final_decider") is True,
      "no_single_foundry_final_authority":policy.get("no_single_foundry_may_select_final_architecture") is True,
      "candidate_identity_matches":str(readiness.get("candidate_id") or "")==str(manifest.get("candidate_id") or ""),
      "agent_foundry_owner":str(readiness.get("owner") or "")==str(review_policy.get("owner_must_be") or "agent-foundry")=="agent-foundry",
      "readiness_complete":readiness.get("evidence_complete_for_review") is True,
      "readiness_holds_incumbent":str(readiness.get("decision") or "")=="READY_FOR_ARCHITECTURE_COUNCIL_REVIEW_HOLD_INCUMBENT",
      "measurable_gain":readiness.get("measurable_gain_verified") is True,
      "guardian_active":readiness.get("guardian_all_hooks_active") is True,
      "sentinel_exact_revision_success":readiness.get("sentinel_exact_revision_success") is True,
      "technology_watch_fresh":watch.get("fresh") is True and watch.get("state")=="FRESH",
      "logician_falsification":readiness.get("logician_falsification_satisfied") is True,
      "candidate_isolated":manifest.get("isolated") is True,
      "incumbent_control_group":manifest.get("incumbent_control_group") is True,
      "production_entrypoint_unchanged":readiness.get("production_entrypoint_changed") is False,
      "self_mutation_forbidden":manifest.get("active_self_mutation") is False and readiness.get("active_self_mutation") is False,
      "self_promotion_forbidden":manifest.get("self_promotion") is False and readiness.get("self_promotion") is False,
      "permission_expansion_forbidden":manifest.get("permission_expansion") is False and readiness.get("permission_expansion") is False,
      "zero_automatic_external_spend":float(readiness.get("automatic_external_spend_eur") or 0)==0 and float(manifest.get("automatic_external_spend_eur") or 0)==0,
      "auto_promotion_forbidden":review_policy.get("architecture_council_may_auto_promote") is False,
      "human_approval_required":review_policy.get("explicit_human_promotion_approval_required") is True,
      "human_approval_absent":readiness.get("human_explicit_promotion_approval_present") is False
    }
    passed=all(checks.values())
    decision="TECHNICALLY_ADMISSIBLE_AWAIT_EXPLICIT_HUMAN_PROMOTION_APPROVAL" if passed else "COUNCIL_REVIEW_BLOCKED_HOLD_INCUMBENT"
    result={
      "schema":SCHEMA,"generated_at":now_iso(),"candidate_id":manifest.get("candidate_id"),
      "review_authority":"architecture-council","policy_digest":sha256(policy_path),"manifest_digest":sha256(manifest_path),
      "readiness_digest":sha256(a.readiness),"incumbent_digest":sha256(incumbent),
      "checks":checks,"technical_review_passed":passed,"decision":decision,
      "architecture_council_review_complete":passed,
      "architecture_council_technical_admissibility":passed,
      "architecture_council_promotion_approval_present":False,
      "human_explicit_promotion_approval_present":False,
      "explicit_human_promotion_approval_required":True,
      "next_action":"AWAIT_EXPLICIT_HUMAN_PROMOTION_APPROVAL" if passed else "REMEDIATE_AND_REVIEW",
      "incumbent_control_group":True,"production_entrypoint_changed":False,
      "production_activation_allowed":False,"promotion_allowed":False,
      "direct_mutation":False,"active_self_mutation":False,"self_promotion":False,"permission_expansion":False,
      "canonical_observation_bus_mutation":False,"benchmark_evidence_mutation":False,
      "architecture_council_final_authority":True,"automatic_external_spend_eur":0
    }
    save(a.output,result)
    print("CHACHA_DEV_V664_ACCEPTANCE_ARCHITECTURE_COUNCIL_REVIEW="+("PASS" if passed else "BLOCK"))
    print("CHACHA_DEV_V664_ACCEPTANCE_TECHNICAL_ADMISSIBILITY="+("PASS" if passed else "BLOCK"))
    print("CHACHA_DEV_V664_HUMAN_PROMOTION_APPROVAL_PRESENT=NO")
    print("CHACHA_DEV_V664_ACCEPTANCE_PRODUCTION_ACTIVATION=NO")
    print("CHACHA_DEV_V664_ACCEPTANCE_PROMOTION=NO")
    print("CHACHA_DEV_V664_INCUMBENT_CONTROL_GROUP=YES")
    print("CHACHA_DEV_V664_SELF_MUTATION=NO")
    print("CHACHA_DEV_V664_SELF_PROMOTION=NO")
    print("CHACHA_DEV_V664_ARCHITECTURE_COUNCIL_FINAL_AUTHORITY=YES")
    print("CHACHA_DEV_V664_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
    return 0 if passed else 20

if __name__=="__main__":raise SystemExit(main())
