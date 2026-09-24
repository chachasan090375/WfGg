#!/usr/bin/env python3
from __future__ import annotations
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];BIN=ROOT/"dev-hub/bin";sys.path.insert(0,str(BIN))
import platform_component_evolution_controller as ctrl

base_evidence={"dispatch_id":"d1","evidence_refs":["e:1","e:2"],
 "independent_verification":True,"measurable_gain":True,"no_material_regression":True,
 "permission_non_escalation":True,"rollback_ready":True,"exact_revision_evidence":True,
 "logician_falsification_pass":True,"technology_watch_revalidation_pass":True,
 "real_harness_available":True}
shadow={"completed":{"d1":{"component_id":"central-orchestrator","candidate_owner":"branch-foundry",
 "shadow_result":{"dispatch_id":"d1","component_id":"central-orchestrator","candidate_owner":"branch-foundry",
  "state":"SHADOW_ASSESSED","pilot_required":True,"shadow_candidate_signals":["cand-a"]}}}}

# Artifact refs are mandatory before readiness.
r0=ctrl.build_pilot_readiness(shadow,{"evidence":[base_evidence]})
assert r0["pilot_ready_count"]==0,r0
assert "candidate_artifact_ref" in r0["rows"][0]["missing_evidence"],r0
assert "incumbent_artifact_ref" in r0["rows"][0]["missing_evidence"],r0

ev={**base_evidence,"candidate_artifact_ref":"git:candidate@abc","incumbent_artifact_ref":"git:incumbent@def",
 "candidate_revision":"abc","incumbent_revision":"def"}
ready=ctrl.build_pilot_readiness(shadow,{"evidence":[ev]})
assert ready["pilot_ready_count"]==1,ready

empty_registry={"harnesses":{}}
blocked=ctrl.build_pilot_contracts(ready,empty_registry)
assert blocked["contract_count"]==0 and blocked["blocked_count"]==1,blocked
assert blocked["blocked"][0]["blocker"]=="REAL_HARNESS_NOT_REGISTERED",blocked

registry={"harnesses":{"central-orchestrator":{
 "harness_id":"central-orchestrator-real-v1","status":"QUALIFIED","real_harness":True,
 "isolated":True,"same_benchmark_contract":True,"automatic_external_spend_eur":0,
 "qualification_workflow_name":"ChaCha DEV universal evolution coverage sync qualification",
 "argv":["/usr/bin/python3","harness.py","--variant","{variant}"],
 "resource_budget":{"memory_mb":256,"cpu_weight":50,"tasks_max":8,"timeout_seconds":120}
}}}
contracts=ctrl.build_pilot_contracts(ready,registry)
assert contracts["contract_count"]==1 and contracts["blocked_count"]==0,contracts
c=contracts["contracts"][0]
assert c["pilot_execution_authorized"] is True,c
assert c["production_change_authorized"] is False,c
assert c["promotion_authorized"] is False,c
assert c["isolated_ephemeral_capsules"] is True,c
assert c["same_benchmark_contract"] is True,c
assert c["qualification_workflow_name"]=="ChaCha DEV universal evolution coverage sync qualification",c
assert c["automatic_external_spend_eur"]==0,c

bad={"harnesses":{"central-orchestrator":{
 "harness_id":"bad","status":"QUALIFIED","real_harness":False,"isolated":True,
 "same_benchmark_contract":True,"automatic_external_spend_eur":0,
 "qualification_workflow_name":"ChaCha DEV universal evolution coverage sync qualification","argv":["x"]
}}}
badout=ctrl.build_pilot_contracts(ready,bad)
assert badout["contract_count"]==0,badout
assert "real_harness" in badout["blocked"][0]["missing"],badout

print("CHACHA_DEV_PLATFORM_PILOT_CONTRACT_GATE=PASS")
print("CHACHA_DEV_PLATFORM_PILOT_EXACT_ARTIFACTS_REQUIRED=YES")
print("CHACHA_DEV_PLATFORM_REAL_HARNESS_REGISTRY_REQUIRED=YES")
print("CHACHA_DEV_PLATFORM_SYNTHETIC_HARNESS_PRODUCTION_DECISION=NO")
print("CHACHA_DEV_PLATFORM_ISOLATED_PILOT_CONTRACT=PASS")
print("CHACHA_DEV_PLATFORM_PILOT_CONTRACT_PRODUCTION_CHANGE=NO")
print("CHACHA_DEV_PLATFORM_PILOT_CONTRACT_PROMOTION=NO")
print("CHACHA_DEV_PLATFORM_PILOT_CONTRACT_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
