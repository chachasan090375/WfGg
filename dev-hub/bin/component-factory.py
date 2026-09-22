#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,hashlib,time
from pathlib import Path

def load(p,default=None):
    path=Path(p)
    if not path.exists():return default if default is not None else {}
    x=json.loads(path.read_text(encoding="utf-8"))
    return x

def compatible(c,req):
    if c.get("state")!="QUALIFIED":return False
    needed=set(req.get("capabilities") or [])
    provides=set(c.get("capabilities") or [])
    return needed<=provides and bool(c.get("compatible",True))

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--request",required=True);ap.add_argument("--registry",required=True)
    ap.add_argument("--output",required=True)
    a=ap.parse_args()
    req=load(a.request);reg=load(a.registry,{"schema":"chacha.dev/component-registry/v1","components":[]})
    matches=[c for c in reg.get("components") or [] if c.get("domain")==req.get("domain") and compatible(c,req)]
    matches.sort(key=lambda c:(float(c.get("quality",0)),float(c.get("reuse_score",0))),reverse=True)
    if matches:
        chosen=matches[0];action="REUSE"
        component_id=chosen["component_id"]
    else:
        seed=json.dumps(req,sort_keys=True,ensure_ascii=False)
        component_id=f"{req.get('domain','domain')}:{hashlib.sha256(seed.encode()).hexdigest()[:12]}"
        action="BUILD"
    result={
      "schema":"chacha.dev/component-factory-plan/v1",
      "project_id":req.get("project_id"),"domain":req.get("domain"),
      "action":action,"component_id":component_id,
      "search_reuse_completed":True,
      "contract_required":True,"verification_required":True,"benchmark_required":True,
      "catalog_after_qualification":True,
      "requested_capabilities":req.get("capabilities") or [],
      "selected_existing":matches[0] if matches else None
    }
    Path(a.output).write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n")
    print("CHACHA_COMPONENT_FACTORY=PASS")
    print("COMPONENT_ACTION="+action)
if __name__=="__main__":main()
