#!/usr/bin/env python3
from __future__ import annotations
import argparse,json
from datetime import datetime,timezone
from pathlib import Path
from statistics import mean
from typing import Any
import technology_source_reputation as tsr
def load(path:Path)->dict[str,Any]:
    x=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise SystemExit("JSON_ROOT_NOT_OBJECT:"+str(path))
    return x
def save(path:Path,x:dict[str,Any])->None:
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
def clamp(v:float)->float:return max(0.0,min(100.0,float(v)))
def parse_day(v:str)->datetime:return datetime.fromisoformat(v.replace("Z","+00:00")).astimezone(timezone.utc)
def _age_score(days:int)->float:
    if days<3:return 10
    if days<7:return 25
    if days<14:return 45
    if days<30:return 65
    if days<60:return 80
    return 95
def _publisher_conf(registry:dict[str,Any],publisher:str,claim_class:str)->float:
    if not registry:return 50.0
    try:return tsr.profile_confidence(registry,publisher,claim_class)
    except Exception:return 50.0
def evaluate(dossier:dict[str,Any],policy:dict[str,Any],source_registry:dict[str,Any]|None=None,challenge:dict[str,Any]|None=None)->dict[str,Any]:
    source_registry=source_registry or {};publisher=str(dossier.get("publisher") or "UNKNOWN");exact_version=str(dossier.get("version") or "").strip()
    exact_ok=exact_version.lower() not in {"","latest","current","unknown","tbd"}
    weights=policy.get("evidence_weights") or {};vendor_types=set(policy.get("publisher_vendor_evidence_types") or [])
    executable_types=set(policy.get("executable_evidence_types") or []);technical_types=set(policy.get("technical_evidence_types") or [])
    multiplier=float(policy.get("contradiction_multiplier") or 1.25)
    evidence=[x for x in dossier.get("evidence") or [] if isinstance(x,dict)];claims=[x for x in dossier.get("claims") or [] if isinstance(x,dict)]
    claim_reports=[];all_support_types=set();duplicate_count=0;any_executable=False;contradictions=0;graph_nodes=[];graph_edges=[]
    for claim in claims:
        cid=str(claim.get("id") or "");cclass=str(claim.get("class") or "general");rows=[x for x in evidence if str(x.get("claim_id") or "")==cid]
        support_groups={};contradict_groups={}
        for e in rows:
            eid=str(e.get("id") or "evidence-"+str(len(graph_nodes)));group=str(e.get("independence_group") or e.get("origin") or eid)
            etype=str(e.get("type") or "unverified_blog");stance=str(e.get("stance") or "SUPPORT").upper()
            verified=bool(e.get("verified") is True);reproducible=bool(e.get("reproducible") is True)
            raw=float(weights.get(etype,0));quality=1.0 if verified else 0.7
            if etype in {"executable_reproduction","benchmark_reproducible"} and not reproducible:quality*=0.65
            if etype in vendor_types:
                pub=_publisher_conf(source_registry,publisher,cclass);quality*=0.5+0.5*(pub/100.0)
            value=raw*quality;target=contradict_groups if stance=="CONTRADICT" else support_groups;prev=target.get(group)
            if prev is None or value>prev["value"]:target[group]={"value":value,"type":etype,"id":eid}
            graph_nodes.append({"id":eid,"kind":"evidence","type":etype,"origin":e.get("origin"),"independence_group":group,"stance":stance})
            graph_edges.append({"from":eid,"to":cid,"relation":"CONTRADICTS" if stance=="CONTRADICT" else "SUPPORTS"})
        all_groups=set(support_groups)|set(contradict_groups);duplicate_count+=max(0,len(rows)-len(all_groups))
        support=sum(x["value"] for x in support_groups.values());penalty=sum(x["value"] for x in contradict_groups.values())*multiplier
        score=round(clamp(support-penalty),1);support_types={x["type"] for x in support_groups.values()};all_support_types|=support_types
        if support_types & executable_types:any_executable=True
        contradictions+=len(contradict_groups)
        claim_reports.append({"claim_id":cid,"claim_class":cclass,"required":bool(claim.get("required",True)),
          "truth_score":score,"support_independence_groups":len(support_groups),"contradiction_independence_groups":len(contradict_groups),
          "support_types":sorted(support_types)})
        graph_nodes.append({"id":cid,"kind":"claim","required":bool(claim.get("required",True))})
    required=[x for x in claim_reports if x["required"]] or claim_reports
    truth=round(mean([x["truth_score"] for x in required]),1) if required else 0.0
    marketing_only=bool(all_support_types) and not bool(all_support_types & technical_types)
    min_claim=float((policy.get("thresholds") or {}).get("minimum_required_claim_truth",55));weak_required=[x["claim_id"] for x in required if x["truth_score"]<min_claim]
    asof=parse_day(str(dossier.get("as_of") or datetime.now(timezone.utc).isoformat()));release=parse_day(str(dossier.get("release_date") or asof.isoformat()))
    age_days=max(0,(asof-release).days);op=dossier.get("operational") or {}
    critical=int(op.get("unresolved_critical_issues") or 0);high=int(op.get("unresolved_high_impact_issues") or 0);medium=int(op.get("unresolved_medium_issues") or 0)
    issue_score=clamp(100-critical*45-high*15-medium*5);maintenance=clamp(op.get("maintenance_health",50));security=clamp(op.get("security_health",50))
    regression=clamp(100-float(op.get("regression_rate_pct",0))*2);rollback_tested=bool(op.get("rollback_tested") is True)
    shadow_passed=bool(op.get("shadow_passed") is True);pilot_passed=bool(op.get("pilot_passed") is True)
    rollback_score=100 if rollback_tested else 45 if op.get("rollback_documented") else 0;pilot_score=100 if pilot_passed else 70 if shadow_passed else 30
    maturity=round(_age_score(age_days)*0.15+issue_score*0.15+maintenance*0.15+security*0.15+regression*0.10+rollback_score*0.15+pilot_score*0.15,1)
    outcome_penalty_truth=0.0;outcome_penalty_maturity=0.0
    for outcome in dossier.get("outcomes") or []:
        if not isinstance(outcome,dict) or outcome.get("verified") is not True:continue
        status=str(outcome.get("status") or "").upper();severity=str(outcome.get("severity") or "").lower()
        if status=="VERIFIED_FAILURE":outcome_penalty_truth+=10;outcome_penalty_maturity+=20
        elif status=="ROLLBACK":outcome_penalty_truth+=5;outcome_penalty_maturity+=15
        elif status=="INCIDENT":
            outcome_penalty_truth+=20 if severity=="critical" else 10;outcome_penalty_maturity+=40 if severity=="critical" else 20
        elif status=="VERIFIED_SUCCESS":maturity=min(100,maturity+3)
    truth=round(clamp(truth-outcome_penalty_truth),1);maturity=round(clamp(maturity-outcome_penalty_maturity),1)
    fit=dossier.get("architecture_fit") or {};fit_keys=["compatibility","security_fit","resource_efficiency","observability","rollback_readiness","integration_fit","cost_fit","migration_safety"]
    fit_score=round(mean([clamp(fit.get(k,50)) for k in fit_keys]),1);publisher_conf=round(_publisher_conf(source_registry,publisher,"general"),1)
    blast=str(dossier.get("blast_radius") or "medium").lower();conflict=contradictions>0;additional_verification=conflict or bool(weak_required) or marketing_only or not exact_ok
    blocking=[]
    if not exact_ok:blocking.append("EXACT_VERSION_REQUIRED")
    if marketing_only:blocking.append("MARKETING_ONLY_EVIDENCE")
    if conflict:blocking.append("CONTRADICTORY_EVIDENCE")
    if weak_required:blocking.append("REQUIRED_CLAIM_UNDER_TRUTH_THRESHOLD")
    if critical>0:blocking.append("UNRESOLVED_CRITICAL_ISSUE")
    adopt=(policy.get("thresholds") or {}).get("adopt") or {};pilot=(policy.get("thresholds") or {}).get("pilot") or {};decision="WATCH"
    if critical>0 and not any_executable:decision="REJECT"
    elif (exact_ok and not marketing_only and not conflict and not weak_required and
          truth>=float(adopt.get("technical_truth",80)) and maturity>=float(adopt.get("operational_maturity",75)) and
          fit_score>=float(adopt.get("architecture_fit",75)) and any_executable and rollback_tested):
        decision="SHADOW" if blast in {"high","critical"} and not (shadow_passed and pilot_passed) else "ADOPT"
    elif (exact_ok and not marketing_only and truth>=float(pilot.get("technical_truth",60)) and
          maturity>=float(pilot.get("operational_maturity",50)) and fit_score>=float(pilot.get("architecture_fit",65))):
        decision="SHADOW" if blast in {"high","critical"} else "PILOT"
    elif truth<25 and conflict:decision="REJECT"
    automatic_selection_allowed=decision=="ADOPT" and blast!="critical" and not additional_verification
    return {"schema":"chacha.dev/technology-truth-score/v1","technology_id":dossier.get("technology_id"),"publisher":publisher,
      "version":dossier.get("version"),"release_date":dossier.get("release_date"),"release_age_days":age_days,"blast_radius":blast,
      "technical_truth_score":truth,"operational_maturity_score":maturity,"architecture_fit_score":fit_score,
      "publisher_confidence_index":publisher_conf,"claim_reports":claim_reports,
      "evidence_graph":{"nodes":graph_nodes,"edges":graph_edges,"duplicate_or_shared_origin_evidence_count":duplicate_count},
      "executable_or_real_pilot_proof":any_executable,"marketing_only":marketing_only,"contradictory_evidence":conflict,
      "additional_verification_required":additional_verification,"blocking_reasons":blocking,"recommendation_class":decision,
      "automatic_selection_allowed":automatic_selection_allowed,"latest_version_priority":False,
      "historical_outcome_penalty":{"truth":outcome_penalty_truth,"maturity":outcome_penalty_maturity},
      "logician_challenge_summary":{"available":bool(challenge),"path_count":len((challenge or {}).get("falsification_paths") or []),"decision_authority":(challenge or {}).get("decision_authority")},
      "technology_watch_owns_final_evidence_score":True,"architecture_council_final_authority":True,
      "guardian_authority_preserved":True,"sentinel_authority_preserved":True,"permission_escalation":False,"automatic_external_spend_eur":0}
