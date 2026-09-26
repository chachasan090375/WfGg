#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,os,time
from pathlib import Path
from typing import Any
import operator_directive_registry as odr

POLICY_SCHEMA="chacha.dev/canonical-component-registry-policy/v1"
DYNAMIC_SCHEMA="chacha.dev/dynamic-component-registry/v1"
RECEIPT_SCHEMA="chacha.dev/universal-materialization-gate-receipt/v1"
DEFAULT_OPERATOR_DIRECTIVES=Path(__file__).resolve().parents[1]/"config/operator-directives.v1.json"

def load(path:Path,default=None):
    try:x=json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        if default is not None:return default
        raise
    if not isinstance(x,dict):raise ValueError("JSON_ROOT_NOT_OBJECT:"+str(path))
    return x

def save(path:Path,x:dict[str,Any])->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+".tmp")
    tmp.write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    os.replace(tmp,path)

def digest(x:Any)->str:
    raw=json.dumps(x,sort_keys=True,ensure_ascii=False,separators=(",",":")).encode()
    return "sha256:"+hashlib.sha256(raw).hexdigest()

def now_iso()->str:return time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())
def materialization_view(manifest:dict[str,Any])->dict[str,Any]:
    nested=manifest.get("universal_materialization") if isinstance(manifest.get("universal_materialization"),dict) else {}
    birth=manifest.get("birth_contract") if isinstance(manifest.get("birth_contract"),dict) else nested.get("birth_contract") if isinstance(nested.get("birth_contract"),dict) else {}
    name=str(manifest.get("agent_id") or manifest.get("object_id") or manifest.get("branch_id") or manifest.get("capability") or manifest.get("component_id") or "").strip()
    gclass=str(manifest.get("governance_class") or nested.get("governance_class") or "").strip()
    owner=str(manifest.get("owner_foundry") or nested.get("owner_foundry") or birth.get("owner_foundry") or "").strip()
    required=bool(manifest.get("materialization_gate_required") is True or nested.get("materialization_gate_required") is True or nested.get("required") is True)
    return {"name":name,"governance_class":gclass,"owner_foundry":owner,"required":required,"birth_contract":birth,"nested":nested}

def component_id(name:str,gclass:str,manifest:dict[str,Any])->str:
    if gclass=="FULL_AGENT":return "agent:"+name
    if gclass=="LIGHTWEIGHT_PROJECT_AGENT":
        project=str(manifest.get("project_id") or "")
        return "agent:"+(project+"::" if project else "")+name
    if gclass=="LIGHTWEIGHT_EMBEDDED_AGENT":return "embedded-probe:"+name
    if gclass=="CONNECTOR_ADAPTER":return "integration:"+name
    if gclass=="RUNTIME_INFRASTRUCTURE":return "runtime:"+name
    if gclass=="DOMAIN_OBJECT":return "object:"+name
    if gclass=="OWNED_ARTIFACT":return "artifact:"+name
    return "core:"+name

def inherited_value(key:str,view:dict[str,Any],manifest:dict[str,Any],directives:dict[str,Any])->Any:
    defaults={
      "identity":view["name"],"governance_class":view["governance_class"],"owner_foundry":view["owner_foundry"],
      "version_or_fingerprint":digest(manifest),"purpose":manifest.get("purpose") or "Materialized ChaCha DEV component: "+view["name"],
      "scope":manifest.get("scope") or ("PROJECT" if manifest.get("project_id") else "PLATFORM"),
      "permissions":manifest.get("permissions") or "CLASS_DEFAULT_LEAST_PRIVILEGE",
      "budget_policy":manifest.get("budget_policy") or "ZERO_INCREMENTAL_COST_DEFAULT",
      "health_contract":manifest.get("health_contract") or "CLASS_DEFAULT_HEALTH",
      "observability":manifest.get("observability") or "CANONICAL_REGISTRY_AND_CLASS_TELEMETRY",
      "lifecycle":manifest.get("lifecycle") or "MATERIALIZING",
      "termination_policy":manifest.get("termination_policy") or "RETIRE_VIA_INTENDANT",
      "retention_policy":manifest.get("retention_policy") or view["nested"].get("retention_policy") or "CLASS_DEFAULT_RETENTION",
      "purge_policy":manifest.get("purge_policy") or view["nested"].get("purge_policy") or "UNIVERSAL_HYGIENE",
      "rollback_policy":manifest.get("rollback_policy") or "ROLLBACK_REQUIRED_WHEN_MATERIAL",
      "provenance":{"manifest_digest":digest(manifest),"owner_foundry":view["owner_foundry"]},
      "compatibility":manifest.get("compatibility") or "RELEASE_QUALIFICATION_REQUIRED",
      "operator_directives":{"active_global_ids":list(directives.get("active_global_ids") or []),
                             "active_global_digest":directives.get("active_global_digest")},
      "automatic_external_spend_eur":0
    }
    return defaults.get(key)
