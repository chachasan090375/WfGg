#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, re
from pathlib import Path
from typing import Any

SCHEMA="chacha.dev/capability-build-request-batch/v1"

def load(p:Path)->dict[str,Any]:
    x=json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(x,dict): raise SystemExit("JSON_ROOT_NOT_OBJECT")
    return x

def save(p:Path,x:dict[str,Any])->None:
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")

def slug(v:str)->str:
    return re.sub(r"[^a-z0-9]+","-",v.lower()).strip("-")[:63]

def candidate_id(c:dict[str,Any])->str:
    return str(c.get("provider_id") or c.get("id") or "").strip()

def zero(v:Any)->bool:
    try:return float(v or 0)==0
    except Exception:return False

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--closure",type=Path,required=True)
    ap.add_argument("--foundry-plan",type=Path,required=True)
    ap.add_argument("--architecture-council",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    a=ap.parse_args()

    closure=load(a.closure);foundry=load(a.foundry_plan);council=load(a.architecture_council)
    if closure.get("schema")!="chacha.dev/capability-foundry-closure-plan/v1":
        raise SystemExit("CLOSURE_SCHEMA_INVALID")
    if foundry.get("schema")!="chacha.dev/capability-foundry-plan/v1":
        raise SystemExit("FOUNDRY_SCHEMA_INVALID")
    if council.get("dispatch_allowed") is not True:
        out={"schema":SCHEMA,"project_id":closure.get("project_id"),"status":"BLOCKED",
             "requests":[],"unresolved":[{"reason":"ARCHITECTURE_COUNCIL_NOT_APPROVED"}],
             "buildable_count":0,"unresolved_count":1}
        save(a.output,out)
        print("CHACHA_DEV_V641_BUILD_REQUEST_COMPILER=BLOCKED")
        return 0

    digest="sha256:"+hashlib.sha256(a.architecture_council.read_bytes()).hexdigest()
    foundry_map={str(x.get("capability")):x for x in foundry.get("plans") or [] if isinstance(x,dict)}
    requests=[];unresolved=[]
    for row in closure.get("plans") or []:
        if not isinstance(row,dict) or row.get("state")!="BUILD_REQUIRED":
            continue
        cap=str(row.get("capability") or "")
        fp=foundry_map.get(cap) or {}
        watch=fp.get("technology_watch") if isinstance(fp.get("technology_watch"),dict) else {}
        if watch.get("consulted") is not True:
            unresolved.append({"capability":cap,"reason":"TECHNOLOGY_WATCH_NOT_CONSULTED"})
            continue
        chosen=None
        reasons=[]
        for ev in row.get("evaluated_candidates") or []:
            c=ev.get("candidate") if isinstance(ev,dict) and isinstance(ev.get("candidate"),dict) else {}
            pid=candidate_id(c)
            safe=(
              c.get("build_profile")=="structured-read-v1"
              and str(c.get("execution") or "")=="vps"
              and c.get("supports")==["read"]
              and c.get("network_access") is False
              and c.get("credentials_required") is False
              and c.get("production_capable") is False
              and not bool(c.get("new_credentials_required"))
              and not bool(c.get("credential_boundary_change"))
              and zero(c.get("external_spend_eur",c.get("automatic_external_spend_eur",0)))
              and bool(pid)
            )
            if safe:
                chosen=c;break
            reasons.append({"provider":pid or None,"reason":"SAFE_BUILD_PROFILE_NOT_EXPLICIT"})
        if chosen is None:
            unresolved.append({"capability":cap,"reason":"BUILD_SPECIALIST_REQUIRED","candidate_reasons":reasons})
            continue
        provider=candidate_id(chosen)
        adapter=str(chosen.get("adapter_id") or (slug(provider)+"-adapter"))
        req={
          "schema":"chacha.dev/capability-build-request/v1",
          "project_id":closure.get("project_id"),
          "capability":cap,
          "provider_id":provider,
          "adapter_id":adapter,
          "profile":"structured-read-v1",
          "execution":"vps",
          "supports":["read"],
          "network_access":False,
          "credentials_required":False,
          "production_capable":False,
          "automatic_external_spend_eur":0,
          "technology_watch":{
            "consulted":True,
            "source_snapshot_digest":watch.get("source_snapshot_digest"),
            "snapshot_freshness":watch.get("snapshot_freshness")
          },
          "architecture_council":{
            "decision":"APPROVED",
            "decision_id":digest
          },
          "source_candidate":chosen
        }
        requests.append(req)
    out={
      "schema":SCHEMA,
      "project_id":closure.get("project_id"),
      "status":"READY" if requests and not unresolved else "PARTIAL" if requests else "BUILD_SPECIALIST_REQUIRED",
      "requests":requests,
      "unresolved":unresolved,
      "buildable_count":len(requests),
      "unresolved_count":len(unresolved),
      "architecture_council_digest":digest,
      "automatic_external_spend_eur":0
    }
    save(a.output,out)
    print("CHACHA_DEV_V641_BUILD_REQUEST_COMPILER=PASS")
    print("CHACHA_DEV_V641_BUILDABLE="+str(len(requests)))
    print("CHACHA_DEV_V641_BUILD_SPECIALIST_REQUIRED="+str(len(unresolved)))
    print("CHACHA_DEV_V641_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
    return 0

if __name__=="__main__": raise SystemExit(main())
