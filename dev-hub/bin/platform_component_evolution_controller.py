#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,importlib.util,json
from pathlib import Path
from typing import Any
import technology_watch_runtime as tw

def load(p:Path)->dict[str,Any]:
    x=json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise ValueError("JSON_ROOT_NOT_OBJECT:"+str(p))
    return x
def save(p:Path,x:dict[str,Any])->None:
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
def digest(x:Any)->str:
    return hashlib.sha256(json.dumps(x,sort_keys=True,ensure_ascii=False,separators=(",",":")).encode()).hexdigest()
def load_module(name:str,path:Path):
    spec=importlib.util.spec_from_file_location(name,path)
    if spec is None or spec.loader is None:raise ValueError("FOUNDRY_MODULE_LOAD_FAILED:"+str(path))
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod
def resolve_component(governance:dict[str,Any],component_id:str)->dict[str,Any]|None:
    rows=[x for x in governance.get("components") or [] if isinstance(x,dict)]
    exact=[x for x in rows if str(x.get("component_id") or "")==component_id]
    if len(exact)==1:return exact[0]
    suffix=[x for x in rows if str(x.get("component_id") or "").endswith(":"+component_id)]
    if len(suffix)==1:return suffix[0]
    return None
def build_dispatch(index:dict[str,Any],governance:dict[str,Any])->dict[str,Any]:
    dispatches=[];blocked=[]
    for action in index.get("routed_actions") or []:
        rid=str(action.get("request_id") or "")
        cid=str(action.get("component_id") or "")
        owner=str(action.get("candidate_owner") or "")
        row=resolve_component(governance,cid)
        if row is None:
            blocked.append({"request_id":rid,"component_id":cid,"candidate_owner":owner,
                "blocker":"COMPONENT_GOVERNANCE_NOT_RESOLVED"});continue
        expected=str(row.get("evolution_owner") or "")
        if owner!=expected:
            blocked.append({"request_id":rid,"component_id":cid,"candidate_owner":owner,
                "expected_owner":expected,"blocker":"EVOLUTION_OWNER_MISMATCH"});continue
        if owner not in {"branch-foundry","capability-foundry"}:
            blocked.append({"request_id":rid,"component_id":cid,"candidate_owner":owner,
                "blocker":"UNSUPPORTED_FOUNDRY_OWNER"});continue
        contract=("chacha.dev/branch-foundry-platform-component-reassessment/v1"
                  if owner=="branch-foundry" else
                  "chacha.dev/capability-foundry-platform-component-reassessment/v1")
        base={"request_id":rid,"component_id":cid,
              "governance_component_id":row.get("component_id"),
              "governance_class":row.get("governance_class"),
              "target_foundry":owner,"target_contract":contract,
              "mode":"PLATFORM_COMPONENT_REASSESSMENT",
              "trigger_reasons":list(action.get("trigger_reasons") or []),
              "required_controls":list(row.get("required_controls") or []),
              "technology_watch_revalidation_required":True,
              "logician_falsification_required":True,
              "guardian_required":True,"sentinel_required":True,
              "shadow_required":bool(action.get("shadow_required") is True),
              "pilot_required":bool(action.get("pilot_required") is True),
              "architecture_council_final_authority":True,
              "materialization_authorized":False,"promotion_authorized":False,
              "direct_component_mutation":False,"permission_expansion":False,
              "automatic_external_spend_eur":0}
        base["dispatch_id"]="pfd-"+digest(base)[:24]
        dispatches.append(base)
    return {"schema":"chacha.dev/platform-foundry-dispatch-index/v1",
      "source_schema":index.get("schema"),"dispatches":dispatches,"blocked":blocked,
      "input_request_count":len(index.get("routed_actions") or []),
      "dispatch_count":len(dispatches),"blocked_count":len(blocked),
      "dispatch_complete":len(dispatches)==len(index.get("routed_actions") or []) and not blocked,
      "materialization_authorized":False,"promotion_authorized":False,
      "direct_component_mutation":False,"self_promotion":False,
      "architecture_council_final_authority":True,"automatic_external_spend_eur":0}
