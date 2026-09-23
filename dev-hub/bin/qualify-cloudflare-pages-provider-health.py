#!/usr/bin/env python3
"""Read-only Cloudflare Pages provider-health qualification for V6.39.

Provider health is deliberately independent from deployment credentials.
This probe uses Cloudflare's public status API only. Credential/account
capability remains a fail-closed deployment preflight in the production adapter.
"""
from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPORT_SCHEMA="chacha.dev/v639-cloudflare-pages-provider-health/v1"
EVIDENCE_SCHEMA="chacha.dev/adapter-promotion-evidence/v1"
ADAPTER="cloudflare-pages-production-adapter"
STATUS_URL="https://www.cloudflarestatus.com/api/v2/components.json"

def now_iso()->str:
    return datetime.now(timezone.utc).isoformat()

def save(path:Path,obj:dict[str,Any])->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")

def get_json(url:str)->dict[str,Any]:
    req=urllib.request.Request(
        url,
        headers={"Accept":"application/json","User-Agent":"ChaCha-DEV-V639-ProviderHealth/1"},
        method="GET"
    )
    try:
        with urllib.request.urlopen(req,timeout=30) as r:
            payload=json.loads(r.read())
    except urllib.error.HTTPError as exc:
        raise SystemExit("CLOUDFLARE_PROVIDER_HEALTH_HTTP_"+str(exc.code))
    if not isinstance(payload,dict):
        raise SystemExit("CLOUDFLARE_PROVIDER_HEALTH_RESPONSE_INVALID")
    return payload

def pages_components(payload:dict[str,Any])->list[dict[str,Any]]:
    rows=payload.get("components") or []
    out=[]
    for row in rows:
        if not isinstance(row,dict):
            continue
        name=str(row.get("name") or "")
        if "pages" in name.lower():
            out.append(row)
    return out

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--report",type=Path,required=True)
    ap.add_argument("--evidence",type=Path,required=True)
    a=ap.parse_args()

    payload=get_json(STATUS_URL)
    rows=pages_components(payload)
    if not rows:
        raise SystemExit("CLOUDFLARE_PAGES_STATUS_COMPONENT_NOT_FOUND")

    unhealthy=[]
    statuses=[]
    for row in rows:
        name=str(row.get("name") or "")
        status=str(row.get("status") or "").lower()
        statuses.append({"name":name,"status":status})
        if status!="operational":
            unhealthy.append({"name":name,"status":status})

    if unhealthy:
        raise SystemExit("CLOUDFLARE_PAGES_PROVIDER_NOT_OPERATIONAL:"+json.dumps(unhealthy,separators=(",",":")))

    ts=now_iso()
    report={
      "schema":REPORT_SCHEMA,
      "adapter":ADAPTER,
      "status":"PASS",
      "provider_health_mode":"PUBLIC_STATUS_READ_ONLY",
      "status_source":STATUS_URL,
      "pages_components":statuses,
      "network_write":False,
      "production_mutation":False,
      "real_production_target":False,
      "credentials_consumed":False,
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
          "source":STATUS_URL,
          "observed_at":ts,
          "details":{
            "provider_health_mode":"PUBLIC_STATUS_READ_ONLY",
            "pages_components":statuses,
            "network_write":False,
            "production_mutation":False,
            "real_production_target":False,
            "credentials_consumed":False
          }
        }
      },
      "approvals":[]
    }
    save(a.evidence,evidence)

    print("CHACHA_DEV_V639_CF_PAGES_PROVIDER_HEALTH=PASS")
    print("CHACHA_DEV_V639_CF_PAGES_PROVIDER_HEALTH_MODE=PUBLIC_STATUS_READ_ONLY")
    print("CHACHA_DEV_V639_CF_PAGES_PROVIDER_NETWORK_WRITE=NO")
    print("CHACHA_DEV_V639_CF_PAGES_PROVIDER_PRODUCTION_MUTATION=NO")
    print("CHACHA_DEV_V639_CF_PAGES_PROVIDER_CREDENTIALS_CONSUMED=NO")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
