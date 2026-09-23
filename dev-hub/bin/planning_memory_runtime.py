#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,re
from typing import Any

SCHEMA="chacha.dev/memory-guided-foundry-advice/v1"
WORD=re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{1,120}")

def canon(v:Any)->str:
    return json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(",",":"))

def digest(v:Any)->str:
    return "sha256:"+hashlib.sha256(canon(v).encode("utf-8")).hexdigest()

def tokens(*values:Any)->set[str]:
    out=set()
    for value in values:
        raw=value if isinstance(value,str) else canon(value)
        for token in WORD.findall(str(raw).lower()):
            if len(token)>=3:
                out.add(token)
    return out

def package_tokens(pkg:dict[str,Any])->set[str]:
    return tokens(
        pkg.get("id",""),
        pkg.get("domain",""),
        pkg.get("kind",""),
        pkg.get("capabilities") or [],
        pkg.get("roles") or [],
        pkg.get("toolchain") or [],
    )

def row_score(row:dict[str,Any],pkg:dict[str,Any])->int:
    q=package_tokens(pkg)
    t=tokens(
        row.get("component_kind",""),row.get("component_id",""),row.get("version",""),
        row.get("subject_kind",""),row.get("subject_id",""),row.get("signal_key",""),
        row.get("domain",""),row.get("functional_signature",""),
    )
    score=len(q&t)*10
    domain=str(pkg.get("domain") or "").lower()
    rid=canon(row).lower()
    if domain and domain in rid:
        score+=40
    for cap in pkg.get("capabilities") or []:
        if str(cap).lower() in rid:
            score+=25
    for role in pkg.get("roles") or []:
        if str(role).lower()==str(row.get("component_id") or row.get("subject_id") or "").lower():
            score+=60
    return score

def _rank(rows:list[Any],pkg:dict[str,Any],limit:int=8)->list[dict[str,Any]]:
    scored=[]
    for row in rows:
        if not isinstance(row,dict):
            continue
        score=row_score(row,pkg)
        if score<=0:
            continue
        scored.append({"planning_relevance_score":score,**row})
    scored.sort(key=lambda x:(
        int(x.get("planning_relevance_score") or 0),
        float(x.get("confidence") or 0),
        int(x.get("verified_success_count") or x.get("success_count") or 0),
    ),reverse=True)
    return scored[:limit]

def package_advice(memory_brief:dict[str,Any]|None,pkg:dict[str,Any])->dict[str,Any]:
    mem=memory_brief or {}
    preferred=_rank(mem.get("trusted_component_candidates") or [],pkg)
    avoid=_rank(mem.get("caution_component_candidates") or [],pkg)
    reuse=_rank(mem.get("current_best_reuse_candidates") or [],pkg)
    trusted=_rank(mem.get("trusted_memory") or [],pkg)
    cautions=_rank(mem.get("cautions") or [],pkg)
    advice={
      "schema":SCHEMA,
      "package_id":str(pkg.get("id") or ""),
      "domain":str(pkg.get("domain") or ""),
      "capabilities":[str(x) for x in pkg.get("capabilities") or []],
      "source_memory_brief_digest":mem.get("brief_digest"),
      "source_memory_snapshot_digest":mem.get("source_memory_snapshot_digest"),
      "preferred_components":preferred,
      "avoid_components":avoid,
      "reuse_candidates":reuse,
      "trusted_signals":trusted,
      "caution_signals":cautions,
      "rules":{
        "memory_is_advisory":True,
        "trusted_memory_may_reorder_only_hard_valid_candidates":True,
        "negative_memory_excludes_fast_reuse":True,
        "memory_cannot_expand_capabilities":True,
        "memory_cannot_expand_permissions":True,
        "memory_cannot_skip_technology_watch":True,
        "architecture_council_final_authority":True
      },
      "automatic_external_spend_eur":0
    }
    advice["advice_digest"]=digest(advice)
    return advice

def preferred_ids(advice:dict[str,Any],kinds:set[str]|None=None)->list[str]:
    out=[]
    for row in advice.get("preferred_components") or []:
        kind=str(row.get("component_kind") or row.get("kind") or "")
        if kinds is not None and kind not in kinds:
            continue
        cid=str(row.get("component_id") or row.get("subject_id") or "")
        if cid and cid not in out:
            out.append(cid)
    return out

def avoid_ids(advice:dict[str,Any],kinds:set[str]|None=None)->set[str]:
    out=set()
    for row in advice.get("avoid_components") or []:
        kind=str(row.get("component_kind") or row.get("kind") or "")
        if kinds is not None and kind not in kinds:
            continue
        cid=str(row.get("component_id") or row.get("subject_id") or "")
        if cid:
            out.add(cid)
    return out