def complete_birth_contract(view:dict[str,Any],manifest:dict[str,Any],policy:dict[str,Any],directives:dict[str,Any])->dict[str,Any]:
    common=list((policy.get("birth_contract") or {}).get("required_common") or [])
    class_controls=list(((policy.get("birth_contract") or {}).get("class_required_controls") or {}).get(view["governance_class"]) or [])
    controls={}
    for key in common:
        value=inherited_value(key,view,manifest,directives)
        if value in (None,"",[],{}):raise ValueError("BIRTH_CONTROL_VALUE_MISSING:"+key)
        controls[key]={"status":"PASS","value":value,"source":"manifest-or-class-default"}
    for key in class_controls:
        controls[key]={"status":"PASS","evidence":"CLASS_POLICY_INHERITED_AT_GATE"}
    return {"schema":"chacha.dev/component-birth-contract/v1","status":"REGISTERED_PENDING_ACTIVATION",
            "controls":controls,"complete":True,"backfilled":False,
            "automatic_external_spend_eur":0}

def validate(view:dict[str,Any],manifest:dict[str,Any],policy:dict[str,Any],directives:dict[str,Any])->dict[str,Any]:
    if policy.get("schema")!=POLICY_SCHEMA:raise ValueError("MATERIALIZATION_POLICY_INVALID")
    if not view["required"]:
        return {"required":False,"status":"NO_REGISTRATION_REQUIRED"}
    if not view["name"]:raise ValueError("MATERIALIZATION_NAME_REQUIRED")
    gclass=view["governance_class"]
    classes=set((policy.get("class_owners") or {}).keys())
    if gclass not in classes:raise ValueError("MATERIALIZATION_CLASS_INVALID:"+gclass)
    owner=view["owner_foundry"]
    expected=str((policy.get("class_owners") or {}).get(gclass) or "")
    if not owner:raise ValueError("MATERIALIZATION_OWNER_REQUIRED")
    if expected!="INHERIT_OWNER" and owner!=expected:
        raise ValueError("MATERIALIZATION_OWNER_MISMATCH:"+owner+":"+expected)
    if float(manifest.get("automatic_external_spend_eur",0) or 0)!=0:
        raise ValueError("MATERIALIZATION_EXTERNAL_SPEND_NONZERO")
    birth=complete_birth_contract(view,manifest,policy,directives)
    return {"required":True,"status":"PASS","birth_contract":birth}

def register(manifest:dict[str,Any],policy:dict[str,Any],dynamic_path:Path,directives:dict[str,Any])->dict[str,Any]:
    view=materialization_view(manifest);verdict=validate(view,manifest,policy,directives)
    if verdict.get("required") is not True:
        return {"schema":RECEIPT_SCHEMA,"status":"PASS_NO_REGISTRATION_REQUIRED","registered":False,
                "automatic_external_spend_eur":0}
    cid=component_id(view["name"],view["governance_class"],manifest)
    state=load(dynamic_path,{"schema":DYNAMIC_SCHEMA,"registrations":[],"history":[]})
    if state.get("schema")!=DYNAMIC_SCHEMA:raise ValueError("DYNAMIC_REGISTRY_SCHEMA_INVALID")
    regs=list(state.get("registrations") or [])
    prior=next((x for x in regs if x.get("component_id")==cid),None)
    if prior and (prior.get("governance_class")!=view["governance_class"] or prior.get("owner_foundry")!=view["owner_foundry"]):
        raise ValueError("DYNAMIC_REGISTRY_IDENTITY_CONFLICT:"+cid)
    row={"component_id":cid,"name":view["name"],"governance_class":view["governance_class"],
         "owner_foundry":view["owner_foundry"],"status":"REGISTERED_PENDING_ACTIVATION",
         "manifest_digest":digest(manifest),"birth_contract":verdict["birth_contract"],
         "registered_at":now_iso(),"automatic_external_spend_eur":0}
    regs=[x for x in regs if x.get("component_id")!=cid]+[row]
    state["registrations"]=sorted(regs,key=lambda x:str(x.get("component_id")))
    state.setdefault("history",[]).append({"event":"REGISTERED","component_id":cid,"at":now_iso(),"manifest_digest":row["manifest_digest"]})
    save(dynamic_path,state)
    return {"schema":RECEIPT_SCHEMA,"status":"PASS","registered":True,"component_id":cid,
            "birth_contract_complete":True,"dynamic_registry":str(dynamic_path),
            "automatic_external_spend_eur":0}
