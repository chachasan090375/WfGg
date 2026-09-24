#!/usr/bin/env python3
from __future__ import annotations
import importlib.util,json,sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BIN=ROOT/"dev-hub/bin"
spec=importlib.util.spec_from_file_location("platform_component_promotion_gate",BIN/"platform-component-promotion-gate.py")
assert spec and spec.loader
gate=importlib.util.module_from_spec(spec);spec.loader.exec_module(gate)

digest="sha256:"+"a"*64
approval_id="platform-component-promotion:central-orchestrator:abc"
evidence="architecture-council-platform-review:"+digest
review={
 "schema":"chacha.dev/architecture-council-platform-component-review/v1",
 "component_id":"central-orchestrator",
 "candidate_revision":"abc","incumbent_revision":"def",
 "technical_review_passed":True,
 "architecture_council_technical_admissibility":True,
 "technical_review_digest":digest,
 "human_approval_request_created":True,
 "approval_request":{
   "schema":"chacha.dev/protected-human-approval-request/v1",
   "project":"chacha-dev-platform","operation":"record-approval",
   "approval_id":approval_id,"actor_requirement":"real-human",
   "evidence":evidence,"technical_review_digest":digest,
   "candidate_revision":"abc","incumbent_revision":"def",
   "component_id":"central-orchestrator",
   "project_control_protected_path_required":True,
   "agent_or_api_approval_synthesis_forbidden":True,
   "production_activation_before_approval":False,
   "promotion_before_approval":False,
   "automatic_external_spend_eur":0
 },
 "production_activation_allowed":False,"promotion_allowed":False,
 "automatic_external_spend_eur":0
}
status={
 "schema":"chacha.dev/project-control-response/v1","project":"chacha-dev-platform",
 "operation":"status","status":"READY",
 "details":{"control_profile":"platform","lifecycle_managed":False,
            "protected_human_approval_boundary":True,"pending_transactions":0,
            "integrity":{"JOURNAL_CHAIN":"OK"}}
}
base_state={
 "schema":"chacha.dev/control-plane-state/v1","project":"chacha-dev-platform",
 "state":{"identity":{"control_profile":"platform"},
          "evidence":{"control_plane_ledger_initialized":True},"approvals":{}}
}
base_ledger={
 "schema":"chacha.dev/evidence-ledger/v1","project":"chacha-dev-platform",
 "approvals":{}
}

awaiting=gate.evaluate(review,status,json.loads(json.dumps(base_state)),json.loads(json.dumps(base_ledger)))
assert awaiting["status"]=="AWAITING_HUMAN_APPROVAL",awaiting
assert awaiting["promotion_authorized"] is False,awaiting
assert awaiting["human_approval_record_present"] is False,awaiting
assert awaiting["production_activation_allowed"] is False,awaiting

# A forged/system approval is a hard block, not a waiting state.
bad_state=json.loads(json.dumps(base_state));bad_ledger=json.loads(json.dumps(base_ledger))
bad_state["state"]["approvals"][approval_id]={"status":"APPROVED","actor":"central-orchestrator","evidence":evidence}
bad_ledger["approvals"][approval_id]={"status":"APPROVED","actor":"central-orchestrator","evidence":evidence}
bad=gate.evaluate(review,status,bad_state,bad_ledger)
assert bad["status"]=="BLOCKED",bad
assert bad["checks"]["ledger_approval_actor_human"] is False,bad
assert bad["promotion_authorized"] is False,bad

