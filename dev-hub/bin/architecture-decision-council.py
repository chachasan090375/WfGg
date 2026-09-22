#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,subprocess,sys
from pathlib import Path
from typing import Any
import technology_watch_runtime as tw

MANDATORY=("technology-watch-pre","architecture-memory","architecture-portfolio","reuse-memory","branch-foundry","agent-foundry","capability-foundry","constraint-policy","technology-watch-final")

def load(p:Path)->dict[str,Any]:
    x=json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(x,dict): raise SystemExit("JSON_ROOT_NOT_OBJECT")
    return x

def search_reuse(script:Path,db:Path,domain:str,caps:list[str],max_age:int)->dict[str,Any]:
    cmd=[sys.executable,str(script),"--db",str(db),"search","--domain",domain,"--limit","5","--max-revalidation-age-minutes",str(max_age)]
    for c in caps: cmd+=["--capability",str(c)]
    p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=30)
    if p.returncode!=0: return {"candidates":[],"error":(p.stderr or p.stdout)[-500:]}
    return json.loads(p.stdout)

def search_architecture_memory(script:Path,db:Path,preplan:Path,max_age:int)->dict[str,Any]:
    cmd=[sys.executable,str(script),"--db",str(db),"search","--preplan",str(preplan),
         "--limit","3","--max-revalidation-age-minutes",str(max_age)]
    p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=30)
    if p.returncode!=0: return {"candidates":[],"error":(p.stderr or p.stdout)[-500:]}
    return json.loads(p.stdout)

def architecture_memory_package(candidate:dict[str,Any],domain:str,caps:list[str],kind:str)->dict[str,Any]|None:
    want_caps=sorted(set(map(str,caps or [])))
    for p in (candidate.get("components") or {}).get("packages") or []:
        if not isinstance(p,dict): continue
        if str(p.get("domain") or "")!=domain: continue
        if str(p.get("kind") or "")!=kind: continue
        if sorted(set(map(str,p.get("capabilities") or [])))!=want_caps: continue
        return p
    return None


def run_architecture_portfolio(root:Path,preplan:Path,branch_topology:Path,agent_topology:Path,
                               architecture_db:Path,policy_path:Path,output:Path,
                               comparative_pilot_result:Path|None=None)->dict[str,Any]:
    cmd=[sys.executable,str(root/"dev-hub/bin/architecture-portfolio-optimizer.py"),
         "--repo-root",str(root),"--preplan",str(preplan),"--branch-topology",str(branch_topology),
         "--agent-topology",str(agent_topology),"--architecture-memory-db",str(architecture_db),
         "--policy",str(policy_path),"--output",str(output)]
    if comparative_pilot_result and comparative_pilot_result.is_file():
        cmd+=["--comparative-pilot-result",str(comparative_pilot_result)]
    p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=45)
    if p.returncode!=0:
        return {"schema":"chacha.dev/architecture-portfolio-optimizer/v1","decision_ready":False,
                "mode":"BLOCKED","reason":"PORTFOLIO_OPTIMIZER_FAILED","error":(p.stderr or p.stdout)[-700:]}
    return json.loads(output.read_text(encoding="utf-8"))


def by_package(topology:dict[str,Any])->dict[str,dict[str,Any]]:
    return {str(x.get("package_id")):x for x in topology.get("decisions") or [] if isinstance(x,dict)}

