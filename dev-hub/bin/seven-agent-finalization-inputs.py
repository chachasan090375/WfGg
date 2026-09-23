#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,time
from pathlib import Path
from typing import Any

SCHEMA="chacha.dev/seven-agent-finalization-inputs/v1"

def load(p:Path)->dict[str,Any]:
    x=json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise SystemExit("JSON_ROOT_NOT_OBJECT:"+str(p))
    return x
def canon(v:Any)->str:return json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(",",":"))
def digest(v:Any)->str:return "sha256:"+hashlib.sha256(canon(v).encode()).hexdigest()
def now()->str:return time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--project-id",required=True)
    ap.add_argument("--revision",required=True)
    ap.add_argument("--logic-report",type=Path,required=True)
    ap.add_argument("--ux-report",type=Path,required=True)
    ap.add_argument("--compromise",type=Path,required=True)
    ap.add_argument("--architecture-council",type=Path,required=True)
    ap.add_argument("--implementation-manifest",type=Path,required=True)
    ap.add_argument("--implementation-verification",type=Path,required=True)
    ap.add_argument("--guardian-functional-receipt-id",required=True)
    ap.add_argument("--sentinel-technical-receipt-id",required=True)
    ap.add_argument("--output",type=Path,required=True)
    a=ap.parse_args()

    files={
      "logic_report":a.logic_report,
      "ux_report":a.ux_report,
      "compromise":a.compromise,
      "architecture_council":a.architecture_council,
      "implementation_manifest":a.implementation_manifest,
      "implementation_verification":a.implementation_verification
    }
    for key,p in files.items():
        if not p.is_file():raise SystemExit("FINALIZATION_INPUT_MISSING:"+key+":"+str(p))

    comp=load(a.compromise);impl=load(a.implementation_manifest);verify=load(a.implementation_verification)
    if comp.get("schema")!="chacha.dev/multi-agent-compromise/v1":raise SystemExit("COMPROMISE_SCHEMA_INVALID")
    cd=str(comp.get("dossier_digest") or digest(comp))
    for src,name in ((impl,"implementation_manifest"),(verify,"implementation_verification")):
        if str(src.get("project_id") or "")!=a.project_id:raise SystemExit("PROJECT_MISMATCH:"+name)
        if str(src.get("revision") or "")!=a.revision:raise SystemExit("REVISION_MISMATCH:"+name)
        if str(src.get("compromise_digest") or "")!=cd:raise SystemExit("COMPROMISE_MISMATCH:"+name)

    result={
      "schema":SCHEMA,"version":"1.0.0",
      "project_id":a.project_id,"revision":a.revision,"compromise_digest":cd,
      "inputs":{k:str(v.resolve()) for k,v in files.items()},
      "guardian_functional_receipt_id":a.guardian_functional_receipt_id,
      "sentinel_technical_receipt_id":a.sentinel_technical_receipt_id,
      "exact_project_revision_compromise":True,
      "ambiguous_source":False,
      "direct_mutation":False,
      "created_at":now()
    }
    result["bundle_digest"]=digest(result)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print("CHACHA_DEV_FINALIZATION_INPUT_BUNDLE=PASS")
    print("PROJECT_ID="+a.project_id)
    print("REVISION="+a.revision)
    print("COMPROMISE_DIGEST="+cd)
    return 0
if __name__=="__main__":raise SystemExit(main())
