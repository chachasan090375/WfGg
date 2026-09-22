#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

REGISTRY_SCHEMA="chacha.dev/capability-registry/v1"
ECON_SCHEMA="chacha.dev/provider-economics/v1"
HEALTH_SCHEMA="chacha.dev/provider-health-snapshot/v1"

STATUS={"ADOPT":100,"PILOT":85,"WATCH":65,"ASSESS":45,"DISCOVER":25,"DEPRECATE":5,"RETIRE":-100}
HEALTH={"HEALTHY":100,"DEGRADED":55,"UNKNOWN":20,"UNAVAILABLE":-100}

def load(path: Path,optional=False) -> dict[str,Any]:
    if optional and not path.exists():return {}
    value=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value,dict):raise SystemExit(f"JSON_ROOT_NOT_OBJECT={path}")
    return value

def recommendation_adjustment(snapshot: dict[str,Any],domain: str,provider: str) -> float:
    domains=snapshot.get("domains") if isinstance(snapshot.get("domains"),dict) else {}
    d=domains.get(domain) if isinstance(domains,dict) else None
    providers=d.get("providers") if isinstance(d,dict) and isinstance(d.get("providers"),dict) else {}
    item=providers.get(provider) if isinstance(providers,dict) else None
    if not isinstance(item,dict):return 0.0
    try:return float(item.get("score_adjustment") or 0)
    except Exception:return 0.0

def resolve(capability: str,domain: str,registry: dict[str,Any],health: dict[str,Any],economics: dict[str,Any],
            radar: dict[str,Any],paid_approved: bool=False) -> dict[str,Any]:
    cap=(registry.get("capabilities") or {}).get(capability)
    if not isinstance(cap,dict):
        return {"capability":capability,"state":"BLOCKED","reason":"capability-not-registered","candidates":[]}
    classes=economics.get("cost_classes") or {}
    weights=economics.get("selection_weights") or {}
    candidates=[]
    for p in cap.get("providers") or []:
        if not isinstance(p,dict):continue
        pid=str(p.get("id") or "")
        status=str(p.get("status") or "DISCOVER")
        if not pid or status=="RETIRE":continue
        h=(health.get("providers") or {}).get(pid) or {}
        hs=str(h.get("state") or "UNKNOWN")
        if hs=="UNAVAILABLE":continue
        cc=str(p.get("cost_class") or "paid")
        cost=classes.get(cc) or {"score":0,"automatic":False}
        automatic=bool(cost.get("automatic"))
        if not automatic and not paid_approved:
            eligible=False
            blocked="cost-approval-required"
        else:
            eligible=True
            blocked=None
        fit=100.0
        health_score=float(HEALTH.get(hs,0))
        cost_score=float(cost.get("score") or 0)
        evidence=100.0 if h.get("source") and h.get("checked_at") else 40.0
        privacy=100.0 if cc in {"free","owned","local","included"} else 60.0
        score=(
            fit*float(weights.get("capability_fit",40))/100+
            health_score*float(weights.get("health",20))/100+
            cost_score*float(weights.get("cost",20))/100+
            evidence*float(weights.get("evidence_quality",10))/100+
            privacy*float(weights.get("privacy_and_security",10))/100+
            recommendation_adjustment(radar,domain,pid)
        )
        score += STATUS.get(status,0)*0.05
        candidates.append({
            "provider":pid,"provider_status":status,"health_state":hs,"cost_class":cc,
            "eligible":eligible,"blocker":blocked,"score":round(score,2),
            "health_source":h.get("source"),"checked_at":h.get("checked_at")
        })
    eligible=[x for x in candidates if x["eligible"]]
    eligible.sort(key=lambda x:(x["score"],x["provider"]),reverse=True)
    candidates.sort(key=lambda x:(x["eligible"],x["score"],x["provider"]),reverse=True)
    if not eligible:
        return {"capability":capability,"domain":domain,"state":"BLOCKED","reason":"no-zero-cost-eligible-provider","candidates":candidates}
    chosen=eligible[0]
    return {
        "capability":capability,"domain":domain,"state":"READY",
        "provider":chosen["provider"],"score":chosen["score"],"cost_class":chosen["cost_class"],
        "reason":"capability-health-cost-evidence-radar-selection",
        "candidates":candidates
    }

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--registry",required=True,type=Path)
    ap.add_argument("--health",required=True,type=Path)
    ap.add_argument("--economics",required=True,type=Path)
    ap.add_argument("--radar",type=Path)
    ap.add_argument("--domain",required=True)
    ap.add_argument("--paid-approved",action="store_true")
    ap.add_argument("capabilities",nargs="+")
    args=ap.parse_args()
    registry=load(args.registry);health=load(args.health);economics=load(args.economics)
    radar=load(args.radar,True) if args.radar else {}
    if registry.get("schema")!=REGISTRY_SCHEMA:raise SystemExit("REGISTRY_SCHEMA_INVALID")
    if economics.get("schema")!=ECON_SCHEMA:raise SystemExit("ECONOMICS_SCHEMA_INVALID")
    if health.get("schema")!=HEALTH_SCHEMA:raise SystemExit("HEALTH_SCHEMA_INVALID")
    results=[resolve(c,args.domain,registry,health,economics,radar,args.paid_approved) for c in args.capabilities]
    print(json.dumps({"domain":args.domain,"ready":all(x["state"]=="READY" for x in results),"resolutions":results},
                     ensure_ascii=False,indent=2))

if __name__=="__main__":main()
