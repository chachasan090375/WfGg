#!/usr/bin/env python3
from __future__ import annotations
import argparse,json
from pathlib import Path
from typing import Any

def load(p:Path)->dict[str,Any]:
    x=json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise ValueError("JSON_ROOT_NOT_OBJECT:"+str(p))
    return x
def save(p:Path,x:dict[str,Any])->None:
    p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
def validate(x:dict[str,Any],revision:str,cfg:dict[str,Any])->list[str]:
    errs=[];ev=cfg.get("evidence") or {}
    if x.get("schema")!="chacha.dev/agent-benchmark-raw-evidence/v1":errs.append("SCHEMA")
    if x.get("truth_scope")!="BENCHMARK_ONLY" or x.get("production_truth_eligible") is not False:errs.append("TRUTH_SCOPE")
    if x.get("verification")!="BENCHMARK_VERIFIED":errs.append("VERIFICATION")
    if str(x.get("verifier") or "") in {"",str(x.get("agent_id") or "")}:errs.append("INDEPENDENT_ORACLE")
    if not x.get("oracle_complete"):errs.append("ORACLE_INCOMPLETE")
    if str(x.get("revision") or "")!=revision:errs.append("REVISION_MISMATCH")
    if not x.get("evidence_refs"):errs.append("EVIDENCE_REFS")
    if not isinstance(x.get("dimensions"),dict) or not x.get("dimensions"):errs.append("DIMENSIONS")
    if x.get("canonical_observation_bus_writes") is not False:errs.append("CANONICAL_BUS_WRITE")
    if x.get("direct_agent_mutation") is not False or x.get("candidate_materialization") is not False:errs.append("AUTHORITY")
    if x.get("guardian_preserved") is not True or x.get("sentinel_preserved") is not True:errs.append("ASSURANCE")
    if float(x.get("automatic_external_spend_eur") or 0)>0:errs.append("SPEND")
    watch=x.get("technology_watch") or {}
    if ev.get("technology_watch_fresh_required",True) and watch.get("fresh") is not True:errs.append("TECHNOLOGY_WATCH_NOT_FRESH")
    return errs
def promote(raw:dict[str,Any],revision:str,cfg:dict[str,Any],output:Path)->dict[str,Any]:
    errs=validate(raw,revision,cfg)
    if errs:return {"status":"BLOCKED","reason_codes":errs,"promoted":False}
    out={k:v for k,v in raw.items()}
    out["schema"]="chacha.dev/agent-benchmark-verified-evidence/v1";out["promotion_status"]="PROMOTED"
    out["promoted_for_scorecard"]=True;out["production_truth_eligible"]=False
    out["overwrite_production_measurement"]=False;out["candidate_materialization"]=False
    save(output,out);return {"status":"PASS","promoted":True,"path":str(output),"evidence":out}
def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument("--input",type=Path,required=True);ap.add_argument("--revision",required=True)
    ap.add_argument("--config",type=Path,required=True);ap.add_argument("--output",type=Path,required=True);a=ap.parse_args()
    result=promote(load(a.input),a.revision,load(a.config),a.output)
    print(json.dumps(result,ensure_ascii=False))
    if result.get("promoted"):print("CHACHA_DEV_V651_BENCHMARK_EVIDENCE_PROMOTION=PASS");print("CHACHA_DEV_V651_PRODUCTION_TRUTH=NO");return 0
    print("CHACHA_DEV_V651_BENCHMARK_EVIDENCE_PROMOTION=BLOCKED");return 20
if __name__=="__main__":raise SystemExit(main())
