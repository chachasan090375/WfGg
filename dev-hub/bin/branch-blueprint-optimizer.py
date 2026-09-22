#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

def load(path:Path)->dict[str,Any]:
    x=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise SystemExit("JSON_ROOT_NOT_OBJECT")
    return x

def candidate_cost(c:dict[str,Any])->dict[str,float]:
    r=c.get("resources") or {}
    return {
        "external_spend_eur":float(c.get("external_spend_eur",0)),
        "memory_mb":float(r.get("memory_mb",0)),
        "disk_mb":float(r.get("disk_mb",0)),
        "cpu_weight":float(r.get("cpu_weight",0)),
        "startup_ms":float(c.get("startup_ms",0)),
        "maintenance":float(c.get("maintenance",0)),
        "model_units":float(c.get("model_units",0)),
        "reuse_credit":float(c.get("reuse_credit",0)),
    }

def cost_key(c:dict[str,Any]):
    x=candidate_cost(c)
    # Strictly lexicographic: euros first, then scarce VPS resources, then work/latency.
    return (
        x["external_spend_eur"],
        x["memory_mb"],
        x["disk_mb"],
        x["model_units"],
        x["cpu_weight"],
        x["startup_ms"],
        x["maintenance"],
        -x["reuse_credit"],
    )

def hard_valid(c:dict[str,Any])->bool:
    h=c.get("hard_constraints") or {}
    return all(bool(v) for v in h.values())

def pareto(candidates:list[dict[str,Any]])->list[str]:
    valid=[c for c in candidates if hard_valid(c)]
    dims=("external_spend_eur","memory_mb","disk_mb","model_units","cpu_weight","startup_ms","maintenance")
    costs={str(c["id"]):candidate_cost(c) for c in valid}
    out=[]
    for a in valid:
        aid=str(a["id"]);ca=costs[aid]
        dominated=False
        for b in valid:
            bid=str(b["id"])
            if bid==aid:continue
            cb=costs[bid]
            no_worse=all(cb[d]<=ca[d] for d in dims)
            strictly=any(cb[d]<ca[d] for d in dims)
            if no_worse and strictly:
                dominated=True;break
        if not dominated:out.append(aid)
    return out