def select_verified_safe(reports:list[dict[str,Any]])->dict[str,Any]:
    rank={"REJECT":0,"WATCH":1,"SHADOW":2,"PILOT":3,"ADOPT":4};eligible=[x for x in reports if isinstance(x,dict)]
    if not eligible:raise ValueError("NO_TECHNOLOGY_REPORTS")
    best=max(eligible,key=lambda x:(rank.get(str(x.get("recommendation_class")),0),float(x.get("technical_truth_score") or 0),
      float(x.get("operational_maturity_score") or 0),float(x.get("architecture_fit_score") or 0),str(x.get("version") or "")))
    return {"schema":"chacha.dev/technology-selection/v1","selected":best,"latest_version_priority":False,
      "selection_principle":"BEST_VERIFIED_SAFE_NOT_NEWEST","architecture_council_final_authority":True,"automatic_external_spend_eur":0}
def main()->int:
    ap=argparse.ArgumentParser();sub=ap.add_subparsers(dest="cmd",required=True)
    s=sub.add_parser("score");s.add_argument("--dossier",type=Path,required=True);s.add_argument("--policy",type=Path,required=True);s.add_argument("--source-reputation",type=Path);s.add_argument("--logician-challenge",type=Path);s.add_argument("--output",type=Path,required=True)
    sel=sub.add_parser("select");sel.add_argument("--report",type=Path,action="append",required=True);sel.add_argument("--output",type=Path,required=True);a=ap.parse_args()
    if a.cmd=="score":
        rep=load(a.source_reputation) if a.source_reputation and a.source_reputation.is_file() else {};challenge=load(a.logician_challenge) if a.logician_challenge and a.logician_challenge.is_file() else {}
        out=evaluate(load(a.dossier),load(a.policy),rep,challenge);save(a.output,out);print(json.dumps(out,ensure_ascii=False))
        print("CHACHA_DEV_V645_TECHNOLOGY_TRUTH_SCORING=PASS");print("CHACHA_DEV_V645_PERMISSION_ESCALATION=NO");print("CHACHA_DEV_V645_AUTOMATIC_EXTERNAL_SPEND_EUR=0");return 0
    out=select_verified_safe([load(p) for p in a.report]);save(a.output,out);print(json.dumps(out,ensure_ascii=False));print("CHACHA_DEV_V645_VERIFIED_SAFE_SELECTION=PASS");return 0
if __name__=="__main__":raise SystemExit(main())
