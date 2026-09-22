#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

SCHEMA="chacha.dev/domain-orchestration/v1"
OUTPUT="chacha.dev/domain-plan/v1"
TOPOLOGY_SCHEMA="chacha.dev/agent-topology/v1"
BRANCH_TOPOLOGY_SCHEMA="chacha.dev/branch-topology/v1"

QUESTION_HINTS=("?","qu'est-ce","comment ","pourquoi ","où ","quel ","quelle ","peux-tu m'expliquer","explique")
CHANGE_HINTS=("crée","cree","ajoute","modifie","corrige","déploie","deploy","implémente","implemente","construis","installe","migration","remplace")

def load(path: Path) -> dict[str,Any]:
    value=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value,dict):raise SystemExit("JSON_ROOT_NOT_OBJECT")
    return value

def normalize(text: str) -> str:
    return re.sub(r"\s+"," ",text.strip().lower())

def canonical_digest(value: Any) -> str:
    raw=json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(",",":")).encode()
    return hashlib.sha256(raw).hexdigest()

def infer_mode(text: str, matched: list[str], explicit_mode: str|None) -> str:
    if explicit_mode:
        return explicit_mode
    has_change=any(x in text for x in CHANGE_HINTS)
    has_question=any(x in text for x in QUESTION_HINTS)
    if not has_change and has_question and len(matched)<=1:
        return "simple_question"
    if len(matched)<=2:
        return "focused_change"
    return "multi_domain_change"

def match_domains(text: str,cfg: dict[str,Any],explicit: list[str]) -> tuple[list[str],dict[str,list[str]]]:
    domains=cfg.get("domains") or {}
    reasons={}
    for d in explicit:
        if d in domains:
            reasons.setdefault(d,[]).append("explicit")
    if not explicit:
        for domain,spec in domains.items():
            hits=sorted({str(k) for k in spec.get("keywords") or [] if normalize(str(k)) in text})
            if hits:
                reasons.setdefault(domain,[]).append("keywords:"+",".join(hits[:8]))
    if not reasons:
        reasons["product"]=["fallback:intent-normalization"]
        reasons["knowledge-research"]=["fallback:unknown-domain-research"]
    order=list(domains)
    matched=[d for d in order if d in reasons]
    return matched,reasons

def expand_reviews(primary: list[str],cfg: dict[str,Any]) -> list[str]:
    domains=cfg.get("domains") or {}
    reviews=[]
    for d in primary:
        for r in (domains.get(d) or {}).get("reviews") or []:
            if r in domains and r not in primary and r not in reviews:
                reviews.append(r)
    return reviews

def work_packages(primary: list[str],reviews: list[str],cfg: dict[str,Any],text: str) -> list[dict[str,Any]]:
    domains=cfg.get("domains") or {}
    out=[]
    for d in primary:
        spec=domains[d]
        out.append({
            "id":f"domain:{d}",
            "domain":d,
            "kind":"primary",
            "orchestrator":spec.get("orchestrator"),
            "roles":spec.get("roles") or [],
            "capabilities":spec.get("capabilities") or [],
            "toolchain":spec.get("toolchain") or [],
            "intent_excerpt":text[:1000],
        })
    for d in reviews:
        spec=domains[d]
        out.append({
            "id":f"review:{d}",
            "domain":d,
            "kind":"review",
            "orchestrator":spec.get("orchestrator"),
            "roles":spec.get("roles") or [],
            "capabilities":spec.get("capabilities") or [],
            "toolchain":spec.get("toolchain") or [],
        })
    return out

def dependency_edges(packages: list[dict[str,Any]],cfg: dict[str,Any]) -> list[dict[str,str]]:
    present={x["domain"] for x in packages}
    edges=[]
    for src,targets in (cfg.get("dependencies") or {}).items():
        if src not in present:continue
        for dst in targets or []:
            if dst in present:
                edges.append({"from":src,"to":dst})
    return edges

