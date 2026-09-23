#!/usr/bin/env python3
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BIN=ROOT/"dev-hub/bin"
CFG=ROOT/"dev-hub/config"

def load(p:Path):
    return json.loads(Path(p).read_text(encoding="utf-8"))

def save(p:Path,x):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")

def run(args,cwd=ROOT):
    return subprocess.run(list(map(str,args)),cwd=str(cwd),
                          stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                          text=True,check=False)

policy=load(CFG/"controlled-production-handoff.v1.json")
assert policy["schema"]=="chacha.dev/controlled-production-handoff/v1"
assert policy["scope"]=="RELEASE_TO_OPERATE"
assert policy["lifecycle"]["approval_id"]=="production-deployment"
assert policy["lifecycle"]["first_production_mutation_requires_approval"] is True
assert policy["deployment"]["controller_direct_production_mutation"] is False
assert policy["deployment"]["controlled_adapter_required"] is True
assert policy["deployment"]["explicit_target_required"] is True
assert policy["deployment"]["reversible_first_pilot"] is True
assert policy["evidence"]["real_target_required"] is True
assert policy["evidence"]["synthetic_or_local_preview_not_sufficient"] is True
assert policy["gates"]["fail_closed"] is True
assert policy["rollback"]["required"] is True
assert policy["rollback"]["must_be_executable"] is True
assert policy["rollback"]["emergency_stop_out_of_band"] is True
assert policy["economics"]["automatic_external_spend_eur"]==0
assert policy["pilot"]["real_production_target"] is False
assert policy["pilot"]["status"]=="DESIGN_ONLY"
assert policy["pilot"]["terminal_marker"]=="CHACHA_DEV_V639_INSTALL=PASS"

adapter_profile=load(CFG/"controlled-production-adapter-dry-run.v1.json")
assert adapter_profile["profile"]=="dry-run-v1"
assert adapter_profile["production_capable"] is False
assert adapter_profile["real_production_target"] is False
assert adapter_profile["reversible"] is True
assert adapter_profile["network_mutation"] is False
assert adapter_profile["external_spend_eur"]==0

lifecycle=load(CFG/"lifecycle.v1.json")
rule=lifecycle["transitions"]["RELEASE->OPERATE"]
assert lifecycle["principles"]["production_change_requires_approval"] is True
assert rule["required_approvals"]==["production-deployment"],rule
assert set(rule["required_artifacts"])==set(policy["evidence"]["required"])
assert set(rule["required_gates"])==set(policy["gates"]["required"])

project_control=load(CFG/"project-control.v1.json")
principles=project_control["principles"]
assert principles["production_deployment_requires_explicit_human_approval"] is True
assert principles["release_and_operate_are_distinct"] is True
assert principles["production_deployment_must_use_controlled_adapter"] is True
assert principles["production_evidence_must_come_from_real_target"] is True
op=project_control["operations"]["controlled-production-handoff"]
assert op["human_boundary"]=="production-deployment"
assert op["production_mutation_before_approval"] is False
assert op["controlled_adapter_required"] is True
assert op["post_deploy_real_evidence_required"] is True
assert op["automatic_external_spend_eur"]==0

# RELEASE -> OPERATE graph must now expose one real human approval task.
with tempfile.TemporaryDirectory(prefix="v639-graph-") as tmp:
    graph=Path(tmp)/"release-operate.json"
    p=run([
      sys.executable,BIN/"task-graph-engine.py",
      "--project","v639-policy-test",
      "--transition","RELEASE->OPERATE",
      "--lifecycle",CFG/"lifecycle.v1.json",
      "--quality",CFG/"quality-gates.v1.json",
      "--catalog",CFG/"evidence-catalog.v1.json",
      "--orchestration",CFG/"orchestration-policy.v1.json",
      "--output",graph
    ])
    assert p.returncode==0,(p.stdout,p.stderr)
    g=load(graph)
    approvals=[x for x in g["tasks"] if x["kind"]=="approval"]
    assert len(approvals)==1,approvals
    approval=approvals[0]
    assert approval["id"]=="approval:production-deployment",approval
    assert approval["verification"]["mode"]=="human",approval
    assert approval["blocking"] is True,approval
    artifact_ids={x["id"].split(":",1)[1] for x in g["tasks"] if x["kind"]=="artifact"}
    gate_ids={x["id"].split(":",1)[1] for x in g["tasks"] if x["kind"]=="gate"}
    assert artifact_ids==set(policy["evidence"]["required"])
    assert gate_ids==set(policy["gates"]["required"])
    dependencies={x["id"] for x in g["tasks"] if x["kind"] in {"artifact","gate"}}
    assert set(approval["depends_on"])==dependencies

