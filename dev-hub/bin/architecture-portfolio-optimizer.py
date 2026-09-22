#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,subprocess,sys
from pathlib import Path
from typing import Any

def load(p:Path)->dict[str,Any]:
    x=json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(x,dict): raise SystemExit("JSON_ROOT_NOT_OBJECT")
    return x

def canon(v:Any)->str:
    return json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(",",":"))

def by_package(doc:dict[str,Any])->dict[str,dict[str,Any]]:
    return {str(x.get("package_id")):x for x in doc.get("decisions") or [] if isinstance(x,dict)}

def search_memory(registry:Path,db:Path,preplan:Path,limit:int,max_age:int,min_success:float,max_incidents:int)->dict[str,Any]:
    cmd=[sys.executable,str(registry),"--db",str(db),"search","--preplan",str(preplan),
         "--limit",str(limit),"--max-revalidation-age-minutes",str(max_age),
         "--min-success-rate",str(min_success),"--max-incidents",str(max_incidents)]
    p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=30)
    if p.returncode!=0: return {"candidates":[],"error":(p.stderr or p.stdout)[-700:]}
    return json.loads(p.stdout)

def candidate_package_map(candidate:dict[str,Any])->dict[tuple[str,str,tuple[str,...]],dict[str,Any]]:
    out={}
    for p in (candidate.get("components") or {}).get("packages") or []:
        if not isinstance(p,dict): continue
        key=(str(p.get("domain") or ""),str(p.get("kind") or ""),tuple(sorted(set(map(str,p.get("capabilities") or [])))))
        out[key]=p
    return out

def current_package_rows(pre:dict[str,Any],branch:dict[str,Any],agent:dict[str,Any])->list[dict[str,Any]]:
    bm=by_package(branch);am=by_package(agent);rows=[]
    for p in pre.get("packages") or []:
        if not isinstance(p,dict): continue
        pid=str(p.get("id") or "")
        b=bm.get(pid) or {};a=am.get(pid) or {}
        rows.append({
          "package_id":pid,
          "domain":str(p.get("domain") or ""),
          "kind":str(p.get("kind") or ""),
          "capabilities":sorted(set(map(str,p.get("capabilities") or []))),
          "architecture":b.get("architecture"),
          "agent_decision":a.get("decision"),
          "external_spend_eur":float((b.get("chosen_cost") or {}).get("external_spend_eur") or 0)
        })
    return rows

def agreement(candidate:dict[str,Any],current:list[dict[str,Any]])->dict[str,Any]:
    cmap=candidate_package_map(candidate);matched=0;architecture_matches=0;agent_matches=0;details=[]
    for row in current:
        key=(row["domain"],row["kind"],tuple(row["capabilities"]))
        cp=cmap.get(key)
        package_match=cp is not None
        arch_match=bool(cp) and canon(cp.get("architecture"))==canon(row.get("architecture"))
        cand_agent=(cp or {}).get("agent_decision")
        agent_match=bool(cp) and (cand_agent is None or cand_agent==row.get("agent_decision"))
        if package_match: matched+=1
        if arch_match: architecture_matches+=1
        if agent_match: agent_matches+=1
        details.append({"package_id":row["package_id"],"package_match":package_match,
                        "architecture_match":arch_match,"agent_match":agent_match})
    total=max(1,len(current))
    return {
      "package_coverage_ratio":round(matched/total,4),
      "architecture_agreement_ratio":round(architecture_matches/total,4),
      "agent_agreement_ratio":round(agent_matches/total,4),
      "full_current_foundry_agreement":bool(matched==len(current) and architecture_matches==len(current) and agent_matches==len(current)),
      "details":details
    }

