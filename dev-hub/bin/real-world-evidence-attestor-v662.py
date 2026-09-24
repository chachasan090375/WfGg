#!/usr/bin/env python3
from __future__ import annotations

import argparse,json
from datetime import datetime,timezone
from pathlib import Path
from typing import Any

SCHEMA="chacha.dev/real-world-agent-attestation/v1"
VERIFIER="v662-real-world-evidence-attestor"
TARGETS=(
  "agent-foundry-architect","branch-foundry-architect","capability-foundry-architect",
  "logician","ergonomist","technology-watch-agent"
)

def load(path:Path)->dict[str,Any]:
    x=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise ValueError("JSON_ROOT_NOT_OBJECT:"+str(path))
    return x

def save(path:Path,x:dict[str,Any])->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")

def now_iso()->str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00","Z")

def run_dirs(runtime_root:Path)->list[Path]:
    root=runtime_root/"golden-path-runs"
    return sorted([p for p in root.iterdir() if p.is_dir()]) if root.is_dir() else []

def _same_path(value:Any,path:Path)->bool:
    try:return Path(str(value or "")).resolve()==path.resolve()
    except Exception:return False

def _advisors_pass(council:dict[str,Any],advisor:str)->bool:
    rows=[x for x in (council.get("decisions") or []) if isinstance(x,dict)]
    return bool(rows) and all(str((x.get("mandatory_advisors") or {}).get(advisor) or "")=="PASS" for x in rows)

def _zero_spend(value:Any)->bool:
    try:return float(value or 0)==0
    except Exception:return False

def _result(agent:str,run:Path,checks:dict[str,bool],refs:list[Path|str],extra:dict[str,Any]|None=None)->dict[str,Any]:
    out={
      "case_id":agent+":"+run.name,
      "run_id":run.name,
      "passed":all(checks.values()),
      "checks":checks,
      "source_refs":[str(x) for x in refs]
    }
    if extra:out.update(extra)
    return out

def _planning(run:Path,name:str)->Path:
    return run/"planning"/name

def agent_foundry_case(run:Path)->dict[str,Any]|None:
    top=_planning(run,"agent-topology.json");finalp=_planning(run,"final-plan.json")
    bootp=_planning(run,"bootstrap-result.json");councilp=_planning(run,"architecture-decision-council.json")
    if not all(p.is_file() for p in (top,finalp,bootp,councilp)):return None
    t=load(top);f=load(finalp);b=load(bootp);c=load(councilp)
    if t.get("schema")!="chacha.dev/agent-topology/v1":return None
    td={str(x.get("package_id") or ""):x for x in (t.get("decisions") or []) if isinstance(x,dict)}
    fp={str(x.get("id") or ""):x for x in (f.get("packages") or []) if isinstance(x,dict)}
    linked=bool(td) and all(
      pid in fp and
      str(fp[pid].get("agent_topology_status") or "")=="RESOLVED" and
      str(fp[pid].get("execution_mode") or "")==str(row.get("decision") or "") and
      str(fp[pid].get("agent_id") or "")==str(row.get("agent_id") or "")
      for pid,row in td.items()
    )
    watch_ok=t.get("technology_watch_consulted") is True and all(
      (row.get("technology_watch") or {}).get("consulted") is True and
      _zero_spend((row.get("technology_watch") or {}).get("automatic_external_spend_eur"))
      for row in td.values()
    )
    checks={
      "project_identity":str(t.get("project_id") or "")==str(b.get("project_id") or ""),
      "bootstrap_consumed_topology":_same_path(b.get("agent_topology"),top),
      "final_plan_consumed_decisions":linked,
      "architecture_council_advisor_pass":_advisors_pass(c,"agent-foundry"),
      "technology_watch_consulted":watch_ok,
      "memory_context_consumed":t.get("central_memory_recall_consumed") is True,
      "dispatch_allowed_after_foundry":b.get("domain_dispatch_allowed") is True,
      "architecture_council_final_authority":b.get("architecture_decision_allowed") is True,
      "automatic_external_spend_zero":_zero_spend(b.get("external_spend_eur"))
    }
    return _result("agent-foundry-architect",run,checks,[top,finalp,bootp,councilp],
                   {"decision_count":len(td)})

