#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path
from typing import Any

SCHEMA="chacha.dev/dark-intelligence-corroboration/v1"

def load(p:Path)->dict[str,Any]:
    x=json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(x,dict): raise ValueError("JSON_ROOT_NOT_OBJECT")
    return x

def save(p:Path,x:dict[str,Any])->None:
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")

def digest(v:Any)->str:
    return hashlib.sha256(json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(",",":")).encode()).hexdigest()

def search_request(dossier:dict[str,Any],policy:dict[str,Any])->dict[str,Any]:
    claims=[]
    for c in dossier.get("claims") or []:
        if not isinstance(c,dict): continue
        text=str(c.get("text") or "").strip()
        if not text: continue
        claims.append({
          "claim_id":str(c.get("id") or "claim"),
          "claim_text":text,
          "query":text,
          "required_independent_support_groups":int(policy.get("minimum_independent_support_groups") or 2)
        })
    src=dossier.get("source") if isinstance(dossier.get("source"),dict) else {}
    cfg=policy.get("corroboration_search") or {}
    return {
      "schema":"chacha.dev/dark-intelligence-corroboration-request/v1",
      "source_id":src.get("id"),"source_class":src.get("class"),"source_ref":src.get("ref"),
      "claims":claims,
      "route":{
        "domain":cfg.get("domain") or "knowledge-research",
        "role":cfg.get("owner_role") or "technology-watch-agent",
        "capability":cfg.get("capability") or "web-research",
        "provider":cfg.get("provider") or "technology-radar",
        "fallback_provider":cfg.get("fallback_provider") or "github"
      },
      "requirements":{
        "official_sources_first":bool(cfg.get("official_sources_first")),
        "independent_sources_required":True,
        "exclude_primary_source_from_corroboration":True,
        "dark_source_links_are_candidates_not_independent_proof":True
      },
      "automatic_external_spend_eur":0
    }

def _best_by_group(rows:list[dict[str,Any]],allowed:set[str],primary_group:str)->dict[str,dict[str,Any]]:
    out={}
    for e in rows:
        if not isinstance(e,dict): continue
        if e.get("verified") is not True: continue
        typ=str(e.get("type") or "")
        if typ not in allowed: continue
        group=str(e.get("independence_group") or e.get("origin") or e.get("id") or "")
        if not group or group==primary_group: continue
        prev=out.get(group)
        quality=float(e.get("confidence_score") or 50)
        if prev is None or quality>float(prev.get("confidence_score") or 50): out[group]=e
    return out

def evaluate(dossier:dict[str,Any],evidence:list[dict[str,Any]],policy:dict[str,Any])->dict[str,Any]:
    if dossier.get("schema")!="chacha.dev/dark-intelligence-dossier/v1":
        raise ValueError("DARK_CORROBORATION_DOSSIER_SCHEMA_INVALID")
    src=dossier.get("source") if isinstance(dossier.get("source"),dict) else {}
    primary_group=str(src.get("id") or "")
    q=policy.get("quality") or {}
    support_allowed={str(x) for x in q.get("accepted_support_types") or []}
    contradict_allowed={str(x) for x in q.get("accepted_contradiction_types") or []}
    min_support=int(policy.get("minimum_independent_support_groups") or 2)
    min_contra=int(policy.get("minimum_independent_contradiction_groups") or 2)
    reports=[]
    overall=[]
    for claim in dossier.get("claims") or []:
        cid=str(claim.get("id") or "")
        rows=[x for x in evidence if isinstance(x,dict) and str(x.get("claim_id") or "")==cid]
        support=_best_by_group([x for x in rows if str(x.get("stance") or "SUPPORT").upper()=="SUPPORT"],support_allowed,primary_group)
        contra=_best_by_group([x for x in rows if str(x.get("stance") or "").upper()=="CONTRADICT"],contradict_allowed,primary_group)
        if len(contra)>=min_contra and len(contra)>len(support):
            verdict="CONTRADICTED"
        elif len(support)>=min_support and len(contra)==0:
            verdict="CORROBORATED"
        else:
            verdict="INCONCLUSIVE"
        overall.append(verdict)
        reports.append({
          "claim_id":cid,"verdict":verdict,
          "independent_support_groups":len(support),
          "independent_contradiction_groups":len(contra),
          "support_groups":sorted(support),
          "contradiction_groups":sorted(contra),
          "primary_dark_source_excluded":True
        })
    if reports and all(x=="CORROBORATED" for x in overall): verdict="CORROBORATED"
    elif any(x=="CONTRADICTED" for x in overall): verdict="CONTRADICTED"
    else: verdict="INCONCLUSIVE"
    return {
      "schema":SCHEMA,"verdict":verdict,"source_id":src.get("id"),
      "claim_reports":reports,
      "primary_dark_source_never_counted_as_independent_corroboration":True,
      "fact_promotion_allowed":False,
      "technology_watch_re_evaluation_required":True,
      "logician_falsification_required":True,
      "architecture_council_final_authority":True,
      "guardian_required":True,"sentinel_required":True,
      "evidence_digest":digest(evidence),
      "automatic_external_spend_eur":0
    }

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--policy",type=Path,required=True)
    sub=ap.add_subparsers(dest="cmd",required=True)
    r=sub.add_parser("request");r.add_argument("--dossier",type=Path,required=True);r.add_argument("--output",type=Path,required=True)
    e=sub.add_parser("evaluate");e.add_argument("--dossier",type=Path,required=True);e.add_argument("--evidence",type=Path,required=True);e.add_argument("--output",type=Path,required=True)
    a=ap.parse_args();policy=load(a.policy);dossier=load(a.dossier)
    if a.cmd=="request":out=search_request(dossier,policy)
    else:
        raw=load(a.evidence);rows=raw.get("evidence") if isinstance(raw.get("evidence"),list) else []
        out=evaluate(dossier,rows,policy)
    save(a.output,out);print(json.dumps(out,ensure_ascii=False))
    print("CHACHA_DEV_V801_DARK_CORROBORATION_"+a.cmd.upper()+"=PASS")
    return 0
if __name__=="__main__":raise SystemExit(main())
