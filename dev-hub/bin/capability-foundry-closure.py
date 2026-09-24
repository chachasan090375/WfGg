#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PLAN_SCHEMA="chacha.dev/capability-foundry-closure-plan/v1"
RECEIPT_SCHEMA="chacha.dev/capability-adoption-receipt/v1"


def load(path:Path)->dict[str,Any]:
    value=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value,dict):
        raise SystemExit(f"JSON_ROOT_NOT_OBJECT:{path}")
    return value


def save(path:Path,value:dict[str,Any])->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")


def atomic_save(path:Path,value:dict[str,Any])->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix=path.name+".",dir=str(path.parent))
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as f:
            json.dump(value,f,indent=2,ensure_ascii=False)
            f.write("\n");f.flush();os.fsync(f.fileno())
        os.chmod(tmp,0o644)
        os.replace(tmp,path)
        dfd=os.open(str(path.parent),os.O_DIRECTORY)
        try: os.fsync(dfd)
        finally: os.close(dfd)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def now_iso()->str:
    return datetime.now(timezone.utc).isoformat()


def candidate_provider_id(candidate:dict[str,Any],policy:dict[str,Any])->str:
    for field in policy.get("provider_candidate_fields") or ["provider_id","id"]:
        value=str(candidate.get(field) or "").strip()
        if value:
            return value
    return ""


def candidate_external_spend(candidate:dict[str,Any])->float:
    raw=candidate.get("external_spend_eur",candidate.get("automatic_external_spend_eur",0))
    try:return float(raw or 0)
    except Exception:return 999999.0


def credential_boundary_change(candidate:dict[str,Any])->bool:
    return any(bool(candidate.get(k)) for k in (
        "credential_boundary_change",
        "credential_change_required",
        "new_credentials_required",
        "new_identity_required",
    ))


def select_existing_provider(plan:dict[str,Any],provider_registry:dict[str,Any],policy:dict[str,Any])->dict[str,Any]:
    providers=provider_registry.get("providers") or {}
    adapters=provider_registry.get("adapters") or {}
    allowed=set(policy.get("eligible_adapter_statuses") or ["ENABLED"])
    protected=set(policy.get("protected_permissions") or [])
    evaluated=[]
    eligible=[]
    for candidate in plan.get("technology_candidates") or []:
        if not isinstance(candidate,dict):
            continue
        pid=candidate_provider_id(candidate,policy)
        spend=candidate_external_spend(candidate)
        provider=providers.get(pid) if pid else None
        adapter_id=(provider or {}).get("adapter") if isinstance(provider,dict) else None
        adapter=adapters.get(adapter_id) if adapter_id else None
        adapter_status=(adapter or {}).get("status") if isinstance(adapter,dict) else None
        supports=set((adapter or {}).get("supports") or []) if isinstance(adapter,dict) else set()
        reasons=[]
        if not pid: reasons.append("PROVIDER_ID_MISSING")
        if spend>0: reasons.append("NONZERO_EXTERNAL_SPEND")
        if credential_boundary_change(candidate): reasons.append("NEW_CREDENTIAL_BOUNDARY")
        if not isinstance(provider,dict): reasons.append("PROVIDER_NOT_REGISTERED")
        if not isinstance(adapter,dict): reasons.append("ADAPTER_NOT_REGISTERED")
        elif adapter_status not in allowed: reasons.append("ADAPTER_NOT_ENABLED")
        row={
            "provider_id":pid or None,
            "adapter_id":adapter_id,
            "adapter_status":adapter_status,
            "external_spend_eur":spend,
            "credential_boundary_change":credential_boundary_change(candidate),
            "production_capable":bool(supports & protected),
            "eligible":not reasons,
            "reason_codes":reasons,
            "candidate":candidate,
        }
        evaluated.append(row)
        if not reasons:
            eligible.append(row)
    eligible.sort(key=lambda x:(x["external_spend_eur"],str(x["provider_id"])))
    return {"selected":eligible[0] if eligible else None,"evaluated":evaluated}


