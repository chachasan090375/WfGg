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

with tempfile.TemporaryDirectory(prefix="project-control-bootstrap-") as raw:
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

    assert policy["operations"]["bootstrap-control-plane"]["idempotent"] is True
    assert policy["operations"]["bootstrap-control-plane"]["forward_only"] is True
    assert policy["operations"]["bootstrap-control-plane"]["implicit_delete_or_rewrite_forbidden"] is True
    assert policy["principles"]["human_approval_recorded_only_via_protected_control_operation"] is True

    # 1) Fresh platform bootstrap through the canonical engines.
    project="chacha-dev-platform-test"
    first=pc.bootstrap_control_plane_operation(project,"bootstrap-test","platform",policy,ROOT)
    assert first["status"]=="OK",first
    assert first["details"]["state_created"] is True,first
    assert first["details"]["ledger_created"] is True,first
    assert first["details"]["audit_event_recorded"] is True,first
    assert first["details"]["idempotent"] is False,first

    state_path=td/"state"/project/"state.json"
    journal_path=td/"state"/project/"audit.jsonl"
    ledger_path=td/"evidence"/project/"ledger.json"
    state=load(state_path);ledger=load(ledger_path)
    assert state["schema"]=="chacha.dev/control-plane-state/v1",state
    assert state["state"]["identity"]["control_profile"]=="platform",state
    assert state["state"]["lifecycle"]["stage"]=="IDEA",state
    assert state["state"]["evidence"]["control_plane_ledger_initialized"] is True,state
    assert state["state"]["evidence"]["ledger_path"]==str(ledger_path),state
    assert ledger["schema"]=="chacha.dev/evidence-ledger/v1" and ledger["project"]==project,ledger
    journal=journal_path.read_text(encoding="utf-8")
    assert '"event_type":"PROJECT_INITIALIZED"' in journal,journal
    assert '"event_type":"EVIDENCE_RECORDED"' in journal,journal

    # Platform profile is governance-only: status is READY without application lifecycle gates.
    status=pc.status_operation(project,policy,ROOT)
    assert status["status"]=="READY",status
    assert status["details"]["control_profile"]=="platform",status
    assert status["details"]["lifecycle_managed"] is False,status
    assert status["details"]["protected_human_approval_boundary"] is True,status
    assert status["details"]["next_stage"] is None,status
    planned=pc.plan_transition(project,None,policy,ROOT)
    assert planned["status"]=="BLOCKED",planned
    assert "PLATFORM_CONTROL_PROFILE_LIFECYCLE_OPERATION_FORBIDDEN" in planned["blockers"],planned
    scheduled=pc.schedule_operation(project,None,policy,ROOT)
    assert scheduled["status"]=="BLOCKED",scheduled
    assert "PLATFORM_CONTROL_PROFILE_LIFECYCLE_OPERATION_FORBIDDEN" in scheduled["blockers"],scheduled
    advanced=pc.advance_operation(project,None,"project-owner",policy,ROOT)
    assert advanced["status"]=="BLOCKED",advanced
    assert "PLATFORM_CONTROL_PROFILE_LIFECYCLE_OPERATION_FORBIDDEN" in advanced["blockers"],advanced

    # 2) Exact replay is idempotent and creates no extra journal entry.
    before=journal_path.read_bytes()
    second=pc.bootstrap_control_plane_operation(project,"bootstrap-test","platform",policy,ROOT)
    assert second["status"]=="OK" and second["details"]["idempotent"] is True,second
    assert journal_path.read_bytes()==before

    # 3) Protected human approval boundary: system actor blocked, real human accepted.
    blocked=pc.record_approval_operation(project,"platform-component-promotion:d1",
                                         "central-orchestrator","council-review:test",policy,ROOT)
    assert blocked["status"]=="BLOCKED",blocked
    assert "HUMAN_APPROVAL_ACTOR_REQUIRED" in blocked["blockers"],blocked
    human=pc.record_approval_operation(project,"platform-component-promotion:d1",
                                       "human-bootstrap-test","council-review:test",policy,ROOT)
    assert human["status"]=="OK" and human["details"]["idempotent"] is False,human
    replay=pc.record_approval_operation(project,"platform-component-promotion:d1",
                                        "human-bootstrap-test","council-review:test",policy,ROOT)
    assert replay["status"]=="OK" and replay["details"]["idempotent"] is True,replay
    conflict=pc.record_approval_operation(project,"platform-component-promotion:d1",
                                          "different-human","different-evidence",policy,ROOT)
    assert conflict["status"]=="BLOCKED" and "APPROVAL_REPLAY_CONFLICT" in conflict["blockers"],conflict

    final_state=load(state_path);final_ledger=load(ledger_path)
    appr=final_ledger["approvals"]["platform-component-promotion:d1"]
    assert appr["status"]=="APPROVED" and appr["actor"]=="human-bootstrap-test",appr
    assert final_state["state"]["approvals"]["platform-component-promotion:d1"]["actor"]=="human-bootstrap-test"
    assert '"event_type":"APPROVAL_RECORDED"' in journal_path.read_text(encoding="utf-8")

    # 4) Forward-only resume: canonical state exists, ledger is still missing.
    resume="resume-platform-test"
    init=td/"resume-initial.json";save(init,{"identity":{"control_profile":"platform"},"lifecycle":{"stage":"IDEA"}})
    p=run([sys.executable,BIN/"control-plane-store.py","--policy",state_policy_path,
           "--root",td/"state","init","--project",resume,"--actor","bootstrap-test","--initial",init])
    assert p.returncode==0,(p.stdout,p.stderr)
    resumed=pc.bootstrap_control_plane_operation(resume,"bootstrap-test","platform",policy,ROOT)
    assert resumed["status"]=="OK",resumed
    assert resumed["details"]["state_created"] is False,resumed
    assert resumed["details"]["ledger_created"] is True,resumed
    assert load(td/"evidence"/resume/"ledger.json")["project"]==resume

    # 5) State/journal partial mismatch fails closed and does not delete the orphan.
    partial="partial-platform-test"
    partial_state=td/"state"/partial/"state.json"
    partial_state.parent.mkdir(parents=True,exist_ok=True)
    partial_state.write_text('{"sentinel":"do-not-delete"}\n',encoding="utf-8")
    partial_before=partial_state.read_bytes()
    mismatch=pc.bootstrap_control_plane_operation(partial,"bootstrap-test","platform",policy,ROOT)
    assert mismatch["status"]=="BLOCKED",mismatch
    assert "CONTROL_PLANE_STATE_JOURNAL_PARTIAL" in mismatch["blockers"],mismatch
    assert partial_state.read_bytes()==partial_before
    assert not (td/"state"/partial/"audit.jsonl").exists()

    # 6) The local JSON API reaches the same canonical engine for bootstrap.
    api_project="api-platform-test"
    request={
      "schema":"chacha.dev/project-control-request/v1",
      "project":api_project,"operation":"bootstrap-control-plane","actor":"api-bootstrap-test",
      "arguments":{"repo_root":str(ROOT),"policy":str(policy_path),"profile":"platform"}
    }
    api=run([sys.executable,BIN/"project-control-api.py"],json.dumps(request))
    assert api.returncode==0,(api.stdout,api.stderr)
    api_result=json.loads(api.stdout)
    assert api_result["status"]=="OK",api_result
    assert load(td/"state"/api_project/"state.json")["state"]["identity"]["control_profile"]=="platform"
    assert load(td/"evidence"/api_project/"ledger.json")["project"]==api_project

    # API remains unable to synthesize the protected human approval operation.
    bad_request={
      "schema":"chacha.dev/project-control-request/v1",
      "project":api_project,"operation":"record-approval","actor":"central-orchestrator",
      "arguments":{"repo_root":str(ROOT),"policy":str(policy_path),
                   "approval_id":"must-not-work","evidence":"fake"}
    }
    bad_api=run([sys.executable,BIN/"project-control-api.py"],json.dumps(bad_request))
    assert bad_api.returncode!=0,bad_api.stdout
    bad_payload=json.loads(bad_api.stdout)
    assert "REQUEST_OPERATION_UNSUPPORTED:record-approval" in bad_payload["blockers"],bad_payload

