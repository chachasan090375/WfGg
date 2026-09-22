#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,re,hashlib
from pathlib import Path

def load(p):
    x=json.loads(Path(p).read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise SystemExit("JSON_ROOT_NOT_OBJECT")
    return x

def slug(s):
    return re.sub(r"[^a-z0-9]+","-",s.lower()).strip("-")[:64] or "capability"

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--request",required=True);ap.add_argument("--policy",required=True)
    ap.add_argument("--domains",required=True);ap.add_argument("--capabilities",required=True)
    ap.add_argument("--output",required=True)
    a=ap.parse_args()
    req,policy,domains,caps=map(load,[a.request,a.policy,a.domains,a.capabilities])
    existing_domains=domains.get("domains") or {}
    existing_caps=caps.get("capabilities") or {}
    project=str(req.get("project_id") or "unknown")
    out=[]
    for gap in req.get("missing_capabilities") or []:
        cid=str(gap.get("id") or "").strip()
        if not cid:continue
        owner=str(gap.get("domain") or "").strip()
        create_domain=False
        if owner not in existing_domains:
            owner="domain-"+slug(owner or cid)
            create_domain=True
        already=cid in existing_caps
        candidates=gap.get("architecture_candidates") or []
        architecture_competition=len(candidates)>=2
        out.append({
          "capability":cid,"already_registered":already,"owner_domain":owner,
          "create_domain":create_domain and not already,
          "domain_factory_id":owner if create_domain else None,
          "technology_watch_required":not already,
          "architecture_competition_required":architecture_competition,
          "sandbox_required":not already,
          "generic_collector":f"generic-domain-collector:{owner}",
          "project_domain_collector":f"project-domain-collector:{project}:{owner}",
          "contracts_required":["component","integration"],
          "fixtures_required":True,
          "rollback_required":True,
          "state":"REUSE" if already else "DESIGN"
        })
    result={
      "schema":"chacha.dev/capability-foundry-plan/v1",
      "project_id":project,"plans":out,
      "created_domain_count":sum(1 for x in out if x["create_domain"]),
      "created_capability_count":sum(1 for x in out if not x["already_registered"]),
      "core_replan_required":any(not x["already_registered"] for x in out),
      "agent_foundry_rerun_required":any(not x["already_registered"] for x in out)
    }
    Path(a.output).write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n")
    print("CHACHA_CAPABILITY_FOUNDRY=PASS")
    print("CAPABILITY_FOUNDRY_NEW="+str(result["created_capability_count"]))
    print("CAPABILITY_FOUNDRY_DOMAINS="+str(result["created_domain_count"]))
if __name__=="__main__":main()
