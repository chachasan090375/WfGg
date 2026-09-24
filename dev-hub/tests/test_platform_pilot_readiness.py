#!/usr/bin/env python3
from __future__ import annotations
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];BIN=ROOT/"dev-hub/bin";sys.path.insert(0,str(BIN))
import platform_component_evolution_controller as ctrl

shadow_result={
 "schema":"chacha.dev/branch-foundry-platform-component-shadow/v1",
 "dispatch_id":"d1","component_id":"central-orchestrator","candidate_owner":"branch-foundry",
 "state":"SHADOW_ASSESSED","pilot_required":True,"shadow_candidate_signals":["candidate-a"],
 "materialization_authorized":False,"promotion_authorized":False
}
ledger={"schema":"chacha.dev/platform-foundry-shadow-ledger/v1","completed":{
 "d1":{"component_id":"central-orchestrator","candidate_owner":"branch-foundry",
       "state":"SHADOW_ASSESSED","shadow_result":shadow_result}
}}

# Candidate presence alone must not allow pilot.
none=ctrl.build_pilot_readiness(ledger,{"evidence":[]})
assert none["pilot_ready_count"]==0,none
assert none["hold_shadow_count"]==1,none
r=none["rows"][0]
assert r["state"]=="HOLD_SHADOW",r
assert r["pilot_execution_authorized"] is False,r
assert "independent_verification" in r["missing_evidence"],r
assert none["candidate_presence_alone_never_authorizes_pilot"] is True

partial={"evidence":[{"dispatch_id":"d1","evidence_refs":["e:1"],
 "independent_verification":True,"measurable_gain":True}]}
p=ctrl.build_pilot_readiness(ledger,partial)
assert p["pilot_ready_count"]==0 and p["hold_shadow_count"]==1,p
assert "rollback_ready" in p["rows"][0]["missing_evidence"],p

complete={"evidence":[{"dispatch_id":"d1","evidence_refs":["e:1","e:2"],
 "independent_verification":True,"measurable_gain":True,"no_material_regression":True,
 "permission_non_escalation":True,"rollback_ready":True,"exact_revision_evidence":True,
 "logician_falsification_pass":True,"technology_watch_revalidation_pass":True,
 "real_harness_available":True,"candidate_artifact_ref":"git:candidate@abc",
 "incumbent_artifact_ref":"git:incumbent@def"}]}
ok=ctrl.build_pilot_readiness(ledger,complete)
assert ok["pilot_ready_count"]==1 and ok["hold_shadow_count"]==0,ok
row=ok["pilot_ready"][0]
assert row["state"]=="PILOT_READY",row
assert row["pilot_execution_authorized"] is False,row
assert row["production_change_authorized"] is False,row
assert row["promotion_authorized"] is False,row
assert row["real_harness_required"] is True,row
assert row["isolated_pilot_required"] is True,row

not_required_result=dict(shadow_result,dispatch_id="d2",pilot_required=False)
nrledger={"completed":{"d2":{"component_id":"central-orchestrator","candidate_owner":"branch-foundry","shadow_result":not_required_result}}}
nr=ctrl.build_pilot_readiness(nrledger,{"evidence":[]})
assert nr["rows"][0]["state"]=="NOT_REQUIRED",nr

print("CHACHA_DEV_PLATFORM_PILOT_GATE=PASS")
print("CHACHA_DEV_PLATFORM_CANDIDATE_ALONE_PILOT=NO")
print("CHACHA_DEV_PLATFORM_INDEPENDENT_EVIDENCE_REQUIRED=YES")
print("CHACHA_DEV_PLATFORM_REAL_HARNESS_REQUIRED=YES")
print("CHACHA_DEV_PLATFORM_PILOT_EXECUTION_AUTHORIZED=NO")
print("CHACHA_DEV_PLATFORM_PRODUCTION_CHANGE_AUTHORIZED=NO")
print("CHACHA_DEV_PLATFORM_PROMOTION_AUTHORIZED=NO")
print("CHACHA_DEV_PLATFORM_PILOT_GATE_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
