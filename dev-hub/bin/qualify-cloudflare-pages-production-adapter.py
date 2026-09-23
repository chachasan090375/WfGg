#!/usr/bin/env python3
"""V6.39 static contract qualification for the Cloudflare Pages production adapter.

This qualification is strictly non-mutating:
- it never enables the real production execution switch;
- it never calls Cloudflare write APIs;
- it never edits the adapter registry;
- it emits promotion evidence suitable only for DESIGNED -> CONTRACT_OK.
"""
from __future__ import annotations

import argparse
import json
import os
import py_compile
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT=Path(__file__).resolve().parents[2]
CFG=ROOT/"dev-hub/config"
ADAPTER=ROOT/"dev-hub/adapters/cloudflare-pages-production-adapter.py"
ADAPTER_ID="cloudflare-pages-production-adapter"
PROVIDER_ID="cloudflare-pages-production"
EVIDENCE_SCHEMA="chacha.dev/adapter-promotion-evidence/v1"

def now_iso()->str:
    return datetime.now(timezone.utc).isoformat()

def load(path:Path)->dict[str,Any]:
    x=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(x,dict):
        raise SystemExit("JSON_ROOT_NOT_OBJECT:"+str(path))
    return x

def save(path:Path,x:dict[str,Any])->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")

def run_adapter(envelope:dict[str,Any],env:dict[str,str])->dict[str,Any]:
    p=subprocess.run(
      [sys.executable,str(ADAPTER)],
      input=json.dumps(envelope),text=True,
      stdout=subprocess.PIPE,stderr=subprocess.PIPE,
      cwd=str(ROOT),env=env,check=False,timeout=30
    )
    try:
        out=json.loads(p.stdout)
    except Exception as exc:
        raise SystemExit("V639_CF_ADAPTER_OUTPUT_INVALID:"+p.stdout[-2000:]+p.stderr[-2000:]) from exc
    if not isinstance(out,dict):
        raise SystemExit("V639_CF_ADAPTER_OUTPUT_NOT_OBJECT")
    out["_exit_code"]=p.returncode
    return out

