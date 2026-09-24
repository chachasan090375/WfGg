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

with tempfile.TemporaryDirectory(prefix="platform-apply-handoff-") as raw:
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

    op=policy["operations"]["issue-platform-component-apply-handoff"]
    assert op["profile_required"]=="platform",op
    assert op["project_required"]=="chacha-dev-platform",op
    assert op["actor_fixed"]=="central-orchestrator",op
    assert op["human_approval_revalidation_required"] is True,op
    assert op["single_use"] is True,op
    assert op["source_candidate_integration_only"] is True,op
    assert op["direct_runtime_mutation"] is False,op
    assert op["production_activation"] is False,op
    assert op["production_deployment"] is False,op
    assert op["merge_to_production_branch"] is False,op
    assert "PLATFORM_COMPONENT_APPLY_HANDOFF_ISSUED" in policy["transaction_policy"]["protected_event_types"]

    project="chacha-dev-platform"
    boot=pc.bootstrap_control_plane_operation(project,"bootstrap-test","platform",policy,ROOT)
    assert boot["status"]=="OK",boot

    cand="a"*40;inc="b"*40
    review_digest="sha256:"+"c"*64
    approval_id="platform-component-promotion:central-orchestrator:"+cand[:16]
    approval_evidence="architecture-council-platform-review:"+review_digest
    human="human-platform-owner"
    approval=pc.record_approval_operation(project,approval_id,human,approval_evidence,policy,ROOT)
    assert approval["status"]=="OK",approval

    controlled={
      "schema":"chacha.dev/platform-component-controlled-apply-contract/v1",
      "component_id":"central-orchestrator","candidate_owner":"branch-foundry",
      "candidate_revision":cand,"incumbent_revision":inc,
      "candidate_artifact_ref":"git:candidate@"+cand,"incumbent_artifact_ref":"git:incumbent@"+inc,
      "qualification_workflow_name":"ChaCha DEV universal evolution coverage sync qualification",
      "approval_id":approval_id,"approval_actor":human,"approval_evidence":approval_evidence,
      "technical_review_digest":review_digest,
      "apply_mode":"SOURCE_RELEASE_CANDIDATE_INTEGRATION",
      "source_candidate_integration_authorized":True,
      "direct_runtime_mutation_authorized":False,
      "production_activation_authorized":False,
      "production_deployment_authorized":False,
      "merge_to_production_branch_authorized":False,
      "automatic_apply":False,
      "central_orchestrator_apply_required":True,
      "candidate_owner_apply_adapter_required":True,
      "exact_revision_required":True,"rollback_required":True,
      "post_apply_exact_sha_gates_required":[
        "ChaCha DEV universal evolution coverage sync qualification",
        "ChaCha DEV Sentinel technical assurance"
      ],
      "guardian_post_apply_assurance_required":True,
      "automatic_external_spend_eur":0
    }
    gate={
      "schema":"chacha.dev/platform-component-promotion-gate/v1",
      "component_id":"central-orchestrator","candidate_revision":cand,"incumbent_revision":inc,
      "status":"PROMOTION_AUTHORIZED_FOR_CONTROLLED_APPLY",
      "human_approval_verified":True,"promotion_authorized":True,
      "controlled_apply_required":True,"controlled_apply_contract_created":True,
      "controlled_apply_contract":controlled,"automatic_apply":False,
      "production_activation_allowed":False,"direct_runtime_mutation":False,
      "central_orchestrator_remains_apply_authority":True,
      "rollback_required":True,"automatic_external_spend_eur":0
    }
    plan={
      "schema":"chacha.dev/platform-component-controlled-apply-plan/v1",
      "component_id":"central-orchestrator","candidate_owner":"branch-foundry",
      "candidate_revision":cand,"incumbent_revision":inc,
      "candidate_artifact_ref":"git:candidate@"+cand,"incumbent_artifact_ref":"git:incumbent@"+inc,
      "adapter_id":"branch-foundry-source-integrator-v1",
      "rollback_adapter_id":"branch-foundry-source-rollback-v1",
      "adapter_qualification_workflow_name":"ChaCha DEV source integration adapter qualification",
      "source_qualification_workflow_name":"ChaCha DEV universal evolution coverage sync qualification",
      "post_apply_exact_sha_gates_required":[
        "ChaCha DEV universal evolution coverage sync qualification",
        "ChaCha DEV Sentinel technical assurance"
      ],
      "guardian_post_apply_assurance_required":True,
      "exact_revision_required":True,"rollback_required":True,
      "apply_mode":"SOURCE_RELEASE_CANDIDATE_INTEGRATION",
      "central_orchestrator_apply_required":True,
      "apply_execution_authorized_by_planner":False,
      "automatic_apply":False,"direct_runtime_mutation":False,
      "production_activation_allowed":False,"production_deployment_allowed":False,
      "merge_to_production_branch_allowed":False,
      "automatic_external_spend_eur":0
    }
    planner={
      "schema":"chacha.dev/platform-component-controlled-apply-planner/v1",
      "status":"READY_FOR_CENTRAL_ORCHESTRATOR_APPLY",
      "component_id":"central-orchestrator","candidate_owner":"branch-foundry",
      "candidate_revision":cand,"incumbent_revision":inc,
      "approval_id":approval_id,"approval_actor":human,"technical_review_digest":review_digest,
      "controlled_apply_plan_ready":True,"apply_execution_authorized_by_planner":False,
      "apply_plan":plan,"automatic_apply":False,"direct_runtime_mutation":False,
      "production_activation_allowed":False,"production_deployment_allowed":False,
      "merge_to_production_branch_allowed":False,"automatic_external_spend_eur":0
    }
    gate_path=td/"promotion-gate.json";planner_path=td/"planner.json";out=td/"handoff.json"
    save(gate_path,gate);save(planner_path,planner)

    before_journal=(td/"state"/project/"audit.jsonl").read_bytes()
    issued=pc.issue_platform_component_apply_handoff(project,gate_path,planner_path,out,policy,ROOT)
    assert issued["status"]=="OK",issued
    assert issued["details"]["idempotent"] is False,issued
    assert out.is_file(),out
    h=load(out)
    assert h["schema"]=="chacha.dev/platform-component-central-apply-handoff/v1",h
    assert h["project"]==project and h["actor"]=="central-orchestrator",h
    assert h["issued_by_project_control"] is True,h
    assert h["human_approval_verified"] is True,h
    assert h["approval_id"]==approval_id and h["approval_actor"]==human,h
    assert h["approval_evidence"]==approval_evidence,h
    assert h["component_id"]=="central-orchestrator" and h["candidate_owner"]=="branch-foundry",h
    assert h["candidate_revision"]==cand and h["incumbent_revision"]==inc,h
    assert h["adapter_id"]=="branch-foundry-source-integrator-v1",h
    assert h["controlled_apply_plan_digest"]==pc.canonical_digest(plan),h
    assert h["apply_execution_authorized"] is True,h
    assert h["single_use"] is True,h
    assert h["source_candidate_integration_only"] is True,h
    assert h["rollback_required"] is True and h["guardian_pre_post_required"] is True,h
    assert h["emergency_stop_required"] is True,h
    assert h["direct_runtime_mutation_authorized"] is False,h
    assert h["production_activation_authorized"] is False,h
    assert h["production_deployment_authorized"] is False,h
    assert h["merge_to_production_branch_authorized"] is False,h
    assert h["automatic_apply"] is False,h
    journal=(td/"state"/project/"audit.jsonl").read_text(encoding="utf-8")
    assert '"event_type":"PLATFORM_COMPONENT_APPLY_HANDOFF_ISSUED"' in journal,journal
    assert (td/"state"/project/"audit.jsonl").read_bytes()!=before_journal

    # Exact replay is idempotent and creates no second audit event.
    journal_after_first=(td/"state"/project/"audit.jsonl").read_bytes()
    replay=pc.issue_platform_component_apply_handoff(project,gate_path,planner_path,out,policy,ROOT)
    assert replay["status"]=="OK" and replay["details"]["idempotent"] is True,replay
    assert (td/"state"/project/"audit.jsonl").read_bytes()==journal_after_first

    # CLI reaches the same canonical operation and remains idempotent.
    cli=run([
      sys.executable,BIN/"project-control.py","--repo-root",ROOT,"--policy",policy_path,"--json",
      "issue-platform-component-apply-handoff","--project",project,
      "--promotion-gate",gate_path,"--planner-result",planner_path,"--output",out
    ])
    assert cli.returncode==0,(cli.stdout,cli.stderr)
    cli_result=json.loads(cli.stdout)
    assert cli_result["status"]=="OK" and cli_result["details"]["idempotent"] is True,cli_result

    # Generic control events cannot forge the protected issuance event.
    fake_payload=td/"fake-handoff-event.json";save(fake_payload,{"fake":True})
    generic=pc.record_control_event(
      project,"PLATFORM_COMPONENT_APPLY_HANDOFF_ISSUED","central-orchestrator",
      fake_payload,None,None,policy,ROOT
    )
    assert generic["status"]=="BLOCKED",generic
    assert "PROTECTED_EVENT_TYPE:PLATFORM_COMPONENT_APPLY_HANDOFF_ISSUED" in generic["blockers"],generic

    # Handoff issuance independently rejects mismatched human approval lineage.
    bad_gate=json.loads(json.dumps(gate))
    bad_gate["controlled_apply_contract"]["approval_actor"]="branch-foundry"
    bad_gate_path=td/"bad-gate.json";save(bad_gate_path,bad_gate)
    bad_out=td/"bad-handoff.json"
    blocked=pc.issue_platform_component_apply_handoff(project,bad_gate_path,planner_path,bad_out,policy,ROOT)
    assert blocked["status"]=="BLOCKED",blocked
    assert "ledger_approval_actor_matches" in blocked["blockers"],blocked
    assert not bad_out.exists()

    # The agent-facing local JSON API cannot synthesize a Central Orchestrator handoff.
    request={
      "schema":"chacha.dev/project-control-request/v1",
      "project":project,"operation":"issue-platform-component-apply-handoff",
      "actor":"central-orchestrator",
      "arguments":{"repo_root":str(ROOT),"policy":str(policy_path),
                   "promotion_gate":str(gate_path),"planner_result":str(planner_path),"output":str(td/"api-handoff.json")}
    }
    api=run([sys.executable,BIN/"project-control-api.py"],json.dumps(request))
    assert api.returncode!=0,api.stdout
    api_result=json.loads(api.stdout)
    assert "REQUEST_OPERATION_UNSUPPORTED:issue-platform-component-apply-handoff" in api_result["blockers"],api_result
    assert not (td/"api-handoff.json").exists()