def branch_foundry_case(run:Path)->dict[str,Any]|None:
    top=_planning(run,"branch-topology-effective.json");finalp=_planning(run,"final-plan.json")
    bootp=_planning(run,"bootstrap-result.json");councilp=_planning(run,"architecture-decision-council.json")
    if not all(p.is_file() for p in (top,finalp,bootp,councilp)):return None
    t=load(top);f=load(finalp);b=load(bootp);c=load(councilp)
    if t.get("schema")!="chacha.dev/branch-topology/v1":return None
    td={str(x.get("package_id") or ""):x for x in (t.get("decisions") or []) if isinstance(x,dict)}
    fp={str(x.get("id") or ""):x for x in (f.get("packages") or []) if isinstance(x,dict)}
    linked=bool(td) and all(
      pid in fp and
      str(fp[pid].get("branch_id") or "")==str(row.get("branch_id") or "") and
      str(fp[pid].get("branch_decision") or "")==str(row.get("decision") or "") and
      bool(fp[pid].get("runtime_required"))==bool(row.get("runtime_required"))
      for pid,row in td.items()
    )
    runtime_expected=sum(1 for x in td.values() if x.get("runtime_required") is True)
    watch_ok=t.get("technology_watch_consulted") is True and all(
      (row.get("technology_watch") or {}).get("consulted") is True and
      _zero_spend((row.get("technology_watch") or {}).get("automatic_external_spend_eur"))
      for row in td.values()
    )
    checks={
      "project_identity":str(t.get("project_id") or "")==str(b.get("project_id") or ""),
      "bootstrap_consumed_topology":_same_path(b.get("branch_topology"),top),
      "final_plan_consumed_decisions":linked,
      "runtime_materialization_count_matches":int(b.get("runtime_materialized_branches") or 0)==runtime_expected,
      "runtime_schedulable":b.get("runtime_schedulable") is True,
      "architecture_council_advisor_pass":_advisors_pass(c,"branch-foundry"),
      "technology_watch_consulted":watch_ok,
      "architecture_council_final_authority":b.get("architecture_decision_allowed") is True,
      "automatic_external_spend_zero":_zero_spend(b.get("external_spend_eur"))
    }
    return _result("branch-foundry-architect",run,checks,[top,finalp,bootp,councilp],
                   {"decision_count":len(td),"runtime_expected":runtime_expected})

def capability_foundry_case(run:Path)->dict[str,Any]|None:
    capp=_planning(run,"capability-foundry.json");bootp=_planning(run,"bootstrap-result.json")
    councilp=_planning(run,"architecture-decision-council.json");gapsp=_planning(run,"capability-gaps.json")
    if not all(p.is_file() for p in (capp,bootp,councilp,gapsp)):return None
    cap=load(capp);b=load(bootp);c=load(councilp);gaps=load(gapsp)
    if cap.get("schema")!="chacha.dev/capability-foundry-plan/v1":return None
    plans=[x for x in (cap.get("plans") or []) if isinstance(x,dict)]
    checks={
      "project_identity":str(cap.get("project_id") or "")==str(b.get("project_id") or ""),
      "bootstrap_consumed_plan":_same_path(b.get("capability_foundry"),capp),
      "created_domain_count_matches":int(b.get("capability_foundry_created_domains") or 0)==int(cap.get("created_domain_count") or 0),
      "created_capability_count_matches":int(b.get("capability_foundry_created_capabilities") or 0)==int(cap.get("created_capability_count") or 0),
      "architecture_council_advisor_pass":_advisors_pass(c,"capability-foundry"),
      "technology_watch_consulted":cap.get("technology_watch_consulted") is True,
      "central_memory_consumed":cap.get("central_memory_recall_consumed") is True,
      "promotion_requires_qualification":cap.get("promotion_requires_qualification") is True,
      "architecture_council_final_authority":b.get("architecture_decision_allowed") is True,
      "automatic_external_spend_zero":_zero_spend(b.get("external_spend_eur"))
    }
    return _result("capability-foundry-architect",run,checks,[capp,bootp,councilp,gapsp],
                   {"plan_count":len(plans),"gap_schema":gaps.get("schema")})

