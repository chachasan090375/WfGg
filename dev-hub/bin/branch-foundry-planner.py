#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any

SCHEMA="chacha.dev/branch-foundry/v1"
OUT="chacha.dev/branch-topology/v1"

def load(path:Path)->dict[str,Any]:
    x=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise SystemExit("JSON_ROOT_NOT_OBJECT")
    return x

def digest(v:Any)->str:
    return hashlib.sha256(json.dumps(v,sort_keys=True,ensure_ascii=False).encode()).hexdigest()

def load_optimizer():
    path=Path(__file__).with_name("branch-blueprint-optimizer.py")
    spec=importlib.util.spec_from_file_location("branch_blueprint_optimizer",path)
    if spec is None or spec.loader is None:raise SystemExit("BRANCH_BLUEPRINT_OPTIMIZER_LOAD_FAILED")
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod

def profile_for(chosen:dict[str,Any])->str:
    if chosen.get("branch_mode")=="MEMORY_ONLY":return "MEMORY_ONLY"
    mem=float((chosen.get("resources") or {}).get("memory_mb",0))
    if mem<=256:return "LIGHT"
    if mem<=512:return "STANDARD"
    return "BURST"

def build(preplan:dict[str,Any],cfg:dict[str,Any],project_id:str,
          agent_topology:dict[str,Any]|None=None)->dict[str,Any]:
    if cfg.get("schema")!=SCHEMA:raise SystemExit("BRANCH_FOUNDRY_SCHEMA_INVALID")
    if preplan.get("schema")!="chacha.dev/domain-plan/v1":raise SystemExit("PREPLAN_SCHEMA_INVALID")
    optimizer=load_optimizer()
    agent_map={}
    if isinstance(agent_topology,dict):
        agent_map={str(x.get("package_id")):x for x in agent_topology.get("decisions") or [] if isinstance(x,dict)}

    decisions=[]
    blocked=[]
    for pkg in preplan.get("packages") or []:
        pid=str(pkg.get("id"))
        opt=optimizer.optimize(pkg,preplan,cfg,agent_map.get(pid))
        if opt.get("state")!="READY":
            blocked.append({"package_id":pid,"reason":opt.get("reason"),"optimization":opt})
            continue
        chosen=opt["chosen"]
        profile=profile_for(chosen)
        runtime=chosen.get("branch_mode")=="MATERIALIZE_EPHEMERAL_BRANCH"
        domain=str(pkg.get("domain"))
        branch_id=f"{project_id}:{domain}:{'review' if pkg.get('kind')=='review' else 'primary'}"
        resources=chosen.get("resources") or {}
        decisions.append({
            "package_id":pid,
            "branch_id":branch_id,
            "domain":domain,
            "kind":pkg.get("kind"),
            "decision":chosen.get("branch_mode"),
            "runtime_required":runtime,
            "materialization_profile":profile,
            "orchestrator_strategy":chosen.get("orchestrator_strategy"),
            "agent_strategy":chosen.get("agent_strategy"),
            "architecture":chosen.get("architecture"),
            "component_strategy":chosen.get("component_strategy"),
            "chosen_cost":opt.get("chosen_cost"),
            "pareto_frontier":opt.get("pareto_frontier"),
            "candidate_count":len(opt.get("candidates") or []),
            "rejected_candidates":opt.get("rejected") or [],
            "ttl_seconds":0 if not runtime else int((cfg.get("runtime_capsules") or {}).get("teardown_after_idle_seconds",900)),
            "resource_budget":{
                "memory_hard_limit_mb":int(resources.get("memory_mb",0)),
                "disk_soft_limit_mb":int(resources.get("disk_mb",0)),
                "cpu_weight":int(resources.get("cpu_weight",0)),
                "processes_max":0 if not runtime else (1 if chosen.get("orchestrator_strategy")!="DEDICATED_EPHEMERAL" else 2)
            },
            "workspace":None if not runtime else f"/opt/chacha-dev/runtime/projects/{project_id}/branches/{domain}",
            "collector_bindings":[
                f"project-collector:{project_id}",
                f"project-branch-collector:{project_id}",
                f"project-domain-collector:{project_id}:{domain}",
                f"generic-domain-collector:{domain}"
            ],
            "persistent_state":[
                f"project-domain-collector:{project_id}:{domain}",
                "component-manifests","contracts","evidence","qualified-components"
            ],
            "ephemeral_state":[
                "temporary-workspace","ephemeral-agent-processes","scratch-files","preview-runtime"
            ] if runtime else [],
            "fast_path":chosen.get("branch_mode")=="MEMORY_ONLY",
            "optimization_strategy":opt.get("strategy"),
            "reason":"minimum-total-cost-valid-blueprint"
        })

    materialized=[x for x in decisions if x["runtime_required"]]
    memory=[x for x in decisions if x["decision"]=="MEMORY_ONLY"]
    return {
        "schema":OUT,
        "project_id":project_id,
        "preplan_digest":digest(preplan),
        "agent_topology_digest":digest(agent_topology) if agent_topology else None,
        "intent":preplan.get("intent"),
        "mandatory_preflight":True,
        "optimization_strategy":"CONSTRAINT_FIRST_MIN_TOTAL_COST",
        "decisions":decisions,
        "blocked":blocked,
        "summary":{
            "branches":len(decisions),
            "blocked":len(blocked),
            "materialized":len(materialized),
            "memory_only":len(memory),
            "runtime_memory_hard_limit_mb":sum(int((x.get("resource_budget") or {}).get("memory_hard_limit_mb") or 0) for x in materialized),
            "runtime_disk_soft_limit_mb":sum(int((x.get("resource_budget") or {}).get("disk_soft_limit_mb") or 0) for x in materialized),
            "external_spend_eur":sum(float((x.get("chosen_cost") or {}).get("external_spend_eur") or 0) for x in decisions)
        },
        "central_memory_persistent":True,
        "runtime_capsules_ephemeral":True,
        "return_to":"chacha-core-orchestrator",
        "dispatch_allowed":not blocked
    }

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--preplan",required=True,type=Path)
    ap.add_argument("--config",required=True,type=Path)
    ap.add_argument("--project-id",required=True)
    ap.add_argument("--agent-topology",type=Path)
    ap.add_argument("--output",required=True,type=Path)
    a=ap.parse_args()
    topo=load(a.agent_topology) if a.agent_topology else None
    out=build(load(a.preplan),load(a.config),a.project_id,topo)
    a.output.write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("CHACHA_BRANCH_FOUNDRY=PASS")
    print("BRANCHES="+str(out["summary"]["branches"]))
    print("MATERIALIZED="+str(out["summary"]["materialized"]))
    print("MEMORY_ONLY="+str(out["summary"]["memory_only"]))
    print("EXTERNAL_SPEND_EUR="+str(out["summary"]["external_spend_eur"]))
    print("RUNTIME_MEMORY_MB="+str(out["summary"]["runtime_memory_hard_limit_mb"]))

if __name__=="__main__":main()
