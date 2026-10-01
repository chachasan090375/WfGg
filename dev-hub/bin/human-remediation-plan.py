#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path
from typing import Any

PLAN_SCHEMA="chacha.dev/autonomy-supervision-plan/v1"
POLICY_SCHEMA="chacha.dev/human-remediation-planning/v1"

def load(path:Path)->dict[str,Any]:
    value=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value,dict): raise ValueError("JSON_ROOT_NOT_OBJECT:"+str(path))
    return value

def digest(path:Path)->str:
    return "sha256:"+hashlib.sha256(path.read_bytes()).hexdigest()

def issues(model:dict[str,Any])->list[dict[str,Any]]:
    rec=model.get("reconciliation") if isinstance(model.get("reconciliation"),dict) else {}
    return [x for x in (rec.get("issues") or []) if isinstance(x,dict)]

def save(path:Path,value:dict[str,Any])->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")

def build(plan:dict[str,Any],model:dict[str,Any],policy:dict[str,Any],self_model_path:Path)->dict[str,Any]:
    if plan.get("schema")!=PLAN_SCHEMA: raise ValueError("PLAN_SCHEMA_MISMATCH")
    if policy.get("schema")!=POLICY_SCHEMA: raise ValueError("POLICY_SCHEMA_MISMATCH")
    if plan.get("next_state")!="AWAIT_HUMAN": raise ValueError("PLAN_NOT_HUMAN_BOUNDARY")
    source={(str(x.get("code")),str(x.get("subject"))):x for x in issues(model)}
    required=list(policy.get("default_required_evidence") or [])
    dossiers=[]
    for row in plan.get("human_boundaries") or []:
        code=str(row.get("issue_code") or "");subject=str(row.get("subject") or "")
        owner=str(row.get("owner") or "");action=str(row.get("reason") or "")
        if not code or not owner or owner=="UNRESOLVED" or not action: raise ValueError("HUMAN_BOUNDARY_DOSSIER_INCOMPLETE:"+code)
        issue=source.get((code,subject)) or {}
        dossiers.append({
            "issue_code":code,"subject":subject,"owner":owner,"required_action":action,
            "issue_class":"HUMAN_BOUNDARY","issue_details":issue.get("details") or {},
            "approval_required":True,"auto_apply":False,"rollback_required":True,
            "guardian_required":True,"sentinel_required":True,"required_evidence":required,
            "direct_mutation_authority":False,"automatic_external_spend_eur":0
        })
    if not dossiers: raise ValueError("NO_HUMAN_BOUNDARY_DOSSIERS")
    return {"schema":"chacha.dev/human-remediation-plan/v1","status":"PASS","state":"PREPARED_AWAITING_HUMAN",
            "dossier_count":len(dossiers),"dossiers":dossiers,"self_model_digest":digest(self_model_path),
            "source_plan_status":plan.get("status"),"source_plan_next_state":plan.get("next_state"),
            "direct_mutation_authority":False,"production_mutation":False,"automatic_external_spend_eur":0}

def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument("--plan",type=Path,required=True);ap.add_argument("--self-model",type=Path,required=True)
    ap.add_argument("--policy",type=Path,required=True);ap.add_argument("--output",type=Path,required=True);a=ap.parse_args()
    try:
        out=build(load(a.plan),load(a.self_model),load(a.policy),a.self_model);save(a.output,out)
        print("HUMAN_REMEDIATION_PLAN=PASS");print("DOSSIERS="+str(out["dossier_count"]));print("AUTOMATIC_EXTERNAL_SPEND_EUR=0");return 0
    except Exception as exc:
        out={"schema":"chacha.dev/human-remediation-plan/v1","status":"BLOCK","reason":str(exc),"direct_mutation_authority":False,"automatic_external_spend_eur":0}
        save(a.output,out);print("HUMAN_REMEDIATION_PLAN=BLOCK");print("REASON="+str(exc));return 20

if __name__=="__main__": raise SystemExit(main())