def execute_shadow_dispatches(dispatch_index:dict[str,Any],governance:dict[str,Any],repo_root:Path,watch_provider=None,completed_dispatch_ids:set[str]|None=None)->dict[str,Any]:
    watch_provider=watch_provider or (lambda consumer,cid:tw.consult(
        repo_root,consumer=consumer,domain="platform-component-evolution",capabilities=[cid]))
    branch_mod=load_module("platform_branch_foundry",repo_root/"dev-hub/bin/branch-foundry-planner.py")
    capability_mod=load_module("platform_capability_foundry",repo_root/"dev-hub/bin/capability-foundry.py")
    completed_dispatch_ids=set(completed_dispatch_ids or set())
    results=[];blocked=[];skipped=[]
    for contract in dispatch_index.get("dispatches") or []:
        did=str(contract.get("dispatch_id") or "")
        if did and did in completed_dispatch_ids:
            skipped.append({"dispatch_id":did,"component_id":contract.get("component_id"),
                "target_foundry":contract.get("target_foundry"),"reason":"ALREADY_SHADOW_ASSESSED"})
            continue
        cid=str(contract.get("component_id") or "")
        row=resolve_component(governance,cid)
        if row is None:
            blocked.append({"dispatch_id":contract.get("dispatch_id"),"component_id":cid,"blocker":"COMPONENT_GOVERNANCE_NOT_RESOLVED"});continue
        owner=str(contract.get("target_foundry") or "")
        try:
            watch=watch_provider(owner,cid)
            if owner=="branch-foundry":
                result=branch_mod.platform_component_reassessment(contract,row,watch)
            elif owner=="capability-foundry":
                result=capability_mod.platform_component_reassessment(contract,row,watch)
            else:
                raise ValueError("UNSUPPORTED_FOUNDRY_OWNER:"+owner)
        except Exception as exc:
            blocked.append({"dispatch_id":contract.get("dispatch_id"),"component_id":cid,
                "target_foundry":owner,"blocker":"SHADOW_REASSESSMENT_FAILED","reason":str(exc)});continue
        result["dispatch_id"]=contract.get("dispatch_id")
        results.append(result)
    all_shadow=all(str(x.get("state") or "")=="SHADOW_ASSESSED" for x in results)
    return {"schema":"chacha.dev/platform-foundry-shadow-execution-index/v1",
      "input_dispatch_count":len(dispatch_index.get("dispatches") or []),
      "shadow_result_count":len(results),"skipped_completed_count":len(skipped),"blocked_count":len(blocked),
      "results":results,"skipped_completed":skipped,"blocked":blocked,
      "shadow_execution_complete":len(results)+len(skipped)==len(dispatch_index.get("dispatches") or []) and not blocked and all_shadow,
      "materialization_authorized":False,"active_component_mutation":False,
      "promotion_authorized":False,"self_promotion":False,
      "architecture_council_final_authority":True,"automatic_external_spend_eur":0}

def build_pilot_readiness(shadow_ledger:dict[str,Any],evidence_index:dict[str,Any])->dict[str,Any]:
    evidence_by={}
    for row in evidence_index.get("evidence") or []:
        if isinstance(row,dict) and str(row.get("dispatch_id") or ""):
            evidence_by[str(row.get("dispatch_id"))]=row
    rows=[];ready=[];blocked=[]
    required=[
      "independent_verification","measurable_gain","no_material_regression",
      "permission_non_escalation","rollback_ready","exact_revision_evidence",
      "logician_falsification_pass","technology_watch_revalidation_pass","real_harness_available"
    ]
    completed=shadow_ledger.get("completed") if isinstance(shadow_ledger.get("completed"),dict) else {}
    for did,entry in sorted(completed.items()):
        result=entry.get("shadow_result") if isinstance(entry.get("shadow_result"),dict) else {}
        cid=str(entry.get("component_id") or result.get("component_id") or "")
        signals=list(result.get("shadow_candidate_signals") or [])
        pilot_required=bool(result.get("pilot_required") is True)
        ev=evidence_by.get(str(did)) or {}
        refs=[str(x) for x in ev.get("evidence_refs") or [] if str(x)]
        pre_pilot_checks={k:(ev.get(k) is True) for k in required}
        missing=[k for k,v in pre_pilot_checks.items() if not v]
        candidate_ref=str(ev.get("candidate_artifact_ref") or "")
        incumbent_ref=str(ev.get("incumbent_artifact_ref") or "")
        candidate_revision=str(ev.get("candidate_revision") or "")
        incumbent_revision=str(ev.get("incumbent_revision") or "")
        if not refs:missing.append("evidence_refs")
        if not signals:missing.append("shadow_candidate_signals")
        if not candidate_ref:missing.append("candidate_artifact_ref")
        if not incumbent_ref:missing.append("incumbent_artifact_ref")
        if not candidate_revision:missing.append("candidate_revision")
        if not incumbent_revision:missing.append("incumbent_revision")
        state="NOT_REQUIRED" if not pilot_required else ("PILOT_READY" if not missing else "HOLD_SHADOW")
        row={"dispatch_id":did,"component_id":cid,"candidate_owner":entry.get("candidate_owner"),
          "state":state,"pilot_required":pilot_required,"shadow_candidate_signal_count":len(signals),
          "evidence_refs":refs,"candidate_artifact_ref":candidate_ref,"incumbent_artifact_ref":incumbent_ref,
          "candidate_revision":candidate_revision,"incumbent_revision":incumbent_revision,
          "pre_pilot_checks":pre_pilot_checks,
          "missing_evidence":sorted(set(missing)),
          "pilot_execution_authorized":False,"production_change_authorized":False,
          "active_component_mutation":False,"promotion_authorized":False,
          "permission_expansion":False,"real_harness_required":True,
          "isolated_pilot_required":True,"guardian_required":True,"sentinel_required":True,
          "architecture_council_final_authority":True,"automatic_external_spend_eur":0}
        rows.append(row)
        if state=="PILOT_READY":ready.append(row)
        elif state=="HOLD_SHADOW":blocked.append(row)
    return {"schema":"chacha.dev/platform-component-pilot-readiness-index/v1",
      "evaluated_count":len(rows),"pilot_ready_count":len(ready),"hold_shadow_count":len(blocked),
      "rows":rows,"pilot_ready":ready,"hold_shadow":blocked,
      "candidate_presence_alone_never_authorizes_pilot":True,
      "pilot_execution_authorized":False,"production_change_authorized":False,
      "promotion_authorized":False,"architecture_council_final_authority":True,
      "automatic_external_spend_eur":0}