print("CHACHA_DEV_PROJECT_CONTROL_BOOTSTRAP=PASS")
print("CHACHA_DEV_PROJECT_CONTROL_BOOTSTRAP_CANONICAL_ENGINES=YES")
print("CHACHA_DEV_PROJECT_CONTROL_BOOTSTRAP_IDEMPOTENT=YES")
print("CHACHA_DEV_PROJECT_CONTROL_PLATFORM_STATUS=READY")
print("CHACHA_DEV_PROJECT_CONTROL_PLATFORM_APPLICATION_LIFECYCLE=FORBIDDEN")
print("CHACHA_DEV_PROJECT_CONTROL_BOOTSTRAP_FORWARD_ONLY=YES")
print("CHACHA_DEV_PROJECT_CONTROL_BOOTSTRAP_PARTIAL_FAIL_CLOSED=YES")
print("CHACHA_DEV_PROJECT_CONTROL_HUMAN_APPROVAL_PROTECTED=YES")
print("CHACHA_DEV_PROJECT_CONTROL_APPROVAL_REPLAY_IDEMPOTENT=YES")
print("CHACHA_DEV_PROJECT_CONTROL_API_APPROVAL_SYNTHESIS=NO")
print("CHACHA_DEV_PROJECT_CONTROL_BOOTSTRAP_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
