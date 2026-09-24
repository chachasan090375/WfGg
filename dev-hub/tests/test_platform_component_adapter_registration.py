#!/usr/bin/env python3
from __future__ import annotations
import importlib.util,json,subprocess,sys,tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BIN=ROOT/"dev-hub/bin"
CFG=ROOT/"dev-hub/config"

def load(p):return json.loads(Path(p).read_text(encoding="utf-8"))
def save(p,x):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
def run(cmd,stdin=None):
    return subprocess.run([str(x) for x in cmd],input=stdin,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                          text=True,check=False,timeout=90)

spec=importlib.util.spec_from_file_location("project_control",BIN/"project-control.py")
assert spec and spec.loader
pc=importlib.util.module_from_spec(spec);spec.loader.exec_module(pc)

with tempfile.TemporaryDirectory(prefix="platform-adapter-registration-") as raw:
    td=Path(raw)
    state_policy=load(CFG/"control-plane-state.v1.json")
    state_policy["storage"]["runtime_root"]=str(td/"state")
    state_policy_path=td/"control-plane-state.json";save(state_policy_path,state_policy)

    policy=load(CFG/"project-control.v1.json")
    for key,name in (
      ("state_root","state"),("evidence_root","evidence"),("plans_root","plans"),
      ("health_root","health"),("runs_root","runs"),("transactions_root","transactions"),
      ("locks_root","locks")
    ):
        policy["runtime"][key]=str(td/name)
    policy["repository_paths"]["control_plane_state"]=str(state_policy_path)
    policy["engine_paths"]["control_plane_store"]=str(BIN/"control-plane-store.py")
    policy["engine_paths"]["evidence_collector"]=str(BIN/"evidence-collector.py")
    policy_path=td/"project-control.json";save(policy_path,policy)

    op=policy["operations"]["issue-platform-component-adapter-registration"]
    assert op["profile_required"]=="platform",op
    assert op["project_required"]=="chacha-dev-platform",op
    assert op["actor_fixed"]=="central-orchestrator",op
    assert op["separate_human_registration_approval_required"] is True,op
    assert op["additive_registry_write_only"] is True,op
    assert op["overwrite_forbidden"] is True and op["delete_forbidden"] is True,op
    assert op["single_use"] is True,op
    assert op["direct_runtime_mutation"] is False,op
    assert op["production_activation"] is False and op["production_deployment"] is False,op
    assert op["source_integration_before_post_registration_gates"] is False,op
    assert "PLATFORM_COMPONENT_ADAPTER_REGISTRATION_ISSUED" in policy["transaction_policy"]["protected_event_types"]

    project="chacha-dev-platform"
    boot=pc.bootstrap_control_plane_operation(project,"bootstrap-test","platform",policy,ROOT)
    assert boot["status"]=="OK",boot

    cand="a"*40;inc="b"*40
    proposal={
      "schema":"chacha.dev/platform-component-adapter-binding-proposal/v1",
      "component_id":"central-orchestrator","candidate_owner":"branch-foundry",
      "candidate_revision":cand,"incumbent_revision":inc,
      "candidate_artifact_ref":"git:candidate@"+cand,
      "incumbent_artifact_ref":"git:incumbent@"+inc,
      "approval_id":"platform-component-promotion:central-orchestrator:"+cand,
      "approval_actor":"human-platform-owner",
      "approval_evidence":"architecture-council-platform-review:sha256:test",
      "technical_review_digest":"sha256:"+"c"*64,
      "qualification_revision":"d"*40,
      "binding":{
        "adapter_id":"branch-foundry-source-integrator-v1","status":"QUALIFIED",
        "candidate_owner":"branch-foundry","apply_mode":"SOURCE_RELEASE_CANDIDATE_INTEGRATION",
        "reversible":True,"rollback_adapter_id":"branch-foundry-source-integrator-v1",
        "exact_revision_enforced":True,
        "executable":"/opt/chacha-dev/adapters/platform-component/branch-foundry-source-integrator/current/branch-foundry-source-integrator",
        "qualification_workflow_name":"ChaCha DEV Branch Foundry source integrator qualification",
        "direct_runtime_mutation":False,"production_activation":False,
        "production_deployment":False,"merge_to_production_branch":False,
        "automatic_apply":False,"automatic_external_spend_eur":0
      },
      "provisioned_byte_digest":"sha256:"+"e"*64,
      "registration_authorized":False,"registry_mutation_authorized":False,
      "protected_registration_required":True,"automatic_registration":False,
      "automatic_external_spend_eur":0
    }
    proposal_digest=pc.canonical_digest(proposal)
    approval_id="platform-component-adapter-registration:central-orchestrator:"+cand
    approval_evidence="platform-component-adapter-binding-proposal:"+proposal_digest
    request={
      "schema":"chacha.dev/protected-human-approval-request/v1",
      "project":project,"operation":"record-approval","approval_id":approval_id,
      "actor_requirement":"real-human","evidence":approval_evidence,
      "binding_proposal_digest":proposal_digest,
      "component_id":"central-orchestrator","candidate_revision":cand,"incumbent_revision":inc,
      "adapter_id":"branch-foundry-source-integrator-v1","candidate_owner":"branch-foundry",
      "project_control_protected_path_required":True,
      "agent_or_api_approval_synthesis_forbidden":True,
      "registration_before_approval":False,"registry_mutation_before_approval":False,
      "automatic_external_spend_eur":0
    }
    gate={
      "schema":"chacha.dev/platform-component-adapter-binding-gate/v1",
      "status":"BINDING_PROPOSAL_READY_AWAIT_PROTECTED_REGISTRATION",
      "component_id":"central-orchestrator","candidate_revision":cand,
      "proposal_created":True,"binding_proposal":proposal,
      "binding_proposal_digest":proposal_digest,
      "human_registration_approval_request_created":True,
      "registration_approval_request":request,
      "registration_authorized":False,"registry_mutation_authorized":False,
      "automatic_registration":False,"automatic_external_spend_eur":0
    }
    gate_path=td/"binding-gate.json";out=td/"registration-contract.json";save(gate_path,gate)

    # No separate registration approval: hard block, no contract.
    denied=pc.issue_platform_component_adapter_registration(project,gate_path,out,policy,ROOT)
    assert denied["status"]=="BLOCKED",denied
    assert "ledger_approval_status" in denied["blockers"],denied
    assert not out.exists()

    # System actor cannot record the registration approval.
    sys_approval=pc.record_approval_operation(project,approval_id,"central-orchestrator",approval_evidence,policy,ROOT)
    assert sys_approval["status"]=="BLOCKED",sys_approval
    assert "HUMAN_APPROVAL_ACTOR_REQUIRED" in sys_approval["blockers"],sys_approval

    human="human-platform-owner"
    approval=pc.record_approval_operation(project,approval_id,human,approval_evidence,policy,ROOT)
    assert approval["status"]=="OK",approval

    before_journal=(td/"state"/project/"audit.jsonl").read_bytes()
    issued=pc.issue_platform_component_adapter_registration(project,gate_path,out,policy,ROOT)
    assert issued["status"]=="OK",issued
    assert issued["details"]["idempotent"] is False,issued
    assert out.is_file(),out
    c=load(out)
    assert c["schema"]=="chacha.dev/platform-component-adapter-registration-contract/v1",c
    assert c["project"]==project and c["actor"]=="central-orchestrator",c
    assert c["issued_by_project_control"] is True and c["human_approval_verified"] is True,c
    assert c["approval_id"]==approval_id and c["approval_actor"]==human,c
    assert c["approval_evidence"]==approval_evidence,c
    assert c["binding_proposal_digest"]==proposal_digest,c
    assert c["component_id"]=="central-orchestrator" and c["candidate_owner"]=="branch-foundry",c
    assert c["candidate_revision"]==cand and c["incumbent_revision"]==inc,c
    assert c["adapter_id"]=="branch-foundry-source-integrator-v1",c
    assert c["registry_key"]=="central-orchestrator",c
    assert c["exact_registry_binding"]==proposal["binding"],c
    assert c["registration_authorized"] is True,c
    assert c["registry_mutation_authorized_for_dedicated_writer"] is True,c
    assert c["additive_write_only"] is True,c
    assert c["overwrite_authorized"] is False and c["delete_authorized"] is False,c
    assert c["default_deny_must_be_preserved"] is True,c
    assert c["single_use"] is True,c
    assert c["source_integration_authorized"] is False,c
    assert set(c["post_registration_exact_sha_gates_required"])=={
      "ChaCha DEV platform adapter binding gate qualification",
      "ChaCha DEV universal evolution coverage sync qualification",
      "ChaCha DEV Sentinel technical assurance"
    },c
    assert c["direct_runtime_mutation_authorized"] is False,c
    assert c["production_activation_authorized"] is False and c["production_deployment_authorized"] is False,c
    assert c["merge_to_production_branch_authorized"] is False and c["automatic_apply"] is False,c
    journal=(td/"state"/project/"audit.jsonl").read_text(encoding="utf-8")
    assert '"event_type":"PLATFORM_COMPONENT_ADAPTER_REGISTRATION_ISSUED"' in journal,journal
    assert (td/"state"/project/"audit.jsonl").read_bytes()!=before_journal

    # The operation still has not touched the canonical source registry.
    registry=load(CFG/"platform-component-apply-adapter-registry.v1.json")
    assert registry["default_admission"]=="DENY" and registry["adapters"]=={},registry

    # Exact replay is idempotent and creates no second audit event.
    journal_after=(td/"state"/project/"audit.jsonl").read_bytes()
    replay=pc.issue_platform_component_adapter_registration(project,gate_path,out,policy,ROOT)
    assert replay["status"]=="OK" and replay["details"]["idempotent"] is True,replay
    assert (td/"state"/project/"audit.jsonl").read_bytes()==journal_after

    # Generic control event cannot forge issuance.
    fake=td/"fake.json";save(fake,{"fake":True})
    generic=pc.record_control_event(project,"PLATFORM_COMPONENT_ADAPTER_REGISTRATION_ISSUED",
                                    "central-orchestrator",fake,None,None,policy,ROOT)
    assert generic["status"]=="BLOCKED",generic
    assert "PROTECTED_EVENT_TYPE:PLATFORM_COMPONENT_ADAPTER_REGISTRATION_ISSUED" in generic["blockers"],generic

    # Proposal digest mismatch fails closed.
    bad=json.loads(json.dumps(gate));bad["binding_proposal_digest"]="sha256:"+"0"*64
    bad_path=td/"bad-gate.json";save(bad_path,bad)
    blocked=pc.issue_platform_component_adapter_registration(project,bad_path,td/"bad-contract.json",policy,ROOT)
    assert blocked["status"]=="BLOCKED",blocked
    assert "proposal_digest_matches" in blocked["blockers"],blocked

    # Agent-facing local API cannot synthesize registration issuance.
    api_request={
      "schema":"chacha.dev/project-control-request/v1","project":project,
      "operation":"issue-platform-component-adapter-registration","actor":"central-orchestrator",
      "arguments":{"binding_gate":str(gate_path),"output":str(td/"api-contract.json")}
    }
    api=run([sys.executable,BIN/"project-control-api.py"],json.dumps(api_request))
    assert api.returncode!=0,api.stdout
    api_result=json.loads(api.stdout)
    assert "REQUEST_OPERATION_UNSUPPORTED:issue-platform-component-adapter-registration" in api_result["blockers"],api_result
    assert not (td/"api-contract.json").exists()

