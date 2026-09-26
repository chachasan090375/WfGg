#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,os,time
from pathlib import Path
from typing import Any
import operator_directive_registry as odr
import directive_impact_analyzer as dia
import version_coupling_audit as vca

SCHEMA="chacha.dev/component-registry-reconciliation/v1"

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

def issue(code:str,severity:str,subject:str,action:str,details:dict[str,Any]|None=None)->dict[str,Any]:
    return {"code":code,"severity":severity,"subject":subject,"recommended_action":action,
            "details":details or {},"automatic_external_spend_eur":0}

def names(registry:dict[str,Any])->dict[str,dict[str,Any]]:
    return {str(x.get("name")):x for x in registry.get("components") or [] if isinstance(x,dict) and x.get("name")}
def fleet_issues(registry:dict[str,Any],fleet:dict[str,Any])->list[dict[str,Any]]:
    out=[]
    expected={str(x.get("name")) for x in registry.get("components") or [] if isinstance(x,dict) and x.get("fleet_required") is True}
    actual={str(x.get("agent_id")) for x in fleet.get("agents") or [] if isinstance(x,dict) and x.get("agent_id")}
    for aid in sorted(expected-actual):
        out.append(issue("FLEET_MISSING","HIGH",aid,"BACKFILL_FLEET_FROM_CANONICAL_REGISTRY"))
    for aid in sorted(actual-expected):
        out.append(issue("FLEET_NONCANONICAL","HIGH",aid,"CLASSIFY_OR_RETIRE_AGENT"))
    return out

def assurance_issues(repo:Path,registry:dict[str,Any])->list[dict[str,Any]]:
    out=[];known=set(names(registry))
    x=load(repo/"dev-hub/config/assurance-agent-instrumentation.v1.json",{})
    for row in x.get("priority_targets") or []:
        aid=str((row or {}).get("agent_id") or "")
        if aid and aid not in known:
            out.append(issue("ASSURANCE_TARGET_UNREGISTERED","CRITICAL",aid,"BACKFILL_CANONICAL_REGISTRY"))
    return out

def guardian_role_issues(repo:Path,registry:dict[str,Any],policy:dict[str,Any])->list[dict[str,Any]]:
    out=[];known=set(names(registry));abstract=set(str(x) for x in policy.get("abstract_guardian_roles") or [])
    x=load(repo/"dev-hub/config/guardian-role-contracts.v1.json",{})
    for row in x.get("contracts") or []:
        cid=str((row or {}).get("contract_id") or "")
        if not cid.startswith("role:") or cid.startswith("role:__"):continue
        name=cid.split(":",1)[1]
        if name in abstract:continue
        if name not in known:
            out.append(issue("GUARDIAN_ROLE_UNREGISTERED","CRITICAL",name,"BACKFILL_CANONICAL_REGISTRY"))
    return out
def release_issues(platform_root:Path,policy:dict[str,Any])->list[dict[str,Any]]:
    out=[]
    releases=platform_root/"releases"
    rows=sorted([p for p in releases.iterdir() if p.is_dir()],key=lambda p:p.stat().st_mtime,reverse=True) if releases.is_dir() else []
    maximum=int(((policy.get("hygiene") or {}).get("release_physical_maximum") or 3))
    active=(platform_root/"current").resolve() if (platform_root/"current").exists() else None
    if len(rows)>maximum:
        retire=[str(p) for p in rows if active is None or p.resolve()!=active][max(0,maximum-1):]
        out.append(issue("RELEASE_OVERAGE","HIGH",str(releases),"RETIRE_SUPERSEDED_RELEASES",
                         {"count":len(rows),"maximum":maximum,"candidate_retirements":retire}))
    if active and active.is_dir():
        prep=load(active/".release-preparation.json",{})
        declared=str(prep.get("activation_status") or "")
        if declared and declared not in {"ACTIVE","ACTIVATED"}:
            out.append(issue("ACTIVE_RELEASE_METADATA_DRIFT","MEDIUM",str(active),"RECONCILE_RUNTIME_RELEASE_STATE",
                             {"declared_activation_status":declared,"actual_current_target":str(active)}))
    return out

def birth_contract_issues(registry:dict[str,Any])->list[dict[str,Any]]:
    out=[]
    for row in registry.get("components") or []:
        if not isinstance(row,dict):continue
        contract=row.get("birth_contract") if isinstance(row.get("birth_contract"),dict) else {}
        if contract.get("complete") is not True:
            out.append(issue("BIRTH_CONTRACT_INCOMPLETE","CRITICAL",str(row.get("component_id")),
                             "BACKFILL_OR_RETIRE_COMPONENT"))
        controls=contract.get("controls") if isinstance(contract.get("controls"),dict) else {}
        failed=[k for k,v in controls.items() if not isinstance(v,dict) or v.get("status")!="PASS"]
        if failed:
            out.append(issue("BIRTH_CONTROL_INCOMPLETE","CRITICAL",str(row.get("component_id")),
                             "BACKFILL_OR_RETIRE_COMPONENT",{"controls":failed}))
    return out
