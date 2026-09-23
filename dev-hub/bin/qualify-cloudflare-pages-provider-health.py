#!/usr/bin/env python3
"""Read-only Cloudflare Pages provider health qualification for V6.39."""
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

REPORT_SCHEMA="chacha.dev/v639-cloudflare-pages-provider-health/v1"
EVIDENCE_SCHEMA="chacha.dev/adapter-promotion-evidence/v1"
ADAPTER="cloudflare-pages-production-adapter"

def now_iso()->str:
    return datetime.now(timezone.utc).isoformat()

def save(path:Path,obj:dict[str,Any])->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")

def get_json(url:str,token:str)->dict[str,Any]:
    req=urllib.request.Request(
        url,
        headers={
            "Authorization":"Bearer "+token,
            "Accept":"application/json",
            "User-Agent":"ChaCha-DEV-V639-ProviderHealth/1"
        },
        method="GET"
    )
    try:
        with urllib.request.urlopen(req,timeout=30) as r:
            payload=json.loads(r.read())
    except urllib.error.HTTPError as exc:
        raise SystemExit("CLOUDFLARE_PROVIDER_HEALTH_HTTP_"+str(exc.code))
    if not isinstance(payload,dict) or payload.get("success") is not True:
        raise SystemExit("CLOUDFLARE_PROVIDER_HEALTH_API_NOT_SUCCESS")
    return payload

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--report",type=Path,required=True)
    ap.add_argument("--evidence",type=Path,required=True)
    a=ap.parse_args()

    token=os.environ.get("CLOUDFLARE_API_TOKEN","").strip()
    account=os.environ.get("CLOUDFLARE_ACCOUNT_ID","").strip()
    if not token:
        raise SystemExit("CLOUDFLARE_API_TOKEN_MISSING")

    # Do not call /user/tokens/verify here: an account-scoped API token may
    # legitimately lack that user-level permission. The provider health proof
    # is instead the exact capability we need: account resolution + Pages read.
    token_status="CAPABILITY_VERIFIED"
    account_source="secret"
    if not account:
        accounts=get_json("https://api.cloudflare.com/client/v4/accounts?per_page=50",token)
        rows=accounts.get("result") or []
        if not isinstance(rows,list) or len(rows)!=1 or not isinstance(rows[0],dict) or not rows[0].get("id"):
            raise SystemExit("CLOUDFLARE_ACCOUNT_RESOLUTION_FAILED")
        account=str(rows[0]["id"])
        account_source="api-single-account"

    aid=urllib.parse.quote(account,safe="")
    projects=get_json(
        f"https://api.cloudflare.com/client/v4/accounts/{aid}/pages/projects?per_page=1",
        token
    )
    result=projects.get("result")
    if not isinstance(result,list):
        raise SystemExit("CLOUDFLARE_PAGES_PROJECT_LIST_INVALID")

    ts=now_iso()
    report={
      "schema":REPORT_SCHEMA,
      "adapter":ADAPTER,
      "status":"PASS",
      "token_status":"CAPABILITY_VERIFIED",
      "pages_api_read":"PASS",
      "account_resolution":account_source,
      "returned_project_rows":len(result),
      "network_write":False,
      "production_mutation":False,
      "real_production_target":False,
      "automatic_external_spend_eur":0,
      "observed_at":ts
    }
    save(a.report,report)

    evidence={
      "schema":EVIDENCE_SCHEMA,
      "adapter":ADAPTER,
      "observed_at":ts,
      "evidence":{
        "provider-health-pass":{
          "status":"PASS",
          "source":"cloudflare-api://pages/projects-read-only",
          "observed_at":ts,
          "details":{
            "token_status":"CAPABILITY_VERIFIED",
            "pages_api_read":"PASS",
            "account_resolution":account_source,
            "network_write":False,
            "production_mutation":False,
            "real_production_target":False
          }
        }
      },
      "approvals":[]
    }
    save(a.evidence,evidence)

    print("CHACHA_DEV_V639_CF_PAGES_PROVIDER_HEALTH=PASS")
    print("CHACHA_DEV_V639_CF_PAGES_TOKEN_CAPABILITY=VERIFIED_BY_PAGES_READ")
    print("CHACHA_DEV_V639_CF_PAGES_PROVIDER_API_READ=PASS")
    print("CHACHA_DEV_V639_CF_PAGES_ACCOUNT_RESOLUTION="+account_source)
    print("CHACHA_DEV_V639_CF_PAGES_PROVIDER_NETWORK_WRITE=NO")
    print("CHACHA_DEV_V639_CF_PAGES_PROVIDER_PRODUCTION_MUTATION=NO")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
