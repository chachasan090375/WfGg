#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,re
from pathlib import Path
from typing import Any

PLAN_SCHEMA="chacha.dev/domain-plan/v1"
COUNCIL_SCHEMA="chacha.dev/architecture-decision-council/v1"
FACTORY_SCHEMA="chacha.dev/domain-factories/v1"
WAVE_SCHEMA="chacha.dev/runtime-wave-plan/v1"
RESULT_SCHEMA="chacha.dev/domain-factory-run/v1"
REGISTRY_SCHEMA="chacha.dev/component-registry/v1"
EXEC_SCHEMA="chacha.dev/domain-execution-manifest/v1"

def load(p:Path,default=None)->dict[str,Any]:
    try:x=json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        if default is not None:return default
        raise
    if not isinstance(x,dict):raise ValueError("JSON_ROOT_NOT_OBJECT:"+str(p))
    return x

def save(p:Path,x:dict[str,Any])->None:
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")

def digest_file(p:Path)->str:
    return "sha256:"+hashlib.sha256(p.read_bytes()).hexdigest()

def canonical(x:Any)->str:
    return json.dumps(x,sort_keys=True,ensure_ascii=False,separators=(",",":"))

def stable_id(package:dict[str,Any])->str:
    seed={
      "package_id":package.get("id"),"domain":package.get("domain"),"kind":package.get("kind"),
      "agent_id":package.get("agent_id"),"branch_id":package.get("branch_id"),
      "capabilities":sorted(str(x) for x in (package.get("capabilities") or []))
    }
    return "domain-component:"+hashlib.sha256(canonical(seed).encode()).hexdigest()[:16]

def safe(value:str)->str:
    return re.sub(r"[^A-Za-z0-9._-]+","-",value).strip("-") or "package"

def package_checks(package:dict[str,Any],decision:dict[str,Any],global_dispatch:bool)->dict[str,bool]:
    cp=decision.get("constraint_policy") or {}
    return {
      "global_dispatch_allowed":global_dispatch is True,
      "package_not_blocked":not bool(decision.get("blocked_by") or []),
      "branch_ready":cp.get("branch_ready") is True,
      "agent_ready":cp.get("agent_ready") is True,
      "capability_gaps_resolved":cp.get("capability_gaps_resolved") is True,
      "zero_spend_rule_respected":cp.get("zero_spend_rule_respected") is True,
      "security_boundary_preserved":cp.get("security_boundary_reduction") is False,
      "agent_topology_resolved":package.get("agent_topology_status")=="RESOLVED",
      "branch_topology_resolved":package.get("branch_topology_status")=="RESOLVED",
      "agent_id_present":bool(package.get("agent_id")),
      "branch_id_present":bool(package.get("branch_id")),
    }

