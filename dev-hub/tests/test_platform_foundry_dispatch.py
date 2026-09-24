#!/usr/bin/env python3
from __future__ import annotations
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
BIN=ROOT/"dev-hub/bin";sys.path.insert(0,str(BIN))
import platform_component_evolution_controller as ctrl

gov={"components":[
 {"component_id":"core:agent-observation-bus","governance_class":"CORE_PLATFORM_COMPONENT",
  "evolution_owner":"branch-foundry","required_controls":["technology-watch","logician","shadow","pilot","rollback"]},
 {"component_id":"integration:github","governance_class":"CONNECTOR_ADAPTER",
  "evolution_owner":"capability-foundry","required_controls":["compatibility-test","technology-watch","pilot","rollback"]},
]}
idx={"schema":"chacha.dev/platform-evolution-reassessment-index/v1","routed_actions":[
 {"request_id":"r1","component_id":"agent-observation-bus","candidate_owner":"branch-foundry",
  "trigger_reasons":["GUARDIAN_COVERAGE_MANIFEST_CHANGED"],"shadow_required":True,"pilot_required":True},
 {"request_id":"r2","component_id":"github","candidate_owner":"capability-foundry",
  "trigger_reasons":["PROVIDER_ADAPTER_CATALOG_CHANGED"],"shadow_required":True,"pilot_required":True},
]}
out=ctrl.build_dispatch(idx,gov)
assert out["dispatch_complete"] is True,out
assert out["dispatch_count"]==2,out
assert out["blocked_count"]==0,out
by={x["request_id"]:x for x in out["dispatches"]}
assert by["r1"]["target_foundry"]=="branch-foundry",by
assert by["r1"]["target_contract"]=="chacha.dev/branch-foundry-platform-component-reassessment/v1",by
assert by["r2"]["target_foundry"]=="capability-foundry",by
assert by["r2"]["target_contract"]=="chacha.dev/capability-foundry-platform-component-reassessment/v1",by
assert all(x["materialization_authorized"] is False for x in out["dispatches"])
assert all(x["promotion_authorized"] is False for x in out["dispatches"])
assert all(x["architecture_council_final_authority"] is True for x in out["dispatches"])

bad={"schema":idx["schema"],"routed_actions":[
 {"request_id":"bad1","component_id":"agent-observation-bus","candidate_owner":"capability-foundry",
  "trigger_reasons":["TEST"],"shadow_required":True,"pilot_required":True}
]}
blocked=ctrl.build_dispatch(bad,gov)
assert blocked["dispatch_complete"] is False,blocked
assert blocked["blocked"][0]["blocker"]=="EVOLUTION_OWNER_MISMATCH",blocked

missing={"schema":idx["schema"],"routed_actions":[
 {"request_id":"bad2","component_id":"unknown","candidate_owner":"branch-foundry",
  "trigger_reasons":["TEST"],"shadow_required":True,"pilot_required":True}
]}
missing_out=ctrl.build_dispatch(missing,gov)
assert missing_out["blocked"][0]["blocker"]=="COMPONENT_GOVERNANCE_NOT_RESOLVED",missing_out

print("CHACHA_DEV_PLATFORM_FOUNDRY_DISPATCH=PASS")
print("CHACHA_DEV_PLATFORM_BRANCH_FOUNDRY_CONTRACT=PASS")
print("CHACHA_DEV_PLATFORM_CAPABILITY_FOUNDRY_CONTRACT=PASS")
print("CHACHA_DEV_PLATFORM_OWNER_MISMATCH=BLOCKED")
print("CHACHA_DEV_PLATFORM_UNKNOWN_COMPONENT=BLOCKED")
print("CHACHA_DEV_PLATFORM_MATERIALIZATION_AUTHORIZED=NO")
print("CHACHA_DEV_PLATFORM_PROMOTION_AUTHORIZED=NO")
print("CHACHA_DEV_PLATFORM_ARCHITECTURE_COUNCIL_FINAL=YES")
print("CHACHA_DEV_PLATFORM_FOUNDRY_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