def build_plan(foundry:dict[str,Any],caps:dict[str,Any],provider_registry:dict[str,Any],policy:dict[str,Any])->dict[str,Any]:
    if foundry.get("schema")!="chacha.dev/capability-foundry-plan/v1":
        raise SystemExit("FOUNDRY_PLAN_SCHEMA_INVALID")
    if caps.get("schema")!="chacha.dev/capability-registry/v1":
        raise SystemExit("CAPABILITY_REGISTRY_SCHEMA_INVALID")
    if provider_registry.get("schema")!="chacha.dev/provider-adapters/v1":
        raise SystemExit("PROVIDER_ADAPTER_REGISTRY_SCHEMA_INVALID")
    if policy.get("schema")!="chacha.dev/capability-foundry-closure/v1":
        raise SystemExit("CLOSURE_POLICY_SCHEMA_INVALID")

    existing=caps.get("capabilities") or {}
    rows=[];overlay={}
    for fp in foundry.get("plans") or []:
        if not isinstance(fp,dict):continue
        cid=str(fp.get("capability") or "").strip()
        if not cid:continue
        if cid in existing:
            rows.append({
              "capability":cid,"state":"REUSE_REGISTERED",
              "selected_provider":None,"build_required":False,
              "same_project_resume_allowed":True,
              "durable_adoption_required":False,
              "durable_adoption_requires_human_approval":False,
              "reason_codes":[]
            })
            continue

        selection=select_existing_provider(fp,provider_registry,policy)
        selected=selection["selected"]
        if selected is None:
            rows.append({
              "capability":cid,"state":"BUILD_REQUIRED",
              "selected_provider":None,"build_required":True,
              "same_project_resume_allowed":False,
              "durable_adoption_required":True,
              "durable_adoption_requires_human_approval":False,
              "evaluated_candidates":selection["evaluated"],
              "reason_codes":["NO_EXISTING_ENABLED_ZERO_SPEND_PROVIDER"]
            })
            continue

        pid=str(selected["provider_id"])
        provider=(provider_registry.get("providers") or {})[pid]
        adapter=(provider_registry.get("adapters") or {})[provider["adapter"]]
        provider_status=str(policy.get("project_local_provider_status") or "PILOT")
        cap={
          "class":"execution",
          "providers":[{
            "id":pid,
            "status":provider_status,
            "health":"runtime-check",
            "cost_class":"included" if selected["external_spend_eur"]==0 else "external",
            "scope":"project-local-auto-closure",
            "fallback":[]
          }],
          "generated_by":"capability-foundry-closure",
          "owner_domain":fp.get("owner_domain"),
          "promotion_state":"PROJECT_LOCAL_PILOT",
          "selected_adapter":provider["adapter"],
          "automatic_external_spend_eur":0
        }
        overlay[cid]=cap
        rows.append({
          "capability":cid,
          "state":"PROJECT_LOCAL_READY",
          "selected_provider":pid,
          "selected_adapter":provider["adapter"],
          "selected_adapter_status":adapter.get("status"),
          "production_capable":bool(selected["production_capable"]),
          "build_required":False,
          "same_project_resume_allowed":True,
          "durable_adoption_required":True,
          "durable_adoption_requires_human_approval":bool(selected["production_capable"]),
          "external_spend_eur":selected["external_spend_eur"],
          "evaluated_candidates":selection["evaluated"],
          "reason_codes":[]
        })

    blocked=sum(1 for x in rows if x["state"]=="BUILD_REQUIRED")
    ready=sum(1 for x in rows if x["state"] in {"PROJECT_LOCAL_READY","REUSE_REGISTERED"})
    return {
      "schema":PLAN_SCHEMA,
      "version":"1.0.0",
      "project_id":foundry.get("project_id"),
      "status":"READY" if blocked==0 else "PARTIAL",
      "plans":rows,
      "capability_overlay":{"schema":"chacha.dev/capability-overlay/v1","capabilities":overlay},
      "summary":{
        "count":len(rows),
        "ready_count":ready,
        "build_required_count":blocked,
        "same_project_resume_allowed":blocked==0
      },
      "automatic_external_spend_eur":0,
      "technology_watch_evidence_required":True,
      "architecture_council_final_authority":True
    }


def validate_adoption(capability:str,provider:str,verification:dict[str,Any],plan_row:dict[str,Any],policy:dict[str,Any],approval_id:str|None)->None:
    ad=policy.get("adoption") or {}
    if verification.get("schema")!=ad.get("verification_schema"):
        raise SystemExit("ADOPTION_EVIDENCE_SCHEMA_INVALID")
    if verification.get("status")!=ad.get("required_status","PASS"):
        raise SystemExit("ADOPTION_EVIDENCE_NOT_PASS")
    if ad.get("require_same_capability",True) and verification.get("capability")!=capability:
        raise SystemExit("ADOPTION_CAPABILITY_MISMATCH")
    if ad.get("require_same_provider",True) and verification.get("provider")!=provider:
        raise SystemExit("ADOPTION_PROVIDER_MISMATCH")
    if ad.get("require_project_success",True) and verification.get("project_success") is not True:
        raise SystemExit("ADOPTION_PROJECT_SUCCESS_REQUIRED")
    if plan_row.get("durable_adoption_requires_human_approval"):
        approvals=verification.get("approvals") or []
        match=next((x for x in approvals if isinstance(x,dict)
                    and x.get("id")==approval_id
                    and x.get("type")=="capability-production-adopt"
                    and x.get("capability")==capability
                    and x.get("target_status")=="ADOPT"
                    and str(x.get("actor") or "") not in {"","central-orchestrator","guardian","sentinel","curator","bastion","intendant","logician","ergonomist"}),None)
        if match is None:
            raise SystemExit("CAPABILITY_ADOPTION_HUMAN_APPROVAL_REQUIRED")