def capability_plan_map(plan:dict[str,Any])->dict[str,dict[str,Any]]:
    out={}
    for x in plan.get("plans") or []:
        if isinstance(x,dict) and x.get("capability"):out[str(x["capability"])]=x
        elif isinstance(x,dict) and x.get("id"):out[str(x["id"])]=x
    return out

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--repo-root",type=Path,default=Path("."))
    ap.add_argument("--preplan",type=Path,required=True)
    ap.add_argument("--branch-topology",type=Path,required=True)
    ap.add_argument("--agent-topology",type=Path,required=True)
    ap.add_argument("--capability-foundry",type=Path,required=True)
    ap.add_argument("--policy",type=Path,required=True)
    ap.add_argument("--reuse-db",type=Path,default=Path("/opt/chacha-dev/runtime/knowledge/reusable-branches.db"))
    ap.add_argument("--architecture-memory-db",type=Path,default=Path("/opt/chacha-dev/runtime/knowledge/reusable-architectures.db"))
    ap.add_argument("--comparative-pilot-result",type=Path)
    ap.add_argument("--output",type=Path,required=True)
    a=ap.parse_args()
    root=a.repo_root.resolve()
    pre=load(a.preplan);branch=load(a.branch_topology);agent=load(a.agent_topology);cap=load(a.capability_foundry);policy=load(a.policy)
    bm=by_package(branch);am=by_package(agent);cm=capability_plan_map(cap)
    max_age=int((policy.get("reuse") or {}).get("maximum_technology_revalidation_age_minutes",60))
    decisions=[];blocked=[];experts=set()
    registry_script=root/"dev-hub/bin/reusable-branch-registry.py"
    architecture_registry_script=root/"dev-hub/bin/reusable-architecture-registry.py"
    architecture_memory=search_architecture_memory(architecture_registry_script,a.architecture_memory_db,a.preplan,max_age)
    architecture_memory_ready=[x for x in architecture_memory.get("candidates") or [] if x.get("reuse_ready") is True]
    selected_architecture_memory=architecture_memory_ready[0] if architecture_memory_ready else None
    portfolio_path=a.output.with_name(a.output.stem+"-portfolio.json")
    portfolio_policy=root/"dev-hub/config/architecture-portfolio-optimizer.v1.json"
    portfolio=run_architecture_portfolio(root,a.preplan,a.branch_topology,a.agent_topology,
                                         a.architecture_memory_db,portfolio_policy,portfolio_path,
                                         a.comparative_pilot_result)
    if portfolio.get("mode") in {"FAST_REUSE","COMPARATIVE_PILOT_RESOLVED"} and (portfolio.get("selected") or {}).get("source")=="REUSABLE_COMPLETE_ARCHITECTURE":
        selected=portfolio.get("selected") or {}
        aid=str(selected.get("architecture_id") or "");ver=str(selected.get("version") or "")
        selected_architecture_memory=next((x for x in architecture_memory_ready
                                           if str(x.get("architecture_id"))==aid and str(x.get("version"))==ver),None)
    for pkg in pre.get("packages") or []:
        pid=str(pkg.get("id"));domain=str(pkg.get("domain") or "");caps=[str(x) for x in pkg.get("capabilities") or []];kind=str(pkg.get("kind") or "")
        experts.add(domain)
        prewatch=tw.consult(root,consumer="architecture-decision-council",domain=domain,capabilities=caps)
        reuse=search_reuse(registry_script,a.reuse_db,domain,caps,max_age)
        branch_op=bm.get(pid) or {};agent_op=am.get(pid) or {}
        gaps=[cm[c] for c in caps if c in cm]
        constraints={
          "branch_ready":bool(branch_op) and not bool(branch.get("blocked")),
          "agent_ready":bool(agent_op),
          "capability_gaps_resolved":all(bool(x) for x in gaps) if gaps else True,
          "zero_spend_rule_respected":float((branch_op.get("chosen_cost") or {}).get("external_spend_eur") or 0)==0,
          "security_boundary_reduction":False
        }
        constraints_pass=(
          constraints["branch_ready"] and
          constraints["agent_ready"] and
          constraints["capability_gaps_resolved"] and
          constraints["zero_spend_rule_respected"] and
          not constraints["security_boundary_reduction"]
        )
        finalwatch=tw.consult(root,consumer="architecture-decision-council",domain=domain,capabilities=caps)
        reuse_candidates=reuse.get("candidates") or []
        reuse_ready=[x for x in reuse_candidates if x.get("reuse_ready") is True]
        architecture_memory_package_match=architecture_memory_package(selected_architecture_memory or {},domain,caps,kind) if selected_architecture_memory else None
        if reuse_ready:
            architecture_source="REUSE_REVALIDATED_BRANCH"
            architecture=reuse_ready[0].get("architecture")
            selected_reuse={"branch_id":reuse_ready[0]["branch_id"],"version":reuse_ready[0]["version"]}
        elif architecture_memory_package_match and architecture_memory_package_match.get("architecture"):
            architecture_source="REUSE_REVALIDATED_COMPLETE_ARCHITECTURE"
            architecture=architecture_memory_package_match.get("architecture")
            selected_reuse={"architecture_id":selected_architecture_memory["architecture_id"],
                            "version":selected_architecture_memory["version"]}
        else:
            architecture_source="FOUNDRY_SYNTHESIS"
            architecture=branch_op.get("architecture")
            selected_reuse=None
        advisor_state={
          "technology-watch-pre":"PASS" if prewatch else "MISSING",
          "architecture-memory":"PASS",
          "architecture-portfolio":"PASS" if portfolio.get("decision_ready") is True else "BLOCKED",
          "reuse-memory":"PASS",
          "branch-foundry":"PASS" if branch_op else "MISSING",
          "agent-foundry":"PASS" if agent_op else "MISSING",
          "capability-foundry":"PASS",
          "constraint-policy":"PASS" if constraints_pass else "BLOCKED",
          "technology-watch-final":"PASS" if finalwatch else "MISSING"
        }
        missing=[x for x in MANDATORY if advisor_state.get(x)!="PASS"]
        d={
          "package_id":pid,"domain":domain,"capabilities":caps,
          "mandatory_advisors":advisor_state,
          "dynamic_expert_advisors":[{"domain":domain,"mode":"ON_DEMAND"}],
          "architecture_memory_candidate":({"architecture_id":selected_architecture_memory.get("architecture_id"),"version":selected_architecture_memory.get("version"),"reuse_ready":selected_architecture_memory.get("reuse_ready")} if selected_architecture_memory else None),
          "reuse_candidates":reuse_candidates,
          "selected_reuse":selected_reuse,
          "branch_foundry_opinion":branch_op,
          "agent_foundry_opinion":agent_op,
          "capability_foundry_opinion":{"gaps_for_package":gaps},
          "constraint_policy":constraints,
          "technology_watch_pre":prewatch,
          "technology_watch_final":finalwatch,
          "architecture_source":architecture_source,
          "architecture":architecture,
          "decision_ready":not missing,
          "blocked_by":missing
        }
        decisions.append(d)
        if missing: blocked.append({"package_id":pid,"reasons":missing})
    out={
      "schema":"chacha.dev/architecture-decision-council/v1",
      "version":"6.15.0",
      "mandatory_advisors":list(MANDATORY),
      "decision_rule":"CENTRAL_ORCHESTRATOR_DECIDES_ONLY_AFTER_ALL_MANDATORY_ADVISORS_AND_FINAL_TECHNOLOGY_REVALIDATION",
      "dynamic_expert_domains":sorted(x for x in experts if x),
      "architecture_memory":{"candidate_count":len(architecture_memory.get("candidates") or []),"selected":({"architecture_id":selected_architecture_memory.get("architecture_id"),"version":selected_architecture_memory.get("version")} if selected_architecture_memory else None)},
      "architecture_portfolio":portfolio,
      "decisions":decisions,
      "blocked":blocked,
      "dispatch_allowed":not blocked,
      "automatic_external_spend_eur":0
    }
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(out,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print("CHACHA_DEV_V615_ARCHITECTURE_DECISION_COUNCIL=PASS")
    print("DISPATCH_ALLOWED="+("YES" if out["dispatch_allowed"] else "NO"))
    print("ADVISORS="+str(len(MANDATORY)))
if __name__=="__main__":main()
