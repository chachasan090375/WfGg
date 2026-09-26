#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,os,time
from pathlib import Path
from typing import Any
import operator_directive_registry as odr

RECEIPT_SCHEMA="chacha.dev/operator-directive-propagation-receipt/v1"

def load(path:Path)->dict[str,Any]:
    x=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise ValueError("JSON_ROOT_NOT_OBJECT:"+str(path))
    return x

def save(path:Path,x:dict[str,Any])->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+".tmp")
    tmp.write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    os.replace(tmp,path)

def now_iso()->str:return time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())
def verify(directives:dict[str,Any],impact:dict[str,Any],registry:dict[str,Any])->dict[str,Any]:
    expected_digest=str(directives.get("active_global_digest") or "")
    expected_ids=sorted(str(x) for x in directives.get("active_global_ids") or [])
    issues=[];verified_components=0
    if impact.get("status")!="PASS":
        issues.append({"code":"DIRECTIVE_IMPACT_NOT_PASS","details":impact.get("missing_targets") or []})
    if registry.get("active_global_directive_digest")!=expected_digest:
        issues.append({"code":"REGISTRY_DIRECTIVE_DIGEST_DRIFT"})
    if sorted(str(x) for x in registry.get("active_global_directive_ids") or [])!=expected_ids:
        issues.append({"code":"REGISTRY_DIRECTIVE_ID_DRIFT"})
    for row in registry.get("components") or []:
        if not isinstance(row,dict):continue
        controls=((row.get("birth_contract") or {}).get("controls") or {})
        value=((controls.get("operator_directives") or {}).get("value") or {})
        if value.get("active_global_digest")!=expected_digest:
            issues.append({"code":"COMPONENT_DIRECTIVE_DIGEST_DRIFT","component_id":row.get("component_id")})
            continue
        if sorted(str(x) for x in value.get("active_global_ids") or [])!=expected_ids:
            issues.append({"code":"COMPONENT_DIRECTIVE_ID_DRIFT","component_id":row.get("component_id")})
            continue
        verified_components+=1
    status="VERIFIED" if not issues else "BLOCKED"
    directive_receipts=[]
    for row in directives.get("active_global_directives") or []:
        directive_receipts.append({"directive_id":row.get("directive_id"),"scope":row.get("scope"),
                                   "status":"ACTIVE" if status=="VERIFIED" else "BLOCKED",
                                   "future_default_updated":status=="VERIFIED",
                                   "existing_component_backfill_verified":status=="VERIFIED"})
    return {"schema":RECEIPT_SCHEMA,"generated_at":now_iso(),"status":status,
            "active_global_digest":expected_digest,"active_global_ids":expected_ids,
            "verified_component_count":verified_components,"component_count":registry.get("component_count"),
            "directive_receipts":directive_receipts,"issue_count":len(issues),"issues":issues,
            "automatic_external_spend_eur":0}
def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--directive-policy",type=Path,required=True)
    ap.add_argument("--impact-report",type=Path,required=True)
    ap.add_argument("--registry",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    ap.add_argument("--strict",action="store_true")
    a=ap.parse_args()
    directives=odr.snapshot(load(a.directive_policy))
    out=verify(directives,load(a.impact_report),load(a.registry))
    save(a.output,out)
    print("CHACHA_DEV_GLOBAL_POLICY_PROPAGATION="+out["status"])
    print("VERIFIED_COMPONENT_COUNT="+str(out["verified_component_count"]))
    print("DIRECTIVE_COUNT="+str(len(out["directive_receipts"])))
    print("CHACHA_DEV_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
    return 2 if a.strict and out["status"]!="VERIFIED" else 0

if __name__=="__main__":raise SystemExit(main())
