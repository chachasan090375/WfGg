#!/usr/bin/env python3
from __future__ import annotations
import argparse,datetime,json,subprocess
from pathlib import Path
from typing import Any
LINEAGE_SCHEMA="chacha.dev/component-lineage/v1"
def load(p:Path)->dict[str,Any]:
    x=json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise ValueError("JSON_OBJECT_REQUIRED:"+str(p))
    return x
def parse_time(v:Any)->datetime.datetime:
    return datetime.datetime.fromisoformat(str(v).replace("Z","+00:00"))
def exact_lineage(v:Any)->bool:
    if not isinstance(v,dict) or v.get("schema")!=LINEAGE_SCHEMA:return False
    rows=v.get("components") or []
    return bool(rows) and all(isinstance(r,dict) and r.get("kind") and r.get("component_id") and r.get("version") for r in rows)
def trusted_context(event:dict[str,Any],policy:dict[str,Any])->bool:
    ctx=event.get("learning_context");lin=(ctx or {}).get("component_lineage") if isinstance(ctx,dict) else None
    digest=str(event.get("result_digest") or "")
    return exact_lineage(lin) and (digest.startswith("sha256:") if policy.get("require_sha256_result_digest",True) else True)
def gate(policy:dict[str,Any],coverage:dict[str,Any],repo_root:Path)->dict[str,Any]:
    if policy.get("schema")!="chacha.dev/learning-lineage-cutover-policy/v1":raise ValueError("POLICY_SCHEMA")
    if policy.get("read_only") is not True or policy.get("execution_authority") is not False or int(policy.get("automatic_external_spend_eur",-1))!=0:raise ValueError("POLICY_NOT_READ_ONLY_ZERO_SPEND")
    cut=parse_time(policy.get("cutover_observed_at"));commit=str(policy.get("cutover_commit") or "")
    commit_exists=subprocess.run(["git","-C",str(repo_root),"cat-file","-e",commit+"^{commit}"],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0
    projects=set();historical=0;missing_after=0;invalid_ts=0;valid_after=0
    required_result=policy.get("required_result_status");required_verification=policy.get("required_verification_status")
    for row in coverage.get("results") or []:
        if not isinstance(row,dict):continue
        p=Path(str(row.get("ledger") or ""));ledger=load(p)
        if ledger.get("schema")!="chacha.dev/evidence-ledger/v1":raise ValueError("LEDGER_SCHEMA:"+str(p))
        project=str(ledger.get("project") or row.get("project_id") or "");projects.add(project)
        for event in ledger.get("history") or []:
            if not isinstance(event,dict) or event.get("event")!="task-result-ingested":continue
            if event.get("result_status")!=required_result or event.get("verification_status")!=required_verification:continue
            try:observed=parse_time(event.get("observed_at"))
            except Exception:invalid_ts+=1;continue
            if trusted_context(event,policy):
                if observed>=cut:valid_after+=1
            elif observed<cut:historical+=1
            else:missing_after+=1
    blockers=[]
    if not commit_exists:blockers.append("CUTOVER_COMMIT_UNAVAILABLE")
    if invalid_ts:blockers.append("INVALID_TIMESTAMP_EVENTS")
    if missing_after:blockers.append("MISSING_CONTEXT_AFTER_CUTOVER")
    if policy.get("require_valid_context_after_cutover",True) and valid_after<1:blockers.append("NO_VALID_CONTEXT_AFTER_CUTOVER")
    if int(coverage.get("missing_context_count") or 0)!=(historical+missing_after):blockers.append("COVERAGE_MISSING_CONTEXT_MISMATCH")
    return {"schema":"chacha.dev/learning-lineage-cutover-gate/v1","status":"PASS" if not blockers else "HOLD","blockers":blockers,"cutover_commit":commit,"cutover_observed_at":policy.get("cutover_observed_at"),"historical_missing_behavior":"QUARANTINE_NO_CONFIDENCE","historical_missing_quarantined":historical,"missing_after_cutover":missing_after,"invalid_timestamp_events":invalid_ts,"valid_context_events_after_cutover":valid_after,"project_count":len(projects),"execution_authority":False,"production_mutation":False,"automatic_external_spend_eur":0}
def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument("--policy",type=Path,required=True);ap.add_argument("--coverage",type=Path,required=True);ap.add_argument("--repo-root",type=Path,required=True);ap.add_argument("--output",type=Path,required=True);a=ap.parse_args()
    out=gate(load(a.policy),load(a.coverage),a.repo_root.resolve());a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(out,indent=2)+"\n");print("CHACHA_DEV_LEARNING_LINEAGE_CUTOVER_GATE="+out["status"]);return 0 if out["status"]=="PASS" else 10
if __name__=="__main__":raise SystemExit(main())