def logician_case(run:Path)->dict[str,Any]|None:
    logicp=_planning(run,"logic-search-report.json");compp=_planning(run,"multi-agent-compromise.json")
    councilp=_planning(run,"architecture-decision-council.json");bootp=_planning(run,"bootstrap-result.json")
    if not all(p.is_file() for p in (logicp,compp,councilp,bootp)):return None
    l=load(logicp);m=load(compp);c=load(councilp);b=load(bootp)
    if l.get("schema")!="chacha.dev/logic-search-report/v1" or m.get("schema")!="chacha.dev/multi-agent-compromise/v1":return None
    best=l.get("best_candidate") or {};cid=str(best.get("candidate_id") or "")
    pos=next((x for x in (m.get("positions") or []) if isinstance(x,dict) and x.get("agent")=="logician"),None)
    proposal=((pos or {}).get("proposal") or {}).get("candidate") or {}
    compromise=((m.get("compromise") or {}).get("logic_proposal") or {}).get("candidate") or {}
    checks={
      "candidate_identity_bound":bool(cid) and str(proposal.get("candidate_id") or "")==cid and str(compromise.get("candidate_id") or "")==cid,
      "candidate_improves_baseline":float(l.get("score_gain") or 0)>0 and float(best.get("score") or 0)>float((l.get("baseline") or {}).get("score") or 0),
      "hard_constraints_preserved":(best.get("metrics") or {}).get("hard_constraints_ok") is True,
      "challenge_requires_replan":str(l.get("challenge_status") or "")=="REPLAN_REQUIRED",
      "central_compromise_found":m.get("central_compromise_found") is True and m.get("continuation_allowed") is True,
      "architecture_council_consumed_compromise":b.get("architecture_council_consumed_compromise") is True,
      "architecture_council_compromise_valid":(c.get("logic_ux_compromise") or {}).get("valid") is True,
      "architecture_council_advisor_pass":_advisors_pass(c,"logic-ux-compromise"),
      "logician_not_final_authority":b.get("revision_request_only_after_failed_compromise") is True and b.get("architecture_decision_allowed") is True,
      "automatic_external_spend_zero":_zero_spend((best.get("automatic_external_spend_eur")))
    }
    return _result("logician",run,checks,[logicp,compp,councilp,bootp],{"candidate_id":cid})

