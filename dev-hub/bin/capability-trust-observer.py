#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import universal_learning_runtime as ul

OUTCOME_SCHEMA="chacha.dev/capability-project-outcome/v1"

def canon(v:Any)->bytes:
    return json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(",",":")).encode()

def digest_obj(v:Any)->str:
    return "sha256:"+hashlib.sha256(canon(v)).hexdigest()

def digest_file(path:Path)->str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""):
            h.update(chunk)
    return "sha256:"+h.hexdigest()

def load(path:Path)->dict[str,Any]:
    v=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(v,dict):
        raise SystemExit("JSON_ROOT_NOT_OBJECT:"+str(path))
    return v

def active_adoption(registry:dict[str,Any],capability:str)->dict[str,Any]:
    matches=[]
    for aid,row in (registry.get("adoptions") or {}).items():
        if isinstance(row,dict) and row.get("status")=="ADOPTED" and row.get("capability")==capability:
            matches.append({**row,"adoption_id":str(row.get("adoption_id") or aid)})
    if len(matches)!=1:
        raise SystemExit("CAPABILITY_ACTIVE_ADOPTION_NOT_UNIQUE")
    return matches[0]

def validate_project_control(outcome:dict[str,Any])->dict[str,Any]:
    project=str(outcome.get("project_id") or "")
    receipt_path=Path(str(outcome.get("project_control_receipt") or ""))
    ledger_path=Path(str(outcome.get("project_control_ledger") or ""))
    claims_path=Path(str(outcome.get("verified_claims_path") or ""))
    declared_digest=str(outcome.get("verified_claims_digest") or "")
    if not receipt_path.is_file():
        raise SystemExit("PROJECT_CONTROL_RECEIPT_REQUIRED")
    if not ledger_path.is_file():
        raise SystemExit("PROJECT_CONTROL_LEDGER_REQUIRED")
    if not claims_path.is_file() or not declared_digest.startswith("sha256:"):
        raise SystemExit("VERIFIED_CLAIMS_REQUIRED")
    if digest_file(claims_path)!=declared_digest:
        raise SystemExit("VERIFIED_CLAIMS_DIGEST_INVALID")

    receipt=load(receipt_path)
    if receipt.get("schema")!="chacha.dev/control-transaction-receipt/v1":
        raise SystemExit("PROJECT_CONTROL_RECEIPT_SCHEMA_INVALID")
    if receipt.get("project")!=project or receipt.get("operation")!="verify-result":
        raise SystemExit("PROJECT_CONTROL_RECEIPT_SCOPE_INVALID")
    if receipt.get("status")!="COMMITTED" or receipt.get("verification_status")!="VERIFIED":
        raise SystemExit("PROJECT_CONTROL_VERIFICATION_NOT_COMMITTED")

    verified_path=Path(str(receipt.get("verified_result") or ""))
    if not verified_path.is_file():
        raise SystemExit("PROJECT_CONTROL_VERIFIED_RESULT_MISSING")
    verified=load(verified_path)
    if verified.get("project")!=project or verified.get("status")!="OK":
        raise SystemExit("PROJECT_CONTROL_VERIFIED_RESULT_SCOPE_INVALID")
    verification=verified.get("verification") if isinstance(verified.get("verification"),dict) else {}
    if verification.get("status")!="VERIFIED":
        raise SystemExit("PROJECT_CONTROL_VERIFIED_RESULT_STATUS_INVALID")
    task_id=str(outcome.get("verified_task_id") or "")
    if task_id and verified.get("task_id")!=task_id:
        raise SystemExit("PROJECT_CONTROL_VERIFIED_TASK_MISMATCH")

    claims=load(claims_path)
    expected={
      "project_id":project,
      "capability":str(outcome.get("capability") or ""),
      "outcome":str(outcome.get("outcome") or ""),
      "technology_watch_revalidated":True
    }
    for key,value in expected.items():
        if claims.get(key)!=value:
            raise SystemExit("VERIFIED_CLAIMS_MISMATCH:"+key)
    if claims.get("evidence_refs")!=outcome.get("evidence_refs"):
        raise SystemExit("VERIFIED_CLAIMS_MISMATCH:evidence_refs")

    evidence=verified.get("evidence") if isinstance(verified.get("evidence"),list) else []
    claims_resolved=str(claims_path.resolve())
    if not any(isinstance(x,dict)
               and str(Path(str(x.get("source") or "")).resolve())==claims_resolved
               and x.get("digest")==declared_digest
               for x in evidence):
        raise SystemExit("VERIFIED_CLAIMS_NOT_IN_RESULT")

    ledger=load(ledger_path)
    if ledger.get("schema")!="chacha.dev/evidence-ledger/v1" or ledger.get("project")!=project:
        raise SystemExit("PROJECT_CONTROL_LEDGER_SCOPE_INVALID")
    if receipt.get("new_ledger_digest")!=digest_obj(ledger):
        raise SystemExit("PROJECT_CONTROL_LEDGER_DIGEST_MISMATCH")
    artifact_id=str(outcome.get("verified_artifact_id") or ("capability-project-outcome:"+str(outcome.get("capability") or "")))
    artifact=(ledger.get("artifacts") or {}).get(artifact_id)
    verified_digest=digest_obj(verified)
    if not isinstance(artifact,dict) or artifact.get("status")!="OK" or artifact.get("digest")!=verified_digest:
        raise SystemExit("PROJECT_CONTROL_OUTCOME_ARTIFACT_INVALID")
    if task_id and artifact.get("task_id")!=task_id:
        raise SystemExit("PROJECT_CONTROL_OUTCOME_ARTIFACT_TASK_MISMATCH")
    history=ledger.get("history") or []
    if not any(isinstance(x,dict)
               and x.get("event")=="task-result-ingested"
               and x.get("task_id")==verified.get("task_id")
               and x.get("result_digest")==verified_digest
               and x.get("verification_status")=="VERIFIED"
               for x in history):
        raise SystemExit("PROJECT_CONTROL_LEDGER_HISTORY_PROOF_MISSING")
    return {"receipt":receipt,"verified":verified,"ledger":ledger,"claims":claims}