def build_candidates(package:dict[str,Any],preplan:dict[str,Any],branch_policy:dict[str,Any],
                     agent_decision:dict[str,Any]|None=None)->list[dict[str,Any]]:
    implementation=bool(preplan.get("implementation_allowed"))
    simple=preplan.get("mode")=="simple_question"
    kind=str(package.get("kind") or "primary")
    caps=list(package.get("capabilities") or [])
    heavy=any(x in {
        "3d-pipeline","graphics-pipeline","animation-pipeline","performance-test-web",
        "security-scan-js","browser-automation","browser-diagnostics","cloud-deploy-edge"
    } for x in caps)
    agent_decision=agent_decision or {}
    agent_mode=str(agent_decision.get("decision") or "TOOL_ONLY")
    created_agent=agent_mode.startswith("CREATE_")
    composed=agent_mode=="COMPOSE_EXISTING_AGENTS"

    common_hard={
        "functional_coverage":True,
        "required_quality":True,
        "security_policy":True,
        "acceptance_contract":True,
        "available_compute":True,
        "license_compatibility":True,
        "rollback_capability":True,
        "declared_latency_or_throughput":True,
    }
    candidates=[]

    candidates.append({
      "id":"memory-only",
      "branch_mode":"MEMORY_ONLY",
      "orchestrator_strategy":"SHARED_CORE",
      "agent_strategy":"NONE",
      "architecture":"KNOWLEDGE_QUERY_ONLY",
      "component_strategy":"REUSE_MEMORY_ONLY",
      "resources":{"memory_mb":0,"disk_mb":0,"cpu_weight":0},
      "external_spend_eur":0,"model_units":0,"startup_ms":20,"maintenance":0,"reuse_credit":100,
      "hard_constraints":{**common_hard,"functional_coverage":(simple and not implementation)}
    })

    candidates.append({
      "id":"virtual-shared",
      "branch_mode":"REUSE_VIRTUAL_FACTORY",
      "orchestrator_strategy":"SHARED_CORE",
      "agent_strategy":agent_mode,
      "architecture":"VIRTUAL_FACTORY",
      "component_strategy":"REUSE_QUALIFIED_FIRST",
      "resources":{"memory_mb":0,"disk_mb":32,"cpu_weight":5},
      "external_spend_eur":0,"model_units":1 if created_agent else 0.2,
      "startup_ms":80,"maintenance":1,"reuse_credit":90,
      "hard_constraints":{**common_hard,
        "functional_coverage":(not implementation or kind=="review"),
        "required_quality":not heavy
      }
    })

    candidates.append({
      "id":"lean-ephemeral",
      "branch_mode":"MATERIALIZE_EPHEMERAL_BRANCH",
      "orchestrator_strategy":"LIGHTWEIGHT_DOMAIN",
      "agent_strategy":agent_mode,
      "architecture":"EPHEMERAL_CAPSULE",
      "component_strategy":"REUSE_QUALIFIED_FIRST_BUILD_MISSING_ONLY",
      "resources":{"memory_mb":192 if not heavy else 320,"disk_mb":256 if not heavy else 512,"cpu_weight":35 if not heavy else 55},
      "external_spend_eur":0,"model_units":1.5 if created_agent else (0.8 if composed else 0.3),
      "startup_ms":250,"maintenance":2,"reuse_credit":85,
      "hard_constraints":dict(common_hard)
    })

    candidates.append({
      "id":"dedicated-ephemeral",
      "branch_mode":"MATERIALIZE_EPHEMERAL_BRANCH",
      "orchestrator_strategy":"DEDICATED_EPHEMERAL",
      "agent_strategy":agent_mode,
      "architecture":"DEDICATED_EPHEMERAL_CAPSULE",
      "component_strategy":"REUSE_QUALIFIED_FIRST_BUILD_MISSING_ONLY",
      "resources":{"memory_mb":384 if not heavy else 640,"disk_mb":512 if not heavy else 896,"cpu_weight":60 if not heavy else 80},
      "external_spend_eur":0,"model_units":2.0 if created_agent else 1.0,
      "startup_ms":600,"maintenance":5,"reuse_credit":75,
      "hard_constraints":dict(common_hard)
    })

    # Dedicated is only justified when lighter candidate cannot meet a declared constraint.
    if package.get("requires_dedicated_orchestrator"):
        candidates[2]["hard_constraints"]["functional_coverage"]=False
    # Review packages should not pay for a runtime unless explicitly required.
    if kind=="review" and not package.get("requires_runtime_review"):
        candidates[2]["hard_constraints"]["functional_coverage"]=False
        candidates[3]["hard_constraints"]["functional_coverage"]=False

    return candidates

def optimize(package:dict[str,Any],preplan:dict[str,Any],branch_policy:dict[str,Any],
             agent_decision:dict[str,Any]|None=None)->dict[str,Any]:
    candidates=build_candidates(package,preplan,branch_policy,agent_decision)
    valid=[c for c in candidates if hard_valid(c)]
    if not valid:
        return {"state":"BLOCKED","reason":"NO_HARD_CONSTRAINT_VALID_BLUEPRINT","candidates":candidates}
    valid.sort(key=cost_key)
    chosen=valid[0]
    frontier=pareto(candidates)
    return {
        "state":"READY",
        "strategy":"CONSTRAINT_FIRST_MIN_TOTAL_COST",
        "chosen":chosen,
        "chosen_cost":candidate_cost(chosen),
        "pareto_frontier":frontier,
        "candidates":candidates,
        "rejected":[{"id":c["id"],"reason":"HARD_CONSTRAINT_FAILED" if not hard_valid(c) else "HIGHER_TOTAL_COST"}
                    for c in candidates if c["id"]!=chosen["id"]]
    }

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--package",required=True,type=Path)
    ap.add_argument("--preplan",required=True,type=Path)
    ap.add_argument("--policy",required=True,type=Path)
    ap.add_argument("--agent-decision",type=Path)
    ap.add_argument("--output",required=True,type=Path)
    a=ap.parse_args()
    decision=load(a.agent_decision) if a.agent_decision else None
    out=optimize(load(a.package),load(a.preplan),load(a.policy),decision)
    a.output.write_text(json.dumps(out,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print("CHACHA_BRANCH_BLUEPRINT_OPTIMIZER=PASS")
    print("STATE="+out["state"])
    if out["state"]=="READY":
        print("CHOSEN="+out["chosen"]["id"])
        print("EXTERNAL_SPEND_EUR="+str(out["chosen_cost"]["external_spend_eur"]))

if __name__=="__main__":main()
