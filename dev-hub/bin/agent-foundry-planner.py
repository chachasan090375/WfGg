#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

SCHEMA="chacha.dev/agent-foundry/v1"
OUT="chacha.dev/agent-topology/v1"

DETERMINISTIC_TOOL_CAPS={
    "unit-test-js","e2e-test-web","smoke-test-web","performance-test-web",
    "security-scan-js","digital-signature-verification","source-control",
    "ci","cloud-deploy-edge","cloud-deploy-static","cloud-preview-static",
    "browser-automation","browser-diagnostics","prose-lint"
}

def load(path:Path)->dict[str,Any]:
    x=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise SystemExit("JSON_ROOT_NOT_OBJECT")
    return x

def digest(value:Any)->str:
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()

def role_capabilities(routing:dict[str,Any],roles:list[str])->set[str]:
    out=set()
    catalog=routing.get("roles") or {}
    for role in roles:
        spec=catalog.get(role) or {}
        out.update(str(x) for x in spec.get("capabilities") or [])
    return out

def task_score(pkg:dict[str,Any],role_fit:float,reusable:bool)->float:
    caps=pkg.get("capabilities") or []
    complexity=min(100,20+len(caps)*12+(15 if pkg.get("kind")=="primary" else 5))
    autonomy_gain=min(100,35+len(caps)*8)
    context_specialization=65 if pkg.get("domain") not in {"qa","platform-release"} else 35
    expected_reuse=80 if reusable else 35
    deterministic=sum(1 for c in caps if c in DETERMINISTIC_TOOL_CAPS)
    deterministic_penalty=min(100,(deterministic/max(1,len(caps)))*100)
    # Higher score means stronger case for creating an agent.
    score=(
        (100-role_fit)*0.30+
        complexity*0.15+
        autonomy_gain*0.15+
        expected_reuse*0.10+
        context_specialization*0.10-
        deterministic_penalty*0.08+
        90*0.07+
        70*0.03+
        80*0.02
    )
    return round(max(0,min(100,score)),2)

def decide_package(pkg:dict[str,Any],routing:dict[str,Any],cfg:dict[str,Any],project_id:str)->dict[str,Any]:
    domain=str(pkg["domain"])
    caps=[str(x) for x in pkg.get("capabilities") or []]
    roles=[str(x) for x in pkg.get("roles") or []]
    covered=role_capabilities(routing,roles)
    fit=100.0*(len(set(caps)&covered)/max(1,len(set(caps))))
    deterministic_ratio=sum(1 for c in caps if c in DETERMINISTIC_TOOL_CAPS)/max(1,len(caps))
    reusable=bool(domain in {"documentation","translation","publication","graphics","animation","cybersecurity","qa","development","data-backend"})
    score=task_score(pkg,fit,reusable)
    th=cfg.get("create_thresholds") or {}
    existing_min=float(th.get("existing_agent_min_fit",80))
    ephemeral_min=float(th.get("ephemeral_agent_min_score",65))
    reusable_min=float(th.get("reusable_agent_min_score",78))

    if caps and deterministic_ratio==1.0 and not roles:
        decision="TOOL_ONLY"
    elif fit>=existing_min and len(roles)==1:
        decision="REUSE_EXISTING_AGENT"
    elif fit>=existing_min and len(roles)>1:
        decision="COMPOSE_EXISTING_AGENTS"
    elif score>=reusable_min and reusable:
        decision="CREATE_REUSABLE_AGENT_CANDIDATE"
    elif score>=ephemeral_min:
        decision="CREATE_EPHEMERAL_AGENT"
    elif roles:
        decision="COMPOSE_EXISTING_AGENTS" if len(roles)>1 else "REUSE_EXISTING_AGENT"
    else:
        decision="TOOL_ONLY"

    agent_id=None
    if decision.startswith("CREATE_"):
        scope="reusable" if decision=="CREATE_REUSABLE_AGENT_CANDIDATE" else "ephemeral"
        agent_id=f"{project_id}:{domain}:{scope}-agent"
    elif decision=="REUSE_EXISTING_AGENT":
        agent_id=roles[0]
    elif decision=="COMPOSE_EXISTING_AGENTS":
        agent_id="+".join(roles)

    return {
        "package_id":pkg["id"],
        "domain":domain,
        "decision":decision,
        "agent_id":agent_id,
        "existing_roles":roles,
        "capabilities":caps,
        "existing_role_fit":round(fit,2),
        "agent_creation_score":score,
        "toolchain":pkg.get("toolchain") or [],
        "manifest":{
            "agent_id":agent_id,
            "purpose":f"Execute {pkg['id']} for project {project_id}",
            "scope":"project" if decision!="CREATE_REUSABLE_AGENT_CANDIDATE" else "catalog-candidate",
            "project_id":project_id,
            "domain":domain,
            "capabilities":caps,
            "provider_strategy":"domain-provider-resolver",
            "tools":pkg.get("toolchain") or [],
            "context_sources":[f"project-collector:{project_id}",f"project-domain-collector:{project_id}:{domain}"],
            "collector_bindings":[
                f"project-agent-collector:{project_id}",
                f"agent-collector:{project_id}:{agent_id}" if agent_id else None,
                "generic-domain-collector:agent-foundry"
            ],
            "memory_policy":"project-scoped-with-reusable-distillation",
            "permissions":"least-privilege-derived-from-work-package",
            "budget_policy":"ZERO_INCREMENTAL_COST_DEFAULT",
            "verification":"qualification-required-before-dispatch",
            "termination_policy":"retire-ephemeral-after-accepted-delivery",
            "promotion_policy":"qualify-generalize-and-promote-only-if-reusable"
        } if agent_id else None
    }

def build(preplan:dict[str,Any],cfg:dict[str,Any],routing:dict[str,Any],project_id:str)->dict[str,Any]:
    if cfg.get("schema")!=SCHEMA:raise SystemExit("AGENT_FOUNDRY_SCHEMA_INVALID")
    if preplan.get("schema")!="chacha.dev/domain-plan/v1":raise SystemExit("PREPLAN_SCHEMA_INVALID")
    decisions=[decide_package(p,routing,cfg,project_id) for p in preplan.get("packages") or []]
    created=[x for x in decisions if x["decision"].startswith("CREATE_")]
    composed=[x for x in decisions if x["decision"]=="COMPOSE_EXISTING_AGENTS"]
    tools=[x for x in decisions if x["decision"]=="TOOL_ONLY"]
    return {
        "schema":OUT,
        "project_id":project_id,
        "preplan_digest":digest(preplan),
        "intent":preplan.get("intent"),
        "mandatory_preflight":True,
        "decisions":decisions,
        "summary":{
            "packages":len(decisions),
            "created_agents":len(created),
            "compositions":len(composed),
            "tool_only":len(tools)
        },
        "replan_required":True,
        "return_to":"chacha-core-orchestrator",
        "dispatch_allowed":False
    }

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--preplan",required=True,type=Path)
    ap.add_argument("--config",required=True,type=Path)
    ap.add_argument("--routing",required=True,type=Path)
    ap.add_argument("--project-id",required=True)
    ap.add_argument("--output",required=True,type=Path)
    a=ap.parse_args()
    out=build(load(a.preplan),load(a.config),load(a.routing),a.project_id)
    a.output.write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("CHACHA_AGENT_FOUNDRY=PASS")
    print("CREATED_AGENTS="+str(out["summary"]["created_agents"]))
    print("REPLAN_REQUIRED=YES")

if __name__=="__main__":main()
