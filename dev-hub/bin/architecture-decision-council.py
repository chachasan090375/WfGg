#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,subprocess,sys
from pathlib import Path
from typing import Any
import technology_watch_runtime as tw

MANDATORY=("technology-watch-pre","reuse-memory","branch-foundry","agent-foundry","capability-foundry","constraint-policy","technology-watch-final")

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
    ap.add_argument("--output",type=Path,required=True)
    a=ap.parse_args()
    root=a.repo_root.resolve()
    pre=load(a.preplan);branch=load(a.branch_topology);agent=load(a.agent_topology);cap=load(a.capability_foundry);policy=load(a.policy)
    bm=by_package(branch);am=by_package(agent);cm=capability_plan_map(cap)
    max_age=int((policy.get("reuse") or {}).get("maximum_technology_revalidation_age_minutes",60))
    decisions=[];blocked=[];experts=set()
    registry_script=root/"dev-hub/bin/reusable-branch-registry.py"
    for pkg in pre.get("packages") or []:
        pid=str(pkg.get("id"));domain=str(pkg.get("domain") or "");caps=[str(x) for x in pkg.get("capabilities") or []]
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
        finalwatch=tw.consult(root,consumer="architecture-decision-council",domain=domain,capabilities=caps)
        reuse_candidates=reuse.get("candidates") or []
        reuse_ready=[x for x in reuse_candidates if x.get("reuse_ready") is True]
        if reuse_ready:
            architecture_source="REUSE_REVALIDATED_BRANCH"
            architecture=reuse_ready[0].get("architecture")
            selected_reuse={"branch_id":reuse_ready[0]["branch_id"],"version":reuse_ready[0]["version"]}
        else:
            architecture_source="FOUNDRY_SYNTHESIS"
            architecture=branch_op.get("architecture")
            selected_reuse=None
        advisor_state={
          "technology-watch-pre":"PASS" if prewatch else "MISSING",
          "reuse-memory":"PASS",
          "branch-foundry":"PASS" if branch_op else "MISSING",
          "agent-foundry":"PASS" if agent_op else "MISSING",
          "capability-foundry":"PASS",
          "constraint-policy":"PASS" if all(constraints.values()) else "BLOCKED",
          "technology-watch-final":"PASS" if finalwatch else "MISSING"
        }
        missing=[x for x in MANDATORY if advisor_state.get(x)!="PASS"]
        d={
          "package_id":pid,"domain":domain,"capabilities":caps,
          "mandatory_advisors":advisor_state,
          "dynamic_expert_advisors":[{"domain":domain,"mode":"ON_DEMAND"}],
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
      "version":"6.11.0",
      "mandatory_advisors":list(MANDATORY),
      "decision_rule":"CENTRAL_ORCHESTRATOR_DECIDES_ONLY_AFTER_ALL_MANDATORY_ADVISORS_AND_FINAL_TECHNOLOGY_REVALIDATION",
      "dynamic_expert_domains":sorted(x for x in experts if x),
      "decisions":decisions,
      "blocked":blocked,
      "dispatch_allowed":not blocked,
      "automatic_external_spend_eur":0
    }
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(out,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print("CHACHA_DEV_V611_ARCHITECTURE_DECISION_COUNCIL=PASS")
    print("DISPATCH_ALLOWED="+("YES" if out["dispatch_allowed"] else "NO"))
    print("ADVISORS="+str(len(MANDATORY)))
if __name__=="__main__":main()