def apply_adoption(registry_path:Path,plan:dict[str,Any],capability:str,verification:dict[str,Any],
                   policy:dict[str,Any],actor:str,approval_id:str|None,receipt_path:Path)->dict[str,Any]:
    registry=load(registry_path)
    if registry.get("schema")!=(policy.get("mutation") or {}).get("allowed_registry_schema"):
        raise SystemExit("ADOPTION_REGISTRY_SCHEMA_INVALID")
    row=next((x for x in plan.get("plans") or [] if x.get("capability")==capability),None)
    if row is None: raise SystemExit("CAPABILITY_NOT_IN_CLOSURE_PLAN")
    if row.get("state")=="REUSE_REGISTERED":
        receipt={
          "schema":RECEIPT_SCHEMA,"capability":capability,"status":"IDEMPOTENT",
          "applied":False,"actor":actor,"observed_at":now_iso()
        }
        save(receipt_path,receipt);return receipt
    if row.get("state")!="PROJECT_LOCAL_READY":
        raise SystemExit("CAPABILITY_NOT_READY_FOR_ADOPTION")
    provider=str(row.get("selected_provider") or "")
    validate_adoption(capability,provider,verification,row,policy,approval_id)

    caps=registry.setdefault("capabilities",{})
    existing=caps.get(capability)
    durable_status=str(policy.get("durable_provider_status") or "ADOPT")
    new_entry={
      "class":"execution",
      "providers":[{
        "id":provider,
        "status":durable_status,
        "health":"runtime-check",
        "cost_class":"included",
        "scope":"platform",
        "fallback":[]
      }],
      "generated_by":"capability-foundry-closure",
      "promotion_state":"ADOPT",
      "selected_adapter":row.get("selected_adapter"),
      "automatic_external_spend_eur":0
    }
    if existing is not None:
        if existing==new_entry:
            receipt={
              "schema":RECEIPT_SCHEMA,"capability":capability,"provider":provider,
              "status":"IDEMPOTENT","applied":False,"actor":actor,"observed_at":now_iso()
            }
            save(receipt_path,receipt);return receipt
        raise SystemExit("CAPABILITY_REGISTRY_CONFLICT")

    caps[capability]=new_entry
    atomic_save(registry_path,registry)
    receipt={
      "schema":RECEIPT_SCHEMA,
      "capability":capability,
      "provider":provider,
      "adapter":row.get("selected_adapter"),
      "status":"COMMITTED",
      "applied":True,
      "actor":actor,
      "approval_id":approval_id,
      "project_id":verification.get("project_id"),
      "verification_status":verification.get("status"),
      "automatic_external_spend_eur":0,
      "observed_at":now_iso()
    }
    save(receipt_path,receipt)
    return receipt


def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--policy",type=Path,required=True)
    ap.add_argument("--foundry-plan",type=Path,required=True)
    ap.add_argument("--capability-registry",type=Path,required=True)
    ap.add_argument("--provider-adapters",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    ap.add_argument("--overlay",type=Path)
    sub=ap.add_subparsers(dest="command",required=True)

    sub.add_parser("plan")

    adopt=sub.add_parser("adopt")
    adopt.add_argument("--capability",required=True)
    adopt.add_argument("--verification",type=Path,required=True)
    adopt.add_argument("--actor",required=True)
    adopt.add_argument("--approval-id")
    adopt.add_argument("--receipt",type=Path,required=True)
    adopt.add_argument("--apply",action="store_true")

    a=ap.parse_args()
    policy=load(a.policy);foundry=load(a.foundry_plan)
    caps=load(a.capability_registry);providers=load(a.provider_adapters)
    plan=build_plan(foundry,caps,providers,policy)
    save(a.output,plan)
    if a.overlay:
        save(a.overlay,plan["capability_overlay"])

    if a.command=="plan":
        print("CHACHA_DEV_V640_CAPABILITY_CLOSURE_PLAN=PASS")
        print("CHACHA_DEV_V640_PROJECT_LOCAL_READY="+str(plan["summary"]["ready_count"]))
        print("CHACHA_DEV_V640_BUILD_REQUIRED="+str(plan["summary"]["build_required_count"]))
        print("CHACHA_DEV_V640_SAME_PROJECT_RESUME_ALLOWED="+("YES" if plan["summary"]["same_project_resume_allowed"] else "NO"))
        print("CHACHA_DEV_V640_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
        return 0

    if not a.apply:
        raise SystemExit("CAPABILITY_ADOPTION_EXPLICIT_APPLY_REQUIRED")
    verification=load(a.verification)
    receipt=apply_adoption(a.capability_registry,plan,a.capability,verification,policy,a.actor,a.approval_id,a.receipt)
    print("CHACHA_DEV_V640_CAPABILITY_ADOPTION="+("PASS" if receipt["status"] in {"COMMITTED","IDEMPOTENT"} else receipt["status"]))
    print("CHACHA_DEV_V640_CAPABILITY_ADOPTION_APPLIED="+("YES" if receipt.get("applied") else "NO"))
    print("CHACHA_DEV_V640_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
    return 0


if __name__=="__main__":
    raise SystemExit(main())