def _preplan(intent: dict[str,Any],cfg: dict[str,Any]) -> dict[str,Any]:
    raw=str(intent.get("text") or intent.get("objective") or "").strip()
    if not raw:raise SystemExit("INTENT_TEXT_MISSING")
    text=normalize(raw)
    explicit=[str(x) for x in intent.get("domains") or []]
    primary,reasons=match_domains(text,cfg,explicit)
    mode=infer_mode(text,primary,str(intent.get("mode") or "") or None)
    max_domains=int((cfg.get("request_modes") or {}).get(mode,{}).get("max_primary_domains",12))
    if len(primary)>max_domains:
        mode="multi_domain_change"
    reviews=expand_reviews(primary,cfg)
    packages=work_packages(primary,reviews,cfg,raw)
    return {
        "schema":OUTPUT,
        "plan_stage":"PREPLAN",
        "mode":mode,
        "intent":raw,
        "primary_domains":primary,
        "review_domains":reviews,
        "reasons":reasons,
        "packages":packages,
        "dependencies":dependency_edges(packages,cfg),
        "implementation_allowed":bool((cfg.get("request_modes") or {}).get(mode,{}).get("implementation_allowed",False)),
        "provider_selection":{
            "owner":"domain-orchestrator",
            "resolver":"domain-provider-resolver",
            "technology_watch_required":True,
            "economics_policy_required":True
        },
        "agent_foundry":{
            "required":True,
            "branch":"agent-foundry",
            "policy":(cfg.get("preflight") or {}).get("policy","dev-hub/config/agent-foundry.v1.json"),
            "returns_to":"chacha-core-orchestrator"
        },
        "dispatch_allowed":False,
        "replan_required":True,
        "production_change_allowed":False
    }

def apply_topology(preplan:dict[str,Any],topology:dict[str,Any],cfg:dict[str,Any]) -> dict[str,Any]:
    if topology.get("schema")!=TOPOLOGY_SCHEMA:
        raise SystemExit("AGENT_TOPOLOGY_SCHEMA_INVALID")
    if str(topology.get("intent") or "") != str(preplan.get("intent") or ""):
        raise SystemExit("AGENT_TOPOLOGY_INTENT_MISMATCH")

    directives=topology.get("replan_directives") if isinstance(topology.get("replan_directives"),dict) else {}
    domains_cfg=cfg.get("domains") or {}
    primary=list(preplan["primary_domains"])
    reasons={k:list(v) for k,v in (preplan.get("reasons") or {}).items()}

    for d in directives.get("remove_domains") or []:
        if d in primary:
            primary.remove(d)
            reasons.setdefault(d,[]).append("agent-foundry:removed")
    added=[]
    for d in directives.get("add_domains") or []:
        if d in domains_cfg and d not in primary:
            primary.append(d);added.append(d)
            reasons.setdefault(d,[]).append("agent-foundry:added")

    order=list(domains_cfg)
    primary=[d for d in order if d in primary]
    reviews=expand_reviews(primary,cfg)
    packages=work_packages(primary,reviews,cfg,preplan["intent"])
    decisions={str(x.get("package_id")):x for x in topology.get("decisions") or [] if isinstance(x,dict)}

    unresolved=[]
    for pkg in packages:
        decision=decisions.get(pkg["id"])
        if decision is None:
            pkg["agent_topology_status"]="UNRESOLVED"
            unresolved.append(pkg["id"])
        else:
            pkg["agent_topology_status"]="RESOLVED"
            pkg["execution_mode"]=decision.get("decision")
            pkg["agent_id"]=decision.get("agent_id")
            pkg["agent_creation_score"]=decision.get("agent_creation_score")
            pkg["agent_manifest"]=decision.get("manifest")

    # If Foundry adds a domain, that new domain must itself pass Foundry before dispatch.
    foundry_iteration_required=bool(added or unresolved)
    out=dict(preplan)
    out.update({
        "plan_stage":"REPLANNED" if not foundry_iteration_required else "PREPLAN_REVISED",
        "primary_domains":primary,
        "review_domains":reviews,
        "reasons":reasons,
        "packages":packages,
        "dependencies":dependency_edges(packages,cfg),
        "agent_foundry":{
            "required":True,
            "completed":not foundry_iteration_required,
            "topology_digest":canonical_digest(topology),
            "iterations_required":2 if foundry_iteration_required else 1,
            "added_domains":added,
            "unresolved_packages":unresolved
        },
        "dispatch_allowed":not foundry_iteration_required,
        "replan_required":foundry_iteration_required,
        "production_change_allowed":False
    })
    return out

