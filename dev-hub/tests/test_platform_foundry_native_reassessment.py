#!/usr/bin/env python3
from __future__ import annotations
import importlib.util,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];BIN=ROOT/"dev-hub/bin";sys.path.insert(0,str(BIN))
import platform_component_evolution_controller as ctrl

def loadmod(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
bf=loadmod("test_branch_foundry",BIN/"branch-foundry-planner.py")
cf=loadmod("test_capability_foundry",BIN/"capability-foundry.py")

branch_row={"component_id":"core:central-orchestrator","governance_class":"CORE_PLATFORM_COMPONENT",
 "evolution_owner":"branch-foundry","required_controls":["technology-watch","logician","shadow","pilot","rollback"]}
cap_row={"component_id":"integration:github","governance_class":"CONNECTOR_ADAPTER",
 "evolution_owner":"capability-foundry","required_controls":["compatibility-test","technology-watch","pilot","rollback"]}
branch_contract={"dispatch_id":"d1","request_id":"r1","component_id":"central-orchestrator",
 "target_foundry":"branch-foundry","target_contract":"chacha.dev/branch-foundry-platform-component-reassessment/v1",
 "trigger_reasons":["TECHNOLOGY_CORE_WATCH_CHANGED"]}
cap_contract={"dispatch_id":"d2","request_id":"r2","component_id":"github",
 "target_foundry":"capability-foundry","target_contract":"chacha.dev/capability-foundry-platform-component-reassessment/v1",
 "trigger_reasons":["PROVIDER_ADAPTER_CATALOG_CHANGED"]}
watch={"snapshot_freshness":"FRESH","targeted_refresh_performed":False,"source_snapshot_digest":"sha256:test",
 "branch_blueprints":[{"id":"bp-zero","external_spend_eur":0}],
 "eligible_provider_candidates":[{"id":"provider-zero","zero_external_spend":True}]}

b=bf.platform_component_reassessment(branch_contract,branch_row,watch)
assert b["state"]=="SHADOW_ASSESSED" and b["stage"]=="SHADOW",b
assert b["candidate_owner"]=="branch-foundry" and b["incumbent_is_control_group"] is True,b
assert b["materialization_authorized"] is False and b["promotion_authorized"] is False,b
c=cf.platform_component_reassessment(cap_contract,cap_row,watch)
assert c["state"]=="SHADOW_ASSESSED" and c["stage"]=="SHADOW",c
assert c["candidate_owner"]=="capability-foundry" and c["incumbent_is_control_group"] is True,c
assert c["materialization_authorized"] is False and c["promotion_authorized"] is False,c

gov={"components":[branch_row,cap_row]}
dispatch={"dispatches":[branch_contract,cap_contract]}
def fake_watch(owner,cid):return watch
out=ctrl.execute_shadow_dispatches(dispatch,gov,ROOT,fake_watch)
assert out["shadow_execution_complete"] is True,out
assert out["shadow_result_count"]==2 and out["blocked_count"]==0,out
assert all(x["state"]=="SHADOW_ASSESSED" for x in out["results"])
assert out["materialization_authorized"] is False and out["promotion_authorized"] is False,out

stale=dict(watch);stale["snapshot_freshness"]="STALE"
blocked=bf.platform_component_reassessment(branch_contract,branch_row,stale)
assert blocked["state"]=="BLOCKED_TECHNOLOGY_WATCH",blocked
assert blocked["next_stage"]=="TECHNOLOGY_WATCH_REVALIDATION",blocked

bad=dict(branch_contract);bad["target_foundry"]="capability-foundry"
try:bf.platform_component_reassessment(bad,branch_row,watch)
except ValueError as e:assert "OWNER_INVALID" in str(e),e
else:raise AssertionError("branch foundry accepted wrong owner")

print("CHACHA_DEV_BRANCH_FOUNDRY_PLATFORM_REASSESSMENT=PASS")
print("CHACHA_DEV_CAPABILITY_FOUNDRY_PLATFORM_REASSESSMENT=PASS")
print("CHACHA_DEV_PLATFORM_REASSESSMENT_SHADOW_EXECUTION=PASS")
print("CHACHA_DEV_PLATFORM_REASSESSMENT_STALE_WATCH=BLOCKED")
print("CHACHA_DEV_PLATFORM_REASSESSMENT_INCUMBENT_CONTROL=YES")
print("CHACHA_DEV_PLATFORM_REASSESSMENT_MATERIALIZATION=NO")
print("CHACHA_DEV_PLATFORM_REASSESSMENT_PROMOTION=NO")
print("CHACHA_DEV_PLATFORM_REASSESSMENT_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
