#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

SCHEMA="chacha.dev/domain-orchestration/v1"
OUTPUT="chacha.dev/domain-plan/v1"

QUESTION_HINTS=("?","qu'est-ce","comment ","pourquoi ","où ","quel ","quelle ","peux-tu m'expliquer","explique")
CHANGE_HINTS=("crée","cree","ajoute","modifie","corrige","déploie","deploy","implémente","implemente","construis","installe","migration","remplace")

def load(path: Path) -> dict[str,Any]:
    value=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value,dict):raise SystemExit("JSON_ROOT_NOT_OBJECT")
    return value

def normalize(text: str) -> str:
    return re.sub(r"\s+"," ",text.strip().lower())

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

def make_plan(intent: dict[str,Any],cfg: dict[str,Any]) -> dict[str,Any]:
    if cfg.get("schema")!=SCHEMA:
        raise SystemExit("DOMAIN_ORCHESTRATION_SCHEMA_INVALID")
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
            "technology_radar_required":True,
            "economics_policy_required":True
        },
        "production_change_allowed":False
    }

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--config",required=True,type=Path)
    ap.add_argument("--intent",required=True,type=Path)
    ap.add_argument("--output",type=Path)
    args=ap.parse_args()
    plan=make_plan(load(args.intent),load(args.config))
    payload=json.dumps(plan,ensure_ascii=False,indent=2)+"\n"
    if args.output:args.output.write_text(payload,encoding="utf-8")
    else:print(payload,end="")

if __name__=="__main__":main()
