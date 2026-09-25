#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,importlib.util,json,re
from pathlib import Path
from typing import Any

RESULT_SCHEMA="chacha.dev/domain-factory-handoff/v1"
GRAPH_SCHEMA="chacha.dev/task-graph/v1"

def load(path:Path)->dict[str,Any]:
    value=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value,dict):raise SystemExit("JSON_ROOT_NOT_OBJECT="+str(path))
    return value

def save(path:Path,value:dict[str,Any])->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")

def digest(value:Any)->str:
    raw=json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(",",":")).encode()
    return "sha256:"+hashlib.sha256(raw).hexdigest()

def safe(value:str)->str:
    return re.sub(r"[^A-Za-z0-9_.-]+","-",value).strip("-") or "package"

def load_contract_registry(repo_root:Path):
    path=repo_root/"dev-hub/bin/contract-registry.py"
    spec=importlib.util.spec_from_file_location("domain_factory_contract_registry",path)
    if spec is None or spec.loader is None:raise SystemExit("CONTRACT_REGISTRY_LOAD_FAILED")
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod

def runtime_caps(capabilities:list[str],semantics:dict[str,Any])->tuple[list[str],list[dict[str,Any]]]:
    feature_defs=semantics.get("domain_features") or {}
    runtime=[];features=[]
    for raw in capabilities:
        cap=str(raw)
        row=feature_defs.get(cap) if isinstance(feature_defs,dict) else None
        if isinstance(row,dict):
            features.append({
              "id":cap,
              "classification":str(row.get("implementation_state") or "BUILD_REQUIRED"),
              "owner_domain":str(row.get("owner_domain") or ""),
              "provider_registration_required":bool(row.get("provider_registration_required",False))
            })
        else:
            runtime.append(cap)
    return runtime,features