# Real two-phase controller + protected approval + reversible dry-run adapter.
with tempfile.TemporaryDirectory(prefix="v639-controller-") as tmp:
    td=Path(tmp)
    project="v639-controller-test"
    revision="b"*40
    target="dry-run://pilot-target"

    state_policy=load(CFG/"control-plane-state.v1.json")
    state_policy["storage"]["runtime_root"]=str(td/"state")
    state_policy_path=td/"control-plane-state.json"
    save(state_policy_path,state_policy)

    pc_policy=load(CFG/"project-control.v1.json")
    for key,name in (
      ("state_root","state"),("evidence_root","evidence"),("plans_root","plans"),
      ("health_root","health"),("runs_root","runs"),("transactions_root","transactions"),
      ("locks_root","locks")
    ):
        pc_policy["runtime"][key]=str(td/name)
    pc_policy["repository_paths"]["control_plane_state"]=str(state_policy_path)
    pc_policy["engine_paths"]["control_plane_store"]=str(BIN/"control-plane-store.py")
    pc_policy_path=td/"project-control.json"
    save(pc_policy_path,pc_policy)

    initial=td/"initial.json"
    save(initial,{"lifecycle":{"stage":"RELEASE"},"identity":{"test":"v639"}})
    p=run([
      sys.executable,BIN/"control-plane-store.py",
      "--policy",state_policy_path,"--root",td/"state",
      "init","--project",project,"--actor","v639-test","--initial",initial
    ])
    assert p.returncode==0,(p.stdout,p.stderr)

    ledger=td/"evidence"/project/"ledger.json"
    save(ledger,{
      "schema":"chacha.dev/evidence-ledger/v1",
      "project":project,"artifacts":{},"gates":{},"approvals":{},
      "risk_acceptances":[],"history":[]
    })

    release_proof=td/"release-proof.json"
    save(release_proof,{
      "schema":"chacha.dev/golden-path-result/v1",
      "project_id":project,"revision":revision,
      "status":"PASS","lifecycle_stage":"RELEASE"
    })
    out=td/"handoff"

    initial_cmd=[
      sys.executable,BIN/"controlled-production-handoff-controller.py",
      "--repo-root",ROOT,
      "--project-control-policy",pc_policy_path,
      "--adapter-profile",CFG/"controlled-production-adapter-dry-run.v1.json",
      "--project",project,"--revision",revision,
      "--target",target,"--release-proof",release_proof,
      "--output-dir",out
    ]
    p=run(initial_cmd)
    assert p.returncode==4,(p.returncode,p.stdout,p.stderr)
    assert "CHACHA_DEV_V639_HANDOFF=AWAITING_DEPLOYMENT_APPROVAL" in p.stdout
    assert "CHACHA_DEV_V639_PREAPPROVAL_PRODUCTION_MUTATION=NO" in p.stdout
    first=load(out/"handoff-result.json")
    assert first["status"]=="AWAITING_DEPLOYMENT_APPROVAL"
    assert first["operate_advanced"] is False
    assert first["real_production_target"] is False
    assert "production-deployment" not in (load(ledger).get("approvals") or {})
    state=load(td/"state"/project/"state.json")
    assert state["state"]["lifecycle"]["stage"]=="RELEASE"

    # Preloading an approval into the initial invocation is forbidden.
    p=run(initial_cmd+["--human-approval-id","should-not-work","--human-actor","human-test"])
    assert p.returncode!=0
    assert "V639_INITIAL_RUN_MUST_NOT_PRELOAD_APPROVAL" in p.stderr+p.stdout

    resume_cmd=initial_cmd+[
      "--resume-from-awaiting-deployment-approval",
      "--human-approval-id","v639-human-approval-evidence",
      "--human-actor","human-test"
    ]
    p=run(resume_cmd)
    assert p.returncode==0,(p.returncode,p.stdout,p.stderr)
    for marker in (
      "CHACHA_DEV_V639_RESUME_CHECKPOINT=PASS",
      "CHACHA_DEV_V639_PROTECTED_DEPLOYMENT_APPROVAL=PASS",
      "CHACHA_DEV_V639_ADAPTER_DEPLOY_DRY_RUN=PASS",
      "CHACHA_DEV_V639_ADAPTER_HEALTH_DRY_RUN=PASS",
      "CHACHA_DEV_V639_ADAPTER_ROLLBACK_DRY_RUN=PASS",
      "CHACHA_DEV_V639_ROLLBACK_PROVEN=PASS",
      "CHACHA_DEV_V639_PRODUCTION_MUTATION=NO",
      "CHACHA_DEV_V639_OPERATE_ADVANCED=NO",
      "CHACHA_DEV_V639_DRY_RUN=PASS"
    ):
        assert marker in p.stdout,(marker,p.stdout)

    final=load(out/"handoff-result.json")
    assert final["status"]=="DRY_RUN_COMPLETE"
    assert final["protected_approval_transaction"]=="PASS"
    assert final["rollback_proven"] is True
    assert final["production_mutation"] is False
    assert final["real_production_target"] is False
    assert final["operate_advanced"] is False
    assert load(final["deployment_receipt"])["production_mutation"] is False
    assert load(final["health_receipt"])["status"]=="PASS"
    assert load(final["rollback_receipt"])["rollback_proven"] is True

    recorded=(load(ledger).get("approvals") or {}).get("production-deployment") or {}
    assert recorded["status"]=="APPROVED"
    assert recorded["actor"]=="human-test"
    assert recorded["evidence"]=="v639-human-approval-evidence"

    # Dry-run qualification must leave the authoritative lifecycle at RELEASE.
    state=load(td/"state"/project/"state.json")
    assert state["state"]["lifecycle"]["stage"]=="RELEASE"