def build_pilot_contracts(readiness:dict[str,Any],harness_registry:dict[str,Any])->dict[str,Any]:
    harnesses=harness_registry.get("harnesses") if isinstance(harness_registry.get("harnesses"),dict) else {}
    contracts=[];blocked=[]
    for row in readiness.get("pilot_ready") or []:
        cid=str(row.get("component_id") or "")
        h=harnesses.get(cid)
        if not isinstance(h,dict):
            blocked.append({"dispatch_id":row.get("dispatch_id"),"component_id":cid,
                "blocker":"REAL_HARNESS_NOT_REGISTERED"});continue
        checks={
          "status_qualified":str(h.get("status") or "")=="QUALIFIED",
          "real_harness":h.get("real_harness") is True,
          "isolated":h.get("isolated") is True,
          "same_benchmark_contract":h.get("same_benchmark_contract") is True,
          "zero_external_spend":float(h.get("automatic_external_spend_eur") or 0)==0,
          "argv_present":isinstance(h.get("argv"),list) and bool(h.get("argv")),
          "qualification_workflow_name_present":bool(str(h.get("qualification_workflow_name") or "")),
          "incumbent_ref_present":bool(str(row.get("incumbent_artifact_ref") or "")),
          "candidate_ref_present":bool(str(row.get("candidate_artifact_ref") or "")),
        }
        missing=[k for k,v in checks.items() if not v]
        if missing:
            blocked.append({"dispatch_id":row.get("dispatch_id"),"component_id":cid,
                "harness_id":h.get("harness_id"),"blocker":"PILOT_CONTRACT_REQUIREMENTS_MISSING",
                "missing":missing});continue
        contract={"schema":"chacha.dev/platform-component-comparative-pilot-contract/v1",
          "contract_id":"pcp-"+digest({"dispatch_id":row.get("dispatch_id"),"harness_id":h.get("harness_id"),
            "candidate":row.get("candidate_artifact_ref"),"incumbent":row.get("incumbent_artifact_ref")})[:24],
          "dispatch_id":row.get("dispatch_id"),"component_id":cid,
          "candidate_owner":row.get("candidate_owner"),"harness_id":h.get("harness_id"),
          "qualification_workflow_name":h.get("qualification_workflow_name"),
          "harness_argv":list(h.get("argv") or []),"resource_budget":h.get("resource_budget") or {},
          "incumbent_artifact_ref":row.get("incumbent_artifact_ref"),
          "candidate_artifact_ref":row.get("candidate_artifact_ref"),
          "incumbent_revision":row.get("incumbent_revision"),"candidate_revision":row.get("candidate_revision"),
          "pre_pilot_checks":row.get("pre_pilot_checks") or {},
          "pre_pilot_evidence_refs":list(row.get("evidence_refs") or []),
          "sentinel_exact_sha_receipt_required":True,
          "same_benchmark_contract":True,"isolated_ephemeral_capsules":True,
          "emergency_stop_required":True,"guardian_pre_post_required":True,
          "sentinel_required":True,"technology_watch_revalidation_required":True,
          "logician_falsification_required":True,"rollback_required":True,
          "pilot_execution_authorized":True,"production_change_authorized":False,
          "promotion_authorized":False,"permission_expansion":False,
          "architecture_council_final_authority":True,"automatic_external_spend_eur":0}
        contracts.append(contract)
    return {"schema":"chacha.dev/platform-component-pilot-contract-index/v1",
      "pilot_ready_input_count":len(readiness.get("pilot_ready") or []),
      "contract_count":len(contracts),"blocked_count":len(blocked),
      "contracts":contracts,"blocked":blocked,
      "default_admission":"DENY","synthetic_harness_for_production_decision":False,
      "production_change_authorized":False,"promotion_authorized":False,
      "architecture_council_final_authority":True,"automatic_external_spend_eur":0}

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--reassessment-index",type=Path,required=True)
    ap.add_argument("--component-governance",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    a=ap.parse_args()
    out=build_dispatch(load(a.reassessment_index),load(a.component_governance));save(a.output,out)
    print("CHACHA_DEV_PLATFORM_FOUNDRY_DISPATCH="+("PASS" if out["dispatch_complete"] else "BLOCKED"))
    print("DISPATCH_COUNT="+str(out["dispatch_count"]))
    print("BLOCKED_COUNT="+str(out["blocked_count"]))
    print("MATERIALIZATION_AUTHORIZED=NO")
    print("PROMOTION_AUTHORIZED=NO")
    print("CHACHA_DEV_PLATFORM_FOUNDRY_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
    return 0 if out["dispatch_complete"] else 2
if __name__=="__main__":raise SystemExit(main())