def observe(args)->dict[str,Any]:
    registry=load(args.registry)
    outcome=load(args.outcome)
    if outcome.get("schema")!=OUTCOME_SCHEMA:
        raise SystemExit("CAPABILITY_OUTCOME_SCHEMA_INVALID")
    capability=str(outcome.get("capability") or "")
    project=str(outcome.get("project_id") or "")
    if not capability or not project:
        raise SystemExit("CAPABILITY_OUTCOME_SCOPE_INVALID")
    action=str(outcome.get("outcome") or "").upper()
    if action not in {"SUCCESS","FAILURE","INCIDENT","RECOVERY"}:
        raise SystemExit("CAPABILITY_OUTCOME_KIND_INVALID")
    if outcome.get("technology_watch_revalidated") is not True:
        raise SystemExit("TECHNOLOGY_WATCH_REVALIDATION_REQUIRED")
    if float(outcome.get("automatic_external_spend_eur") or 0)!=0:
        raise SystemExit("CAPABILITY_OUTCOME_NONZERO_EXTERNAL_SPEND")
    proof=validate_project_control(outcome)
    adoption=active_adoption(registry,capability)
    adoption_id=str(adoption["adoption_id"])
    if outcome.get("adoption_id") and outcome.get("adoption_id")!=adoption_id:
        raise SystemExit("CAPABILITY_OUTCOME_ADOPTION_MISMATCH")

    lineage={"schema":"chacha.dev/component-lineage/v1","components":[{
      "kind":"capability","component_id":capability,"version":adoption_id,
      "contract_id":"durable-capability:"+adoption_id,
      "artifact_digest":str(adoption.get("executable_digest") or adoption.get("source_digest") or "")
    }]}
    evaluation=None;anomaly=None
    if action=="SUCCESS":
        evaluation={"schema":"chacha.dev/component-evaluation/v1","verified":True,"outcome":"PASS","acceptance_score":1.0}
    elif action=="FAILURE":
        evaluation={"schema":"chacha.dev/component-evaluation/v1","verified":True,"outcome":"FAIL","acceptance_score":0.0}
    elif action=="INCIDENT":
        severity=str(outcome.get("severity") or "").lower()
        if severity not in {"high","critical"}:
            raise SystemExit("CAPABILITY_INCIDENT_SEVERITY_INVALID")
        anomaly={"severity":severity,"class":str(outcome.get("incident_class") or "capability-runtime-anomaly"),
                 "status":"open","resolution_verified":False}
    else:
        severity=str(outcome.get("severity") or "critical").lower()
        if severity not in {"high","critical"}:
            raise SystemExit("CAPABILITY_RECOVERY_SEVERITY_INVALID")
        anomaly={"severity":severity,"class":str(outcome.get("incident_class") or "capability-runtime-anomaly"),
                 "status":"verified-resolved","resolution_verified":True}

    state={"capability":capability,"adoption_id":adoption_id,"last_project_id":project,
           "last_project_outcome":action,"technology_watch_revalidated":True}
    obs=ul.observe(project_id=project,
                   source_id="capability-trust:"+capability,
                   source_kind="learning-module",
                   deployment_id=adoption_id,
                   state=state,anomaly=anomaly,evaluation=evaluation,
                   lineage=lineage,evidence_refs=[str(x) for x in (outcome.get("evidence_refs") or [])],
                   outbox_root=args.outbox_root,state_root=args.state_root)
    result={"schema":"chacha.dev/capability-trust-observation-result/v1",
            "status":str(obs.get("status") or "UNKNOWN"),"queued":bool(obs.get("queued")),
            "project_id":project,"capability":capability,"adoption_id":adoption_id,
            "outcome":action,"delta_id":obs.get("delta_id"),"outbox":obs.get("outbox"),
            "project_control_committed_proof":True,
            "technology_watch_revalidated":True,
            "automatic_external_spend_eur":0}
    return result

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--registry",type=Path,required=True)
    ap.add_argument("--outcome",type=Path,required=True)
    ap.add_argument("--outbox-root",type=Path,required=True)
    ap.add_argument("--state-root",type=Path,required=True)
    ap.add_argument("--output",type=Path)
    a=ap.parse_args()
    result=observe(a)
    if a.output:
        a.output.parent.mkdir(parents=True,exist_ok=True)
        a.output.write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps(result,indent=2,ensure_ascii=False))
    print("CHACHA_DEV_V643_PROJECT_CONTROL_VERIFIED_CAPABILITY_OBSERVATION=PASS")
    print("CHACHA_DEV_V643_EXACT_CAPABILITY_LINEAGE=PASS")
    print("CHACHA_DEV_V643_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
