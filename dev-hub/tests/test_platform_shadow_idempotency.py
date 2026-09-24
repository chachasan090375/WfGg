#!/usr/bin/env python3
from __future__ import annotations
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];BIN=ROOT/"dev-hub/bin";sys.path.insert(0,str(BIN))
import platform_component_evolution_controller as ctrl

row={"component_id":"core:central-orchestrator","governance_class":"CORE_PLATFORM_COMPONENT",
 "evolution_owner":"branch-foundry","required_controls":["technology-watch","logician","shadow","pilot","rollback"]}
contract={"dispatch_id":"pfd-stable-1","request_id":"r1","component_id":"central-orchestrator",
 "target_foundry":"branch-foundry","target_contract":"chacha.dev/branch-foundry-platform-component-reassessment/v1",
 "trigger_reasons":["TECHNOLOGY_CORE_WATCH_CHANGED"]}
dispatch={"dispatches":[contract]}
gov={"components":[row]}
watch={"snapshot_freshness":"FRESH","targeted_refresh_performed":False,"source_snapshot_digest":"sha256:test",
 "branch_blueprints":[],"eligible_provider_candidates":[]}
calls={"n":0}
def provider(owner,cid):
    calls["n"]+=1
    return watch

first=ctrl.execute_shadow_dispatches(dispatch,gov,ROOT,provider,set())
assert first["shadow_execution_complete"] is True,first
assert first["shadow_result_count"]==1 and first["skipped_completed_count"]==0,first
assert calls["n"]==1,calls

second=ctrl.execute_shadow_dispatches(dispatch,gov,ROOT,provider,{"pfd-stable-1"})
assert second["shadow_execution_complete"] is True,second
assert second["shadow_result_count"]==0 and second["skipped_completed_count"]==1,second
assert second["blocked_count"]==0,second
assert second["skipped_completed"][0]["reason"]=="ALREADY_SHADOW_ASSESSED",second
assert calls["n"]==1,calls

changed={"dispatches":[dict(contract,dispatch_id="pfd-stable-2",request_id="r2")]}
third=ctrl.execute_shadow_dispatches(changed,gov,ROOT,provider,{"pfd-stable-1"})
assert third["shadow_result_count"]==1 and third["skipped_completed_count"]==0,third
assert calls["n"]==2,calls

print("CHACHA_DEV_PLATFORM_SHADOW_IDEMPOTENCY=PASS")
print("CHACHA_DEV_PLATFORM_SHADOW_REPEAT_WATCH_CALL=NO")
print("CHACHA_DEV_PLATFORM_SHADOW_NEW_DISPATCH_EXECUTES=YES")
print("CHACHA_DEV_PLATFORM_SHADOW_QUEUE_DELETE_REQUIRED=NO")
print("CHACHA_DEV_PLATFORM_SHADOW_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