print("CHACHA_DEV_PLATFORM_COMPONENT_ADAPTER_REGISTRATION_CONTRACT=PASS")
print("CHACHA_DEV_PLATFORM_COMPONENT_ADAPTER_REGISTRATION_PROJECT_CONTROL=CANONICAL")
print("CHACHA_DEV_PLATFORM_COMPONENT_ADAPTER_REGISTRATION_SEPARATE_HUMAN_APPROVAL=YES")
print("CHACHA_DEV_PLATFORM_COMPONENT_ADAPTER_REGISTRATION_SYSTEM_APPROVAL=BLOCKED")
print("CHACHA_DEV_PLATFORM_COMPONENT_ADAPTER_REGISTRATION_ADDITIVE_ONLY=YES")
print("CHACHA_DEV_PLATFORM_COMPONENT_ADAPTER_REGISTRATION_OVERWRITE=NO")
print("CHACHA_DEV_PLATFORM_COMPONENT_ADAPTER_REGISTRATION_DELETE=NO")
print("CHACHA_DEV_PLATFORM_COMPONENT_ADAPTER_REGISTRATION_SOURCE_INTEGRATION=NO")
print("CHACHA_DEV_PLATFORM_COMPONENT_ADAPTER_REGISTRATION_AUDITED=YES")
print("CHACHA_DEV_PLATFORM_COMPONENT_ADAPTER_REGISTRATION_IDEMPOTENT=YES")
print("CHACHA_DEV_PLATFORM_COMPONENT_ADAPTER_REGISTRATION_GENERIC_EVENT=BLOCKED")
print("CHACHA_DEV_PLATFORM_COMPONENT_ADAPTER_REGISTRATION_API_SYNTHESIS=NO")
print("CHACHA_DEV_PLATFORM_COMPONENT_ADAPTER_REGISTRY_MUTATION_DURING_ISSUANCE=NO")
print("CHACHA_DEV_PLATFORM_COMPONENT_ADAPTER_REGISTRATION_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