def transition(dynamic_path:Path,cid:str,state_name:str)->dict[str,Any]:
    state=load(dynamic_path,{"schema":DYNAMIC_SCHEMA,"registrations":[],"history":[]})
    regs=list(state.get("registrations") or [])
    row=next((x for x in regs if x.get("component_id")==cid),None)
    if not row:raise ValueError("DYNAMIC_COMPONENT_NOT_REGISTERED:"+cid)
    allowed={"ACTIVE":{"REGISTERED_PENDING_ACTIVATION"},"RETIRED":{"ACTIVE","REGISTERED_PENDING_ACTIVATION"}}
    current=str(row.get("status") or "")
    if current not in allowed.get(state_name,set()) and current!=state_name:
        raise ValueError("DYNAMIC_COMPONENT_INVALID_TRANSITION:"+current+":"+state_name)
    row["status"]=state_name
    row[state_name.casefold()+"_at"]=now_iso()
    state.setdefault("history",[]).append({"event":state_name,"component_id":cid,"at":now_iso()})
    save(dynamic_path,state)
    return {"schema":RECEIPT_SCHEMA,"status":"PASS","component_id":cid,"component_state":state_name,
            "automatic_external_spend_eur":0}

def check_only(manifest:dict[str,Any],policy:dict[str,Any],directives:dict[str,Any])->dict[str,Any]:
    view=materialization_view(manifest);verdict=validate(view,manifest,policy,directives)
    return {"schema":RECEIPT_SCHEMA,"status":"PASS","registered":False,"check_only":True,
            "component_id":component_id(view["name"],view["governance_class"],manifest) if verdict.get("required") else None,
            "birth_contract_complete":bool((verdict.get("birth_contract") or {}).get("complete")) if verdict.get("required") else True,
            "automatic_external_spend_eur":0}

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--mode",choices=["check","register","activate","retire"],default="register")
    ap.add_argument("--manifest",type=Path)
    ap.add_argument("--component-id")
    ap.add_argument("--policy",type=Path,required=True)
    ap.add_argument("--operator-directives",type=Path,default=DEFAULT_OPERATOR_DIRECTIVES)
    ap.add_argument("--dynamic-registry",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    a=ap.parse_args();policy=load(a.policy);directives=odr.snapshot(load(a.operator_directives))
    if a.mode in {"check","register"}:
        if not a.manifest:raise SystemExit("MANIFEST_REQUIRED")
        receipt=check_only(load(a.manifest),policy,directives) if a.mode=="check" else register(load(a.manifest),policy,a.dynamic_registry,directives)
    else:
        if not a.component_id:raise SystemExit("COMPONENT_ID_REQUIRED")
        receipt=transition(a.dynamic_registry,a.component_id,"ACTIVE" if a.mode=="activate" else "RETIRED")
    save(a.output,receipt)
    print("CHACHA_DEV_V820_UNIVERSAL_MATERIALIZATION_GATE=PASS")
    print("MODE="+a.mode.upper())
    if receipt.get("component_id"):print("COMPONENT_ID="+str(receipt["component_id"]))
    print("CHACHA_DEV_V820_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
    return 0

if __name__=="__main__":raise SystemExit(main())
