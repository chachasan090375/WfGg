#!/usr/bin/env python3
from __future__ import annotations
import importlib.util,json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BIN=ROOT/"dev-hub/bin"
CFG=ROOT/"dev-hub/config"
spec=importlib.util.spec_from_file_location("platform_component_adapter_binding_gate",BIN/"platform-component-adapter-binding-gate.py")
assert spec and spec.loader
gate=importlib.util.module_from_spec(spec);spec.loader.exec_module(gate)

policy=json.loads((CFG/"platform-component-adapter-binding-gate.v1.json").read_text(encoding="utf-8"))
registry=json.loads((CFG/"platform-component-apply-adapter-registry.v1.json").read_text(encoding="utf-8"))
adapter_policy=json.loads((CFG/"platform-component-branch-foundry-source-integrator.v1.json").read_text(encoding="utf-8"))
provisioning=json.loads((CFG/"adapter-provisioning.v1.json").read_text(encoding="utf-8"))
source=ROOT/"dev-hub/adapters/platform-component-branch-foundry-source-integrator.py"
digest=gate.digest_file(source)
REV="a"*40
INC="b"*40
contract={
 "schema":"chacha.dev/platform-component-controlled-apply-contract/v1",
 "component_id":"central-orchestrator","candidate_owner":"branch-foundry",
 "candidate_revision":REV,"incumbent_revision":INC,
 "candidate_artifact_ref":"git:candidate@"+REV,
 "incumbent_artifact_ref":"git:incumbent@"+INC,
 "qualification_workflow_name":"ChaCha DEV universal evolution coverage sync qualification",
 "approval_id":"platform-component-promotion:central-orchestrator:"+REV,
 "approval_actor":"human-platform-owner",
 "approval_evidence":"architecture-council-platform-review:sha256:test",
 "technical_review_digest":"sha256:"+"c"*64,
 "apply_mode":"SOURCE_RELEASE_CANDIDATE_INTEGRATION",
 "source_candidate_integration_authorized":True,
 "direct_runtime_mutation_authorized":False,
 "production_activation_authorized":False,
 "production_deployment_authorized":False,
 "merge_to_production_branch_authorized":False,
 "automatic_apply":False,"automatic_external_spend_eur":0
}
promotion={
 "schema":"chacha.dev/platform-component-promotion-gate/v1",
 "status":"PROMOTION_AUTHORIZED_FOR_CONTROLLED_APPLY",
 "human_approval_verified":True,"promotion_authorized":True,
 "controlled_apply_required":True,"controlled_apply_contract_created":True,
 "controlled_apply_contract":contract
}
receipt={
 "schema":"chacha.dev/adapter-provisioning-receipt/v1",
 "adapter":"branch-foundry-source-integrator-v1","version":"1.0.1",
 "applied":True,
 "source_digest":digest,"installed_digest":digest,"executable_digest":digest,
 "executable_path":"/opt/chacha-dev/adapters/platform-component/branch-foundry-source-integrator/current/branch-foundry-source-integrator",
 "probe":{"status":"PASS"}
}
runs={"workflow_runs":[
 {"name":"ChaCha DEV Branch Foundry source integrator qualification","head_sha":REV,"status":"completed","conclusion":"success"},
 {"name":"ChaCha DEV universal evolution coverage sync qualification","head_sha":REV,"status":"completed","conclusion":"success"},
 {"name":"ChaCha DEV Sentinel technical assurance","head_sha":REV,"status":"completed","conclusion":"success"}
]}

ok=gate.evaluate(ROOT,policy,promotion,registry,adapter_policy,provisioning,receipt,runs,REV)
assert ok["status"]=="BINDING_PROPOSAL_READY_AWAIT_PROTECTED_REGISTRATION",ok
assert ok["proposal_created"] is True,ok
assert ok["registration_authorized"] is False and ok["registry_mutation_authorized"] is False,ok
assert ok["human_registration_approval_request_created"] is True,ok
req=ok["registration_approval_request"]
assert req["schema"]=="chacha.dev/protected-human-approval-request/v1",req
assert req["project"]=="chacha-dev-platform" and req["operation"]=="record-approval",req
assert req["actor_requirement"]=="real-human",req
assert req["agent_or_api_approval_synthesis_forbidden"] is True,req
assert req["binding_proposal_digest"]==ok["binding_proposal_digest"],req
assert req["evidence"]=="platform-component-adapter-binding-proposal:"+ok["binding_proposal_digest"],req
assert req["registration_before_approval"] is False and req["registry_mutation_before_approval"] is False,req
proposal=ok["binding_proposal"]
assert proposal["schema"]=="chacha.dev/platform-component-adapter-binding-proposal/v1",proposal
assert proposal["component_id"]=="central-orchestrator",proposal
assert proposal["candidate_revision"]==REV and proposal["incumbent_revision"]==INC,proposal
assert proposal["binding"]["adapter_id"]=="branch-foundry-source-integrator-v1",proposal
assert proposal["binding"]["candidate_owner"]=="branch-foundry",proposal
assert proposal["binding"]["apply_mode"]=="SOURCE_RELEASE_CANDIDATE_INTEGRATION",proposal
assert proposal["binding"]["rollback_adapter_id"]=="branch-foundry-source-integrator-v1",proposal
assert proposal["binding"]["executable"].startswith("/opt/chacha-dev/adapters/platform-component/"),proposal
assert proposal["provisioned_byte_digest"]==digest,proposal
assert proposal["registration_authorized"] is False and proposal["registry_mutation_authorized"] is False,proposal