print("CHACHA_DEV_PLATFORM_COMPONENT_APPLY_HANDOFF=PASS")
print("CHACHA_DEV_PLATFORM_COMPONENT_APPLY_HANDOFF_PROJECT_CONTROL=CANONICAL")
print("CHACHA_DEV_PLATFORM_COMPONENT_APPLY_HANDOFF_HUMAN_APPROVAL=REVALIDATED")
print("CHACHA_DEV_PLATFORM_COMPONENT_APPLY_HANDOFF_ACTOR=CENTRAL_ORCHESTRATOR")
print("CHACHA_DEV_PLATFORM_COMPONENT_APPLY_HANDOFF_SINGLE_USE=YES")
print("CHACHA_DEV_PLATFORM_COMPONENT_APPLY_HANDOFF_AUDITED=YES")
print("CHACHA_DEV_PLATFORM_COMPONENT_APPLY_HANDOFF_IDEMPOTENT=YES")
print("CHACHA_DEV_PLATFORM_COMPONENT_APPLY_HANDOFF_GENERIC_EVENT=BLOCKED")
print("CHACHA_DEV_PLATFORM_COMPONENT_APPLY_HANDOFF_API_SYNTHESIS=NO")
print("CHACHA_DEV_PLATFORM_COMPONENT_APPLY_HANDOFF_RUNTIME_MUTATION=NO")
print("CHACHA_DEV_PLATFORM_COMPONENT_APPLY_HANDOFF_PRODUCTION_ACTIVATION=NO")
print("CHACHA_DEV_PLATFORM_COMPONENT_APPLY_HANDOFF_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
