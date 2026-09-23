#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,time
from pathlib import Path
from typing import Any

SCHEMA="chacha.dev/compromise-release-receipt/v1"

def load(path:Path)->dict[str,Any]:
    x=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise SystemExit("JSON_ROOT_NOT_OBJECT:"+str(path))
    return x
def canon(v:Any)->str:return json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(",",":"))
def digest(v:Any)->str:return "sha256:"+hashlib.sha256(canon(v).encode()).hexdigest()
def now()->str:return time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())

def normalize_review(x:dict[str,Any])->dict[str,Any]:
    if x.get("schema")!="chacha.dev/compromise-agent-review/v1":
        raise SystemExit("AGENT_REVIEW_SCHEMA_INVALID")
    return {
      "agent":str(x.get("agent") or ""),
      "project_id":str(x.get("project_id") or ""),
      "revision":str(x.get("revision") or ""),
      "compromise_digest":str(x.get("compromise_digest") or ""),
      "verdict":str(x.get("verdict") or ""),
      "hard_objections":[str(v) for v in x.get("hard_objections") or []],
      "soft_objections":[str(v) for v in x.get("soft_objections") or []],
      "evidence_refs":[str(v) for v in x.get("evidence_refs") or []],
      "implementation_verified":x.get("implementation_verified") is True,
      "source_authority":str(x.get("source_authority") or ""),
      "source_reverified":x.get("source_reverified") is True,
      "original_proposal_referenced":x.get("original_proposal_referenced") is True,
      "post_implementation_second_read":x.get("post_implementation_second_read") is True,
      "reviewed_at":x.get("reviewed_at")
    }

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--project-id",required=True)
    ap.add_argument("--revision",required=True)
    ap.add_argument("--policy",type=Path,required=True)
    ap.add_argument("--compromise",type=Path,required=True)
    ap.add_argument("--council",type=Path,required=True)
    ap.add_argument("--implementation-verification",type=Path,required=True)
    ap.add_argument("--agent-review",type=Path,action="append",default=[])
    ap.add_argument("--output",type=Path,required=True)
    a=ap.parse_args()

    policy=load(a.policy);comp=load(a.compromise);council=load(a.council);verify=load(a.implementation_verification)
    required_defs=[x for x in policy.get("required_agents") or [] if isinstance(x,dict)]
    required=[str(x.get("id")) for x in required_defs]
    required_kind={str(x.get("id")):str(x.get("kind") or "") for x in required_defs}
    reviews=[normalize_review(load(p)) for p in a.agent_review]
    by_agent={r["agent"]:r for r in reviews if r["agent"]}
    reasons=[]

    if comp.get("schema")!="chacha.dev/multi-agent-compromise/v1":reasons.append("COMPROMISE_SCHEMA_INVALID")
    compromise_digest=str(comp.get("dossier_digest") or digest(comp))
    if comp.get("central_compromise_search_attempted") is not True:reasons.append("CENTRAL_COMPROMISE_SEARCH_MISSING")
    if comp.get("central_compromise_found") is not True:reasons.append("CENTRAL_COMPROMISE_NOT_FOUND")
    if comp.get("continuation_allowed") is not True:reasons.append("COMPROMISE_CONTINUATION_NOT_ALLOWED")
    if comp.get("revision_request_only_after_failed_compromise") is not True:reasons.append("REVISION_POLICY_INVALID")

    if council.get("schema")!="chacha.dev/architecture-decision-council/v1":reasons.append("COUNCIL_SCHEMA_INVALID")
    council_comp=council.get("logic_ux_compromise") or {}
    if council.get("dispatch_allowed") is not True:reasons.append("ARCHITECTURE_COUNCIL_NOT_READY")
    if council_comp.get("required") is not True or council_comp.get("valid") is not True:
        reasons.append("ARCHITECTURE_COUNCIL_DID_NOT_ACCEPT_COMPROMISE")
    if str(council_comp.get("dossier_digest") or "")!=compromise_digest:
        reasons.append("ARCHITECTURE_COUNCIL_COMPROMISE_DIGEST_MISMATCH")

    if verify.get("schema")!="chacha.dev/implementation-verification/v1":reasons.append("IMPLEMENTATION_VERIFICATION_SCHEMA_INVALID")
    if str(verify.get("project_id") or "")!=a.project_id:reasons.append("IMPLEMENTATION_PROJECT_MISMATCH")
    if str(verify.get("revision") or "")!=a.revision:reasons.append("IMPLEMENTATION_REVISION_MISMATCH")
    if str(verify.get("compromise_digest") or "")!=compromise_digest:reasons.append("IMPLEMENTATION_COMPROMISE_MISMATCH")
    if verify.get("status")!="PASS":reasons.append("IMPLEMENTATION_NOT_VERIFIED")
    if verify.get("non_dominated_compromise_verified") is not True:reasons.append("NON_DOMINATED_COMPROMISE_NOT_VERIFIED")
    if verify.get("hard_constraints_satisfied") is not True:reasons.append("HARD_CONSTRAINTS_NOT_SATISFIED")

    architecture_changed=verify.get("architecture_changed") is True
    if architecture_changed:
        if verify.get("technology_watch_status")!="PASS":reasons.append("ARCHITECTURE_CHANGE_TECHNOLOGY_WATCH_NOT_PASS")
        if verify.get("architecture_council_status")!="PASS":reasons.append("ARCHITECTURE_CHANGE_COUNCIL_NOT_PASS")

    missing=[x for x in required if x not in by_agent]
    if missing:reasons.append("REQUIRED_AGENT_REVIEW_MISSING:"+",".join(sorted(missing)))

    accounted=[]
    for agent in required:
        r=by_agent.get(agent)
        if not r:continue
        accounted.append(agent)
        if r["project_id"]!=a.project_id:reasons.append("AGENT_PROJECT_MISMATCH:"+agent)
        if r["revision"]!=a.revision:reasons.append("AGENT_REVISION_MISMATCH:"+agent)
        if r["compromise_digest"]!=compromise_digest:reasons.append("AGENT_COMPROMISE_MISMATCH:"+agent)
        if r["verdict"]!="ACCEPT":reasons.append("AGENT_NOT_ACCEPT:"+agent+":"+r["verdict"])
        if r["hard_objections"]:reasons.append("UNRESOLVED_HARD_OBJECTION:"+agent)
        if not r["implementation_verified"]:reasons.append("AGENT_IMPLEMENTATION_NOT_VERIFIED:"+agent)
        if not r["evidence_refs"]:reasons.append("AGENT_EVIDENCE_MISSING:"+agent)
        if required_kind.get(agent)=="external" and not r["source_reverified"]:
            reasons.append("EXTERNAL_REVIEW_NOT_SOURCE_REVERIFIED:"+agent)
        if required_kind.get(agent)=="internal":
            if not r["original_proposal_referenced"]:reasons.append("INTERNAL_ORIGINAL_PROPOSAL_NOT_REFERENCED:"+agent)
            if not r["post_implementation_second_read"]:reasons.append("INTERNAL_POST_IMPLEMENTATION_SECOND_READ_MISSING:"+agent)

    release_allowed=not reasons
    result={
      "schema":SCHEMA,
      "version":"1.0.0",
      "project_id":a.project_id,
      "revision":a.revision,
      "compromise_digest":compromise_digest,
      "required_agents":required,
      "accounted_agents":accounted,
      "all_required_agents_accounted_for":set(accounted)==set(required),
      "external_reviews_source_reverified":all(
        (by_agent.get(agent) or {}).get("source_reverified") is True
        for agent in required if required_kind.get(agent)=="external"
      ),
      "internal_second_reads_verified":all(
        (by_agent.get(agent) or {}).get("original_proposal_referenced") is True and
        (by_agent.get(agent) or {}).get("post_implementation_second_read") is True
        for agent in required if required_kind.get(agent)=="internal"
      ),
      "unanimous_preferences_required":False,
      "majority_vote_used":False,
      "central_compromise_search_attempted":comp.get("central_compromise_search_attempted") is True,
      "central_compromise_found":comp.get("central_compromise_found") is True,
      "architecture_council_consumed_compromise":council_comp.get("valid") is True,
      "implementation_verified":verify.get("status")=="PASS",
      "non_dominated_compromise_verified":verify.get("non_dominated_compromise_verified") is True,
      "release_allowed":release_allowed,
      "reason_codes":reasons,
      "direct_mutation":False,
      "remediation_owner":"central-orchestrator",
      "technology_watch_required_for_architecture_change":True,
      "architecture_council_final_authority":True,
      "automatic_external_spend_eur":0,
      "checked_at":now()
    }
    result["receipt_digest"]=digest(result)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print("CHACHA_DEV_COMPROMISE_RELEASE_GATE="+("PASS" if release_allowed else "BLOCK"))
    print("REQUIRED_AGENTS="+str(len(required)))
    print("ACCOUNTED_AGENTS="+str(len(accounted)))
    print("RELEASE_ALLOWED="+("YES" if release_allowed else "NO"))
    print("REVISION_REQUEST_ONLY_AFTER_FAILED_COMPROMISE=YES")
    return 0 if release_allowed else 20

if __name__=="__main__":raise SystemExit(main())