def find_reuse(registry:dict[str,Any],package:dict[str,Any])->dict[str,Any]|None:
    need=set(str(x) for x in (package.get("capabilities") or []))
    rows=[]
    for c in registry.get("components") or []:
        if not isinstance(c,dict):continue
        if c.get("state")!="QUALIFIED":continue
        if c.get("component_kind")!="DOMAIN_EXECUTION_CAPSULE":continue
        if c.get("domain")!=package.get("domain"):continue
        if need<=set(str(x) for x in (c.get("capabilities") or [])) and c.get("compatible",True):
            rows.append(c)
    rows.sort(key=lambda x:(float(x.get("quality",0)),float(x.get("reuse_score",0))),reverse=True)
    return rows[0] if rows else None

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--repo-root",type=Path,required=True)
    ap.add_argument("--final-plan",type=Path,required=True)
    ap.add_argument("--council",type=Path,required=True)
    ap.add_argument("--wave-plan",type=Path,required=True)
    ap.add_argument("--factory-policy",type=Path,required=True)
    ap.add_argument("--registry",type=Path)
    ap.add_argument("--output-dir",type=Path,required=True)
    a=ap.parse_args()

    repo=a.repo_root.resolve()
    plan=load(a.final_plan);council=load(a.council);waves=load(a.wave_plan);policy=load(a.factory_policy)
    if plan.get("schema")!=PLAN_SCHEMA:raise SystemExit("FINAL_PLAN_SCHEMA_INVALID")
    if council.get("schema")!=COUNCIL_SCHEMA:raise SystemExit("COUNCIL_SCHEMA_INVALID")
    if waves.get("schema")!=WAVE_SCHEMA:raise SystemExit("WAVE_PLAN_SCHEMA_INVALID")
    if policy.get("schema")!=FACTORY_SCHEMA:raise SystemExit("DOMAIN_FACTORY_POLICY_SCHEMA_INVALID")
    if council.get("dispatch_allowed") is not True:raise SystemExit("ARCHITECTURE_COUNCIL_DISPATCH_REQUIRED")
    if waves.get("schedulable") is not True or waves.get("unschedulable"):raise SystemExit("RUNTIME_WAVE_PLAN_NOT_SCHEDULABLE")

    registry=load(a.registry,{"schema":REGISTRY_SCHEMA,"components":[]}) if a.registry else {"schema":REGISTRY_SCHEMA,"components":[]}
    if registry.get("schema")!=REGISTRY_SCHEMA:raise SystemExit("COMPONENT_REGISTRY_SCHEMA_INVALID")
    out=a.output_dir.resolve();out.mkdir(parents=True,exist_ok=True)
    decisions={str(x.get("package_id")):x for x in council.get("decisions") or [] if isinstance(x,dict) and x.get("package_id")}
    branch_wave={}
    for w in waves.get("waves") or []:
        for bid in w.get("branches") or []:branch_wave[str(bid)]=int(w.get("wave") or 0)

    components=[];blocked=[];reused=0;materialized=0
    for package in plan.get("packages") or []:
        if not isinstance(package,dict) or not package.get("id"):continue
        pid=str(package["id"]);decision=decisions.get(pid) or {}
        checks=package_checks(package,decision,True)
        runtime_required=bool(package.get("runtime_required"))
        if runtime_required:
            checks["runtime_wave_assigned"]=str(package.get("branch_id") or "") in branch_wave
        failed=[k for k,v in checks.items() if not v]
        if failed:
            blocked.append({"package_id":pid,"domain":package.get("domain"),"failed_checks":failed})
            continue

        existing=find_reuse(registry,package)
        component_id=str(existing.get("component_id")) if existing else stable_id(package)
        action="REUSE" if existing else "MATERIALIZE_APPROVED_PACKAGE"
        reused+=int(existing is not None);materialized+=int(existing is None)
        cdir=out/"components"/safe(pid);cdir.mkdir(parents=True,exist_ok=True)
        caps=[str(x) for x in (package.get("capabilities") or [])]
        manifest={
          "schema":"chacha.dev/component-manifest/v1","component_id":component_id,
          "component_kind":"DOMAIN_EXECUTION_CAPSULE","package_id":pid,"domain":package.get("domain"),
          "package_kind":package.get("kind"),"state":"QUALIFIED","qualification_scope":"FACTORY_PACKAGE_ONLY",
          "task_execution_required":True,"business_delivery_verified":False,
          "production_authority":False,"durable_promotion":False,
          "agent_id":package.get("agent_id"),"branch_id":package.get("branch_id"),
          "runtime_required":runtime_required,"runtime_wave":branch_wave.get(str(package.get("branch_id") or "")),
          "runtime_architecture":package.get("runtime_architecture"),
          "materialization_profile":package.get("materialization_profile"),
          "resource_budget":package.get("resource_budget") or {},
          "capabilities":caps,"automatic_external_spend_eur":0
        }
        contract={
          "schema":"chacha.dev/component-contract/v1","component_id":component_id,"package_id":pid,
          "domain":package.get("domain"),"capabilities":caps,
          "inputs":["approved-domain-plan","architecture-council-decision","runtime-wave-plan"],
          "outputs":["domain-execution-evidence","task-results","domain-deliverables"],
          "verification":{"guardian_required":True,"sentinel_required":True,"self_certification_allowed":False},
          "authority":{"architecture":False,"production":False,"permission_expansion":False},
          "execution":{"required":True,"branch_id":package.get("branch_id"),"wave":manifest["runtime_wave"]},
          "automatic_external_spend_eur":0
        }
        evidence={
          "schema":"chacha.dev/component-verification-evidence/v1","component_id":component_id,
          "status":"PASS","checks":checks,"blocked_by":decision.get("blocked_by") or [],
          "constraint_policy":decision.get("constraint_policy") or {},
          "qualification_scope":"FACTORY_PACKAGE_ONLY","business_delivery_verified":False,
          "source_digests":{
            "final_plan":digest_file(a.final_plan),"architecture_council":digest_file(a.council),
            "runtime_wave_plan":digest_file(a.wave_plan),"domain_factory_policy":digest_file(a.factory_policy)
          },"automatic_external_spend_eur":0
        }
        compat={
          "schema":"chacha.dev/component-compatibility-metadata/v1","component_id":component_id,
          "platform_revision":(repo/".revision").read_text(encoding="utf-8").strip() if (repo/".revision").is_file() else "UNKNOWN",
          "domain":package.get("domain"),"branch_decision":package.get("branch_decision"),
          "runtime_architecture":package.get("runtime_architecture"),"compatible":True,
          "automatic_external_spend_eur":0
        }
        provenance={
          "schema":"chacha.dev/component-provenance/v1","component_id":component_id,
          "action":action,"sources":[str(a.final_plan),str(a.council),str(a.wave_plan),str(a.factory_policy)],
          "digests":evidence["source_digests"],"generated_by":"domain-factory-runner",
          "automatic_external_spend_eur":0
        }
        fixtures={
          "schema":"chacha.dev/factory-fixtures/v1","component_id":component_id,
          "package_id":pid,"branch_id":package.get("branch_id"),"agent_id":package.get("agent_id"),
          "capabilities":caps,"automatic_external_spend_eur":0
        }
        paths={
          "manifest":cdir/"component-manifest.json","contract":cdir/"component-contract.json",
          "evidence":cdir/"verification-evidence.json","compatibility":cdir/"compatibility-metadata.json",
          "provenance":cdir/"provenance.json","fixtures":cdir/"factory-fixtures.json"
        }
        for key,p in paths.items():save(p,{"manifest":manifest,"contract":contract,"evidence":evidence,"compatibility":compat,"provenance":provenance,"fixtures":fixtures}[key])
        row={
          "component_id":component_id,"component_kind":"DOMAIN_EXECUTION_CAPSULE","package_id":pid,
          "domain":package.get("domain"),"state":"QUALIFIED","quality":1.0,"reuse_score":1.0,
          "capabilities":caps,"compatible":True,"action":action,
          "branch_id":package.get("branch_id"),"agent_id":package.get("agent_id"),
          "runtime_required":runtime_required,"wave":manifest["runtime_wave"],
          "manifest":str(paths["manifest"]),"contract":str(paths["contract"]),"evidence":str(paths["evidence"])
        }
        components.append(row)

    if blocked:
        result={"schema":RESULT_SCHEMA,"status":"BLOCKED","next_stage":"DOMAIN_FACTORY_REPLAN_REQUIRED",
                "blocked":blocked,"component_count":len(components),"automatic_external_spend_eur":0}
        save(out/"domain-factory-result.json",result);print(json.dumps(result,indent=2,ensure_ascii=False));return 2

    new_registry={"schema":REGISTRY_SCHEMA,"components":components,"scope":"PROJECT_LOCAL",
                  "durable_promotion":False,"automatic_external_spend_eur":0}
    save(out/"component-registry.json",new_registry)
    component_by_branch={str(x.get("branch_id")):x for x in components if x.get("branch_id")}
    execution_waves=[]
    for w in waves.get("waves") or []:
        items=[]
        for bid in w.get("branches") or []:
            comp=component_by_branch.get(str(bid))
            if not comp:raise SystemExit("RUNTIME_BRANCH_COMPONENT_MISSING:"+str(bid))
            items.append({"branch_id":bid,"component_id":comp["component_id"],"package_id":comp["package_id"],"domain":comp["domain"],"agent_id":comp["agent_id"]})
        execution_waves.append({"wave":w.get("wave"),"components":items,
                                "memory_mb":w.get("memory_mb"),"disk_mb":w.get("disk_mb"),
                                "cpu_weight":w.get("cpu_weight"),"processes":w.get("processes")})
    virtual=[{"component_id":x["component_id"],"package_id":x["package_id"],"domain":x["domain"],"agent_id":x["agent_id"]}
             for x in components if not x.get("runtime_required")]
    execution={
      "schema":EXEC_SCHEMA,"status":"READY","project_id":plan.get("project_id") or council.get("project_id"),
      "waves":execution_waves,"virtual_components":virtual,"wave_count":len(execution_waves),
      "component_count":len(components),"execution_required":True,
      "production_authority":False,"automatic_external_spend_eur":0
    }
    save(out/"domain-execution-manifest.json",execution)
    catalog={"schema":"chacha.dev/component-catalog/v1","components":components,
             "qualified_count":len(components),"scope":"PROJECT_LOCAL","automatic_external_spend_eur":0}
    save(out/"component-catalog.json",catalog)
    result={
      "schema":RESULT_SCHEMA,"status":"PASS","next_stage":"DOMAIN_EXECUTION",
      "component_count":len(components),"materialized_count":materialized,"reused_count":reused,
      "blocked":[],"registry":str(out/"component-registry.json"),
      "catalog":str(out/"component-catalog.json"),"execution_manifest":str(out/"domain-execution-manifest.json"),
      "required_outputs":policy.get("required_outputs") or [],
      "factory_cycle":policy.get("factory_cycle") or [],
      "automatic_external_spend_eur":0
    }
    save(out/"domain-factory-result.json",result)
    print(json.dumps(result,indent=2,ensure_ascii=False))
    print("CHACHA_DEV_V817_DOMAIN_FACTORIES=PASS")
    print("CHACHA_DEV_V817_COMPONENTS="+str(len(components)))
    print("CHACHA_DEV_V817_MATERIALIZED="+str(materialized))
    print("CHACHA_DEV_V817_REUSED="+str(reused))
    print("CHACHA_DEV_V817_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
    return 0

if __name__=="__main__":raise SystemExit(main())