def evidence_rank(x:dict[str,Any])->tuple:
    # Hard validity is handled before ranking. Among valid zero-spend candidates,
    # prefer fewer incidents/failures, then stronger quality/evidence, then efficiency.
    return (
      int(x.get("incident_count") or 0),
      int(x.get("failure_count") or 0),
      -float(x.get("quality_score") or 0),
      -float(x.get("success_rate") or 0),
      -int(x.get("success_count") or 0),
      float(x.get("latency_ms")) if x.get("latency_ms") is not None else float("inf"),
      float(x.get("memory_mb")) if x.get("memory_mb") is not None else float("inf"),
      str(x.get("version") or "")
    )

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--repo-root",type=Path,default=Path("."))
    ap.add_argument("--preplan",type=Path,required=True)
    ap.add_argument("--branch-topology",type=Path,required=True)
    ap.add_argument("--agent-topology",type=Path,required=True)
    ap.add_argument("--architecture-memory-db",type=Path,required=True)
    ap.add_argument("--policy",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    a=ap.parse_args()
    root=a.repo_root.resolve();pre=load(a.preplan);branch=load(a.branch_topology);agent=load(a.agent_topology);policy=load(a.policy)
    memory=policy.get("memory_gate") or {}
    max_age=int(memory.get("maximum_technology_revalidation_age_minutes",60))
    min_success=float(memory.get("minimum_success_rate",0.95))
    max_incidents=int(memory.get("maximum_incident_count",0))
    registry=root/"dev-hub/bin/reusable-architecture-registry.py"
    found=search_memory(registry,a.architecture_memory_db,a.preplan,int(policy.get("candidate_limit",10)),max_age,min_success,max_incidents)
    current=current_package_rows(pre,branch,agent)
    foundry_zero=all(float(x.get("external_spend_eur") or 0)==0 for x in current)
    candidates=[]
    for x in found.get("candidates") or []:
        if not isinstance(x,dict): continue
        y=dict(x);y["agreement_with_current_foundries"]=agreement(y,current)
        y["evidence_attempts"]=int(y.get("success_count") or 0)+int(y.get("failure_count") or 0)
        y["hard_valid"]=bool(y.get("reuse_ready") is True and float(y.get("external_spend_eur") or 0)==0)
        candidates.append(y)
    valid=[x for x in candidates if x["hard_valid"]]
    valid.sort(key=evidence_rank)
    historical_best=valid[0] if valid else None

    if not foundry_zero:
        mode="BLOCKED"
        selected=None
        reason="CURRENT_FOUNDRY_ZERO_SPEND_CONSTRAINT_FAILED"
        decision_ready=False
    elif historical_best is None:
        mode="CURRENT_FOUNDRY_SYNTHESIS"
        selected={"source":"CURRENT_FOUNDRY_SYNTHESIS"}
        reason="NO_REUSABLE_COMPLETE_ARCHITECTURE_WITH_CURRENT_EVIDENCE"
        decision_ready=True
    elif historical_best["agreement_with_current_foundries"]["full_current_foundry_agreement"]:
        mode="FAST_REUSE"
        selected={"source":"REUSABLE_COMPLETE_ARCHITECTURE",
                  "architecture_id":historical_best["architecture_id"],"version":historical_best["version"]}
        reason="HISTORICAL_BEST_AND_CURRENT_FOUNDRIES_AGREE"
        decision_ready=True
    else:
        mode="COMPARATIVE_PILOT_REQUIRED"
        selected=None
        reason="HISTORICAL_BEST_CONFLICTS_WITH_CURRENT_FOUNDRY_SYNTHESIS"
        decision_ready=False

    out={
      "schema":"chacha.dev/architecture-portfolio-optimizer/v1",
      "version":"6.14.0",
      "selection_principle":"HARD_CONSTRAINTS_THEN_ZERO_SPEND_THEN_PROVEN_EVIDENCE_WITH_CURRENT_FOUNDRY_CONSENSUS",
      "current_foundry_candidate":{"zero_spend":foundry_zero,"packages":current},
      "memory_candidate_count":len(candidates),
      "valid_memory_candidate_count":len(valid),
      "historical_best":historical_best,
      "selected":selected,
      "mode":mode,
      "reason":reason,
      "decision_ready":decision_ready,
      "comparative_pilot_required":mode=="COMPARATIVE_PILOT_REQUIRED",
      "ranked_memory_candidates":valid,
      "automatic_external_spend_eur":0
    }
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(out,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print("CHACHA_DEV_V614_ARCHITECTURE_PORTFOLIO_OPTIMIZER=PASS")
    print("MODE="+mode)
    print("DECISION_READY="+("YES" if decision_ready else "NO"))
if __name__=="__main__":main()