def base_envelope(task_id:str,permission:str,action:str)->dict[str,Any]:
    return {
      "schema":"chacha.dev/dispatch-envelope/v1",
      "project":"v639-cf-pages-contract-qualification",
      "transition":"RELEASE->OPERATE",
      "run_id":"v639-cf-pages-contract-qualification",
      "wave":1,
      "task":{
        "id":task_id,
        "kind":"adapter-contract",
        "description":"V6.39 Cloudflare Pages production adapter static contract qualification",
        "owner_role":"platform-cloud-engineer",
        "permission":permission,
        "outputs":[],
        "verification":{"mode":"machine","self_certification_allowed":False,"required_evidence":["source","timestamp","digest"]}
      },
      "bindings":[{
        "capability":"cloud-deploy-static",
        "provider":PROVIDER_ID,
        "adapter":ADAPTER_ID,
        "fallback_used":False,
        "health_state":"UNKNOWN"
      }],
      "policy_context":{
        "resource_class":"light",
        "requires_storage_preflight":False,
        "human_approval_required":False,
        "approval_id":None,
        "timeout_seconds":20
      },
      "workspace":None,
      "metadata":{"cloudflare_pages_production":{"action":action}}
    }

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--evidence",type=Path,required=True)
    ap.add_argument("--report",type=Path,required=True)
    a=ap.parse_args()

    registry=load(CFG/"provider-adapters.v1.json")
    contract=load(CFG/"adapter-contract.v1.json")
    policy=load(CFG/"cloudflare-pages-production-adapter.v1.json")
    provisioning=load(CFG/"adapter-provisioning.v1.json")
    rollbacks=load(CFG/"adapter-rollbacks.v1.json")

    blockers:list[str]=[]
    providers=registry.get("providers") or {}
    adapters=registry.get("adapters") or {}
    provider=providers.get(PROVIDER_ID)
    entry=adapters.get(ADAPTER_ID)

    if not isinstance(provider,dict) or provider.get("adapter")!=ADAPTER_ID:
        blockers.append("PROVIDER_BINDING_INVALID")
    if isinstance(provider,dict) and provider.get("execution")!="vps":
        blockers.append("EXECUTION_KIND_NOT_VPS")
    if not isinstance(entry,dict):
        blockers.append("ADAPTER_REGISTRY_ENTRY_MISSING")
        entry={}
    if entry.get("status") not in {"DESIGNED","CONTRACT_OK"}:
        blockers.append("ADAPTER_STATUS_NOT_CONTRACT_QUALIFIABLE")
    if entry.get("executable") is not None:
        blockers.append("DESIGNED_ADAPTER_EXECUTABLE_MUST_BE_NULL")
    if set(entry.get("supports") or [])!={"read","production-deploy"}:
        blockers.append("PRODUCTION_PERMISSION_CONTRACT_INVALID")

    known=set(contract.get("known_permissions") or [])
    if not set(entry.get("supports") or []).issubset(known):
        blockers.append("UNKNOWN_PERMISSION_IN_ADAPTER")

    if policy.get("schema")!="chacha.dev/cloudflare-pages-production-adapter/v1":
        blockers.append("PRODUCTION_POLICY_SCHEMA_INVALID")
    if policy.get("production_capable") is not True:
        blockers.append("PRODUCTION_CAPABLE_FLAG_MISSING")
    if policy.get("status_required_for_execution")!="ENABLED":
        blockers.append("EXECUTION_STATUS_GUARD_INVALID")
    guard=policy.get("mutation_guard") or {}
    if guard.get("protected_approval_id")!="production-deployment":
        blockers.append("PROTECTED_APPROVAL_ID_INVALID")
    if guard.get("project_control_receipt_required") is not True:
        blockers.append("PROJECT_CONTROL_RECEIPT_NOT_REQUIRED")
    if policy.get("qualification",{}).get("real_production_execution") is not False:
        blockers.append("QUALIFICATION_MUST_FORBID_REAL_PRODUCTION")
    if policy.get("qualification",{}).get("network_write_test") is not False:
        blockers.append("QUALIFICATION_MUST_FORBID_NETWORK_WRITE")
    if float((policy.get("economics") or {}).get("automatic_external_spend_eur") or 0)!=0:
        blockers.append("AUTOMATIC_EXTERNAL_SPEND_NOT_ZERO")

    rb=(rollbacks.get("adapters") or {}).get(ADAPTER_ID)
    if not isinstance(rb,dict) or rb.get("enabled") is not True:
        blockers.append("ROLLBACK_REGISTRY_MISSING")
    prov=(provisioning.get("adapters") or {}).get(ADAPTER_ID)
    if not isinstance(prov,dict):
        blockers.append("PROVISIONING_CONTRACT_MISSING")
    else:
        probe=(prov.get("probe") or {}).get("input") or {}
        meta=(probe.get("metadata") or {}).get("cloudflare_pages_production") or {}
        task=probe.get("task") or {}
        if meta.get("action")!="contract-status" or task.get("permission")!="read":
            blockers.append("PROVISIONING_PROBE_NOT_READ_ONLY")

    try:
        py_compile.compile(str(ADAPTER),doraise=True)
    except Exception:
        blockers.append("ADAPTER_PYTHON_COMPILE_FAILED")

    source=ADAPTER.read_text(encoding="utf-8")
    for forbidden in ("os.system(","shell=True","subprocess.call("):
        if forbidden in source:
            blockers.append("FORBIDDEN_EXECUTION_PATTERN:"+forbidden)
    for required in (
      "REAL_PRODUCTION_EXECUTION_SWITCH_NOT_ENABLED",
      "PROJECT_CONTROL_APPROVAL_RECEIPT_MISSING",
      "PREVIOUS_SUCCESSFUL_PRODUCTION_DEPLOYMENT_REQUIRED",
      "canonical_production(",
      "/rollback",
      "shell=False"
    ):
        if required not in source:
            blockers.append("REQUIRED_GUARD_MISSING:"+required)

    env={**os.environ}
    env.pop("CHACHA_DEV_V639_REAL_PRODUCTION_EXECUTION",None)
    env.pop("CLOUDFLARE_API_TOKEN",None)
    env.pop("CLOUDFLARE_ACCOUNT_ID",None)
    env["CHACHA_CF_PAGES_PROD_POLICY"]=str(CFG/"cloudflare-pages-production-adapter.v1.json")
    env["CHACHA_CF_PAGES_PROD_ALLOWED_PROJECTS"]="v639-contract-test"

    contract_env=base_envelope("contract-status","read","contract-status")
    out=run_adapter(contract_env,env)
    if out.get("_exit_code")!=0 or out.get("status")!="OK":
        blockers.append("CONTRACT_STATUS_PROBE_FAILED")

    with tempfile.TemporaryDirectory(prefix="v639-cf-contract-") as td:
        build=Path(td)/"build";build.mkdir()
        (build/"index.html").write_text("<!doctype html><title>V639 contract</title>",encoding="utf-8")

        plan=base_envelope("deployment-plan","read","deployment-plan")
        plan["metadata"]["cloudflare_pages_production"].update({
          "project_name":"v639-contract-test",
          "production_branch":"main",
          "revision":"d"*40,
          "build_directory":str(build)
        })
        pout=run_adapter(plan,env)
        details=((pout.get("evidence") or [{}])[0].get("details") or {}) if isinstance(pout.get("evidence"),list) else {}
        if pout.get("_exit_code")!=0 or pout.get("status")!="OK":
            blockers.append("DEPLOYMENT_PLAN_PROBE_FAILED")
        if details.get("production_mutation") is not False:
            blockers.append("PLAN_PRODUCTION_MUTATION_NOT_FALSE")
        if details.get("execution_switch_enabled") is not False:
            blockers.append("PLAN_EXECUTION_SWITCH_NOT_FALSE")

        deploy=json.loads(json.dumps(plan))
        deploy["task"]["id"]="production-deploy-blocked"
        deploy["task"]["permission"]="production-deploy"
        deploy["policy_context"]["human_approval_required"]=True
        deploy["policy_context"]["approval_id"]="production-deployment"
        deploy["metadata"]["cloudflare_pages_production"]["action"]="production-deploy"
        deploy["metadata"]["cloudflare_pages_production"]["approval_receipt"]=str(Path(td)/"missing.json")
        dout=run_adapter(deploy,env)
        if dout.get("_exit_code")!=2 or dout.get("status")!="BLOCKED":
            blockers.append("PRODUCTION_DEPLOY_NOT_FAIL_CLOSED")
        if dout.get("summary")!="REAL_PRODUCTION_EXECUTION_SWITCH_NOT_ENABLED":
            blockers.append("PRODUCTION_DEPLOY_WRONG_BLOCK_REASON")

        rollback=json.loads(json.dumps(deploy))
        rollback["task"]["id"]="production-rollback-blocked"
        rollback["metadata"]["cloudflare_pages_production"]["action"]="production-rollback"
        rollback["metadata"]["cloudflare_pages_production"]["previous_deployment_id"]="fake"
        rout=run_adapter(rollback,env)
        if rout.get("_exit_code")!=2 or rout.get("status")!="BLOCKED":
            blockers.append("PRODUCTION_ROLLBACK_NOT_FAIL_CLOSED")
        if rout.get("summary")!="REAL_PRODUCTION_EXECUTION_SWITCH_NOT_ENABLED":
            blockers.append("PRODUCTION_ROLLBACK_WRONG_BLOCK_REASON")

    status="PASS" if not blockers else "FAIL"
    report={
      "schema":"chacha.dev/v639-cloudflare-pages-production-static-contract/v1",
      "adapter":ADAPTER_ID,
      "provider":PROVIDER_ID,
      "status":status,
      "blockers":sorted(set(blockers)),
      "current_status":entry.get("status"),
      "production_mutation":False,
      "network_write_test":False,
      "real_production_target":False,
      "automatic_external_spend_eur":0,
      "observed_at":now_iso()
    }
    save(a.report,report)

    evidence={
      "schema":EVIDENCE_SCHEMA,
      "adapter":ADAPTER_ID,
      "observed_at":report["observed_at"],
      "evidence":{
        "static-contract-pass":{
          "status":status,
          "source":str(a.report.resolve()),
          "observed_at":report["observed_at"],
          "details":{
            "production_mutation":False,
            "network_write_test":False,
            "real_production_target":False,
            "blocker_count":len(report["blockers"])
          }
        }
      },
      "approvals":[]
    }
    save(a.evidence,evidence)

    print("CHACHA_DEV_V639_CF_PAGES_STATIC_CONTRACT="+status)
    print("CHACHA_DEV_V639_CF_PAGES_NETWORK_WRITE_TEST=NO")
    print("CHACHA_DEV_V639_CF_PAGES_PRODUCTION_MUTATION=NO")
    print("CHACHA_DEV_V639_CF_PAGES_REAL_PRODUCTION_TARGET=NO")
    for b in report["blockers"]:
        print("BLOCKER="+b)
    return 0 if status=="PASS" else 2

if __name__=="__main__":
    raise SystemExit(main())
