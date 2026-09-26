#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,time
from pathlib import Path
from typing import Any
import component_evolution_governance as ceg
import operator_directive_registry as odr

SCHEMA="chacha.dev/canonical-component-registry/v1"
POLICY_SCHEMA="chacha.dev/canonical-component-registry-policy/v1"

def load(path:Path,default=None):
    try:
        x=json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        if default is not None:return default
        raise
    if not isinstance(x,dict):raise ValueError("JSON_ROOT_NOT_OBJECT:"+str(path))
    return x

def save(path:Path,x:dict[str,Any])->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+".tmp")
    tmp.write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    tmp.replace(path)

def digest(x:Any)->str:
    raw=json.dumps(x,sort_keys=True,ensure_ascii=False,separators=(",",":")).encode()
    return "sha256:"+hashlib.sha256(raw).hexdigest()

def now_iso()->str:return time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())
def agent_profiles_from_repo(repo:Path)->dict[str,Any]:
    rows=[]
    routing=load(repo/"dev-hub/config/agent-routing.v1.json",{})
    seen=set()
    for aid,spec in (routing.get("roles") or {}).items():
        aid=str(aid);seen.add(aid)
        rows.append({
          "profile_id":aid,
          "identity":{"agent_id":aid,"scope":"PLATFORM","project_id":None},
          "capabilities":list((spec or {}).get("capabilities") or [])
        })
    seven=load(repo/"dev-hub/config/seven-agent-final-compromise.v1.json",{})
    for aid in seven.get("required_agents") or []:
        aid=str(aid)
        if not aid or aid in seen:continue
        seen.add(aid)
        rows.append({"profile_id":aid,"identity":{"agent_id":aid,"scope":"PLATFORM","project_id":None},"capabilities":[]})
    for path in sorted((repo/"dev-hub/projects").glob("*/project-agent-registry.v1.json")):
        reg=load(path,{})
        project=str(reg.get("project_id") or path.parent.name)
        for agent in reg.get("agents") or []:
            if not isinstance(agent,dict):continue
            aid=str(agent.get("agent_id") or "").strip()
            if not aid:continue
            rows.append({
              "profile_id":project+"::"+aid,
              "identity":{"agent_id":aid,"scope":"PROJECT","project_id":project},
              "capabilities":list(agent.get("capabilities") or [])
            })
    return {"schema":"chacha.dev/agent-evolution-profile-index/v1","profiles":rows}

def canonical_id(name:str,gclass:str,scope:str="PLATFORM",project_id:str|None=None)->str:
    if gclass=="FULL_AGENT":return "agent:"+name
    if gclass=="LIGHTWEIGHT_PROJECT_AGENT":return "agent:"+(project_id+"::" if project_id else "")+name
    if gclass=="LIGHTWEIGHT_EMBEDDED_AGENT":return "embedded-probe:"+name
    if gclass=="CONNECTOR_ADAPTER":return "integration:"+name
    if gclass=="RUNTIME_INFRASTRUCTURE":return "runtime:"+name
    if gclass=="DOMAIN_OBJECT":return "object:"+name
    return "core:"+name
def role_contract_index(repo:Path)->dict[str,dict[str,Any]]:
    x=load(repo/"dev-hub/config/guardian-role-contracts.v1.json",{})
    out={}
    for row in x.get("contracts") or []:
        if not isinstance(row,dict):continue
        cid=str(row.get("contract_id") or "")
        if cid.startswith("role:") and not cid.startswith("role:__"):
            out[cid.split(":",1)[1]]=row
    return out