def ergonomist_case(run:Path)->dict[str,Any]|None:
    uxp=_planning(run,"ux-planning-report.json");compp=_planning(run,"multi-agent-compromise.json")
    councilp=_planning(run,"architecture-decision-council.json");bootp=_planning(run,"bootstrap-result.json")
    contractp=_planning(run,"functional-contract.json")
    if not all(p.is_file() for p in (uxp,compp,councilp,bootp,contractp)):return None
    ux=load(uxp);m=load(compp);c=load(councilp);b=load(bootp);contract=load(contractp)
    if ux.get("schema")!="chacha.dev/ux-planning-report/v1" or m.get("schema")!="chacha.dev/multi-agent-compromise/v1":return None
    pos=next((x for x in (m.get("positions") or []) if isinstance(x,dict) and x.get("agent")=="ergonomist"),None)
    proposal=(pos or {}).get("proposal") or {};compromise=(m.get("compromise") or {}).get("ux_proposal") or {}
    digest=str(ux.get("report_digest") or "")
    evidence_refs=[str(x) for x in ((pos or {}).get("evidence_refs") or [])]
    checks={
      "contract_identity_bound":bool(str(ux.get("contract_id") or "")) and str(ux.get("contract_id") or "")==str(contract.get("contract_id") or ""),
      "challenge_status_bound":str((pos or {}).get("status") or "")==str(ux.get("challenge_status") or "")=="REPLAN_REQUIRED",
      "report_digest_bound":digest.startswith("sha256:") and digest in evidence_refs,
      "proposal_matches_report":proposal.get("kind")=="UX_PLAN" and proposal.get("ux_contract")==ux.get("ux_contract"),
      "central_compromise_preserves_ux":compromise.get("kind")=="UX_PLAN" and compromise.get("ux_contract")==ux.get("ux_contract"),
      "central_compromise_found":m.get("central_compromise_found") is True and m.get("continuation_allowed") is True,
      "architecture_council_consumed_compromise":b.get("architecture_council_consumed_compromise") is True,
      "architecture_council_compromise_valid":(c.get("logic_ux_compromise") or {}).get("valid") is True,
      "architecture_council_advisor_pass":_advisors_pass(c,"logic-ux-compromise"),
      "direct_mutation_forbidden":ux.get("direct_mutation") is False,
      "architecture_council_final_authority":ux.get("architecture_council_final_authority") is True and b.get("architecture_decision_allowed") is True,
      "automatic_external_spend_zero":_zero_spend(ux.get("automatic_external_spend_eur"))
    }
    return _result("ergonomist",run,checks,[uxp,compp,councilp,bootp,contractp],
                   {"report_digest":digest,"challenge_reason":ux.get("challenge_reason")})

def technology_watch_case(run:Path,runtime_root:Path)->dict[str,Any]|None:
    agentp=_planning(run,"agent-topology.json");branchp=_planning(run,"branch-topology-effective.json")
    capp=_planning(run,"capability-foundry.json");councilp=_planning(run,"architecture-decision-council.json")
    bootp=_planning(run,"bootstrap-result.json");snap=runtime_root/"technology-watch/optimizer-input.json"
    if not all(p.is_file() for p in (agentp,branchp,capp,councilp,bootp,snap)):return None
    a=load(agentp);br=load(branchp);cap=load(capp);c=load(councilp);b=load(bootp);s=load(snap)
    if s.get("schema")!="chacha.dev/technology-watch-snapshot/v1":return None
    candidates=[x for x in (s.get("provider_candidates") or []) if isinstance(x,dict)]
    eligible_count=sum(1 for x in candidates if x.get("admissible_for_automatic_selection") is True)
    zero_count=sum(1 for x in candidates if x.get("admissible_for_automatic_selection") is True and x.get("zero_external_spend") is True)
    checks={
      "agent_foundry_consumed_watch":a.get("technology_watch_consulted") is True,
      "branch_foundry_consumed_watch":br.get("technology_watch_consulted") is True,
      "capability_foundry_consumed_watch":cap.get("technology_watch_consulted") is True,
      "architecture_council_pre_watch_pass":_advisors_pass(c,"technology-watch-pre"),
      "architecture_council_final_watch_pass":_advisors_pass(c,"technology-watch-final"),
      "bootstrap_lists_both_watch_advisors":"technology-watch-pre" in (b.get("architecture_mandatory_advisors") or []) and "technology-watch-final" in (b.get("architecture_mandatory_advisors") or []),
      "snapshot_candidate_count_consistent":int(s.get("candidate_count") or 0)==len(candidates),
      "snapshot_eligible_count_consistent":int(s.get("eligible_candidate_count") or 0)==eligible_count,
      "snapshot_zero_spend_count_consistent":int(s.get("zero_spend_candidate_count") or 0)==zero_count,
      "zero_spend_candidate_available":s.get("zero_spend_candidate_available") is True and zero_count>0,
      "zero_spend_selection_rule":str(s.get("selection_rule") or "")=="IF_ANY_ADMISSIBLE_HARD_VALID_ZERO_SPEND_CANDIDATE_EXISTS_EXCLUDE_NONZERO_CANDIDATES",
      "automatic_external_spend_zero":_zero_spend(s.get("automatic_external_spend_eur"))
    }
    return _result("technology-watch-agent",run,checks,[agentp,branchp,capp,councilp,bootp,snap],
                   {"candidate_count":len(candidates),"zero_spend_candidate_count":zero_count})

