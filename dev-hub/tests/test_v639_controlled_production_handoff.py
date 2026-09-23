#!/usr/bin/env python3
from __future__ import annotations
import json,subprocess,sys,tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BIN=ROOT/"dev-hub/bin"
CFG=ROOT/"dev-hub/config"

def load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))

def run(args):
    return subprocess.run(list(map(str,args)),cwd=str(ROOT),stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False)

policy=load(CFG/"controlled-production-handoff.v1.json")
assert policy["schema"]=="chacha.dev/controlled-production-handoff/v1"
assert policy["scope"]=="RELEASE_TO_OPERATE"
assert policy["lifecycle"]["from"]=="RELEASE"
assert policy["lifecycle"]["to"]=="OPERATE"
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

with tempfile.TemporaryDirectory(prefix="v639-graph-") as td:
    graph=Path(td)/"release-operate.json"
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
    assert artifact_ids==set(policy["evidence"]["required"]),(artifact_ids,policy["evidence"]["required"])
    assert gate_ids==set(policy["gates"]["required"]),(gate_ids,policy["gates"]["required"])
    expected_dependencies={x["id"] for x in g["tasks"] if x["kind"] in {"artifact","gate"}}
    assert set(approval["depends_on"])==expected_dependencies,(approval["depends_on"],expected_dependencies)

pc_source=(BIN/"project-control.py").read_text(encoding="utf-8")
assert "def record_approval_operation" in pc_source
assert "HUMAN_APPROVAL_ACTOR_REQUIRED" in pc_source
assert "APPROVAL_RECORDED" in pc_source
assert "idempotent" in pc_source

print("CHACHA_DEV_V639_PRODUCTION_APPROVAL_BOUNDARY=PASS")
print("CHACHA_DEV_V639_RELEASE_OPERATE_TASK_GRAPH=PASS")
print("CHACHA_DEV_V639_CONTROLLED_ADAPTER_REQUIRED=PASS")
print("CHACHA_DEV_V639_REAL_TARGET_EVIDENCE_REQUIRED=PASS")
print("CHACHA_DEV_V639_ROLLBACK_REQUIRED=PASS")
print("CHACHA_DEV_V639_REAL_PRODUCTION_TARGET=NO")
print("CHACHA_DEV_V639_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
