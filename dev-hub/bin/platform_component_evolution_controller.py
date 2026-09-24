#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path
from typing import Any

def load(p:Path)->dict[str,Any]:
    x=json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise ValueError("JSON_ROOT_NOT_OBJECT:"+str(p))
    return x
def save(p:Path,x:dict[str,Any])->None:
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
def digest(x:Any)->str:
    return hashlib.sha256(json.dumps(x,sort_keys=True,ensure_ascii=False,separators=(",",":")).encode()).hexdigest()
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
