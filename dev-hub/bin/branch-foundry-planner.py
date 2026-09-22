#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

SCHEMA="chacha.dev/branch-foundry/v1"
OUT="chacha.dev/branch-topology/v1"

HEAVY_CAPS={
    "3d-pipeline","graphics-pipeline","animation-pipeline","performance-test-web",
    "security-scan-js","browser-automation","browser-diagnostics","cloud-deploy-edge",
}
KNOWLEDGE_CAPS={
    "documentation","architecture-documentation","library-docs","web-research",
    "collector-knowledge-inspect","translation","terminology-management",
    "publication-writing","style-transformation","technology-radar","architecture-optimization",
}

def load(path:Path)->dict[str,Any]:
    x=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise SystemExit("JSON_ROOT_NOT_OBJECT")
    return x

def digest(v:Any)->str:
    return hashlib.sha256(json.dumps(v,sort_keys=True,ensure_ascii=False).encode()).hexdigest()

def choose_profile(pkg:dict[str,Any],mode:str)->str:
    caps=set(str(x) for x in pkg.get("capabilities") or [])
    if mode=="MEMORY_ONLY":
        return "MEMORY_ONLY"
    if caps & HEAVY_CAPS:
        return "BURST"
    if len(caps)>=5:
        return "STANDARD"
    return "LIGHT"

def decide(pkg:dict[str,Any],preplan:dict[str,Any],cfg:dict[str,Any],project_id:str)->dict[str,Any]:
    domain=str(pkg.get("domain"))
    caps=[str(x) for x in pkg.get("capabilities") or []]
    implementation=bool(preplan.get("implementation_allowed"))
    simple=preplan.get("mode")=="simple_question"
    fast=cfg.get("fast_path") or {}

    if simple and not implementation:
        decision="MEMORY_ONLY"
        runtime=False
    elif not implementation and all(c in KNOWLEDGE_CAPS for c in caps):
        decision="MEMORY_ONLY"
        runtime=False
    elif pkg.get("kind")=="review":
        decision="REUSE_VIRTUAL_FACTORY"
        runtime=False
    else:
        decision="MATERIALIZE_EPHEMERAL_BRANCH"
        runtime=True

    profile=choose_profile(pkg,decision)
    profiles=cfg.get("materialization_profiles") or {}
    pconf=profiles.get(profile) or {}
    ttl=int(pconf.get("ttl_seconds") or (cfg.get("runtime_capsules") or {}).get("teardown_after_idle_seconds",900))

    branch_id=f"{project_id}:{domain}:{'review' if pkg.get('kind')=='review' else 'primary'}"
    return {
        "package_id":pkg.get("id"),
        "branch_id":branch_id,
        "domain":domain,
        "kind":pkg.get("kind"),
        "decision":decision,
        "runtime_required":runtime,
        "materialization_profile":profile,
        "ttl_seconds":0 if profile=="MEMORY_ONLY" else ttl,
        "resource_budget":{
            "memory_hard_limit_mb":pconf.get("memory_hard_limit_mb",0),
            "disk_soft_limit_mb":pconf.get("disk_soft_limit_mb",0),
            "processes_max":pconf.get("processes_max",0)
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
        "fast_path":decision=="MEMORY_ONLY",
        "reason":"simple-question-central-memory" if decision=="MEMORY_ONLY" else (
            "review-virtual-factory" if decision=="REUSE_VIRTUAL_FACTORY" else "project-work-required"
        )
    }

def build(preplan:dict[str,Any],cfg:dict[str,Any],project_id:str)->dict[str,Any]:
    if cfg.get("schema")!=SCHEMA:raise SystemExit("BRANCH_FOUNDRY_SCHEMA_INVALID")
    if preplan.get("schema")!="chacha.dev/domain-plan/v1":raise SystemExit("PREPLAN_SCHEMA_INVALID")
    decisions=[decide(p,preplan,cfg,project_id) for p in preplan.get("packages") or []]
    materialized=[x for x in decisions if x["runtime_required"]]
    memory=[x for x in decisions if x["decision"]=="MEMORY_ONLY"]
    return {
        "schema":OUT,
        "project_id":project_id,
        "preplan_digest":digest(preplan),
        "intent":preplan.get("intent"),
        "mandatory_preflight":True,
        "decisions":decisions,
        "summary":{
            "branches":len(decisions),
            "materialized":len(materialized),
            "memory_only":len(memory),
            "runtime_memory_hard_limit_mb":sum(int((x.get("resource_budget") or {}).get("memory_hard_limit_mb") or 0) for x in materialized),
            "runtime_disk_soft_limit_mb":sum(int((x.get("resource_budget") or {}).get("disk_soft_limit_mb") or 0) for x in materialized)
        },
        "central_memory_persistent":True,
        "runtime_capsules_ephemeral":True,
        "return_to":"chacha-core-orchestrator",
        "dispatch_allowed":False
    }

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--preplan",required=True,type=Path)
    ap.add_argument("--config",required=True,type=Path)
    ap.add_argument("--project-id",required=True)
    ap.add_argument("--output",required=True,type=Path)
    a=ap.parse_args()
    out=build(load(a.preplan),load(a.config),a.project_id)
    a.output.write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("CHACHA_BRANCH_FOUNDRY=PASS")
    print("BRANCHES="+str(out["summary"]["branches"]))
    print("MATERIALIZED="+str(out["summary"]["materialized"]))
    print("MEMORY_ONLY="+str(out["summary"]["memory_only"]))

if __name__=="__main__":main()
