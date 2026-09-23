#!/usr/bin/env python3
"""Read-only discovery of existing Cloudflare Pages production targets for V6.39.

The script never prints tokens or account ids. It accepts both the legacy and
current ChaCha DEV secret names and probes only GET endpoints.
"""
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

SCHEMA="chacha.dev/v639-cloudflare-pages-target-discovery/v1"

def now_iso()->str:
    return datetime.now(timezone.utc).isoformat()

def request_json(url:str,token:str)->tuple[int,dict[str,Any]]:
    req=urllib.request.Request(
        url,
        headers={
            "Authorization":"Bearer "+token,
            "Accept":"application/json",
            "User-Agent":"ChaCha-DEV-V639-TargetDiscovery/1"
        },
        method="GET"
    )
    try:
        with urllib.request.urlopen(req,timeout=30) as r:
            payload=json.loads(r.read())
            return int(r.status),payload if isinstance(payload,dict) else {}
    except urllib.error.HTTPError as exc:
        try:
            payload=json.loads(exc.read())
        except Exception:
            payload={}
        return int(exc.code),payload if isinstance(payload,dict) else {}

def candidates(values:list[str])->list[str]:
    out=[]
    for v in values:
        v=(v or "").strip()
        if v and v not in out:
            out.append(v)
    return out

def resolve_account(token:str,account_ids:list[str])->tuple[str,str]:
    for aid in account_ids:
        q=urllib.parse.quote(aid,safe="")
        status,payload=request_json(
            f"https://api.cloudflare.com/client/v4/accounts/{q}/pages/projects?per_page=1",
            token
        )
        if status==200 and payload.get("success") is True:
            return aid,"provided-secret"

    status,payload=request_json(
        "https://api.cloudflare.com/client/v4/accounts?per_page=50",
        token
    )
    rows=(payload.get("result") or []) if status==200 and payload.get("success") is True else []
    rows=[r for r in rows if isinstance(r,dict) and r.get("id")]
    if len(rows)==1:
        return str(rows[0]["id"]),"api-single-account"
    raise RuntimeError(f"ACCOUNT_RESOLUTION_FAILED_HTTP_{status}")

def project_row(row:dict[str,Any])->dict[str,Any]:
    canonical=row.get("canonical_deployment") or {}
    if not isinstance(canonical,dict):
        canonical={}
    latest=canonical.get("latest_stage") or {}
    if not isinstance(latest,dict):
        latest={}
    domains=row.get("domains") or []
    if not isinstance(domains,list):
        domains=[]
    return {
      "project_name":str(row.get("name") or ""),
      "production_branch":str(row.get("production_branch") or ""),
      "subdomain":str(row.get("subdomain") or ""),
      "domains":[str(x) for x in domains if isinstance(x,str)],
      "canonical_deployment_id":str(canonical.get("id") or ""),
      "canonical_deployment_url":str(canonical.get("url") or ""),
      "canonical_status":str(latest.get("status") or ""),
      "created_on":str(row.get("created_on") or ""),
      "modified_on":str(row.get("modified_on") or "")
    }

def score(row:dict[str,Any])->tuple[int,str]:
    name=str(row.get("project_name") or "").lower()
    # Only a deterministic discovery hint, never an automatic deployment choice.
    preferred=0
    for token in ("v639","pilot","golden-path","sandbox","test"):
        if token in name:
            preferred-=1
    return preferred,name

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--output",type=Path,required=True)
    args=ap.parse_args()

    tokens=candidates([
      os.environ.get("CF_API_TOKEN",""),
      os.environ.get("CLOUDFLARE_API_TOKEN","")
    ])
    account_ids=candidates([
      os.environ.get("CF_ACCOUNT_ID",""),
      os.environ.get("CLOUDFLARE_ACCOUNT_ID","")
    ])
    if not tokens:
        raise SystemExit("V639_CF_PAGES_DISCOVERY_TOKEN_MISSING")

    chosen_token=None
    account_id=None
    account_source=None
    errors=[]
    for idx,token in enumerate(tokens,1):
        try:
            aid,source=resolve_account(token,account_ids)
            chosen_token=token
            account_id=aid
            account_source=source
            token_slot=idx
            break
        except Exception as exc:
            errors.append(type(exc).__name__+":"+str(exc))
    if chosen_token is None or account_id is None:
        raise SystemExit("V639_CF_PAGES_ACCOUNT_RESOLUTION_FAILED:"+"|".join(errors))

    aid=urllib.parse.quote(account_id,safe="")
    status,payload=request_json(
        f"https://api.cloudflare.com/client/v4/accounts/{aid}/pages/projects?per_page=100",
        chosen_token
    )
    if status!=200 or payload.get("success") is not True:
        raise SystemExit("V639_CF_PAGES_PROJECT_LIST_FAILED_HTTP_"+str(status))

    rows=payload.get("result") or []
    projects=[project_row(x) for x in rows if isinstance(x,dict)]
    projects.sort(key=score)

    out={
      "schema":SCHEMA,
      "status":"PASS",
      "observed_at":now_iso(),
      "account_resolution":account_source,
      "credential_slot_used":token_slot,
      "account_id_disclosed":False,
      "network_write":False,
      "production_mutation":False,
      "real_production_deployment_authorized":False,
      "project_count":len(projects),
      "projects":projects
    }
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(out,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")

    print("CHACHA_DEV_V639_CF_PAGES_TARGET_DISCOVERY=PASS")
    print("CHACHA_DEV_V639_CF_PAGES_TARGET_COUNT="+str(len(projects)))
    print("CHACHA_DEV_V639_CF_PAGES_TARGET_NETWORK_WRITE=NO")
    print("CHACHA_DEV_V639_CF_PAGES_TARGET_PRODUCTION_MUTATION=NO")
    for p in projects:
        print(
          "TARGET project="+p["project_name"]+
          " branch="+p["production_branch"]+
          " url="+p["canonical_deployment_url"]
        )
    return 0

if __name__=="__main__":
    raise SystemExit(main())
