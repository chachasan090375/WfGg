#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,re,hashlib
from pathlib import Path

import technology_watch_runtime as tw

def load(p):
    x=json.loads(Path(p).read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise SystemExit("JSON_ROOT_NOT_OBJECT")
    return x

def slug(s):
    return re.sub(r"[^a-z0-9]+","-",s.lower()).strip("-")[:64] or "capability"

def generated_domain(owner,cid):
    dslug=slug(owner or cid)
    domain="domain-"+dslug if not str(owner).startswith("domain-") else str(owner)
    role=f"{dslug}-specialist"
    return domain,role,{
      "orchestrator":f"{domain}-orchestrator",
      "roles":[role],
      "capabilities":[cid],
      "keywords":[cid,dslug],
      "toolchain":[],
      "reviews":["qa","cybersecurity"],
      "generated_by":"capability-foundry",
      "promotion_state":"PROJECT_LOCAL"
    }

def generated_capability(cid,domain):
    return {
      "class":"execution",
      "providers":[{
        "id":"chacha-dev-architect",
        "status":"PILOT",
        "health":"runtime-check",
        "cost_class":"local",
        "scope":"project",
        "fallback":[]
      }],
      "generated_by":"capability-foundry",
      "owner_domain":domain,
      "promotion_state":"PROJECT_LOCAL"
    }

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--request",required=True);ap.add_argument("--policy",required=True)
    ap.add_argument("--domains",required=True);ap.add_argument("--capabilities",required=True)
    ap.add_argument("--output",required=True)
    ap.add_argument("--domain-overlay")
    ap.add_argument("--capability-overlay")
    ap.add_argument("--routing-overlay")
    a=ap.parse_args()
    req,policy,domains,caps=map(load,[a.request,a.policy,a.domains,a.capabilities])
    existing_domains=domains.get("domains") or {}
    existing_caps=caps.get("capabilities") or {}
    project=str(req.get("project_id") or "unknown")
    repo_root=Path(__file__).resolve().parents[2]
    plans=[];domain_overlay={};cap_overlay={};roles={}
    for gap in req.get("missing_capabilities") or []:
        cid=str(gap.get("id") or "").strip()
        if not cid:continue
        owner_hint=str(gap.get("domain") or "").strip()
        watch=tw.consult(
            repo_root,
            consumer="capability-foundry",
            domain=owner_hint,
            capabilities=[cid],
        )
        already=cid in existing_caps
        if owner_hint in existing_domains:
            owner=owner_hint;create_domain=False;role=None;domain_def=None
        else:
            owner,role,domain_def=generated_domain(owner_hint,cid);create_domain=not already
        candidates=gap.get("architecture_candidates") or []
        if create_domain and domain_def:
            domain_overlay[owner]=domain_def
            roles[role]={"capabilities":[cid],"default_risk":"medium","generated_by":"capability-foundry","promotion_state":"PROJECT_LOCAL"}
        if not already:
            cap_overlay[cid]=generated_capability(cid,owner)
        plans.append({
          "capability":cid,"already_registered":already,"owner_domain":owner,
          "create_domain":create_domain,
          "domain_factory_id":owner if create_domain else None,
          "generated_role":role,
          "technology_watch_required":True,
          "technology_candidates":watch.get("eligible_provider_candidates") or [],
          "technology_watch":{
            "consulted":True,
            "snapshot_freshness":watch.get("snapshot_freshness"),
            "targeted_refresh_performed":watch.get("targeted_refresh_performed"),
            "source_snapshot_digest":watch.get("source_snapshot_digest"),
            "zero_spend_candidate_available":watch.get("zero_spend_candidate_available"),
            "selection_rule":watch.get("selection_rule"),
            "automatic_external_spend_eur":0
          },
          "architecture_competition_required":len(candidates)>=2,
          "architecture_candidates":candidates,
          "sandbox_required":not already,
          "generic_collector":f"generic-domain-collector:{owner}",
          "project_domain_collector":f"project-domain-collector:{project}:{owner}",
          "contracts_required":["component","integration"],
          "fixtures_required":True,"rollback_required":True,
          "state":"REUSE" if already else "PROJECT_LOCAL_PILOT"
        })
    result={
      "schema":"chacha.dev/capability-foundry-plan/v1","project_id":project,"plans":plans,
      "domain_overlay":domain_overlay,"capability_overlay":cap_overlay,"role_overlay":roles,
      "created_domain_count":len(domain_overlay),"created_capability_count":len(cap_overlay),
      "technology_watch_consulted":True,
      "core_replan_required":bool(cap_overlay or domain_overlay),
      "agent_foundry_rerun_required":bool(cap_overlay or domain_overlay),
      "promotion_requires_qualification":True
    }
    Path(a.output).write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n")
    if a.domain_overlay:
        Path(a.domain_overlay).write_text(json.dumps({"schema":"chacha.dev/domain-overlay/v1","domains":domain_overlay},indent=2,ensure_ascii=False)+"\n")
    if a.capability_overlay:
        Path(a.capability_overlay).write_text(json.dumps({"schema":"chacha.dev/capability-overlay/v1","capabilities":cap_overlay},indent=2,ensure_ascii=False)+"\n")
    if a.routing_overlay:
        Path(a.routing_overlay).write_text(json.dumps({"schema":"chacha.dev/agent-routing-overlay/v1","roles":roles},indent=2,ensure_ascii=False)+"\n")
    print("CHACHA_CAPABILITY_FOUNDRY=PASS")
    print("CHACHA_CAPABILITY_FOUNDRY_TECHNOLOGY_WATCH=CONSULTED")
    print("CAPABILITY_FOUNDRY_NEW="+str(result["created_capability_count"]))
    print("CAPABILITY_FOUNDRY_DOMAINS="+str(result["created_domain_count"]))
    print("CAPABILITY_FOUNDRY_PROJECT_LOCAL_OVERLAY=YES")
if __name__=="__main__":main()
