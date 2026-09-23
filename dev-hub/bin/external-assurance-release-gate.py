#!/usr/bin/env python3
from __future__ import annotations
import argparse,json
from pathlib import Path
from typing import Any

def load(p:Path)->dict[str,Any]:
    x=json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise RuntimeError("JSON_ROOT_NOT_OBJECT:"+str(p))
    return x
def combine(functional:dict[str,Any],technical:dict[str,Any],project_id:str,revision:str)->dict[str,Any]:
    reasons=[]
    if functional.get("schema")!="chacha.dev/guardian-functional-acceptance-receipt/v1":reasons.append("GUARDIAN_RECEIPT_SCHEMA_INVALID")
    if technical.get("schema")!="chacha.dev/sentinel-technical-receipt/v1":reasons.append("SENTINEL_RECEIPT_SCHEMA_INVALID")
    if str(functional.get("project_id") or "")!=project_id:reasons.append("GUARDIAN_PROJECT_MISMATCH")
    if str(technical.get("project_id") or "")!=project_id:reasons.append("SENTINEL_PROJECT_MISMATCH")
    if str(functional.get("revision") or "")!=revision:reasons.append("GUARDIAN_REVISION_MISMATCH")
    if str(technical.get("revision") or "")!=revision:reasons.append("SENTINEL_REVISION_MISMATCH")
    if str(functional.get("verdict") or "")!="PASS":reasons.append("GUARDIAN_FUNCTIONAL_NOT_PASS")
    if str(technical.get("verdict") or "")!="PASS":reasons.append("SENTINEL_TECHNICAL_NOT_PASS")
    allowed=not reasons
    return {
      "schema":"chacha.dev/external-dual-assurance-release-gate/v1",
      "project_id":project_id,"revision":revision,
      "guardian_functional_receipt_id":functional.get("receipt_id"),
      "sentinel_technical_receipt_id":technical.get("receipt_id"),
      "guardian_functional_verdict":functional.get("verdict"),
      "sentinel_technical_verdict":technical.get("verdict"),
      "production_allowed":allowed,"reason_codes":reasons,
      "remediation_owner":"central-orchestrator",
      "guardian_direct_mutation":False,"sentinel_direct_mutation":False,
      "automatic_external_spend_eur":0
    }
def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument("--project-id",required=True);ap.add_argument("--revision",required=True)
    ap.add_argument("--guardian-receipt",type=Path,required=True);ap.add_argument("--sentinel-receipt",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True);a=ap.parse_args()
    out=combine(load(a.guardian_receipt),load(a.sentinel_receipt),a.project_id,a.revision)
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(out,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print("CHACHA_DEV_EXTERNAL_DUAL_ASSURANCE="+("PASS" if out["production_allowed"] else "BLOCK"))
    print("PRODUCTION_ALLOWED="+("YES" if out["production_allowed"] else "NO"))
    print("REMEDIATION_OWNER=central-orchestrator")
    return 0 if out["production_allowed"] else 20
if __name__=="__main__":raise SystemExit(main())
