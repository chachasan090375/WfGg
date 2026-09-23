#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,time
from pathlib import Path
from typing import Any

SCHEMA="chacha.dev/multi-agent-compromise/v1"

def load(p:Path)->dict[str,Any]:
    x=json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise SystemExit("JSON_ROOT_NOT_OBJECT:"+str(p))
    return x
def now()->str:return time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())
def canon(v:Any)->str:return json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(",",":"))
def digest(v:Any)->str:return "sha256:"+hashlib.sha256(canon(v).encode()).hexdigest()
def uniq(xs):return list(dict.fromkeys(str(x) for x in xs if str(x)))

def internal_positions(logic:dict[str,Any],ux:dict[str,Any])->list[dict[str,Any]]:
    lp={
      "agent":"logician","status":str(logic.get("challenge_status") or "KEEP"),
      "proposal":{
        "kind":"LOGIC_PATH",
        "candidate":logic.get("best_candidate"),
        "score_gain":logic.get("score_gain"),
        "recommended_next_action":logic.get("recommended_next_action")
      },
      "hard_constraints":[],
      "soft_constraints":[
        {"key":"logic.candidate_id","value":(logic.get("best_candidate") or {}).get("candidate_id")},
        {"key":"logic.execution_mode","value":(logic.get("best_candidate") or {}).get("execution_mode")}
      ],
      "evidence_refs":[str(logic.get("report_digest") or digest(logic))]
    }
    ux_contract=ux.get("ux_contract") or {}
    ep={
      "agent":"ergonomist","status":str(ux.get("challenge_status") or "KEEP"),
      "proposal":{
        "kind":"UX_PLAN",
        "ux_contract":ux_contract,
        "recommended_next_action":ux.get("recommended_next_action")
      },
      "hard_constraints":[],
      "soft_constraints":[
        {"key":"ux.primary_job_first","value":True},
        {"key":"ux.curator_handoff_required","value":bool(ux_contract.get("curator_handoff_required"))}
      ],
      "evidence_refs":[str(ux.get("report_digest") or digest(ux))]
    }
    return [lp,ep]

def external_position(report:dict[str,Any])->dict[str,Any]:
    agent=str(report.get("agent") or report.get("assurance_role") or "")
    if not agent:raise SystemExit("AGENT_REPORT_MISSING_AGENT")
    status=str(report.get("status") or report.get("challenge_status") or "KEEP")
    if status in {"PASS","ACCEPT","OBSERVE"}:status="KEEP"
    if status in {"BLOCK","CRITICAL"}:status="REPLAN_REQUIRED"
    return {
      "agent":agent,"status":status,
      "proposal":report.get("proposal"),
      "hard_constraints":[x for x in report.get("hard_constraints") or [] if isinstance(x,dict)],
      "soft_constraints":[x for x in report.get("soft_constraints") or report.get("constraints") or [] if isinstance(x,dict)],
      "evidence_refs":uniq(report.get("evidence_refs") or [digest(report)])
    }

def conflict_key(c:dict[str,Any])->str:
    return str(c.get("key") or c.get("id") or "")

def hard_conflicts(positions:list[dict[str,Any]])->list[dict[str,Any]]:
    seen:dict[str,tuple[Any,str]]={}
    conflicts=[]
    for p in positions:
        for c in p.get("hard_constraints") or []:
            k=conflict_key(c)
            if not k:continue
            v=c.get("value")
            if k in seen and seen[k][0]!=v:
                conflicts.append({
                  "key":k,
                  "left_agent":seen[k][1],"left_value":seen[k][0],
                  "right_agent":p["agent"],"right_value":v
                })
            else:seen[k]=(v,p["agent"])
    return conflicts