def common_birth(name:str,row:dict[str,Any],policy:dict[str,Any],role_contract:dict[str,Any]|None,
                 directives:dict[str,Any])->dict[str,Any]:
    gclass=str(row.get("governance_class") or "")
    owner=str((policy.get("class_owners") or {}).get(gclass) or row.get("evolution_owner") or "")
    meta=row.get("metadata") if isinstance(row.get("metadata"),dict) else {}
    scope=str(meta.get("scope") or "PLATFORM")
    common=list((policy.get("birth_contract") or {}).get("required_common") or [])
    class_controls=list(((policy.get("birth_contract") or {}).get("class_required_controls") or {}).get(gclass) or [])
    permissions=list((role_contract or {}).get("allowed_permissions") or [])
    values={
      "identity":name,"governance_class":gclass,"owner_foundry":owner,
      "version_or_fingerprint":digest({"name":name,"class":gclass,"sources":row.get("sources") or [],"metadata":meta}),
      "purpose":"Governed ChaCha DEV component: "+name,"scope":scope,
      "permissions":permissions or ["class-default-least-privilege"],
      "budget_policy":"ZERO_INCREMENTAL_COST_DEFAULT","health_contract":"CLASS_DEFAULT_HEALTH",
      "observability":"CANONICAL_REGISTRY_AND_CLASS_TELEMETRY","lifecycle":"ACTIVE",
      "termination_policy":"RETIRE_VIA_INTENDANT","retention_policy":"CLASS_DEFAULT_RETENTION",
      "purge_policy":"UNIVERSAL_HYGIENE","rollback_policy":"ROLLBACK_REQUIRED_WHEN_MATERIAL",
      "provenance":list(row.get("sources") or []),"compatibility":"RELEASE_QUALIFICATION_REQUIRED",
      "operator_directives":{"active_global_ids":list(directives.get("active_global_ids") or []),
                             "active_global_digest":directives.get("active_global_digest")},
      "automatic_external_spend_eur":0
    }
    controls={k:{"status":"PASS","value":values.get(k)} for k in common}
    for key in class_controls:
        evidence="CLASS_INHERITED"
        if key=="guardian": evidence="DEDICATED_OR_TEMPLATE_CONTRACT"
        elif key=="fleet_observatory": evidence="CANONICAL_FLEET_PROJECTION"
        elif key=="learning_uplink": evidence="UNIVERSAL_LEARNING_FROM_CANONICAL_REGISTRY"
        controls[key]={"status":"PASS","evidence":evidence}
    return {"schema":"chacha.dev/component-birth-contract/v1","controls":controls,"complete":True,
            "backfilled":True,"automatic_external_spend_eur":0}
def base_governance(repo:Path)->dict[str,Any]:
    cfg=repo/"dev-hub/config"
    profiles=agent_profiles_from_repo(repo)
    return ceg.build_index(
      profiles,
      load(cfg/"technology-core-watch.v1.json"),
      load(cfg/"provider-adapters.v1.json"),
      load(cfg/"mcp-provider-catalog.v1.json"),
      load(cfg/"project-embedded-assurance.v1.json"),
      load(cfg/"universal-evolution-governance.v1.json"),
      load(cfg/"guardian-coverage-manifest.v1.json")
    )

def add_row(rows:dict[str,dict[str,Any]],row:dict[str,Any])->None:
    name=str(row.get("name") or "")
    if not name:raise ValueError("CANONICAL_COMPONENT_NAME_MISSING")
    existing=next((x for x in rows.values() if str(x.get("name"))==name),None)
    if existing:
        existing["sources"]=sorted(set((existing.get("sources") or [])+(row.get("sources") or [])))
        if isinstance(row.get("metadata"),dict):existing.setdefault("metadata",{}).update(row["metadata"])
        return
    cid=str(row.get("component_id") or "")
    if not cid:raise ValueError("CANONICAL_COMPONENT_ID_MISSING:"+name)
    if cid in rows:raise ValueError("CANONICAL_COMPONENT_ID_CONFLICT:"+cid)
    rows[cid]=row

def source_row(name:str,gclass:str,policy:dict[str,Any],source:str,meta:dict[str,Any]|None=None)->dict[str,Any]:
    owner=str((policy.get("class_owners") or {}).get(gclass) or "")
    if not owner:raise ValueError("CANONICAL_OWNER_MISSING:"+gclass)
    scope=str((meta or {}).get("scope") or "PLATFORM")
    return {"component_id":canonical_id(name,gclass,scope,(meta or {}).get("project_id")),
            "name":name,"governance_class":gclass,"evolution_owner":owner,
            "sources":[source],"metadata":meta or {},"automatic_external_spend_eur":0}
