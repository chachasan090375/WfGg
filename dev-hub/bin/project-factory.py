#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, re
from pathlib import Path

SCHEMA="chacha.dev/project-factory/v1"
OUT="chacha.dev/project-instance/v1"

def load(p:Path):
    x=json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(x,dict): raise SystemExit("JSON_ROOT_NOT_OBJECT")
    return x

def slug(s:str):
    x=re.sub(r"[^a-z0-9]+","-",s.lower()).strip("-")
    return x[:48] or "project"

def make(intent,plan,cfg,fabric):
    if cfg.get("schema")!=SCHEMA: raise SystemExit("PROJECT_FACTORY_SCHEMA_INVALID")
    raw=str(intent.get("text") or intent.get("objective") or "").strip()
    if not raw: raise SystemExit("PROJECT_INTENT_MISSING")
    seed=json.dumps({"intent":raw,"domains":plan.get("primary_domains") or []},sort_keys=True,ensure_ascii=False)
    short=hashlib.sha256(seed.encode()).hexdigest()[:10]
    project_id=f"{slug(str(intent.get('name') or raw[:50]))}-{short}"
    domains=list(dict.fromkeys((plan.get("primary_domains") or [])+(plan.get("review_domains") or [])))
    project_collector=f"project-collector:{project_id}"
    domain_collectors=[{
        "domain":d,
        "project_collector":f"project-domain-collector:{project_id}:{d}",
        "generic_collector":f"generic-domain-collector:{d}",
        "promotion_policy":"reusable-distilled-knowledge-only"
    } for d in domains]
    return {
        "schema":OUT,
        "project_id":project_id,
        "name":str(intent.get("name") or project_id),
        "functional_intent":raw,
        "application_agnostic":True,
        "domains":domains,
        "collectors":{
            "project":project_collector,
            "domains":domain_collectors
        },
        "orchestrators":{
            "core":cfg["orchestrators"]["core"],
            "assembly":cfg["orchestrators"]["assembly"],
            "context":cfg["orchestrators"]["context"],
            "acceptance":cfg["orchestrators"]["acceptance"]
        },
        "artifacts_to_provision":cfg.get("provision_on_project_creation") or [],
        "per_domain_artifacts":cfg.get("provision_per_active_domain") or [],
        "knowledge_gateway":(fabric.get("global_query_gateway") or {}).get("name"),
        "autonomy":cfg.get("autonomy") or {},
        "delivery":cfg.get("delivery") or {}
    }

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--intent",required=True,type=Path)
    ap.add_argument("--domain-plan",required=True,type=Path)
    ap.add_argument("--config",required=True,type=Path)
    ap.add_argument("--knowledge-fabric",required=True,type=Path)
    ap.add_argument("--output",required=True,type=Path)
    a=ap.parse_args()
    out=make(load(a.intent),load(a.domain_plan),load(a.config),load(a.knowledge_fabric))
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("CHACHA_PROJECT_FACTORY=PASS")
    print("PROJECT_ID="+out["project_id"])
    print("PROJECT_DOMAIN_COUNT="+str(len(out["domains"])))

if __name__=="__main__":main()
