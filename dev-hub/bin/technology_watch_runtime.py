#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import sqlite3

DEFAULT_CONFIG = Path("dev-hub/config/technology-watch-runtime.v1.json")
ZERO_DEFAULT = {"free", "owned", "local", "included"}
ADMISSIBLE_DEFAULT = {"ADOPT", "ENABLED"}

def _load(path: Path) -> dict[str, Any]:
    value=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value,dict):
        raise RuntimeError(f"JSON_ROOT_NOT_OBJECT:{path}")
    return value

def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00","Z")

def _digest(value: Any) -> str:
    raw=json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(",",":")).encode()
    return hashlib.sha256(raw).hexdigest()

def _snapshot_path(cfg: dict[str, Any]) -> Path:
    override=os.environ.get("CHACHA_TECHNOLOGY_WATCH_SNAPSHOT","").strip()
    return Path(override or str(cfg["snapshot"]))

def load_config(repo_root: Path) -> dict[str, Any]:
    cfg=_load(repo_root/DEFAULT_CONFIG)
    if cfg.get("schema")!="chacha.dev/technology-watch-runtime/v1":
        raise RuntimeError("TECHNOLOGY_WATCH_CONFIG_SCHEMA_INVALID")
    return cfg

def _provider_candidate(provider: dict[str, Any], capability: str, cfg: dict[str, Any]) -> dict[str, Any]:
    status=str(provider.get("status") or provider.get("runtime_status") or "UNKNOWN").upper()
    cost_class=str(provider.get("cost_class") or "unknown").lower()
    zero_classes=set(cfg.get("zero_external_cost_classes") or ZERO_DEFAULT)
    conditional=set(cfg.get("conditional_zero_cost_classes") or ["quota"])
    quota_ok=bool(provider.get("quota_available") is True)
    zero=(cost_class in zero_classes) or (cost_class in conditional and quota_ok)
    admissible=status in set(cfg.get("admissible_provider_statuses") or ADMISSIBLE_DEFAULT)
    return {
        "id":str(provider.get("id") or "unknown"),
        "capability":capability,
        "status":status,
        "health":provider.get("health"),
        "scope":provider.get("scope"),
        "cost_class":cost_class,
        "external_spend_eur":0 if zero else None,
        "zero_external_spend":zero,
        "admissible_for_automatic_selection":admissible,
        "fallback":provider.get("fallback") or [],
        "evidence":"capability-registry",
    }

def _reusable_branch_taxonomy(db_path: Path) -> dict[str, Any]:
    if not db_path.is_file():
        return {"branch_count":0,"domains":{}}
    try:
        db=sqlite3.connect(db_path)
        rows=db.execute("""SELECT domain,branch_id,version,qualification_status,state,
                          technology_revalidated_at,external_spend_eur,quality_score
                          FROM reusable_branches""").fetchall()
    except Exception:
        return {"branch_count":0,"domains":{}}
    domains={}
    for domain,branch_id,version,qualification,state,revalidated,cost,quality in rows:
        domains.setdefault(str(domain),[]).append({
            "branch_id":branch_id,"version":version,"qualification_status":qualification,
            "state":state,"technology_revalidated_at":revalidated,
            "external_spend_eur":cost,"quality_score":quality
        })
    return {"branch_count":len(rows),"domains":domains}


def _technology_taxonomy(domains: dict[str, Any], capreg: dict[str, Any], candidates: list[dict[str, Any]]) -> dict[str, Any]:
    out={}
    domain_specs=domains.get("domains") or {}
    cap_specs=capreg.get("capabilities") or {}
    for domain,spec in domain_specs.items():
        if not isinstance(spec,dict): continue
        caps=[str(x) for x in spec.get("capabilities") or []]
        providers=sorted({str(x.get("id")) for x in candidates if isinstance(x,dict) and str(x.get("capability")) in set(caps)})
        out[str(domain)]={
            "capabilities":sorted(caps),
            "known_provider_ids":providers,
            "orchestrator":spec.get("orchestrator"),
            "roles":spec.get("roles") or [],
            "reviews":spec.get("reviews") or []
        }
    unowned=[]
    owned={cap for spec in out.values() for cap in spec.get("capabilities") or []}
    for cap in cap_specs:
        if cap not in owned: unowned.append(str(cap))
    return {
        "domain_categories":out,
        "unowned_capabilities":sorted(unowned),
        "known_domain_count":len(out),
        "known_capability_count":len(cap_specs)
    }