controller=(BIN/"controlled-production-handoff-controller.py").read_text(encoding="utf-8")
adapter=(BIN/"controlled-production-adapter.py").read_text(encoding="utf-8")
assert "record-approval" in controller
assert "production-deployment" in controller
assert "V639_INITIAL_RUN_MUST_NOT_PRELOAD_APPROVAL" in controller
assert "V639_DRY_RUN_MUST_NOT_ADVANCE_OPERATE" in controller
assert "production_mutation" in adapter
assert "real_production_target" in adapter
assert "V639_DRY_RUN_TARGET_SCHEME_REQUIRED" in adapter

print("CHACHA_DEV_V639_PRODUCTION_APPROVAL_BOUNDARY=PASS")
print("CHACHA_DEV_V639_RELEASE_OPERATE_TASK_GRAPH=PASS")
print("CHACHA_DEV_V639_TRUE_TWO_PHASE_DEPLOYMENT_HANDOFF=PASS")
print("CHACHA_DEV_V639_PROTECTED_APPROVAL_TRANSACTION=PASS")
print("CHACHA_DEV_V639_CONTROLLED_ADAPTER_DRY_RUN=PASS")
print("CHACHA_DEV_V639_ROLLBACK_PROVEN=PASS")
print("CHACHA_DEV_V639_OPERATE_ADVANCED=NO")
print("CHACHA_DEV_V639_REAL_PRODUCTION_TARGET=NO")
print("CHACHA_DEV_V639_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