def revision_request(targets:list[str],positions:list[dict[str,Any]],conflicts:list[dict[str,Any]],cycle:int)->dict[str,Any]:
    cross=[]
    for p in positions:
        if p["agent"] in targets:continue
        for c in (p.get("hard_constraints") or [])+(p.get("soft_constraints") or []):
            if isinstance(c,dict):cross.append({"source_agent":p["agent"],**c})
    payload={
      "schema":"chacha.dev/agent-revision-request/v1",
      "cycle":cycle,"target_agents":sorted(set(targets)),
      "reason":"NO_ADMISSIBLE_CENTRAL_COMPROMISE",
      "hard_conflicts":conflicts,
      "constraints_to_consider":cross,
      "must_preserve_prior_evidence":True,
      "must_reference_superseded_proposal":True,
      "central_compromise_search_attempted":True,
      "direct_mutation":False
    }
    payload["request_id"]="revreq-"+hashlib.sha256(canon(payload).encode()).hexdigest()[:20]
    return payload

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--policy",type=Path,required=True)
    ap.add_argument("--logic-report",type=Path,required=True)
    ap.add_argument("--ux-report",type=Path,required=True)
    ap.add_argument("--agent-report",type=Path,action="append",default=[])
    ap.add_argument("--cycle",type=int,default=1)
    ap.add_argument("--output",type=Path,required=True)
    a=ap.parse_args()
    policy=load(a.policy)
    positions=internal_positions(load(a.logic_report),load(a.ux_report))
    positions.extend(external_position(load(p)) for p in a.agent_report)

    conflicts=hard_conflicts(positions)
    missing_proposal=[
      p["agent"] for p in positions
      if p["status"]=="REPLAN_REQUIRED" and p.get("proposal") is None and not p.get("hard_constraints")
    ]
    compromise_possible=not conflicts and not missing_proposal

    merged_hard={}
    merged_soft=[]
    for p in positions:
        for c in p.get("hard_constraints") or []:
            k=conflict_key(c)
            if k:merged_hard[k]={"value":c.get("value"),"source_agent":p["agent"]}
        for c in p.get("soft_constraints") or []:
            merged_soft.append({"source_agent":p["agent"],**c})

    revision_requests=[]
    if compromise_possible:
        challenge="COMPROMISE_PROPOSED"
        continuation=True
        negotiation_state="CENTRAL_COMPROMISE_FOUND"
    else:
        challenge="REPLAN_REQUIRED"
        continuation=False
        negotiation_state="REVISION_REQUIRED_AFTER_FAILED_COMPROMISE"
        targets=missing_proposal[:]
        for cf in conflicts:targets.extend([cf["left_agent"],cf["right_agent"]])
        revision_requests=[revision_request(targets,positions,conflicts,a.cycle)]

    result={
      "schema":SCHEMA,"version":"1.0.0","generated_at":now(),"cycle":a.cycle,
      "positions":positions,
      "central_compromise_search_attempted":True,
      "central_compromise_found":compromise_possible,
      "negotiation_state":negotiation_state,
      "challenge_status":challenge,
      "continuation_allowed":continuation,
      "compromise":{
        "logic_proposal":next((p["proposal"] for p in positions if p["agent"]=="logician"),None),
        "ux_proposal":next((p["proposal"] for p in positions if p["agent"]=="ergonomist"),None),
        "hard_constraints":merged_hard,
        "soft_constraints":merged_soft,
        "non_dominated_selection_required":True,
        "must_be_verified_after_implementation":True
      } if compromise_possible else None,
      "hard_conflicts":conflicts,
      "missing_actionable_proposals":missing_proposal,
      "revision_requests":revision_requests,
      "revision_request_only_after_failed_compromise":True,
      "central_brain_must_not_request_revision_when_compromise_exists":True,
      "current_plan_has_no_incumbency_privilege":True,
      "technology_watch_required_for_architecture_change":True,
      "architecture_council_final_authority":True,
      "direct_mutation":False,"automatic_external_spend_eur":0
    }
    result["dossier_digest"]=digest(result)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print("CHACHA_DEV_MULTI_AGENT_COMPROMISE=PASS")
    print("CENTRAL_COMPROMISE_FOUND="+("YES" if compromise_possible else "NO"))
    print("REVISION_REQUESTS="+str(len(revision_requests)))
    print("CONTINUATION_ALLOWED="+("YES" if continuation else "NO"))
    return 0

if __name__=="__main__":raise SystemExit(main())