# A real human approval with exact evidence in both ledger and projection authorizes controlled apply only.
human_state=json.loads(json.dumps(base_state));human_ledger=json.loads(json.dumps(base_ledger))
record={"status":"APPROVED","actor":"human-platform-owner","evidence":evidence}
human_state["state"]["approvals"][approval_id]=dict(record)
human_ledger["approvals"][approval_id]=dict(record)
ok=gate.evaluate(review,status,human_state,human_ledger)
assert ok["status"]=="PROMOTION_AUTHORIZED_FOR_CONTROLLED_APPLY",ok
assert ok["human_approval_verified"] is True,ok
assert ok["promotion_authorized"] is True,ok
assert ok["controlled_apply_required"] is True,ok
assert ok["automatic_apply"] is False,ok
assert ok["production_activation_allowed"] is False,ok
assert ok["production_deployment_requires_separate_controlled_handoff"] is True,ok
assert ok["central_orchestrator_remains_apply_authority"] is True,ok

# Exact evidence mismatch fails closed.
mismatch_state=json.loads(json.dumps(human_state));mismatch_ledger=json.loads(json.dumps(human_ledger))
mismatch_ledger["approvals"][approval_id]["evidence"]="different"
mismatch=gate.evaluate(review,status,mismatch_state,mismatch_ledger)
assert mismatch["status"]=="BLOCKED",mismatch
assert mismatch["checks"]["ledger_approval_evidence_exact"] is False,mismatch

# Pending Project Control transaction blocks promotion even with a valid approval.
pending=json.loads(json.dumps(status));pending["details"]["pending_transactions"]=1
pend=gate.evaluate(review,pending,human_state,human_ledger)
assert pend["status"]=="BLOCKED",pend
assert pend["checks"]["project_control_no_pending_transactions"] is False,pend

# Gate itself must be governed and read-only.
guardian=json.loads((ROOT/"dev-hub/config/guardian-coverage-manifest.v1.json").read_text(encoding="utf-8"))
assert any(x.get("component_id")=="platform-component-promotion-gate" for x in guardian.get("expected_components") or []),guardian
assert guardian["d1_write_budget"]["expected_max_component_heartbeat_writes_per_day"]==len(guardian["expected_components"])*12*24
core=json.loads((ROOT/"dev-hub/config/technology-core-watch.v1.json").read_text(encoding="utf-8"))
crow=next(x for x in core["components"] if x["id"]=="platform-component-promotion-gate")
assert crow["class"]=="verification" and crow["criticality"]=="critical",crow
roles=json.loads((ROOT/"dev-hub/config/guardian-role-contracts.v1.json").read_text(encoding="utf-8"))
role=next(x for x in roles["contracts"] if x["contract_id"]=="role:platform-component-promotion-gate")
assert set(role["allowed_permissions"])=={"read","plan"},role
assert {"PRODUCTION_DEPLOY","PROMOTE_COMPONENT","MODIFY_GUARDIAN_CONTRACTS","EXPAND_PERMISSIONS"}<=set(role["forbidden_actions"]),role

print("CHACHA_DEV_PLATFORM_COMPONENT_PROMOTION_GATE=PASS")
print("CHACHA_DEV_PLATFORM_COMPONENT_PROMOTION_NO_APPROVAL=AWAIT")
print("CHACHA_DEV_PLATFORM_COMPONENT_PROMOTION_SYSTEM_APPROVAL=BLOCKED")
print("CHACHA_DEV_PLATFORM_COMPONENT_PROMOTION_HUMAN_APPROVAL=VERIFIED")
print("CHACHA_DEV_PLATFORM_COMPONENT_PROMOTION_CONTROLLED_APPLY_REQUIRED=YES")
print("CHACHA_DEV_PLATFORM_COMPONENT_PROMOTION_AUTOMATIC_APPLY=NO")
print("CHACHA_DEV_PLATFORM_COMPONENT_PROMOTION_PRODUCTION_ACTIVATION=NO")
print("CHACHA_DEV_PLATFORM_COMPONENT_PROMOTION_GUARDIAN_COVERAGE=PASS")
print("CHACHA_DEV_PLATFORM_COMPONENT_PROMOTION_READ_ONLY_GATE=YES")
print("CHACHA_DEV_PLATFORM_COMPONENT_PROMOTION_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
