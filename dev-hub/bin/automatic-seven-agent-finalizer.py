#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,subprocess,sys,time
from pathlib import Path
from typing import Any

SCHEMA="chacha.dev/automatic-seven-agent-finalization-result/v1"

def load(p:Path)->dict[str,Any]:
    x=json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise RuntimeError("JSON_ROOT_NOT_OBJECT:"+str(p))
    return x
def save(p:Path,x:dict[str,Any])->None:
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
def now()->str:return time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())
def source_path(raw:str)->Path:
    s=str(raw or "").strip()
    if not s:raise RuntimeError("FINALIZATION_BUNDLE_SOURCE_MISSING")
    if ";" in s:raise RuntimeError("FINALIZATION_BUNDLE_SOURCE_AMBIGUOUS")
    if s.startswith("file:"):s=s[5:]
    return Path(s)
def resolve_input(bundle_path:Path,raw:str)->Path:
    p=Path(str(raw))
    if not p.is_absolute():p=bundle_path.parent/p
    return p.resolve()

def valid_existing_final(ledger:dict[str,Any],project:str,revision:str,compromise_digest:str)->Path|None:
    row=(ledger.get("artifacts") or {}).get("seven-agent-final-delivery-receipt")
    gate=(ledger.get("gates") or {}).get("compromise-release")
    if not isinstance(row,dict) or row.get("status")!="OK":return None
    if not isinstance(gate,dict) or gate.get("status")!="OK":return None
    try:p=source_path(str(row.get("source") or ""))
    except Exception:return None
    if not p.is_file():return None
    try:x=load(p)
    except Exception:return None
    if x.get("schema")!="chacha.dev/seven-agent-final-delivery/v1":return None
    if x.get("delivery_allowed") is not True or x.get("status")!="DELIVERED":return None
    if str(x.get("project_id") or "")!=project:return None
    if str(x.get("revision") or "")!=revision:return None
    if str(x.get("compromise_digest") or "")!=compromise_digest:return None
    return p

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--project",required=True)
    ap.add_argument("--policy",type=Path,required=True)
    ap.add_argument("--ledger",type=Path,required=True)
    ap.add_argument("--repo-root",type=Path,required=True)
    ap.add_argument("--output-dir",type=Path,required=True)
    ap.add_argument("--result",type=Path,required=True)
    a=ap.parse_args()

    policy=load(a.policy);ledger=load(a.ledger)
    if policy.get("schema")!="chacha.dev/automatic-seven-agent-finalization-policy/v1":
        raise SystemExit("AUTOMATIC_FINALIZATION_POLICY_SCHEMA_INVALID")
    if ledger.get("schema")!="chacha.dev/evidence-ledger/v1":
        raise SystemExit("EVIDENCE_LEDGER_SCHEMA_INVALID")
    if str(ledger.get("project") or "")!=a.project:
        raise SystemExit("EVIDENCE_LEDGER_PROJECT_MISMATCH")

    artifact_id=str((policy.get("source_of_truth") or {}).get("finalization_bundle_artifact_id") or "seven-agent-finalization-inputs")
    row=(ledger.get("artifacts") or {}).get(artifact_id)
    if not isinstance(row,dict):raise SystemExit("FINALIZATION_INPUT_ARTIFACT_MISSING")
    if row.get("status")!="OK":raise SystemExit("FINALIZATION_INPUT_ARTIFACT_NOT_OK")
    bundle_path=source_path(str(row.get("source") or ""))
    if not bundle_path.is_file():raise SystemExit("FINALIZATION_INPUT_BUNDLE_FILE_MISSING="+str(bundle_path))
    bundle=load(bundle_path)
    if bundle.get("schema")!="chacha.dev/seven-agent-finalization-inputs/v1":
        raise SystemExit("FINALIZATION_INPUT_BUNDLE_SCHEMA_INVALID")
    if str(bundle.get("project_id") or "")!=a.project:
        raise SystemExit("FINALIZATION_INPUT_PROJECT_MISMATCH")
    revision=str(bundle.get("revision") or "")
    compromise_digest=str(bundle.get("compromise_digest") or "")
    if not revision or not compromise_digest:raise SystemExit("FINALIZATION_INPUT_IDENTITY_INCOMPLETE")

    existing=valid_existing_final(ledger,a.project,revision,compromise_digest)
    if existing:
        result={"schema":SCHEMA,"version":"1.0.0","project_id":a.project,"revision":revision,
                "compromise_digest":compromise_digest,"status":"ALREADY_FINALIZED",
                "delivery_allowed":True,"idempotent_reuse":True,
                "final_receipt":str(existing),"external_calls_skipped":True,
                "checked_at":now()}
        save(a.result,result)
        print("CHACHA_DEV_V637_AUTOMATIC_FINALIZATION=PASS")
        print("AUTOMATIC_FINALIZATION_IDEMPOTENT_REUSE=YES")
        print("FINAL_DELIVERY_ALLOWED=YES")
        return 0

    inputs=bundle.get("inputs") or {}
    required=list(policy.get("required_inputs") or [])
    path_keys=[x for x in required if x not in {"guardian_functional_receipt_id","sentinel_technical_receipt_id"}]
    paths={}
    for key in path_keys:
        raw=inputs.get(key)
        if not raw:raise SystemExit("FINALIZATION_INPUT_REFERENCE_MISSING:"+key)
        p=resolve_input(bundle_path,str(raw))
        if not p.is_file():raise SystemExit("FINALIZATION_INPUT_FILE_MISSING:"+key+":"+str(p))
        paths[key]=p

    guardian_id=str(bundle.get("guardian_functional_receipt_id") or "")
    sentinel_id=str(bundle.get("sentinel_technical_receipt_id") or "")
    if not guardian_id:raise SystemExit("GUARDIAN_SOURCE_RECEIPT_ID_MISSING")
    if not sentinel_id:raise SystemExit("SENTINEL_SOURCE_RECEIPT_ID_MISSING")

    a.output_dir.mkdir(parents=True,exist_ok=True)
    final_output=a.output_dir/"seven-agent-final-delivery.json"
    controller=a.repo_root/"dev-hub/bin/seven-agent-final-compromise-controller.py"
    cmd=[sys.executable,str(controller),
      "--project-id",a.project,"--revision",revision,
      "--compromise",str(paths["compromise"]),
      "--council",str(paths["architecture_council"]),
      "--logic-report",str(paths["logic_report"]),
      "--ux-report",str(paths["ux_report"]),
      "--implementation-manifest",str(paths["implementation_manifest"]),
      "--implementation-verification",str(paths["implementation_verification"]),
      "--guardian-functional-receipt-id",guardian_id,
      "--sentinel-technical-receipt-id",sentinel_id,
      "--repo-root",str(a.repo_root),
      "--output-dir",str(a.output_dir/"reviews"),
      "--final-output",str(final_output),
      "--evidence-ledger",str(a.ledger)]
    p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=180)

    final=load(final_output) if final_output.is_file() else {}
    status="PASS" if p.returncode==0 and final.get("delivery_allowed") is True else "BLOCK"
    result={"schema":SCHEMA,"version":"1.0.0","project_id":a.project,"revision":revision,
            "compromise_digest":compromise_digest,"status":status,
            "delivery_allowed":status=="PASS","idempotent_reuse":False,
            "controller_returncode":p.returncode,"controller_stdout":p.stdout[-4000:],
            "controller_stderr":p.stderr[-2000:],
            "final_receipt":str(final_output) if final_output.exists() else None,
            "central_remediation_before_renegotiation":True,
            "checked_at":now()}
    save(a.result,result)
    print("CHACHA_DEV_V637_AUTOMATIC_FINALIZATION="+status)
    print("FINAL_DELIVERY_ALLOWED="+("YES" if status=="PASS" else "NO"))
    print("CENTRAL_REMEDIATION_BEFORE_RENEGOTIATION=YES")
    return 0 if status=="PASS" else 20

if __name__=="__main__":raise SystemExit(main())