already=json.loads(json.dumps(registry))
already["adapters"]["central-orchestrator"]={"adapter_id":"something"}
r=gate.evaluate(ROOT,policy,promotion,already,adapter_policy,provisioning,receipt,runs,REV)
assert r["status"]=="BLOCKED",r
assert "component_not_already_bound" in r["blockers"],r

wrong_owner=json.loads(json.dumps(adapter_policy));wrong_owner["candidate_owner"]="capability-foundry"
r=gate.evaluate(ROOT,policy,promotion,registry,wrong_owner,provisioning,receipt,runs,REV)
assert r["status"]=="BLOCKED",r
assert "adapter_owner_matches" in r["blockers"],r

bad_digest=json.loads(json.dumps(receipt));bad_digest["executable_digest"]="sha256:"+"0"*64
r=gate.evaluate(ROOT,policy,promotion,registry,adapter_policy,provisioning,bad_digest,runs,REV)
assert r["status"]=="BLOCKED",r
assert "executable_digest_matches_source" in r["blockers"],r

missing_run={"workflow_runs":runs["workflow_runs"][:-1]}
r=gate.evaluate(ROOT,policy,promotion,registry,adapter_policy,provisioning,receipt,missing_run,REV)
assert r["status"]=="BLOCKED",r
assert "all_required_exact_sha_workflows_success" in r["blockers"],r

forged=json.loads(json.dumps(promotion));forged["human_approval_verified"]=False
r=gate.evaluate(ROOT,policy,forged,registry,adapter_policy,provisioning,receipt,runs,REV)
assert r["status"]=="BLOCKED",r
assert "human_approval_verified" in r["blockers"],r

assert policy["principles"]["automatic_registration_forbidden"] is True
assert policy["principles"]["registry_mutation_forbidden"] is True
assert policy["principles"]["protected_registration_required"] is True

print("CHACHA_DEV_PLATFORM_COMPONENT_ADAPTER_BINDING_GATE=PASS")
print("CHACHA_DEV_PLATFORM_COMPONENT_ADAPTER_BINDING_PROPOSAL=PASS")
print("CHACHA_DEV_PLATFORM_COMPONENT_ADAPTER_BINDING_EXISTING_BINDING=BLOCKED")
print("CHACHA_DEV_PLATFORM_COMPONENT_ADAPTER_BINDING_OWNER_MISMATCH=BLOCKED")
print("CHACHA_DEV_PLATFORM_COMPONENT_ADAPTER_BINDING_DIGEST_MISMATCH=BLOCKED")
print("CHACHA_DEV_PLATFORM_COMPONENT_ADAPTER_BINDING_EXACT_SHA_GATES=REQUIRED")
print("CHACHA_DEV_PLATFORM_COMPONENT_ADAPTER_BINDING_HUMAN_APPROVAL=REQUIRED")
print("CHACHA_DEV_PLATFORM_COMPONENT_ADAPTER_REGISTRATION_APPROVAL_REQUEST=PROTECTED")
print("CHACHA_DEV_PLATFORM_COMPONENT_ADAPTER_REGISTRATION_API_SYNTHESIS=NO")
print("CHACHA_DEV_PLATFORM_COMPONENT_ADAPTER_REGISTRATION_AUTHORIZED=NO")
print("CHACHA_DEV_PLATFORM_COMPONENT_ADAPTER_REGISTRY_MUTATION=NO")
print("CHACHA_DEV_PLATFORM_COMPONENT_ADAPTER_AUTOMATIC_REGISTRATION=NO")
print("CHACHA_DEV_PLATFORM_COMPONENT_ADAPTER_BINDING_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