def attestation(agent_id:str,cases:list[dict[str,Any]])->dict[str,Any]:
    total=len(cases);passed=sum(1 for x in cases if x.get("passed") is True)
    value=round(100.0*passed/total,1) if total else None
    refs=sorted({r for c in cases for r in (c.get("source_refs") or [])})
    return {
      "schema":SCHEMA,"subject_agent":agent_id,"verifier":VERIFIER,
      "verification":"INDEPENDENTLY_RECOMPUTED","verification_scope":"REAL_RUNTIME",
      "generated_at":now_iso(),"case_count":total,"passed_case_count":passed,
      "dimension_values":{
        "evidence_quality":value,"handoff_quality":value,"authority_discipline":value
      },
      "production_truth_eligible":total>0,
      "accuracy_inference":False,
      "source_refs":refs,"cases":cases,
      "decision_authority":False,"direct_mutation":False,
      "active_self_mutation":False,"self_promotion":False,"permission_expansion":False,
      "canonical_observation_bus_mutation":False,"benchmark_evidence_mutation":False,
      "architecture_council_final_authority":True,"automatic_external_spend_eur":0
    }

def build(runtime_root:Path,output_root:Path)->dict[str,dict[str,Any]]:
    cases={x:[] for x in TARGETS}
    for run in run_dirs(runtime_root):
        for aid,fn in (
          ("agent-foundry-architect",agent_foundry_case),
          ("branch-foundry-architect",branch_foundry_case),
          ("capability-foundry-architect",capability_foundry_case),
          ("logician",logician_case),
          ("ergonomist",ergonomist_case)
        ):
            row=fn(run)
            if row:cases[aid].append(row)
        row=technology_watch_case(run,runtime_root)
        if row:cases["technology-watch-agent"].append(row)
    out={}
    for aid,rows in cases.items():
        x=attestation(aid,rows);out[aid]=x
        if rows:save(output_root/("attestation-"+aid+".json"),x)
    return out

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--runtime-root",type=Path,required=True)
    ap.add_argument("--output-root",type=Path,required=True)
    a=ap.parse_args()
    out=build(a.runtime_root.resolve(),a.output_root.resolve())
    ok=True
    for aid in TARGETS:
        x=out[aid]
        print(aid.upper().replace("-","_")+"_CASES="+str(x["case_count"]))
        print(aid.upper().replace("-","_")+"_STRUCTURAL="+str((x["dimension_values"] or {}).get("evidence_quality")))
        ok=ok and x["case_count"]>0 and x["passed_case_count"]==x["case_count"]
    print("CHACHA_DEV_V661_REAL_WORLD_STRUCTURAL_ATTESTATION="+("PASS" if ok else "BLOCK"))
    print("CHACHA_DEV_V661_ACCURACY_INFERENCE=NO")
    print("CHACHA_DEV_V661_CANONICAL_OBSERVATION_BUS_MUTATION=NO")
    print("CHACHA_DEV_V661_SELF_MUTATION=NO")
    print("CHACHA_DEV_V661_SELF_PROMOTION=NO")
    print("CHACHA_DEV_V661_ARCHITECTURE_COUNCIL_FINAL_AUTHORITY=YES")
    print("CHACHA_DEV_V661_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
    return 0 if ok else 20

if __name__=="__main__":
    raise SystemExit(main())
