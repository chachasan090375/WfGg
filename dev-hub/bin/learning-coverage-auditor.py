#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,os
from pathlib import Path
from typing import Any

POLICY_SCHEMA="chacha.dev/learning-coverage-audit/v1"
LEDGER_SCHEMA="chacha.dev/evidence-ledger/v1"
LINEAGE_SCHEMA="chacha.dev/component-lineage/v1"

def load(path:Path)->dict[str,Any]:
    value=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value,dict): raise ValueError("JSON_ROOT_NOT_OBJECT:"+str(path))
    return value

def canon(value:Any)->str:
    return json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(",",":"))

def event_key(project_id:str,result_digest:str,context:dict[str,Any])->str:
    payload={"project_id":project_id,"result_digest":result_digest,"learning_context":context}
    return hashlib.sha256(canon(payload).encode()).hexdigest()

def exact_lineage(value:Any)->bool:
    if not isinstance(value,dict) or value.get("schema")!=LINEAGE_SCHEMA: return False
    rows=value.get("components") or []
    if not rows: return False
    return all(isinstance(r,dict) and r.get("kind") and r.get("component_id") and r.get("version") for r in rows)

def classify(event:dict[str,Any],project_id:str,marker_root:Path,policy:dict[str,Any])->dict[str,Any]:
    elig=policy.get("eligibility") or {}
    result=str(event.get("result_status") or "")
    verification=str(event.get("verification_status") or "")
    digest_value=str(event.get("result_digest") or "")
    context=event.get("learning_context")
    verified_success=(result==elig.get("required_result_status") and verification==elig.get("required_verification_status"))
    if not verified_success:
        return {"classification":"NOT_ELIGIBLE","eligible":False,"task_id":event.get("task_id")}
    if not isinstance(context,dict) or not exact_lineage(context.get("component_lineage")):
        return {"classification":"MISSING_CONTEXT","eligible":False,"task_id":event.get("task_id"),"advisory":True}
    if elig.get("require_sha256_result_digest",True) and not digest_value.startswith("sha256:"):
        return {"classification":"MISSING_CONTEXT","eligible":False,"task_id":event.get("task_id"),"advisory":True,"reason":"RESULT_DIGEST_INVALID"}
    key=event_key(project_id,digest_value,context);marker=marker_root/(key+".json")
    covered=marker.is_file()
    return {"classification":"COVERED" if covered else "GAP","eligible":True,"covered":covered,
            "task_id":event.get("task_id"),"event_key":key,"marker":str(marker),"result_digest":digest_value}

def audit_ledger(path:Path,marker_root:Path,policy:dict[str,Any])->dict[str,Any]:
    ledger=load(path)
    if ledger.get("schema")!=LEDGER_SCHEMA: raise ValueError("EVIDENCE_LEDGER_SCHEMA_INVALID:"+str(path))
    project_id=str(ledger.get("project") or "")
    if not project_id: raise ValueError("EVIDENCE_LEDGER_PROJECT_MISSING:"+str(path))
    rows=[]
    for event in ledger.get("history") or []:
        if isinstance(event,dict) and event.get("event")=="task-result-ingested":
            rows.append(classify(event,project_id,marker_root,policy))
    return {"ledger":str(path),"project_id":project_id,"events":rows}

def discover(root:Path)->list[Path]:
    if not root.exists(): return []
    return sorted(p for p in root.glob("*/ledger.json") if p.is_file())

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--policy",type=Path,required=True);ap.add_argument("--evidence-root",type=Path)
    ap.add_argument("--ledger",type=Path,action="append",default=[]);ap.add_argument("--marker-root",type=Path,required=True)
    ap.add_argument("--output",type=Path)
    args=ap.parse_args();pol=load(args.policy)
    if pol.get("schema")!=POLICY_SCHEMA: raise SystemExit("LEARNING_COVERAGE_POLICY_INVALID")
    if pol.get("read_only") is not True or int(pol.get("automatic_external_spend_eur",-1))!=0:
        raise SystemExit("LEARNING_COVERAGE_POLICY_NOT_READ_ONLY_ZERO_SPEND")
    ledgers=list(args.ledger) or discover(args.evidence_root or Path("/opt/chacha-dev/runtime/evidence"))
    results=[audit_ledger(p,args.marker_root,pol) for p in ledgers]
    flat=[e for r in results for e in r["events"]]
    eligible=sum(bool(e.get("eligible")) for e in flat);covered=sum(e.get("classification")=="COVERED" for e in flat)
    gaps=[e for e in flat if e.get("classification")=="GAP"]
    missing=[e for e in flat if e.get("classification")=="MISSING_CONTEXT"]
    excluded=sum(e.get("classification")=="NOT_ELIGIBLE" for e in flat)
    block=bool(gaps) and bool((pol.get("enforcement") or {}).get("block_on_eligible_gap",True))
    status="BLOCK" if block else ("PASS_WITH_ADVISORY" if missing else "PASS")
    coverage=100.0 if eligible==0 else round((covered/eligible)*100,2)
    out={"schema":"chacha.dev/learning-coverage-report/v1","status":status,"ledger_count":len(results),
         "event_count":len(flat),"eligible_count":eligible,"covered_count":covered,"gap_count":len(gaps),
         "missing_context_count":len(missing),"not_eligible_count":excluded,"coverage_percent":coverage,
         "results":results,"production_mutation":False,"d1_write_performed":False,"automatic_external_spend_eur":0}
    rendered=json.dumps(out,indent=2,ensure_ascii=False)+"\n"
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(rendered,encoding="utf-8")
    print(rendered,end="")
    return 20 if block else 0

if __name__=="__main__": raise SystemExit(main())