def apply_branch_topology(plan:dict[str,Any],branch_topology:dict[str,Any]) -> dict[str,Any]:
    if branch_topology.get("schema")!=BRANCH_TOPOLOGY_SCHEMA:
        raise SystemExit("BRANCH_TOPOLOGY_SCHEMA_INVALID")
    if str(branch_topology.get("intent") or "") != str(plan.get("intent") or ""):
        raise SystemExit("BRANCH_TOPOLOGY_INTENT_MISMATCH")
    decisions={str(x.get("package_id")):x for x in branch_topology.get("decisions") or [] if isinstance(x,dict)}
    unresolved=[]
    packages=[]
    for pkg in plan.get("packages") or []:
        x=dict(pkg)
        b=decisions.get(str(pkg.get("id")))
        if b is None:
            x["branch_topology_status"]="UNRESOLVED"
            unresolved.append(str(pkg.get("id")))
        else:
            x["branch_topology_status"]="RESOLVED"
            x["branch_id"]=b.get("branch_id")
            x["branch_decision"]=b.get("decision")
            x["runtime_required"]=b.get("runtime_required")
            x["materialization_profile"]=b.get("materialization_profile")
            x["orchestrator_strategy"]=b.get("orchestrator_strategy")
            x["runtime_architecture"]=b.get("architecture")
            x["component_strategy"]=b.get("component_strategy")
            x["resource_budget"]=b.get("resource_budget")
            x["branch_cost"]=b.get("chosen_cost")
            x["collector_bindings"]=b.get("collector_bindings")
        packages.append(x)
    out=dict(plan)
    out["packages"]=packages
    out["branch_foundry"]={
        "required":True,
        "completed":not unresolved and not bool(branch_topology.get("blocked")),
        "topology_digest":canonical_digest(branch_topology),
        "unresolved_packages":unresolved,
        "runtime_summary":branch_topology.get("summary") or {}
    }
    ready=bool((out.get("agent_foundry") or {}).get("completed")) and out["branch_foundry"]["completed"]
    out["dispatch_allowed"]=ready and not bool(out.get("replan_required"))
    if ready and not out.get("replan_required"):
        out["plan_stage"]="TOPOLOGIES_RECONCILED"
    return out

def make_plan(intent: dict[str,Any],cfg: dict[str,Any],topology:dict[str,Any]|None=None,
              branch_topology:dict[str,Any]|None=None) -> dict[str,Any]:
    if cfg.get("schema")!=SCHEMA:
        raise SystemExit("DOMAIN_ORCHESTRATION_SCHEMA_INVALID")
    preplan=_preplan(intent,cfg)
    if topology is None and branch_topology is None:
        return preplan
    plan=preplan
    if topology is not None:
        plan=apply_topology(plan,topology,cfg)
    if branch_topology is not None:
        plan=apply_branch_topology(plan,branch_topology)
    else:
        plan=dict(plan)
        plan["branch_foundry"]={"required":True,"completed":False}
        plan["dispatch_allowed"]=False
    return plan

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--config",required=True,type=Path)
    ap.add_argument("--intent",required=True,type=Path)
    ap.add_argument("--agent-topology",type=Path)
    ap.add_argument("--branch-topology",type=Path)
    ap.add_argument("--output",type=Path)
    args=ap.parse_args()
    topology=load(args.agent_topology) if args.agent_topology else None
    branch_topology=load(args.branch_topology) if args.branch_topology else None
    plan=make_plan(load(args.intent),load(args.config),topology,branch_topology)
    payload=json.dumps(plan,ensure_ascii=False,indent=2)+"\n"
    if args.output:args.output.write_text(payload,encoding="utf-8")
    else:print(payload,end="")

if __name__=="__main__":main()