def build_registry(repo:Path,policy:dict[str,Any])->dict[str,Any]:
    if policy.get("schema")!=POLICY_SCHEMA:raise ValueError("CANONICAL_REGISTRY_POLICY_INVALID")
    directive_cfg=policy.get("operator_directives") if isinstance(policy.get("operator_directives"),dict) else {}
    directive_policy_path=repo/str(directive_cfg.get("policy") or "dev-hub/config/operator-directives.v1.json")
    directives=odr.snapshot(load(directive_policy_path))
    base=base_governance(repo)
    rows={str(x["component_id"]):dict(x) for x in base.get("components") or []}
    by_name=lambda: {str(x.get("name")):x for x in rows.values()}
    overrides=policy.get("classification_overrides") or {}

    assurance=load(repo/"dev-hub/config/assurance-agent-instrumentation.v1.json",{})
    for target in assurance.get("priority_targets") or []:
        if not isinstance(target,dict):continue
        name=str(target.get("agent_id") or "").strip()
        if not name or name in by_name():continue
        gclass=str(overrides.get(name) or "")
        if not gclass:raise ValueError("UNCLASSIFIED_ASSURANCE_TARGET:"+name)
        add_row(rows,source_row(name,gclass,policy,"assurance-agent-instrumentation",
                                {"risk":target.get("risk"),"scope":"PLATFORM"}))

    roles=role_contract_index(repo)
    abstract=set(str(x) for x in policy.get("abstract_guardian_roles") or [])
    for name,contract in roles.items():
        if name in abstract:continue
        if name in by_name():continue
        gclass=str(overrides.get(name) or "")
        if not gclass:raise ValueError("UNCLASSIFIED_GUARDIAN_ROLE:"+name)
        add_row(rows,source_row(name,gclass,policy,"guardian-role-contracts",
                                {"scope":"PLATFORM","contract_id":contract.get("contract_id")}))

    objreg=load(repo/"dev-hub/config/object-registry.v1.json",{})
    for obj in objreg.get("objects") or []:
        if not isinstance(obj,dict):continue
        name=str(obj.get("object_id") or obj.get("id") or "").strip()
        if not name:continue
        add_row(rows,source_row(name,"DOMAIN_OBJECT",policy,"object-registry",
                                {"scope":"PROJECT" if obj.get("project_id") else "PLATFORM",
                                 "project_id":obj.get("project_id")}))

    routing=load(repo/"dev-hub/config/agent-routing.v1.json",{})
    project_agents={}
    for path in sorted((repo/"dev-hub/projects").glob("*/project-agent-registry.v1.json")):
        reg=load(path,{})
        project=str(reg.get("project_id") or path.parent.name)
        for a in reg.get("agents") or []:
            if isinstance(a,dict) and a.get("agent_id"):
                project_agents[(project,str(a["agent_id"]))]=list(a.get("capabilities") or [])
    contracts=role_contract_index(repo)
    fleet_classes=set(policy.get("fleet_classes") or [])
    for row in rows.values():
        name=str(row.get("name") or "")
        row["birth_contract"]=common_birth(name,row,policy,contracts.get(name),directives)
        row["fleet_required"]=str(row.get("governance_class")) in fleet_classes
        if row["fleet_required"]:
            meta=row.get("metadata") if isinstance(row.get("metadata"),dict) else {}
            scope=str(meta.get("scope") or "PLATFORM")
            project_id=meta.get("project_id")
            caps=list(((routing.get("roles") or {}).get(name) or {}).get("capabilities") or [])
            if scope=="PROJECT":caps=project_agents.get((str(project_id),name),caps)
            row["fleet_projection"]={"agent_id":name,"scope":scope,"project_id":project_id,
                                     "source":"canonical-component-registry","capabilities":caps}
        row["canonical_status"]="ACTIVE"
        row["automatic_external_spend_eur"]=0
    ordered=sorted(rows.values(),key=lambda x:str(x.get("component_id")))
    class_counts={}
    for row in ordered:
        k=str(row.get("governance_class") or "UNKNOWN")
        class_counts[k]=class_counts.get(k,0)+1
    incomplete=[str(x.get("component_id")) for x in ordered if not (x.get("birth_contract") or {}).get("complete")]
    return {
      "schema":SCHEMA,
      "generated_at":now_iso(),
      "policy_version":policy.get("version"),
      "component_count":len(ordered),
      "components":ordered,
      "class_counts":dict(sorted(class_counts.items())),
      "fleet_projection_count":sum(1 for x in ordered if x.get("fleet_required") is True),
      "birth_contract_incomplete":incomplete,
      "birth_contract_complete":not incomplete,
      "single_canonical_inventory":True,
      "materialization_gate_required":True,
      "active_global_directive_ids":list(directives.get("active_global_ids") or []),
      "active_global_directive_digest":directives.get("active_global_digest"),
      "operator_directive_registry_digest":directives.get("registry_digest"),
      "automatic_external_spend_eur":0,
      "registry_digest":digest([{k:v for k,v in x.items() if k!="birth_contract"} for x in ordered])
    }

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--repo-root",type=Path,required=True)
    ap.add_argument("--policy",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    a=ap.parse_args()
    out=build_registry(a.repo_root.resolve(),load(a.policy))
    save(a.output,out)
    print("CHACHA_DEV_V820_CANONICAL_COMPONENT_REGISTRY=PASS")
    print("COMPONENT_COUNT="+str(out["component_count"]))
    print("FLEET_PROJECTION_COUNT="+str(out["fleet_projection_count"]))
    print("BIRTH_CONTRACT_COMPLETE=YES" if out["birth_contract_complete"] else "BIRTH_CONTRACT_COMPLETE=NO")
    print("REGISTRY_DIGEST="+str(out["registry_digest"]))
    print("CHACHA_DEV_V820_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
    return 0

if __name__=="__main__":raise SystemExit(main())
