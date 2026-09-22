#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json
from typing import Any

SCHEMA="chacha.dev/dynamic-agent-role-contract/v1"
READ_ONLY_HINTS=("read","inspect","research","search","diagnostic","lint","scan","verify","verification","audit","monitor","analysis")
PREVIEW_HINTS=("preview","sandbox-deploy","staging-deploy")

def canonical(v:Any)->str:
    return json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(",",":"))

def permissions_for(capabilities:list[str])->list[str]:
    caps=[str(x).lower() for x in capabilities]
    perms={"read","plan"}
    if any(any(h in c for h in PREVIEW_HINTS) for c in caps):
        perms.add("preview-deploy")
    if any(not any(h in c for h in READ_ONLY_HINTS+PREVIEW_HINTS) for c in caps):
        perms.add("workspace-write")
    order=["read","plan","workspace-write","preview-deploy"]
    return [x for x in order if x in perms]

def build_contract(*,agent_id:str,project_id:str,domain:str,package_id:str,
                   capabilities:list[str],tools:list[Any],scope:str)->dict[str,Any]:
    if not agent_id:
        raise ValueError("AGENT_ID_REQUIRED")
    core={
      "schema":SCHEMA,
      "contract_id":"agent:"+agent_id,
      "template_contract_id":"role:__agent__",
      "issued_by":"agent-foundry",
      "agent_id":agent_id,
      "project_id":project_id,
      "domain":domain,
      "package_id":package_id,
      "scope":scope,
      "allowed_actions":["DISPATCH_TASK","INVOKE_COMPONENT","REPORT_TASK_RESULT"],
      "forbidden_actions":["FINAL_ARCHITECTURE_DECISION","MODIFY_GUARDIAN_CONTRACTS","PRODUCTION_DEPLOY"],
      "allowed_permissions":permissions_for(capabilities),
      "allowed_capabilities":sorted(set(map(str,capabilities))),
      "allowed_tools":tools,
      "production_permissions_allowed":False,
      "human_approval_cannot_expand_contract":True,
      "automatic_external_spend_eur":0
    }
    dig=hashlib.sha256(canonical(core).encode()).hexdigest()
    core["version"]="v1-"+dig[:12]
    core["contract_digest"]=dig
    return core