def build_snapshot(repo_root: Path, *, scope_domain: str|None=None,
                   scope_capabilities: list[str]|None=None,
                   targeted: bool=False) -> dict[str, Any]:
    cfg=load_config(repo_root)
    capreg=_load(repo_root/"dev-hub/config/capability-registry.v1.json")
    domains=_load(repo_root/"dev-hub/config/domain-orchestration.v1.json")
    economics=_load(repo_root/"dev-hub/config/provider-economics.v1.json")
    requested={str(x) for x in (scope_capabilities or []) if str(x)}
    candidates=[]
    for capability,spec in (capreg.get("capabilities") or {}).items():
        if requested and capability not in requested:
            continue
        if not isinstance(spec,dict):
            continue
        for p in spec.get("providers") or []:
            if isinstance(p,dict):
                candidates.append(_provider_candidate(p,str(capability),cfg))
    eligible=[x for x in candidates if x["admissible_for_automatic_selection"]]
    zero=[x for x in eligible if x["zero_external_spend"]]
    selected_pool=zero if zero else eligible
    selected_pool=sorted(selected_pool,key=lambda x:(x["cost_class"],x["id"],x["capability"]))
    reusable_db=Path(os.environ.get("CHACHA_REUSABLE_BRANCH_DB","/opt/chacha-dev/runtime/knowledge/reusable-branches.db"))
    taxonomy=_technology_taxonomy(domains,capreg,candidates)
    reusable_taxonomy=_reusable_branch_taxonomy(reusable_db)
    body={
        "schema":"chacha.dev/technology-watch-snapshot/v1",
        "generated_at":_utcnow(),
        "targeted":bool(targeted),
        "scope":{"domain":scope_domain,"capabilities":sorted(requested)},
        "source_mode":"DETERMINISTIC_REGISTRIES_FIRST",
        "sources":[
            "dev-hub/config/capability-registry.v1.json",
            "dev-hub/config/domain-orchestration.v1.json",
            "dev-hub/config/provider-economics.v1.json"
        ],
        "domain_count":len(domains.get("domains") or {}),
        "candidate_count":len(candidates),
        "eligible_candidate_count":len(eligible),
        "zero_spend_candidate_count":len(zero),
        "zero_spend_candidate_available":bool(zero),
        "selection_rule":cfg["zero_spend_rule"],
        "automatic_external_spend_eur":0,
        "provider_candidates":candidates,
        "eligible_provider_candidates":selected_pool,
        "branch_blueprints":[],
        "technology_taxonomy":taxonomy,
        "reusable_branch_taxonomy":reusable_taxonomy,
        "provider_economics_digest":_digest(economics),
    }
    body["snapshot_digest"]=_digest(body)
    return body

def _parse_ts(value: str) -> float:
    return datetime.fromisoformat(value.replace("Z","+00:00")).timestamp()

def snapshot_status(repo_root: Path) -> dict[str, Any]:
    cfg=load_config(repo_root); path=_snapshot_path(cfg)
    if not path.is_file():
        return {"state":"MISSING","fresh":False,"path":str(path),"age_seconds":None}
    try:
        snap=_load(path)
        age=max(0.0,time.time()-_parse_ts(str(snap.get("generated_at") or "")))
    except Exception as exc:
        return {"state":"INVALID","fresh":False,"path":str(path),"age_seconds":None,"reason":str(exc)}
    max_age=int(cfg.get("maximum_snapshot_age_minutes") or 60)*60
    return {"state":"FRESH" if age<=max_age else "STALE","fresh":age<=max_age,
            "path":str(path),"age_seconds":round(age,3),
            "snapshot_digest":snap.get("snapshot_digest")}

def write_full_snapshot(repo_root: Path) -> dict[str, Any]:
    cfg=load_config(repo_root); path=_snapshot_path(cfg)
    snap=build_snapshot(repo_root,targeted=False)
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+".tmp")
    tmp.write_text(json.dumps(snap,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    os.replace(tmp,path)
    return snap

def _filter_snapshot(snapshot: dict[str, Any], capabilities: list[str]) -> list[dict[str, Any]]:
    wanted={str(x) for x in capabilities if str(x)}
    rows=[x for x in snapshot.get("provider_candidates") or []
          if isinstance(x,dict) and (not wanted or str(x.get("capability")) in wanted)]
    eligible=[x for x in rows if x.get("admissible_for_automatic_selection") is True]
    zero=[x for x in eligible if x.get("zero_external_spend") is True]
    pool=zero if zero else eligible
    return sorted(pool,key=lambda x:(str(x.get("cost_class")),str(x.get("id")),str(x.get("capability"))))

def consult(repo_root: Path, *, consumer: str, domain: str,
            capabilities: list[str]) -> dict[str, Any]:
    cfg=load_config(repo_root); path=_snapshot_path(cfg)
    status=snapshot_status(repo_root)
    targeted=False
    if status.get("fresh") and path.is_file():
        snap=_load(path)
    else:
        snap=build_snapshot(repo_root,scope_domain=domain,scope_capabilities=capabilities,targeted=True)
        targeted=True
    pool=_filter_snapshot(snap,capabilities)
    zero=any(x.get("zero_external_spend") is True for x in pool)
    return {
        "schema":"chacha.dev/technology-watch-materialization-feed/v1",
        "consumer":consumer,
        "domain":domain,
        "capabilities":capabilities,
        "consulted_at":_utcnow(),
        "snapshot_freshness":status.get("state"),
        "targeted_refresh_performed":targeted,
        "source_snapshot_digest":snap.get("snapshot_digest"),
        "zero_spend_candidate_available":zero,
        "selection_rule":cfg["zero_spend_rule"],
        "automatic_external_spend_eur":0,
        "eligible_provider_candidates":pool,
        "branch_blueprints":snap.get("branch_blueprints") or [],
    }
