#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json
from typing import Any

SCHEMA="chacha.dev/dynamic-component-role-contract/v1"

def canonical(v:Any)->str:
    return json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(",",":"))

def permissions_for_branch(row:dict[str,Any])->list[str]:
    perms=["read","plan"]
    if bool(row.get("runtime_required")):
        perms.append("workspace-write")
    arch=row.get("architecture") if isinstance(row.get("architecture"),dict) else {}
    if any("preview" in str(v).lower() for v in arch.values()):
        perms.append("preview-deploy")
    return list(dict.fromkeys(perms))

def build_branch_contract(*,row:dict[str,Any],project_id:str,capabilities:list[str])->dict[str,Any]:
    branch_id=str(row.get("branch_id") or "")
    if not branch_id: raise ValueError("BRANCH_ID_REQUIRED")
    core={
      "schema":SCHEMA,
      "component_kind":"branch",
      "contract_id":"branch:"+branch_id,
      "template_contract_id":"role:__branch__",
      "issued_by":"branch-foundry",
      "component_id":branch_id,
      "project_id":project_id,
      "domain":str(row.get("domain") or ""),
      "package_id":str(row.get("package_id") or ""),
      "allowed_actions":["INVOKE_COMPONENT","DISPATCH_TASK","REPORT_TASK_RESULT"],
      "forbidden_actions":["FINAL_ARCHITECTURE_DECISION","EXECUTE_PROVIDER_DIRECTLY","MODIFY_GUARDIAN_CONTRACTS","PRODUCTION_DEPLOY"],
      "allowed_permissions":permissions_for_branch(row),
      "allowed_capabilities":sorted(set(map(str,capabilities))),
      "production_permissions_allowed":False,
      "automatic_external_spend_eur":0
    }
    dig=hashlib.sha256(canonical(core).encode()).hexdigest()
    core["version"]="v1-"+dig[:12]
    core["contract_digest"]=dig
    return core

def build_orchestrator_contract(*,component_id:str,project_id:str,domain:str,package_id:str,capabilities:list[str],source:str)->dict[str,Any]:
    if not component_id: raise ValueError("ORCHESTRATOR_ID_REQUIRED")
    core={
      "schema":SCHEMA,
      "component_kind":"orchestrator",
      "contract_id":"orchestrator:"+component_id,
      "template_contract_id":"role:__dynamic-orchestrator__",
      "issued_by":source,
      "component_id":component_id,
      "project_id":project_id,
      "domain":domain,
      "package_id":package_id,
      "allowed_actions":["INVOKE_COMPONENT","DISPATCH_TASK","FINALIZE_PROJECT_PLAN","REPORT_PLAN"],
      "forbidden_actions":["FINAL_ARCHITECTURE_DECISION","EXECUTE_PROVIDER_DIRECTLY","MODIFY_GUARDIAN_CONTRACTS","PRODUCTION_DEPLOY"],
      "allowed_permissions":["read","plan","workspace-write"],
      "allowed_capabilities":sorted(set(map(str,capabilities))),
      "production_permissions_allowed":False,
      "automatic_external_spend_eur":0
    }
    dig=hashlib.sha256(canonical(core).encode()).hexdigest()
    core["version"]="v1-"+dig[:12]
    core["contract_digest"]=dig
    return core