def build(repo_root:Path,planning:Path,output_dir:Path)->dict[str,Any]:
    plan=load(planning/"final-plan.json")
    council=load(planning/"architecture-decision-council.json")
    components=load(planning/"component-role-contracts.json")
    agents=load(planning/"agent-role-contracts.json")
    semantics=load(repo_root/"dev-hub/config/capability-semantics.v1.json")
    capability_registry=load(repo_root/"dev-hub/config/capability-registry.v1.json")

    errors=[]
    if plan.get("schema")!="chacha.dev/domain-plan/v1":errors.append("FINAL_PLAN_SCHEMA_INVALID")
    if council.get("schema")!="chacha.dev/architecture-decision-council/v1":errors.append("COUNCIL_SCHEMA_INVALID")
    if components.get("schema")!="chacha.dev/dynamic-component-role-contract-batch/v1":errors.append("COMPONENT_CONTRACT_SCHEMA_INVALID")
    if agents.get("schema")!="chacha.dev/dynamic-agent-role-contract-batch/v1":errors.append("AGENT_CONTRACT_SCHEMA_INVALID")
    if semantics.get("schema")!="chacha.dev/capability-semantics/v1":errors.append("CAPABILITY_SEMANTICS_SCHEMA_INVALID")
    if council.get("dispatch_allowed") is not True:errors.append("ARCHITECTURE_COUNCIL_DISPATCH_NOT_ALLOWED")
    if council.get("blocked"):errors.append("ARCHITECTURE_COUNCIL_BLOCKED")

    contract_mod=load_contract_registry(repo_root)
    reconciliation=contract_mod.reconcile_dynamic(plan,components)
    save(output_dir/"contract-reconciliation.json",reconciliation)
    if reconciliation.get("assembly_allowed") is not True:
        errors.append("COMPONENT_CONTRACT_RECONCILIATION_FAILED")

    contract_projects=sorted({
      str(x.get("project_id") or "") for x in (components.get("contracts") or [])
      if isinstance(x,dict) and str(x.get("project_id") or "")
    })
    project_id=str(plan.get("project_id") or council.get("project_id") or components.get("project_id") or "")
    if not project_id and len(contract_projects)==1:
        project_id=contract_projects[0]
    elif not project_id and len(contract_projects)>1:
        errors.append("PROJECT_ID_AMBIGUOUS")
    if not project_id:
        errors.append("PROJECT_ID_UNRESOLVED")
    by_package={str(x.get("package_id") or ""):x for x in components.get("contracts") or [] if isinstance(x,dict)}
    manifests=[]
    tasks=[]
    required_providers={}
    registry_caps=capability_registry.get("capabilities") or {}

    package_dir=output_dir/"packages"
    for pkg in plan.get("packages") or []:
        if not isinstance(pkg,dict) or pkg.get("runtime_required") is not True:continue
        pid=str(pkg.get("id") or "")
        domain=str(pkg.get("domain") or "")
        branch_id=str(pkg.get("branch_id") or "")
        contract=by_package.get(pid)
        p_errors=[]
        if not pid:p_errors.append("PACKAGE_ID_MISSING")
        if not branch_id:p_errors.append("BRANCH_ID_MISSING")
        if not isinstance(contract,dict):
            p_errors.append("DYNAMIC_COMPONENT_CONTRACT_MISSING")
            contract={}
        if branch_id and str(contract.get("component_id") or "")!=branch_id:
            p_errors.append("BRANCH_CONTRACT_ID_MISMATCH")
        if project_id and str(contract.get("project_id") or "")!=project_id:
            p_errors.append("BRANCH_CONTRACT_PROJECT_MISMATCH")
        if contract.get("production_permissions_allowed") is not False:
            p_errors.append("PRODUCTION_PERMISSION_NOT_DENIED")
        if float(contract.get("automatic_external_spend_eur") or 0)!=0:
            p_errors.append("NONZERO_AUTOMATIC_EXTERNAL_SPEND")
        caps=[str(x) for x in pkg.get("capabilities") or []]
        allowed=set(str(x) for x in contract.get("allowed_capabilities") or [])
        missing=sorted(set(caps)-allowed)
        if missing:p_errors.extend("CAPABILITY_OUTSIDE_BRANCH_CONTRACT:"+x for x in missing)

        rcaps,features=runtime_caps(caps,semantics)
        for cap in rcaps:
            caprow=registry_caps.get(cap)
            if not isinstance(caprow,dict):
                p_errors.append("RUNTIME_CAPABILITY_NOT_REGISTERED:"+cap)
                continue
            providers=[]
            for provider in caprow.get("providers") or []:
                if not isinstance(provider,dict) or provider.get("status")=="RETIRE":continue
                provider_id=str(provider.get("id") or "")
                if provider_id:
                    providers.append({"id":provider_id,"status":provider.get("status")})
                    required_providers.setdefault(provider_id,set()).add(cap)
            if not providers:p_errors.append("RUNTIME_CAPABILITY_HAS_NO_PROVIDER:"+cap)

        state="READY" if not p_errors else "BLOCKED"
        manifest={
          "schema":"chacha.dev/domain-factory-package/v1",
          "project_id":project_id,"package_id":pid,"domain":domain,
          "kind":pkg.get("kind"),"state":state,
          "component_id":branch_id,"agent_id":pkg.get("agent_id"),
          "component_contract_id":contract.get("contract_id"),
          "component_contract_version":contract.get("version"),
          "component_contract_digest":contract.get("contract_digest"),
          "allowed_permissions":contract.get("allowed_permissions") or [],
          "runtime_capabilities":rcaps,
          "domain_features":features,
          "errors":p_errors,
          "production_permissions_allowed":False,
          "automatic_external_spend_eur":0,
          "direct_mutation":False
        }
        save(package_dir/(safe(pid)+".json"),manifest)
        manifests.append(manifest)

        if state=="READY":
            permission="workspace-write" if "workspace-write" in set(contract.get("allowed_permissions") or []) else "plan"
            tasks.append({
              "id":"package:"+pid,
              "kind":"domain-package",
              "description":"Execute approved domain package "+pid+" under its dynamic branch contract",
              "owner_role":str(pkg.get("agent_id") or domain+"-agent"),
              "capabilities":rcaps,
              "permission":permission,
              "depends_on":[],
              "outputs":[{"type":"domain-package-result","id":pid}],
              "verification":{"mode":"independent-agent","self_certification_allowed":False,
                              "required_evidence":["source","timestamp","digest","guardian-verdict"]},
              "blocking":True,
              "parallel_group":"domain-"+domain,
              "metadata":{
                "component_id":branch_id,"domain":domain,"package_id":pid,
                "domain_features":[x["id"] for x in features]
              }
            })

    blocked=[{"package_id":m["package_id"],"errors":m["errors"]} for m in manifests if m["state"]!="READY"]
    graph={
      "schema":GRAPH_SCHEMA,
      "project":project_id,
      "transition":"DOMAIN_FACTORIES->DOMAIN_EXECUTION",
      "tasks":tasks,
      "guardian_binding":None,
      "summary":{
        "task_count":len(tasks),
        "blocking_tasks":len(tasks),
        "domain_feature_count":sum(len(m["domain_features"]) for m in manifests),
        "runtime_capability_count":sum(len(m["runtime_capabilities"]) for m in manifests)
      }
    }
    save(output_dir/"domain-execution-graph.json",graph)

    providers=[
      {"provider":pid,"capabilities":sorted(caps),"health_required":True}
      for pid,caps in sorted(required_providers.items())
    ]
    provider_req={
      "schema":"chacha.dev/provider-health-requirements/v1",
      "project_id":project_id,
      "providers":providers,
      "required_provider_count":len(providers),
      "unknown_health_is_not_healthy":True,
      "automatic_external_spend_eur":0
    }
    save(output_dir/"provider-health-requirements.json",provider_req)

    status="READY" if not errors and not blocked else "BLOCKED"
    result={
      "schema":RESULT_SCHEMA,
      "project_id":project_id,
      "status":status,
      "next_stage":"PROVIDER_HEALTH_REQUIRED" if status=="READY" else "DOMAIN_FACTORY_REPAIR_REQUIRED",
      "architecture_council_dispatch_allowed":council.get("dispatch_allowed") is True,
      "contract_reconciliation":str(output_dir/"contract-reconciliation.json"),
      "domain_execution_graph":str(output_dir/"domain-execution-graph.json"),
      "provider_health_requirements":str(output_dir/"provider-health-requirements.json"),
      "package_count":len(manifests),
      "ready_package_count":sum(m["state"]=="READY" for m in manifests),
      "blocked_package_count":len(blocked),
      "runtime_task_count":len(tasks),
      "errors":errors,
      "blocked_packages":blocked,
      "direct_mutation":False,
      "provider_execution_started":False,
      "production_permissions_allowed":False,
      "automatic_external_spend_eur":0
    }
    save(output_dir/"domain-factory-result.json",result)
    return result

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--repo-root",type=Path,default=Path("/opt/chacha-dev/platform/current"))
    ap.add_argument("--planning-dir",type=Path,required=True)
    ap.add_argument("--output-dir",type=Path,required=True)
    a=ap.parse_args()
    result=build(a.repo_root.resolve(),a.planning_dir.resolve(),a.output_dir.resolve())
    print("CHACHA_DEV_V818_DOMAIN_FACTORY_HANDOFF="+("PASS" if result["status"]=="READY" else "BLOCKED"))
    print("PACKAGES="+str(result["package_count"]))
    print("READY="+str(result["ready_package_count"]))
    print("BLOCKED="+str(result["blocked_package_count"]))
    print("NEXT_STAGE="+str(result["next_stage"]))
    print("AUTOMATIC_EXTERNAL_SPEND_EUR=0")
    return 0 if result["status"]=="READY" else 2

if __name__=="__main__":
    raise SystemExit(main())
