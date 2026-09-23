#!/usr/bin/env python3
"""V6.39 targeted read-only preflight for the canonical wfgg Pages project."""
from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA="chacha.dev/v639-cloudflare-pages-target-preflight/v1"

def now_iso()->str:
    return datetime.now(timezone.utc).isoformat()

def save(path:Path,obj:dict[str,Any])->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")

def request_json(url:str,token:str)->tuple[int,dict[str,Any]]:
    req=urllib.request.Request(
        url,
        headers={
            "Authorization":"Bearer "+token,
            "Accept":"application/json",
            "User-Agent":"ChaCha-DEV-V639-TargetPreflight/1"
        },
        method="GET"
    )
    try:
        with urllib.request.urlopen(req,timeout=30) as r:
            x=json.loads(r.read())
            return int(r.status),x if isinstance(x,dict) else {}
    except urllib.error.HTTPError as exc:
        try:x=json.loads(exc.read())
        except Exception:x={}
        return int(exc.code),x if isinstance(x,dict) else {}

def first_env(*names:str)->str:
    for name in names:
        value=os.environ.get(name,"").strip()
        if value:return value
    return ""

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--bindings",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    a=ap.parse_args()

    bindings=json.loads(a.bindings.read_text(encoding="utf-8"))
    b=bindings["projects"]["wfgg"]
    expected_project=b["pages_project"]
    expected_branch=b["production_branch"]
    expected_url=b["production_url"]

    token=first_env("CLOUDFLARE_PAGES_API_TOKEN","CLOUDFLARE_API_TOKEN","CF_API_TOKEN")
    account=first_env("CLOUDFLARE_ACCOUNT_ID","CF_ACCOUNT_ID")
    if not token or not account:
        reason="TOKEN_MISSING" if not token else "ACCOUNT_ID_MISSING"
        save(a.output,{
          "schema":SCHEMA,"status":"BLOCKED","reason":reason,
          "project":expected_project,"production_branch":expected_branch,
          "production_url":expected_url,"network_write":False,
          "production_mutation":False,"observed_at":now_iso()
        })
        print("CHACHA_DEV_V639_WFGG_TARGET_PREFLIGHT=BLOCKED")
        print("CHACHA_DEV_V639_WFGG_TARGET_PREFLIGHT_REASON="+reason)
        return 0

    aid=urllib.parse.quote(account,safe="")
    project=urllib.parse.quote(expected_project,safe="")
    status,payload=request_json(
        f"https://api.cloudflare.com/client/v4/accounts/{aid}/pages/projects/{project}",
        token
    )
    if status!=200 or payload.get("success") is not True:
        save(a.output,{
          "schema":SCHEMA,"status":"BLOCKED",
          "reason":"PROJECT_GET_FAILED","http_status":status,
          "project":expected_project,"production_branch":expected_branch,
          "production_url":expected_url,"network_write":False,
          "production_mutation":False,"observed_at":now_iso()
        })
        print("CHACHA_DEV_V639_WFGG_TARGET_PREFLIGHT=BLOCKED")
        print("CHACHA_DEV_V639_WFGG_TARGET_PREFLIGHT_REASON=PROJECT_GET_HTTP_"+str(status))
        return 0

    row=payload.get("result") or {}
    canonical=row.get("canonical_deployment") or {}
    latest=canonical.get("latest_stage") or {}
    observed_branch=str(row.get("production_branch") or "")
    observed_name=str(row.get("name") or "")
    canonical_id=str(canonical.get("id") or "")
    canonical_url=str(canonical.get("url") or "")
    canonical_status=str(latest.get("status") or "").lower()

    blockers=[]
    if observed_name!=expected_project:blockers.append("PROJECT_NAME_MISMATCH")
    if observed_branch!=expected_branch:blockers.append("PRODUCTION_BRANCH_MISMATCH")
    if not canonical_id:blockers.append("CANONICAL_DEPLOYMENT_MISSING")
    if canonical_status!="success":blockers.append("CANONICAL_DEPLOYMENT_NOT_SUCCESSFUL")

    status_text="PASS" if not blockers else "BLOCKED"
    save(a.output,{
      "schema":SCHEMA,
      "status":status_text,
      "blockers":blockers,
      "project":expected_project,
      "production_branch":expected_branch,
      "production_url":expected_url,
      "canonical_deployment_id":canonical_id,
      "canonical_deployment_url":canonical_url,
      "canonical_status":canonical_status,
      "account_id_disclosed":False,
      "network_write":False,
      "production_mutation":False,
      "real_production_deployment_authorized":False,
      "observed_at":now_iso()
    })

    print("CHACHA_DEV_V639_WFGG_TARGET_PREFLIGHT="+status_text)
    print("CHACHA_DEV_V639_WFGG_TARGET_PROJECT="+expected_project)
    print("CHACHA_DEV_V639_WFGG_TARGET_BRANCH="+expected_branch)
    print("CHACHA_DEV_V639_WFGG_TARGET_URL="+expected_url)
    print("CHACHA_DEV_V639_WFGG_TARGET_NETWORK_WRITE=NO")
    print("CHACHA_DEV_V639_WFGG_TARGET_PRODUCTION_MUTATION=NO")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