def materializer_issues(repo:Path)->list[dict[str,Any]]:
    out=[]
    checks=[
      ("agent-foundry",repo/"dev-hub/config/agent-foundry.v1.json","principles"),
      ("branch-foundry",repo/"dev-hub/config/branch-foundry.v1.json","principles"),
      ("capability-foundry",repo/"dev-hub/config/capability-foundry.v1.json","rules"),
      ("object-factory",repo/"dev-hub/config/object-factory.v1.json","principles")
    ]
    required={
      "canonical_component_registry_required":True,
      "universal_materialization_gate_required":True,
      "birth_contract_required":True,
      "retention_and_purge_contract_required":True
    }
    for name,path,section in checks:
        x=load(path,{})
        cfg=x.get(section) if isinstance(x.get(section),dict) else {}
        missing=[k for k,v in required.items() if cfg.get(k) is not v]
        if missing:
            out.append(issue("MATERIALIZER_DEFAULT_GAP","CRITICAL",name,"UPDATE_FOUNDRY_DEFAULTS",
                             {"missing_defaults":missing,"config":str(path)}))
    return out

def learning_issues(repo:Path)->list[dict[str,Any]]:
    x=load(repo/"dev-hub/config/universal-learning.v1.json",{})
    if x.get("canonical_registry_discovery") is True:return []
    return [issue("LEARNING_DISCOVERY_NOT_CANONICAL","HIGH","universal-learning",
                  "ENABLE_CANONICAL_REGISTRY_DISCOVERY")]

def directive_issues(repo:Path,registry:dict[str,Any],policy:dict[str,Any])->list[dict[str,Any]]:
    out=[]
    cfg=policy.get("operator_directives") if isinstance(policy.get("operator_directives"),dict) else {}
    directive_policy=repo/str(cfg.get("policy") or "dev-hub/config/operator-directives.v1.json")
    directives=odr.snapshot(load(directive_policy))
    expected=str(directives.get("active_global_digest") or "")
    if registry.get("active_global_directive_digest")!=expected:
        out.append(issue("DIRECTIVE_PROPAGATION_DRIFT","CRITICAL","canonical-component-registry",
                         "REBUILD_CANONICAL_REGISTRY_FROM_ACTIVE_DIRECTIVES"))
    expected_ids=sorted(str(x) for x in directives.get("active_global_ids") or [])
    for row in registry.get("components") or []:
        controls=((row.get("birth_contract") or {}).get("controls") or {})
        value=((controls.get("operator_directives") or {}).get("value") or {})
        if value.get("active_global_digest")!=expected or sorted(str(x) for x in value.get("active_global_ids") or [])!=expected_ids:
            out.append(issue("DIRECTIVE_PROPAGATION_DRIFT","CRITICAL",str(row.get("component_id")),
                             "BACKFILL_COMPONENT_DIRECTIVES"))
    catalog=load(repo/"dev-hub/config/operator-directive-sinks.v1.json",{})
    impact=dia.analyze(repo,directives,catalog)
    for miss in impact.get("missing_targets") or []:
        out.append(issue("DIRECTIVE_SINK_MISSING","CRITICAL",str(miss.get("sink")),
                         "RESTORE_DIRECTIVE_PROPAGATION_SINK",miss))
    return out

def version_coupling_issues(repo:Path)->list[dict[str,Any]]:
    report=vca.audit(repo/"dev-hub")
    return [issue("VERSION_COUPLED_ACTIVE_LOGIC","CRITICAL",str(r.get("path")),
                  "REPLACE_PLATFORM_MAJOR_BRANCH_WITH_CAPABILITY_OR_CONTRACT",r) for r in report.get("blocking") or []]
def reconcile(repo:Path,registry:dict[str,Any],policy:dict[str,Any],fleet:dict[str,Any]|None,
              platform_root:Path)->dict[str,Any]:
    issues=[]
    issues.extend(birth_contract_issues(registry))
    if fleet is not None:issues.extend(fleet_issues(registry,fleet))
    issues.extend(assurance_issues(repo,registry))
    issues.extend(guardian_role_issues(repo,registry,policy))
    issues.extend(materializer_issues(repo))
    issues.extend(learning_issues(repo))
    issues.extend(directive_issues(repo,registry,policy))
    issues.extend(version_coupling_issues(repo))
    issues.extend(release_issues(platform_root,policy))
    blocking=[x for x in issues if x.get("severity") in {"CRITICAL","HIGH"}]
    return {
      "schema":SCHEMA,"generated_at":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),
      "registry_digest":registry.get("registry_digest"),"component_count":registry.get("component_count"),
      "issue_count":len(issues),"blocking_issue_count":len(blocking),"issues":issues,
      "status":"PASS" if not blocking else "BLOCKED",
      "promotion_allowed":not blocking,
      "automatic_external_spend_eur":0
    }

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--repo-root",type=Path,required=True)
    ap.add_argument("--registry",type=Path,required=True)
    ap.add_argument("--policy",type=Path,required=True)
    ap.add_argument("--fleet",type=Path)
    ap.add_argument("--platform-root",type=Path,default=Path("/opt/chacha-dev/platform"))
    ap.add_argument("--output",type=Path,required=True)
    ap.add_argument("--strict",action="store_true")
    a=ap.parse_args()
    fleet=load(a.fleet) if a.fleet and a.fleet.is_file() else None
    out=reconcile(a.repo_root.resolve(),load(a.registry),load(a.policy),fleet,a.platform_root)
    save(a.output,out)
    print("CHACHA_DEV_V820_COMPONENT_REGISTRY_RECONCILER="+out["status"])
    print("ISSUE_COUNT="+str(out["issue_count"]))
    print("BLOCKING_ISSUE_COUNT="+str(out["blocking_issue_count"]))
    print("PROMOTION_ALLOWED="+("YES" if out["promotion_allowed"] else "NO"))
    print("CHACHA_DEV_V820_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
    return 2 if a.strict and not out["promotion_allowed"] else 0

if __name__=="__main__":raise SystemExit(main())
