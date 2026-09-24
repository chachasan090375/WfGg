#!/usr/bin/env python3
"""ChaCha DEV HUB Project Control V1.1.

Unified local control surface for one project. It does not expose a network
listener. The control-plane journal/projection is canonical. Mutating operations
are serialized per project, recheck integrity, and delegate to specialist
engines using structured argv without shell interpolation.
"""
from __future__ import annotations

import argparse
import copy
import fcntl
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import trusted_dispatch_learning as tdl
import agent_observation_bus as aob

POLICY_SCHEMA = "chacha.dev/project-control/v1"
STATE_SCHEMA = "chacha.dev/control-plane-state/v1"
LEDGER_SCHEMA = "chacha.dev/evidence-ledger/v1"
RESPONSE_SCHEMA = "chacha.dev/project-control-response/v1"
RECEIPT_SCHEMA = "chacha.dev/control-transaction-receipt/v1"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit(f"FILE_NOT_FOUND={path}")
    except json.JSONDecodeError as exc:
        raise SystemExit(f"JSON_INVALID={path}:{exc.lineno}:{exc.colno}:{exc.msg}")
    if not isinstance(value, dict):
        raise SystemExit(f"JSON_ROOT_NOT_OBJECT={path}")
    return value


def save(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(value, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def canonical_digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def response(project: str, operation: str, status: str, summary: str,
             details: dict[str, Any] | None = None, blockers: list[str] | None = None,
             next_actions: list[str] | None = None, artifacts: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "schema": RESPONSE_SCHEMA,
        "project": project,
        "operation": operation,
        "status": status,
        "observed_at": now_iso(),
        "summary": summary,
        "details": details or {},
        "blockers": blockers or [],
        "next_actions": next_actions or [],
        "artifacts": artifacts or [],
    }


def emit(value: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(value, indent=2, ensure_ascii=False))
        return
    print(f"PROJECT={value['project']}")
    print(f"OPERATION={value['operation']}")
    print(f"STATUS={value['status']}")
    print(f"SUMMARY={value['summary']}")
    for item in value.get("blockers") or []:
        print(f"BLOCKER={item}")
    for item in value.get("next_actions") or []:
        print(f"NEXT={item}")
    for key, item in (value.get("details") or {}).items():
        if isinstance(item, (str, int, float, bool)) or item is None:
            print(f"{key.upper()}={item}")


def resolve_repo(repo_root: Path, configured: str) -> Path:
    path = Path(configured)
    return path if path.is_absolute() else repo_root / path


def project_paths(policy: dict[str, Any], project: str) -> dict[str, Path]:
    runtime = policy.get("runtime") or {}
    state_root = Path(str(runtime.get("state_root", "/opt/chacha-dev/runtime/state")))
    evidence_root = Path(str(runtime.get("evidence_root", "/opt/chacha-dev/runtime/evidence")))
    plans_root = Path(str(runtime.get("plans_root", "/opt/chacha-dev/runtime/plans")))
    health_root = Path(str(runtime.get("health_root", "/opt/chacha-dev/runtime/health")))
    runs_root = Path(str(runtime.get("runs_root", "/opt/chacha-dev/runtime/runs")))
    transactions_root = Path(str(runtime.get("transactions_root", "/opt/chacha-dev/runtime/transactions")))
    locks_root = Path(str(runtime.get("locks_root", "/opt/chacha-dev/runtime/locks/control")))
    return {
        "state": state_root / project / "state.json",
        "journal": state_root / project / "audit.jsonl",
        "ledger": evidence_root / project / "ledger.json",
        "plans": plans_root / project,
        "health": health_root / project / "providers.json",
        "runs": runs_root / project,
        "transactions": transactions_root / project,
        "lock": locks_root / f"{project}.lock",
    }


@contextmanager
def project_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as fh:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


def run_tool(tool: Path, argv: list[str], timeout: int = 60) -> tuple[int, str, str]:
    if not tool.exists():
        return 127, "", f"TOOL_NOT_FOUND={tool}"
    try:
        proc = subprocess.run(
            [sys.executable, str(tool), *argv],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            shell=False,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return 124, "", f"TOOL_TIMEOUT={tool}"
    return proc.returncode, proc.stdout, proc.stderr


def parse_kv(text: str) -> tuple[dict[str, str], list[str]]:
    values: dict[str, str] = {}
    blockers: list[str] = []
    for line in text.splitlines():
        if line.startswith("BLOCKER="):
            blockers.append(line.split("=", 1)[1])
        elif "=" in line and not line.startswith("==="):
            key, value = line.split("=", 1)
            if key and " " not in key:
                values[key] = value
    return values, blockers


def next_stage(lifecycle: dict[str, Any], current: str) -> str | None:
    stages = list(lifecycle.get("stages") or [])
    if current not in stages:
        return None
    idx = stages.index(current)
    return stages[idx + 1] if idx + 1 < len(stages) else None


def state_policy_root(policy: dict[str, Any], repo_root: Path) -> tuple[Path, Path]:
    refs = policy.get("repository_paths") or {}
    state_policy = resolve_repo(repo_root, refs["control_plane_state"])
    configured = (load(state_policy).get("storage") or {}).get("runtime_root", "/opt/chacha-dev/runtime/state")
    return state_policy, Path(str(configured))


def state_verify_raw(project: str, policy: dict[str, Any], repo_root: Path) -> tuple[int, dict[str, str], str, str]:
    tools = policy.get("engine_paths") or {}
    state_policy, root = state_policy_root(policy, repo_root)
    rc, stdout, stderr = run_tool(resolve_repo(repo_root, tools["control_plane_store"]), [
        "--policy", str(state_policy), "--root", str(root), "verify", "--project", project,
    ])
    values, _ = parse_kv(stdout)
    return rc, values, stdout, stderr


def store_record(project: str, event_type: str, actor: str, payload: Path | None, patch: Path | None,
                 references: Path | None, policy: dict[str, Any], repo_root: Path) -> tuple[int, dict[str, str], str, str]:
    tools = policy.get("engine_paths") or {}
    state_policy, root = state_policy_root(policy, repo_root)
    argv = [
        "--policy", str(state_policy), "--root", str(root), "record",
        "--project", project, "--event-type", event_type, "--actor", actor,
    ]
    if payload:
        argv += ["--payload", str(payload)]
    if patch:
        argv += ["--patch", str(patch)]
    if references:
        argv += ["--references", str(references)]
    rc, stdout, stderr = run_tool(resolve_repo(repo_root, tools["control_plane_store"]), argv)
    values, _ = parse_kv(stdout)
    return rc, values, stdout, stderr


def lifecycle_check(project: str, target: str, projection: dict[str, Any], ledger: Path,
                    lifecycle: Path, quality: Path, engine: Path) -> tuple[dict[str, str], list[str], int, str]:
    stage = str(((projection.get("state") or {}).get("lifecycle") or {}).get("stage") or "UNKNOWN")
    with tempfile.TemporaryDirectory(prefix="chacha-project-control-") as td:
        ephemeral = Path(td) / "lifecycle-state.json"
        save(ephemeral, {
            "schema": "chacha.dev/project-lifecycle-state/v1",
            "project": project,
            "current_stage": stage,
            "created_at": projection.get("created_at") or now_iso(),
            "updated_at": projection.get("updated_at") or now_iso(),
            "history": [],
        })
        rc, out, err = run_tool(engine, [
            "--lifecycle", str(lifecycle),
            "check",
            "--state", str(ephemeral),
            "--target", target,
            "--evidence", str(ledger),
            "--quality-gates", str(quality),
        ])
    values, blockers = parse_kv(out)
    return values, blockers, rc, err.strip()


def pending_transactions(path: Path) -> list[str]:
    if not path.exists():
        return []
    out: list[str] = []
    for receipt in sorted(path.glob("*/receipt.json")):
        try:
            value = load(receipt)
        except SystemExit:
            out.append(f"CONTROL_TRANSACTION_RECEIPT_INVALID:{receipt}")
            continue
        status = str(value.get("status") or "UNKNOWN")
        if status not in {"COMMITTED", "VERIFIED_ONLY", "FAILED"}:
            out.append(f"CONTROL_TRANSACTION_PENDING:{value.get('transaction_id') or receipt.parent.name}:{status}")
    return out


def status_operation(project: str, policy: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    p = project_paths(policy, project)
    if not p["state"].exists():
        return response(project, "status", "UNKNOWN", "Control-plane state is not initialized.",
                        {"state": str(p["state"])}, ["CONTROL_PLANE_STATE_MISSING"], ["initialize project control-plane state"])
    projection = load(p["state"])
    if projection.get("schema") != STATE_SCHEMA:
        return response(project, "status", "BLOCKED", "Control-plane state schema is invalid.",
                        {"schema": projection.get("schema")}, ["CONTROL_PLANE_STATE_SCHEMA_INVALID"])
    stage = str(((projection.get("state") or {}).get("lifecycle") or {}).get("stage") or "UNKNOWN")
    control_profile=str(((projection.get("state") or {}).get("identity") or {}).get("control_profile") or "project")
    tx_blockers = pending_transactions(p["transactions"])
    if control_profile=="platform":
        details={
          "control_profile":"platform","stage":stage,"lifecycle_managed":False,
          "version":projection.get("version"),"last_event_sequence":projection.get("last_event_sequence"),
          "last_event_digest":projection.get("last_event_digest"),"next_stage":None,
          "state":str(p["state"]),"ledger":str(p["ledger"]),"pending_transactions":len(tx_blockers),
          "protected_human_approval_boundary":True
        }
        if tx_blockers:
            return response(project,"status","BLOCKED","A platform control transaction requires recovery.",
                            details,tx_blockers,["inspect and recover pending control transaction"])
        if not p["ledger"].exists():
            return response(project,"status","BLOCKED","Platform Evidence Ledger is missing.",details,
                            ["EVIDENCE_LEDGER_MISSING"],["rerun bootstrap-control-plane"])
        ledger_value=load(p["ledger"])
        if ledger_value.get("schema")!=LEDGER_SCHEMA or str(ledger_value.get("project") or "")!=project:
            return response(project,"status","BLOCKED","Platform Evidence Ledger identity is invalid.",details,
                            ["EVIDENCE_LEDGER_IDENTITY_INVALID"])
        evidence=((projection.get("state") or {}).get("evidence") or {})
        if evidence.get("control_plane_ledger_initialized") is not True:
            return response(project,"status","BLOCKED","Platform control-plane bootstrap marker is missing.",details,
                            ["CONTROL_PLANE_BOOTSTRAP_MARKER_MISSING"],["rerun bootstrap-control-plane"])
        rc_v,values_v,out_v,err_v=state_verify_raw(project,policy,repo_root)
        if rc_v!=0:
            details.update({"verify_stdout":out_v.strip(),"verify_stderr":err_v.strip()})
            return response(project,"status","BLOCKED","Platform control-plane integrity check failed.",details,
                            ["CONTROL_PLANE_INTEGRITY_FAILED"])
        approval_contract=((policy.get("operations") or {}).get("record-approval") or {})
        if approval_contract.get("human_actor_required") is not True:
            return response(project,"status","BLOCKED","Protected human approval policy is not active.",details,
                            ["HUMAN_APPROVAL_BOUNDARY_NOT_PROTECTED"])
        details["integrity"]=values_v
        return response(project,"status","READY",
                        "Platform control plane is ready for protected governance operations.",
                        details,next_actions=["await governed evidence or explicit human approval request"])
    lifecycle_path = resolve_repo(repo_root, (policy.get("repository_paths") or {})["lifecycle"])
    lifecycle = load(lifecycle_path)
    target = next_stage(lifecycle, stage)
    details = {
        "stage": stage,
        "version": projection.get("version"),
        "last_event_sequence": projection.get("last_event_sequence"),
        "last_event_digest": projection.get("last_event_digest"),
        "next_stage": target,
        "state": str(p["state"]),
        "ledger": str(p["ledger"]),
        "pending_transactions": len(tx_blockers),
    }
    if tx_blockers:
        return response(project, "status", "BLOCKED", "A control transaction requires recovery before further promotion.",
                        details, tx_blockers, ["inspect and recover pending control transaction"])
    if target is None:
        if stage == "RETIRE":
            return response(project, "status", "COMPLETE", "Project lifecycle is complete.", details)
        return response(project, "status", "BLOCKED", "Current lifecycle stage is invalid.", details, [f"CURRENT_STAGE_INVALID:{stage}"])
    if not p["ledger"].exists():
        return response(project, "status", "BLOCKED", "Evidence ledger is missing.", details,
                        ["EVIDENCE_LEDGER_MISSING"], ["initialize evidence ledger"])
    ledger_value = load(p["ledger"])
    if ledger_value.get("schema") != LEDGER_SCHEMA:
        return response(project, "status", "BLOCKED", "Evidence ledger schema is invalid.", details,
                        ["EVIDENCE_LEDGER_SCHEMA_INVALID"])
    refs = policy.get("repository_paths") or {}
    tools = policy.get("engine_paths") or {}
    values, blockers, rc, err = lifecycle_check(
        project, target, projection, p["ledger"], lifecycle_path,
        resolve_repo(repo_root, refs["quality_gates"]),
        resolve_repo(repo_root, tools["lifecycle_engine"]),
    )
    details.update({"transition": f"{stage}->{target}", "transition_allowed": values.get("ALLOWED") == "YES"})
    if err:
        details["engine_error"] = err
    if not blockers and rc == 0:
        return response(project, "status", "READY", f"Project is ready for transition {stage}->{target}.", details,
                        next_actions=[f"plan transition {stage}->{target}", f"advance to {target} when ready"])
    approval_blockers = [x for x in blockers if x.startswith("APPROVAL_")]
    non_approval = [x for x in blockers if not x.startswith("APPROVAL_")]
    state = "AWAITING_APPROVAL" if approval_blockers and not non_approval else "BLOCKED"
    return response(project, "status", state, f"Project cannot transition {stage}->{target} yet.", details,
                    blockers, ["satisfy listed blockers", f"recheck transition {stage}->{target}"])


def plan_transition(project: str, target: str | None, policy: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    p = project_paths(policy, project)
    if not p["state"].exists():
        return response(project, "plan-transition", "BLOCKED", "Control-plane state missing.", blockers=["CONTROL_PLANE_STATE_MISSING"])
    projection = load(p["state"])
    control_profile=str(((projection.get("state") or {}).get("identity") or {}).get("control_profile") or "project")
    if control_profile=="platform":
        return response(project,"plan-transition","BLOCKED","Platform control profile does not use application lifecycle transitions.",
                        {"control_profile":"platform","lifecycle_managed":False},
                        ["PLATFORM_CONTROL_PROFILE_LIFECYCLE_OPERATION_FORBIDDEN"])

    stage = str(((projection.get("state") or {}).get("lifecycle") or {}).get("stage") or "UNKNOWN")
    lifecycle_path = resolve_repo(repo_root, (policy.get("repository_paths") or {})["lifecycle"])
    lifecycle = load(lifecycle_path)
    target = target or next_stage(lifecycle, stage)
    if not target:
        return response(project, "plan-transition", "BLOCKED", "No next lifecycle stage exists.", {"stage": stage}, ["NO_NEXT_STAGE"])
    transition = f"{stage}->{target.upper()}"
    out = p["plans"] / (transition.replace("->", "-to-") + ".task-graph.json")
    refs, tools = policy.get("repository_paths") or {}, policy.get("engine_paths") or {}
    rc, stdout, stderr = run_tool(resolve_repo(repo_root, tools["task_graph_engine"]), [
        "--project", project,
        "--transition", transition,
        "--lifecycle", str(lifecycle_path),
        "--quality", str(resolve_repo(repo_root, refs["quality_gates"])),
        "--catalog", str(resolve_repo(repo_root, refs["evidence_catalog"])),
        "--orchestration", str(resolve_repo(repo_root, refs["orchestration"])),
        "--output", str(out),
    ])
    if rc != 0:
        return response(project, "plan-transition", "FAILED", "Task Graph generation failed.",
                        {"transition": transition, "stderr": stderr.strip(), "stdout": stdout.strip()}, ["TASK_GRAPH_GENERATION_FAILED"])
    return response(project, "plan-transition", "OK", f"Task Graph prepared for {transition}.",
                    {"transition": transition, "task_graph": str(out)}, artifacts=[{"type": "task-graph", "path": str(out)}])


def schedule_operation(project: str, graph: Path | None, policy: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    p = project_paths(policy, project)
    if not p["state"].exists():
        return response(project, "schedule", "BLOCKED", "Control-plane state missing.", blockers=["CONTROL_PLANE_STATE_MISSING"])
    projection = load(p["state"])
    control_profile=str(((projection.get("state") or {}).get("identity") or {}).get("control_profile") or "project")
    if control_profile=="platform":
        return response(project,"schedule","BLOCKED","Platform control profile does not schedule application lifecycle transitions.",
                        {"control_profile":"platform","lifecycle_managed":False},
                        ["PLATFORM_CONTROL_PROFILE_LIFECYCLE_OPERATION_FORBIDDEN"])

    stage = str(((projection.get("state") or {}).get("lifecycle") or {}).get("stage") or "UNKNOWN")
    lifecycle = load(resolve_repo(repo_root, (policy.get("repository_paths") or {})["lifecycle"]))
    target = next_stage(lifecycle, stage)
    if not target:
        return response(project, "schedule", "BLOCKED", "No schedulable next transition.", blockers=["NO_NEXT_STAGE"])
    transition = f"{stage}->{target}"
    graph = graph or p["plans"] / (transition.replace("->", "-to-") + ".task-graph.json")
    if not graph.exists():
        return response(project, "schedule", "BLOCKED", "Task Graph does not exist.", {"task_graph": str(graph)}, ["TASK_GRAPH_MISSING"], ["run plan-transition"])
    if not p["health"].exists():
        return response(project, "schedule", "BLOCKED", "Provider health snapshot does not exist.", {"health": str(p["health"])}, ["PROVIDER_HEALTH_SNAPSHOT_MISSING"])
    out = p["plans"] / (transition.replace("->", "-to-") + ".execution-plan.json")
    refs, tools = policy.get("repository_paths") or {}, policy.get("engine_paths") or {}
    rc, stdout, stderr = run_tool(resolve_repo(repo_root, tools["execution_scheduler"]), [
        "--graph", str(graph),
        "--registry", str(resolve_repo(repo_root, refs["capability_registry"])),
        "--health", str(p["health"]),
        "--policy", str(resolve_repo(repo_root, refs["execution_scheduler"])),
        "--output", str(out),
    ])
    if rc != 0:
        return response(project, "schedule", "FAILED", "Execution scheduling failed.",
                        {"stderr": stderr.strip(), "stdout": stdout.strip()}, ["EXECUTION_SCHEDULER_FAILED"])
    plan = load(out)
    blocked = [f"TASK_BLOCKED:{x.get('task_id')}:{'|'.join(x.get('reasons') or [])}" for x in plan.get("blocked_tasks") or []]
    status = "BLOCKED" if blocked else "OK"
    return response(project, "schedule", status, f"Execution plan prepared for {transition}.",
                    {"execution_plan": str(out), "summary": plan.get("summary")}, blocked,
                    artifacts=[{"type": "execution-plan", "path": str(out)}])


def prepare_or_dispatch(project: str, execute: bool, plan: Path, graph: Path, workspace: str | None,
                        policy: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    p = project_paths(policy, project)
    if not p["ledger"].exists():
        return response(project, "dispatch" if execute else "prepare-run", "BLOCKED", "Evidence ledger missing.", blockers=["EVIDENCE_LEDGER_MISSING"])
    refs, tools = policy.get("repository_paths") or {}, policy.get("engine_paths") or {}
    argv = [
        "--plan", str(plan), "--graph", str(graph), "--ledger", str(p["ledger"]),
        "--policy", str(resolve_repo(repo_root, refs["run_controller"])),
        "--adapters", str(resolve_repo(repo_root, refs["provider_adapters"])),
        "--output-dir", str(p["runs"]),
    ]
    if workspace:
        argv += ["--workspace", workspace]
    if execute:
        argv.append("--execute")
    rc, stdout, stderr = run_tool(resolve_repo(repo_root, tools["run_controller"]), argv, timeout=3700 if execute else 120)
    values, blockers = parse_kv(stdout)
    operation = "dispatch" if execute else "prepare-run"
    if rc != 0:
        detail = {"stdout": stdout.strip(), "stderr": stderr.strip(), **values}
        if execute and "EXECUTION_DISABLED_BY_POLICY" in stderr + stdout:
            blockers.append("EXECUTION_DISABLED_BY_POLICY")
        return response(project, operation, "BLOCKED" if blockers else "FAILED", "Run Controller did not complete.", detail, blockers or ["RUN_CONTROLLER_FAILED"])
    return response(project, operation, "OK", "Run Controller completed in requested mode.", values,
                    artifacts=[{"type": "run-record", "path": values.get("RUN_RECORD")}])


def verify_state(project: str, policy: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    rc, values, stdout, stderr = state_verify_raw(project, policy, repo_root)
    if rc != 0:
        return response(project, "verify-state", "FAILED", "Control-plane integrity verification failed.",
                        {"stdout": stdout.strip(), "stderr": stderr.strip(), **values}, ["CONTROL_PLANE_INTEGRITY_FAILED"])
    return response(project, "verify-state", "OK", "Control-plane projection and audit chain verify.", values)


def crypto_verify(project: str, checkpoint: Path, public_key: Path, policy: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    refs, tools = policy.get("repository_paths") or {}, policy.get("engine_paths") or {}
    rc, stdout, stderr = run_tool(resolve_repo(repo_root, tools["crypto_trust"]), [
        "--policy", str(resolve_repo(repo_root, refs["cryptographic_trust"])),
        "verify", "--checkpoint", str(checkpoint), "--public-key", str(public_key),
    ])
    values, _ = parse_kv(stdout)
    if rc != 0:
        errors = values.get("ERRORS", "SIGNATURE_VERIFICATION_FAILED").split(",")
        return response(project, "crypto-verify", "FAILED", "Signed checkpoint verification failed.",
                        {"stdout": stdout.strip(), "stderr": stderr.strip(), **values}, errors)
    return response(project, "crypto-verify", "OK", "Signed checkpoint is cryptographically valid.", values)


def write_receipt(path: Path, value: dict[str, Any]) -> None:
    payload = {"schema": RECEIPT_SCHEMA, **value, "updated_at": now_iso()}
    save(path, payload)


def classify_blockers(blockers: list[str]) -> str:
    approvals = [x for x in blockers if x.startswith("APPROVAL_")]
    others = [x for x in blockers if not x.startswith("APPROVAL_")]
    return "AWAITING_APPROVAL" if approvals and not others else "BLOCKED"


FINALIZATION_OUTPUT_ARTIFACTS={"compromise-release-receipt","seven-agent-final-delivery-receipt"}

def is_finalization_output_blocker(blocker:str)->bool:
    b=str(blocker)
    for artifact in FINALIZATION_OUTPUT_ARTIFACTS:
        if b.startswith("ARTIFACT_MISSING:"+artifact):return True
        if b.startswith("ARTIFACT_NOT_OK:"+artifact+":"):return True
        if b.startswith("ARTIFACT_SOURCE_MISSING:"+artifact):return True
        if b.startswith("ARTIFACT_TIMESTAMP_MISSING:"+artifact):return True
    return (
        b=="GATE_MISSING:compromise-release" or
        b.startswith("GATE_BLOCKING:compromise-release:") or
        b.startswith("GATE_FORBIDDEN:compromise-release:") or
        b.startswith("GATE_NOT_RELEASE_READY:compromise-release:")
    )

def automatic_finalization_eligible(current:str,target:str,blockers:list[str])->bool:
    if current!="PREVIEW" or target!="RELEASE":return False
    if not any(is_finalization_output_blocker(x) for x in blockers):return False
    non_final=[
      x for x in blockers
      if not is_finalization_output_blocker(x) and not str(x).startswith("APPROVAL_")
    ]
    return not non_final

def run_automatic_finalization(project:str,actor:str,policy:dict[str,Any],repo_root:Path,p:dict[str,Path])->dict[str,Any]:
    refs,tools=policy.get("repository_paths") or {},policy.get("engine_paths") or {}
    engine_ref=tools.get("automatic_seven_agent_finalizer")
    policy_ref=refs.get("automatic_seven_agent_finalization")
    if not engine_ref or not policy_ref:
        return {"status":"BLOCKED","blockers":["AUTOMATIC_FINALIZATION_NOT_CONFIGURED"]}
    engine=resolve_repo(repo_root,str(engine_ref))
    final_policy=resolve_repo(repo_root,str(policy_ref))
    if not engine.is_file() or not final_policy.is_file():
        return {"status":"BLOCKED","blockers":["AUTOMATIC_FINALIZATION_COMPONENT_MISSING"]}

    txid="ctx-finalize-"+uuid.uuid4().hex
    txdir=p["transactions"]/txid
    txdir.mkdir(parents=True,exist_ok=False)
    receipt=txdir/"receipt.json"
    staged=txdir/"ledger.staged.json"
    shutil.copy2(p["ledger"],staged)
    old=load(p["ledger"])
    old_digest=canonical_digest(old)
    output_dir=p["plans"]/"automatic-finalization"
    result_path=txdir/"automatic-finalization-result.json"
    write_receipt(receipt,{
      "transaction_id":txid,"project":project,"operation":"automatic-seven-agent-finalization",
      "status":"PREPARED","actor":actor,"old_ledger_digest":old_digest
    })
    rc,stdout,stderr=run_tool(engine,[
      "--project",project,
      "--policy",str(final_policy),
      "--ledger",str(staged),
      "--repo-root",str(repo_root),
      "--output-dir",str(output_dir),
      "--result",str(result_path)
    ],timeout=240)
    final_result=load(result_path) if result_path.exists() else {}
    if rc!=0 or final_result.get("delivery_allowed") is not True:
        write_receipt(receipt,{
          "transaction_id":txid,"project":project,"operation":"automatic-seven-agent-finalization",
          "status":"FAILED","actor":actor,"returncode":rc,
          "result":str(result_path) if result_path.exists() else None,
          "stdout":stdout[-4000:],"stderr":stderr[-2000:]
        })
        return {
          "status":"BLOCKED","transaction_id":txid,
          "blockers":["AUTOMATIC_SEVEN_AGENT_FINALIZATION_BLOCKED"],
          "result":str(result_path) if result_path.exists() else None,
          "stdout":stdout[-2000:],"stderr":stderr[-1000:]
        }

    staged_value=load(staged)
    new_digest=canonical_digest(staged_value)
    if new_digest==old_digest:
        write_receipt(receipt,{
          "transaction_id":txid,"project":project,"operation":"automatic-seven-agent-finalization",
          "status":"COMMITTED","actor":actor,"idempotent":True,
          "old_ledger_digest":old_digest,"new_ledger_digest":new_digest,
          "result":str(result_path)
        })
        return {"status":"PASS","transaction_id":txid,"idempotent":True,"result":str(result_path)}

    payload_path=txdir/"payload.json"
    save(payload_path,{
      "transaction_id":txid,
      "source":"automatic-seven-agent-finalization",
      "old_ledger_digest":old_digest,
      "new_ledger_digest":new_digest,
      "staged_ledger":str(staged),
      "finalization_result":str(result_path),
      "commit_protocol":"journal-first-ledger-finalize"
    })
    rc_evt,event_values,out_evt,err_evt=store_record(
      project,"EVIDENCE_RECORDED","central-orchestrator",payload_path,None,None,policy,repo_root
    )
    if rc_evt!=0:
        write_receipt(receipt,{
          "transaction_id":txid,"project":project,"operation":"automatic-seven-agent-finalization",
          "status":"FAILED","failure":"FINALIZATION_EVIDENCE_AUDIT_COMMIT_FAILED",
          "stdout":out_evt[-2000:],"stderr":err_evt[-1000:]
        })
        return {"status":"BLOCKED","transaction_id":txid,"blockers":["FINALIZATION_EVIDENCE_AUDIT_COMMIT_FAILED"]}

    p["ledger"].parent.mkdir(parents=True,exist_ok=True)
    fd,tmp_name=tempfile.mkstemp(prefix="ledger.",suffix=".v637",dir=str(p["ledger"].parent))
    os.close(fd)
    tmp=Path(tmp_name)
    try:
        shutil.copy2(staged,tmp)
        with tmp.open("rb") as fh:os.fsync(fh.fileno())
        os.replace(tmp,p["ledger"])
    except Exception as exc:
        if tmp.exists():tmp.unlink()
        write_receipt(receipt,{
          "transaction_id":txid,"project":project,"operation":"automatic-seven-agent-finalization",
          "status":"CONTROL_EVENT_COMMITTED_LEDGER_PENDING",
          "failure":str(exc),"event":event_values,"staged_ledger":str(staged),
          "new_ledger_digest":new_digest
        })
        return {"status":"BLOCKED","transaction_id":txid,"blockers":["CONTROL_TRANSACTION_LEDGER_FINALIZE_PENDING"]}

    finalized=load(p["ledger"])
    if canonical_digest(finalized)!=new_digest:
        write_receipt(receipt,{
          "transaction_id":txid,"project":project,"operation":"automatic-seven-agent-finalization",
          "status":"COMMIT_UNCERTAIN","expected_ledger_digest":new_digest,
          "actual_ledger_digest":canonical_digest(finalized)
        })
        return {"status":"BLOCKED","transaction_id":txid,"blockers":["CONTROL_TRANSACTION_COMMIT_UNCERTAIN"]}

    write_receipt(receipt,{
      "transaction_id":txid,"project":project,"operation":"automatic-seven-agent-finalization",
      "status":"COMMITTED","actor":actor,
      "event_sequence":event_values.get("EVENT_SEQUENCE"),
      "event_digest":event_values.get("EVENT_DIGEST"),
      "old_ledger_digest":old_digest,"new_ledger_digest":new_digest,
      "result":str(result_path)
    })
    return {
      "status":"PASS","transaction_id":txid,"idempotent":False,
      "event_sequence":event_values.get("EVENT_SEQUENCE"),
      "event_digest":event_values.get("EVENT_DIGEST"),
      "result":str(result_path)
    }


def advance_operation(project: str, target: str | None, actor: str, policy: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    p = project_paths(policy, project)
    with project_lock(p["lock"]):
        pending = pending_transactions(p["transactions"])
        if pending:
            return response(project, "advance", "BLOCKED", "Pending control transaction must be recovered first.", blockers=pending)
        rc0, _, out0, err0 = state_verify_raw(project, policy, repo_root)
        if rc0 != 0:
            return response(project, "advance", "BLOCKED", "Control-plane integrity failed before transition.",
                            {"stdout": out0.strip(), "stderr": err0.strip()}, ["CONTROL_PLANE_INTEGRITY_FAILED"])
        if not p["ledger"].exists():
            return response(project, "advance", "BLOCKED", "Evidence ledger missing.", blockers=["EVIDENCE_LEDGER_MISSING"])
        projection = load(p["state"])
        control_profile=str(((projection.get("state") or {}).get("identity") or {}).get("control_profile") or "project")
        if control_profile=="platform":
            return response(project,"advance","BLOCKED",
                            "Platform control profile cannot advance through application lifecycle stages.",
                            {"control_profile":"platform","lifecycle_managed":False},
                            ["PLATFORM_CONTROL_PROFILE_LIFECYCLE_OPERATION_FORBIDDEN"])

        ledger = load(p["ledger"])
        if ledger.get("schema") != LEDGER_SCHEMA:
            return response(project, "advance", "BLOCKED", "Evidence ledger schema invalid.", blockers=["EVIDENCE_LEDGER_SCHEMA_INVALID"])
        current = str(((projection.get("state") or {}).get("lifecycle") or {}).get("stage") or "UNKNOWN")
        refs, tools = policy.get("repository_paths") or {}, policy.get("engine_paths") or {}
        lifecycle_path = resolve_repo(repo_root, refs["lifecycle"])
        lifecycle = load(lifecycle_path)
        target = (target or next_stage(lifecycle, current) or "").upper()
        if not target:
            return response(project, "advance", "BLOCKED", "No target lifecycle stage exists.", blockers=["NO_NEXT_STAGE"])
        values, blockers, rc_check, err_check = lifecycle_check(
            project, target, projection, p["ledger"], lifecycle_path,
            resolve_repo(repo_root, refs["quality_gates"]),
            resolve_repo(repo_root, tools["lifecycle_engine"]),
        )
        automatic_finalization=None
        if (rc_check != 0 or blockers) and automatic_finalization_eligible(current,target,blockers):
            automatic_finalization=run_automatic_finalization(project,actor,policy,repo_root,p)
            if automatic_finalization.get("status")=="PASS":
                ledger=load(p["ledger"])
                projection=load(p["state"])
                current=str(((projection.get("state") or {}).get("lifecycle") or {}).get("stage") or current)
                if current!="PREVIEW":
                    return response(
                        project,"advance","BLOCKED",
                        "Control-plane lifecycle changed unexpectedly during automatic finalization.",
                        {"automatic_finalization":automatic_finalization,"current_stage":current},
                        ["AUTOMATIC_FINALIZATION_CONTROL_PLANE_STAGE_CHANGED"]
                    )
                values, blockers, rc_check, err_check = lifecycle_check(
                    project, target, projection, p["ledger"], lifecycle_path,
                    resolve_repo(repo_root, refs["quality_gates"]),
                    resolve_repo(repo_root, tools["lifecycle_engine"]),
                )
            else:
                details={"transition":f"{current}->{target}","automatic_finalization":automatic_finalization,**values}
                return response(
                    project,"advance","BLOCKED",
                    "Automatic seven-agent finalization did not authorize release.",
                    details,automatic_finalization.get("blockers") or ["AUTOMATIC_SEVEN_AGENT_FINALIZATION_BLOCKED"],
                    ["repair implementation and re-run release advance; renegotiate agents only if compromise is infeasible"]
                )
        if rc_check != 0 or blockers:
            details = {"transition": f"{current}->{target}", "engine_error": err_check, **values}
            if automatic_finalization is not None:details["automatic_finalization"]=automatic_finalization
            return response(project, "advance", classify_blockers(blockers), "Lifecycle transition requirements are not satisfied.",
                            details, blockers or ["LIFECYCLE_CHECK_FAILED"])
        txid = "ctx-" + uuid.uuid4().hex
        txdir = p["transactions"] / txid
        txdir.mkdir(parents=True, exist_ok=False)
        receipt = txdir / "receipt.json"
        pre_version = int(projection.get("version") or 0)
        pre_head = str(projection.get("last_event_digest") or "")
        ledger_digest = canonical_digest(ledger)
        observed = now_iso()
        write_receipt(receipt, {
            "transaction_id": txid, "project": project, "operation": "advance", "status": "PREPARED",
            "actor": actor, "transition": f"{current}->{target}", "pre_version": pre_version,
            "pre_head_digest": pre_head, "evidence_ledger_digest": ledger_digest,
        })
        payload = {
            "transaction_id": txid,
            "transition": f"{current}->{target}",
            "from": current,
            "to": target,
            "actor": actor,
            "observed_at": observed,
            "evidence_ledger_digest": ledger_digest,
            "precondition": {"version": pre_version, "journal_head_digest": pre_head},
            "lifecycle_check": {"allowed": True, "engine_values": values},
            "automatic_seven_agent_finalization": automatic_finalization,
        }
        patch = {
            "lifecycle": {
                "stage": target,
                "last_transition": {
                    "transaction_id": txid, "from": current, "to": target,
                    "actor": actor, "observed_at": observed, "evidence_ledger_digest": ledger_digest,
                },
            }
        }
        payload_path, patch_path = txdir / "payload.json", txdir / "patch.json"
        save(payload_path, payload)
        save(patch_path, patch)
        current_projection = load(p["state"])
        if int(current_projection.get("version") or 0) != pre_version or str(current_projection.get("last_event_digest") or "") != pre_head:
            write_receipt(receipt, {
                "transaction_id": txid, "project": project, "operation": "advance", "status": "FAILED",
                "actor": actor, "transition": f"{current}->{target}", "failure": "PRECONDITION_CHANGED",
                "pre_version": pre_version, "pre_head_digest": pre_head,
            })
            return response(project, "advance", "BLOCKED", "Control-plane changed during transition preparation.",
                            {"transaction_id": txid}, ["CONTROL_TRANSACTION_PRECONDITION_CHANGED"])
        rc, event_values, stdout, stderr = store_record(
            project, "LIFECYCLE_TRANSITION", actor, payload_path, patch_path, None, policy, repo_root
        )
        if rc != 0:
            write_receipt(receipt, {
                "transaction_id": txid, "project": project, "operation": "advance", "status": "FAILED",
                "actor": actor, "transition": f"{current}->{target}", "failure": "AUDIT_COMMIT_FAILED",
                "stdout": stdout.strip(), "stderr": stderr.strip(),
            })
            return response(project, "advance", "FAILED", "Lifecycle audit commit failed.",
                            {"transaction_id": txid, "stdout": stdout.strip(), "stderr": stderr.strip()},
                            ["CONTROL_TRANSACTION_AUDIT_COMMIT_FAILED"])
        rc1, verify_values, out1, err1 = state_verify_raw(project, policy, repo_root)
        post = load(p["state"])
        post_stage = str(((post.get("state") or {}).get("lifecycle") or {}).get("stage") or "UNKNOWN")
        committed = (
            rc1 == 0
            and post_stage == target
            and int(post.get("version") or 0) == pre_version + 1
            and str(post.get("last_event_digest") or "") == str(event_values.get("EVENT_DIGEST") or "")
        )
        if not committed:
            write_receipt(receipt, {
                "transaction_id": txid, "project": project, "operation": "advance", "status": "COMMIT_UNCERTAIN",
                "actor": actor, "transition": f"{current}->{target}", "event": event_values,
                "post_version": post.get("version"), "post_head_digest": post.get("last_event_digest"),
                "post_stage": post_stage, "verify_stdout": out1.strip(), "verify_stderr": err1.strip(),
            })
            return response(project, "advance", "BLOCKED",
                            "Audit event was written but post-commit verification is not conclusive.",
                            {"transaction_id": txid, "receipt": str(receipt), **event_values},
                            ["CONTROL_TRANSACTION_COMMIT_UNCERTAIN"],
                            ["inspect receipt and run verify-state before any further mutation"])
        write_receipt(receipt, {
            "transaction_id": txid, "project": project, "operation": "advance", "status": "COMMITTED",
            "actor": actor, "transition": f"{current}->{target}", "pre_version": pre_version,
            "post_version": post.get("version"), "pre_head_digest": pre_head,
            "post_head_digest": post.get("last_event_digest"), "evidence_ledger_digest": ledger_digest,
            "event_sequence": event_values.get("EVENT_SEQUENCE"), "event_digest": event_values.get("EVENT_DIGEST"),
            "integrity": verify_values,
        })
        return response(project, "advance", "OK", f"Lifecycle advanced transactionally from {current} to {target}.",
                        {"transaction_id": txid, "transition": f"{current}->{target}",
                         "event_sequence": event_values.get("EVENT_SEQUENCE"),
                         "event_digest": event_values.get("EVENT_DIGEST"),
                         "post_version": post.get("version"), "receipt": str(receipt),
                         "automatic_seven_agent_finalization": automatic_finalization},
                        artifacts=[{"type": "control-transaction-receipt", "path": str(receipt)}])



def bootstrap_control_plane_operation(project: str, actor: str, profile: str,
                                      policy: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    """Initialize Project Control state+journal+Evidence Ledger through canonical engines.

    Bootstrap is idempotent and forward-only. A valid partial bootstrap may be
    completed, but inconsistent partial state is never deleted or rewritten.
    """
    project=str(project or "").strip()
    actor=str(actor or "").strip()
    profile=str(profile or "project").strip().lower()
    if not project:
        return response(project or "unknown","bootstrap-control-plane","BLOCKED","Project id is required.",
                        blockers=["PROJECT_ID_MISSING"])
    if not actor:
        return response(project,"bootstrap-control-plane","BLOCKED","Bootstrap actor is required.",
                        blockers=["BOOTSTRAP_ACTOR_MISSING"])
    if profile not in {"project","platform"}:
        return response(project,"bootstrap-control-plane","BLOCKED","Unsupported control-plane profile.",
                        {"profile":profile},["CONTROL_PLANE_PROFILE_INVALID"])

    p=project_paths(policy,project)
    tools=policy.get("engine_paths") or {}
    state_policy,state_root=state_policy_root(policy,repo_root)
    expected_state_root=p["state"].parent.parent
    if state_root.resolve()!=expected_state_root.resolve():
        return response(project,"bootstrap-control-plane","BLOCKED",
                        "Project Control and Control Plane Store state roots differ.",
                        {"project_control_root":str(expected_state_root),"store_root":str(state_root)},
                        ["CONTROL_PLANE_STATE_ROOT_MISMATCH"])

    def ledger_check()->tuple[bool,str|None]:
        if not p["ledger"].exists():return False,None
        try:x=load(p["ledger"])
        except Exception as exc:return False,"EVIDENCE_LEDGER_INVALID:"+str(exc)
        if x.get("schema")!=LEDGER_SCHEMA:return False,"EVIDENCE_LEDGER_SCHEMA_INVALID"
        if str(x.get("project") or "")!=project:return False,"EVIDENCE_LEDGER_PROJECT_MISMATCH"
        return True,None

    with project_lock(p["lock"]):
        state_exists=p["state"].exists()
        journal_exists=p["journal"].exists()
        if state_exists!=journal_exists:
            return response(project,"bootstrap-control-plane","BLOCKED",
                            "Control-plane state/journal are partially initialized.",
                            {"state_exists":state_exists,"journal_exists":journal_exists},
                            ["CONTROL_PLANE_STATE_JOURNAL_PARTIAL"])

        ledger_exists=p["ledger"].exists()
        ledger_ok,ledger_error=ledger_check()
        if ledger_exists and not ledger_ok:
            return response(project,"bootstrap-control-plane","BLOCKED","Existing Evidence Ledger is invalid.",
                            {"ledger":str(p["ledger"])},[str(ledger_error or "EVIDENCE_LEDGER_INVALID")])
        if not state_exists and ledger_exists:
            lv=load(p["ledger"])
            nonempty=bool((lv.get("artifacts") or {}) or (lv.get("gates") or {}) or
                          (lv.get("approvals") or {}) or (lv.get("risk_acceptances") or []) or
                          (lv.get("history") or []))
            if nonempty:
                return response(project,"bootstrap-control-plane","BLOCKED",
                                "A non-empty ledger exists without control-plane state.",
                                {"ledger":str(p["ledger"])},["ORPHAN_NONEMPTY_EVIDENCE_LEDGER"])

        if state_exists:
            rc0,_,out0,err0=state_verify_raw(project,policy,repo_root)
            if rc0!=0:
                return response(project,"bootstrap-control-plane","BLOCKED",
                                "Existing control-plane integrity check failed.",
                                {"stdout":out0.strip(),"stderr":err0.strip()},
                                ["CONTROL_PLANE_INTEGRITY_FAILED"])
            projection=load(p["state"])
            existing_profile=str(((projection.get("state") or {}).get("identity") or {}).get("control_profile") or "")
            if existing_profile and existing_profile!=profile:
                return response(project,"bootstrap-control-plane","BLOCKED","Existing control profile differs.",
                                {"existing_profile":existing_profile,"requested_profile":profile},
                                ["CONTROL_PLANE_PROFILE_MISMATCH"])

        state_created=False
        ledger_created=False
        if not state_exists:
            with tempfile.TemporaryDirectory(prefix="chacha-control-bootstrap-") as td:
                initial=Path(td)/"initial.json"
                save(initial,{"identity":{"control_profile":profile,"bootstrap_actor":actor},
                              "lifecycle":{"stage":"IDEA"}})
                rc,out,err=run_tool(resolve_repo(repo_root,tools["control_plane_store"]),[
                    "--policy",str(state_policy),"--root",str(state_root),"init",
                    "--project",project,"--actor",actor,"--initial",str(initial)
                ])
            if rc!=0:
                return response(project,"bootstrap-control-plane","FAILED",
                                "Control Plane Store initialization failed.",
                                {"stdout":out.strip(),"stderr":err.strip()},
                                ["CONTROL_PLANE_STATE_INIT_FAILED"])
            state_created=True

        rc1,_,out1,err1=state_verify_raw(project,policy,repo_root)
        if rc1!=0:
            return response(project,"bootstrap-control-plane","BLOCKED",
                            "Control-plane integrity failed after initialization.",
                            {"stdout":out1.strip(),"stderr":err1.strip()},
                            ["CONTROL_PLANE_POST_INIT_INTEGRITY_FAILED"])

        ledger_ok,ledger_error=ledger_check()
        if not p["ledger"].exists():
            rc,out,err=run_tool(resolve_repo(repo_root,tools["evidence_collector"]),[
                "init","--project",project,"--ledger",str(p["ledger"])
            ])
            if rc!=0:
                return response(project,"bootstrap-control-plane","BLOCKED",
                                "Control-plane state exists; Evidence Ledger initialization must resume.",
                                {"stdout":out.strip(),"stderr":err.strip(),"state_created":state_created},
                                ["CONTROL_PLANE_BOOTSTRAP_LEDGER_PENDING"],
                                ["rerun bootstrap-control-plane after resolving ledger initialization"])
            ledger_created=True
            ledger_ok,ledger_error=ledger_check()
        if not ledger_ok:
            return response(project,"bootstrap-control-plane","BLOCKED","Evidence Ledger validation failed.",
                            {"ledger":str(p["ledger"])},[str(ledger_error or "EVIDENCE_LEDGER_INVALID")])

        projection=load(p["state"])
        evidence_state=((projection.get("state") or {}).get("evidence") or {})
        marker_ok=(
            evidence_state.get("control_plane_ledger_initialized") is True and
            str(evidence_state.get("ledger_path") or "")==str(p["ledger"])
        )
        event_recorded=False
        if not marker_ok:
            ledger_digest=canonical_digest(load(p["ledger"]))
            with tempfile.TemporaryDirectory(prefix="chacha-control-bootstrap-event-") as td:
                payload=Path(td)/"payload.json";patch=Path(td)/"patch.json"
                save(payload,{"kind":"control-plane-bootstrap","ledger":str(p["ledger"]),
                              "ledger_digest":ledger_digest,"profile":profile})
                save(patch,{"evidence":{"control_plane_ledger_initialized":True,
                                       "ledger_path":str(p["ledger"]),
                                       "ledger_digest":ledger_digest}})
                rc_evt,values,out_evt,err_evt=store_record(
                    project,"EVIDENCE_RECORDED",actor,payload,patch,None,policy,repo_root)
            if rc_evt!=0:
                return response(project,"bootstrap-control-plane","BLOCKED",
                                "Ledger exists but bootstrap audit event could not be committed.",
                                {"stdout":out_evt.strip(),"stderr":err_evt.strip()},
                                ["CONTROL_PLANE_BOOTSTRAP_AUDIT_PENDING"],
                                ["rerun bootstrap-control-plane after resolving audit commit"])
            event_recorded=True

        rc2,verify_values,out2,err2=state_verify_raw(project,policy,repo_root)
        if rc2!=0:
            return response(project,"bootstrap-control-plane","BLOCKED",
                            "Bootstrap completed but final integrity check failed.",
                            {"stdout":out2.strip(),"stderr":err2.strip()},
                            ["CONTROL_PLANE_BOOTSTRAP_FINAL_INTEGRITY_FAILED"])
        final=load(p["state"])
        final_evidence=((final.get("state") or {}).get("evidence") or {})
        if final_evidence.get("control_plane_ledger_initialized") is not True:
            return response(project,"bootstrap-control-plane","BLOCKED",
                            "Bootstrap evidence marker is missing after commit.",
                            blockers=["CONTROL_PLANE_BOOTSTRAP_MARKER_MISSING"])

        idempotent=not state_created and not ledger_created and not event_recorded
        return response(project,"bootstrap-control-plane","OK",
                        "Control plane and Evidence Ledger are initialized and integrity-checked.",
                        {"profile":profile,"state":str(p["state"]),"journal":str(p["journal"]),
                         "ledger":str(p["ledger"]),"state_created":state_created,
                         "ledger_created":ledger_created,"audit_event_recorded":event_recorded,
                         "idempotent":idempotent,"integrity":verify_values},
                        artifacts=[
                          {"type":"control-plane-state","path":str(p["state"])},
                          {"type":"evidence-ledger","path":str(p["ledger"])}
                        ])


def record_approval_operation(project: str, approval_id: str, actor: str, evidence: str | None,
                              policy: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    """Record an explicit human approval through the protected control path.

    The audit journal remains authoritative. The Evidence Ledger is staged first,
    the protected APPROVAL_RECORDED event is committed, then the staged ledger is
    atomically finalized. Replays of the same approval by the same human actor are
    idempotent; conflicting actors/evidence fail closed.
    """
    approval_id=str(approval_id or "").strip()
    actor=str(actor or "").strip()
    if not approval_id:
        return response(project,"record-approval","BLOCKED","Approval id is required.",
                        blockers=["APPROVAL_ID_MISSING"])
    if not actor or actor in {"central-orchestrator","guardian","sentinel","curator","bastion","intendant","logician","ergonomist"}:
        return response(project,"record-approval","BLOCKED","A real human approval actor is required.",
                        {"actor":actor},["HUMAN_APPROVAL_ACTOR_REQUIRED"])
    p=project_paths(policy,project)
    if not p["ledger"].exists():
        return response(project,"record-approval","BLOCKED","Evidence ledger missing.",
                        blockers=["EVIDENCE_LEDGER_MISSING"])

    with project_lock(p["lock"]):
        foreign=pending_transactions(p["transactions"])
        if foreign:
            return response(project,"record-approval","BLOCKED",
                            "Another control transaction requires recovery.",blockers=foreign)
        rc0,_,out0,err0=state_verify_raw(project,policy,repo_root)
        if rc0!=0:
            return response(project,"record-approval","BLOCKED",
                            "Control-plane integrity failed before approval transaction.",
                            {"stdout":out0.strip(),"stderr":err0.strip()},
                            ["CONTROL_PLANE_INTEGRITY_FAILED"])

        original=load(p["ledger"])
        if original.get("schema")!=LEDGER_SCHEMA:
            return response(project,"record-approval","BLOCKED","Evidence ledger schema invalid.",
                            blockers=["EVIDENCE_LEDGER_SCHEMA_INVALID"])
        existing=(original.get("approvals") or {}).get(approval_id)
        if isinstance(existing,dict) and existing.get("status")=="APPROVED":
            if existing.get("actor")==actor and str(existing.get("evidence") or "")==str(evidence or ""):
                return response(project,"record-approval","OK",
                                "Approval already recorded with identical evidence.",
                                {"approval_id":approval_id,"actor":actor,"idempotent":True})
            return response(project,"record-approval","BLOCKED",
                            "Approval already exists with different actor or evidence.",
                            {"approval_id":approval_id,"existing":existing},
                            ["APPROVAL_REPLAY_CONFLICT"])

        txid="ctx-approval-"+uuid.uuid4().hex
        txdir=p["transactions"]/txid
        txdir.mkdir(parents=True,exist_ok=False)
        receipt=txdir/"receipt.json"
        staged=txdir/"ledger.staged.json"
        staged_value=copy.deepcopy(original)
        stamp=now_iso()
        staged_value.setdefault("approvals",{})[approval_id]={
            "status":"APPROVED","actor":actor,"observed_at":stamp,
            "evidence":evidence or None
        }
        staged_value["updated_at"]=stamp
        save(staged,staged_value)
        old_digest=canonical_digest(original)
        new_digest=canonical_digest(staged_value)
        write_receipt(receipt,{
            "transaction_id":txid,"project":project,"operation":"record-approval",
            "status":"PREPARED","approval_id":approval_id,"actor":actor,
            "old_ledger_digest":old_digest,"new_ledger_digest":new_digest
        })
        payload=txdir/"payload.json"
        patch_path=txdir/"state-patch.json"
        save(payload,{
            "approval_id":approval_id,"status":"APPROVED","actor":actor,
            "observed_at":stamp,"evidence":evidence or None,
            "ledger_digest":new_digest
        })
        save(patch_path,{"approvals":{approval_id:{
            "status":"APPROVED","actor":actor,"observed_at":stamp,
            "evidence":evidence or None
        }}})
        rc_evt,event_values,out_evt,err_evt=store_record(
            project,"APPROVAL_RECORDED",actor,payload,patch_path,None,policy,repo_root
        )
        if rc_evt!=0:
            write_receipt(receipt,{
                "transaction_id":txid,"project":project,"operation":"record-approval",
                "status":"FAILED","approval_id":approval_id,
                "stdout":out_evt[-2000:],"stderr":err_evt[-1000:]
            })
            return response(project,"record-approval","BLOCKED",
                            "Protected approval audit event failed.",
                            {"transaction_id":txid},["APPROVAL_AUDIT_COMMIT_FAILED"])

        p["ledger"].parent.mkdir(parents=True,exist_ok=True)
        fd,tmp_name=tempfile.mkstemp(prefix="ledger.",suffix=".approval",dir=str(p["ledger"].parent))
        os.close(fd);tmp=Path(tmp_name)
        try:
            shutil.copy2(staged,tmp)
            with tmp.open("rb") as fh:os.fsync(fh.fileno())
            os.replace(tmp,p["ledger"])
        except Exception as exc:
            if tmp.exists():tmp.unlink()
            write_receipt(receipt,{
                "transaction_id":txid,"project":project,"operation":"record-approval",
                "status":"CONTROL_EVENT_COMMITTED_LEDGER_PENDING",
                "approval_id":approval_id,"failure":str(exc),
                "staged_ledger":str(staged),"new_ledger_digest":new_digest
            })
            return response(project,"record-approval","BLOCKED",
                            "Approval audit event committed but ledger finalize is pending.",
                            {"transaction_id":txid,"staged_ledger":str(staged)},
                            ["CONTROL_TRANSACTION_LEDGER_FINALIZE_PENDING"])

        finalized=load(p["ledger"])
        if canonical_digest(finalized)!=new_digest:
            write_receipt(receipt,{
                "transaction_id":txid,"project":project,"operation":"record-approval",
                "status":"COMMIT_UNCERTAIN","approval_id":approval_id,
                "expected_ledger_digest":new_digest,
                "actual_ledger_digest":canonical_digest(finalized)
            })
            return response(project,"record-approval","BLOCKED",
                            "Approval ledger commit is uncertain.",
                            {"transaction_id":txid},["CONTROL_TRANSACTION_COMMIT_UNCERTAIN"])

        rc1,verify_values,out1,err1=state_verify_raw(project,policy,repo_root)
        if rc1!=0:
            write_receipt(receipt,{
                "transaction_id":txid,"project":project,"operation":"record-approval",
                "status":"COMMIT_UNCERTAIN","approval_id":approval_id,
                "stdout":out1[-2000:],"stderr":err1[-1000:]
            })
            return response(project,"record-approval","BLOCKED",
                            "Approval committed but post-write integrity is inconclusive.",
                            {"transaction_id":txid},["CONTROL_TRANSACTION_COMMIT_UNCERTAIN"])

        write_receipt(receipt,{
            "transaction_id":txid,"project":project,"operation":"record-approval",
            "status":"COMMITTED","approval_id":approval_id,"actor":actor,
            "event_sequence":event_values.get("EVENT_SEQUENCE"),
            "event_digest":event_values.get("EVENT_DIGEST"),
            "old_ledger_digest":old_digest,"new_ledger_digest":new_digest,
            "integrity":verify_values
        })
        return response(project,"record-approval","OK","Human approval recorded transactionally.",
                        {"transaction_id":txid,"approval_id":approval_id,"actor":actor,
                         "event_sequence":event_values.get("EVENT_SEQUENCE"),
                         "event_digest":event_values.get("EVENT_DIGEST"),
                         "receipt":str(receipt),"idempotent":False},
                        artifacts=[{"type":"control-transaction-receipt","path":str(receipt)}])


def issue_platform_component_adapter_registration(project: str, binding_gate: Path, output: Path,
                                                  policy: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    """Issue a protected, single-use adapter registry registration contract.

    This operation never mutates the source registry. It independently
    revalidates the component-specific binding proposal and a separate real-human
    registration approval recorded through Project Control, then commits an
    auditable protected event and emits an exact additive registry-write contract.
    """
    op="issue-platform-component-adapter-registration"
    if project!="chacha-dev-platform":
        return response(project,op,"BLOCKED","Platform adapter registration is restricted to chacha-dev-platform.",
                        blockers=["PLATFORM_CONTROL_PROJECT_REQUIRED"])
    if not binding_gate.is_file():
        return response(project,op,"BLOCKED","Adapter binding gate evidence is required.",
                        {"binding_gate":str(binding_gate)},["ADAPTER_BINDING_GATE_INPUT_MISSING"])
    try:
        gate=load(binding_gate)
    except Exception as exc:
        return response(project,op,"BLOCKED","Adapter binding gate evidence is invalid.",
                        {"reason":str(exc)},["ADAPTER_BINDING_GATE_INPUT_INVALID"])

    proposal=gate.get("binding_proposal") if isinstance(gate.get("binding_proposal"),dict) else {}
    request=gate.get("registration_approval_request") if isinstance(gate.get("registration_approval_request"),dict) else {}
    binding=proposal.get("binding") if isinstance(proposal.get("binding"),dict) else {}
    p=project_paths(policy,project)
    registry_rel=str((policy.get("repository_paths") or {}).get("platform_component_apply_adapter_registry") or "")
    registry_path=resolve_repo(repo_root,registry_rel) if registry_rel else None
    system_actors={
      "central-orchestrator","guardian","sentinel","curator","bastion","intendant",
      "logician","ergonomist","architecture-council","agent-foundry","branch-foundry",
      "capability-foundry","platform-component-pilot-runner","platform-component-promotion-gate",
      "platform-component-controlled-apply-planner","platform-component-source-integration-executor",
      "platform-component-adapter-binding-gate"
    }

    with project_lock(p["lock"]):
        pending=pending_transactions(p["transactions"])
        if pending:
            return response(project,op,"BLOCKED","A control transaction requires recovery before registration issuance.",
                            blockers=pending)
        rc0,verify0,out0,err0=state_verify_raw(project,policy,repo_root)
        if rc0!=0:
            return response(project,op,"BLOCKED","Control-plane integrity failed before registration issuance.",
                            {"stdout":out0.strip(),"stderr":err0.strip()},["CONTROL_PLANE_INTEGRITY_FAILED"])
        if not p["state"].is_file() or not p["ledger"].is_file() or registry_path is None or not registry_path.is_file():
            return response(project,op,"BLOCKED","Platform control state, Evidence Ledger or canonical adapter registry is missing.",
                            blockers=["PLATFORM_ADAPTER_REGISTRATION_PREREQUISITE_MISSING"])

        projection=load(p["state"]);ledger=load(p["ledger"]);registry=load(registry_path)
        identity=((projection.get("state") or {}).get("identity") or {})
        bootstrap=((projection.get("state") or {}).get("evidence") or {})
        approval_id=str(request.get("approval_id") or "")
        ledger_approval=((ledger.get("approvals") or {}).get(approval_id) or {}) if approval_id else {}
        state_approval=((((projection.get("state") or {}).get("approvals") or {}).get(approval_id) or {})
                        if approval_id else {})
        actor=str(ledger_approval.get("actor") or "")
        evidence=str(ledger_approval.get("evidence") or "")
        expected_evidence=str(request.get("evidence") or "")
        component=str(proposal.get("component_id") or "")
        candidate=str(proposal.get("candidate_revision") or "")
        proposal_digest=str(gate.get("binding_proposal_digest") or "")
        registry_adapters=registry.get("adapters") if isinstance(registry.get("adapters"),dict) else {}
        expected_after=copy.deepcopy(registry)
        if component and isinstance(expected_after.get("adapters"),dict):
            expected_after["adapters"][component]=copy.deepcopy(binding)

        checks={
          "state_schema":projection.get("schema")==STATE_SCHEMA,
          "ledger_schema":ledger.get("schema")==LEDGER_SCHEMA,
          "state_project":projection.get("project")==project,
          "ledger_project":ledger.get("project")==project,
          "platform_profile":identity.get("control_profile")=="platform",
          "bootstrap_marker":bootstrap.get("control_plane_ledger_initialized") is True,
          "binding_gate_schema":gate.get("schema")=="chacha.dev/platform-component-adapter-binding-gate/v1",
          "binding_gate_ready":gate.get("status")=="BINDING_PROPOSAL_READY_AWAIT_PROTECTED_REGISTRATION",
          "binding_proposal_created":gate.get("proposal_created") is True,
          "binding_proposal_schema":proposal.get("schema")=="chacha.dev/platform-component-adapter-binding-proposal/v1",
          "proposal_registration_not_preapproved":proposal.get("registration_authorized") is False,
          "proposal_registry_mutation_not_preapproved":proposal.get("registry_mutation_authorized") is False,
          "proposal_protected_registration_required":proposal.get("protected_registration_required") is True,
          "proposal_digest_present":bool(proposal_digest),
          "proposal_digest_matches":bool(proposal_digest) and canonical_digest(proposal)==proposal_digest,
          "approval_request_created":gate.get("human_registration_approval_request_created") is True,
          "approval_request_schema":request.get("schema")=="chacha.dev/protected-human-approval-request/v1",
          "approval_request_project":request.get("project")==project,
          "approval_request_operation":request.get("operation")=="record-approval",
          "approval_request_actor_real_human":request.get("actor_requirement")=="real-human",
          "approval_request_api_synthesis_forbidden":request.get("agent_or_api_approval_synthesis_forbidden") is True,
          "approval_request_digest_matches":request.get("binding_proposal_digest")==proposal_digest and bool(proposal_digest),
          "approval_request_evidence_exact":bool(proposal_digest) and expected_evidence=="platform-component-adapter-binding-proposal:"+proposal_digest,
          "component_present":bool(component),
          "candidate_revision_present":bool(candidate),
          "binding_adapter_present":bool(str(binding.get("adapter_id") or "")),
          "binding_status_qualified":binding.get("status")=="QUALIFIED",
          "binding_owner_matches":binding.get("candidate_owner")==proposal.get("candidate_owner") and bool(binding.get("candidate_owner")),
          "binding_source_only":binding.get("apply_mode")=="SOURCE_RELEASE_CANDIDATE_INTEGRATION",
          "binding_reversible":binding.get("reversible") is True,
          "binding_exact_revision":binding.get("exact_revision_enforced") is True,
          "binding_runtime_mutation_forbidden":binding.get("direct_runtime_mutation") is False,
          "binding_production_activation_forbidden":binding.get("production_activation") is False,
          "binding_production_deployment_forbidden":binding.get("production_deployment") is False,
          "binding_production_merge_forbidden":binding.get("merge_to_production_branch") is False,
          "binding_automatic_apply_forbidden":binding.get("automatic_apply") is False,
          "binding_zero_external_spend":float(binding.get("automatic_external_spend_eur") or 0)==0,
          "registry_schema":registry.get("schema")=="chacha.dev/platform-component-apply-adapter-registry/v1",
          "registry_default_deny":registry.get("default_admission")=="DENY",
          "component_not_already_registered":component not in registry_adapters,
          "approval_id_present":bool(approval_id),
          "ledger_approval_status":ledger_approval.get("status")=="APPROVED",
          "ledger_approval_actor_human":bool(actor) and actor not in system_actors,
          "ledger_approval_evidence_exact":bool(expected_evidence) and evidence==expected_evidence,
          "state_approval_status":state_approval.get("status")=="APPROVED",
          "state_approval_actor_matches":bool(actor) and state_approval.get("actor")==actor,
          "state_approval_evidence_matches":bool(evidence) and state_approval.get("evidence")==evidence,
          "zero_automatic_external_spend":float(proposal.get("automatic_external_spend_eur") or 0)==0,
        }
        blockers=sorted(k for k,v in checks.items() if not v)
        if blockers:
            return response(project,op,"BLOCKED","Platform adapter registration prerequisites are not satisfied.",
                            {"checks":checks},blockers)

        seed={
          "project":project,"component_id":component,"candidate_revision":candidate,
          "adapter_id":binding.get("adapter_id"),"approval_id":approval_id,
          "binding_proposal_digest":proposal_digest,
          "registry_before_digest":canonical_digest(registry),
          "registry_after_digest":canonical_digest(expected_after)
        }
        registration_id="pcar-"+hashlib.sha256(
          json.dumps(seed,sort_keys=True,separators=(",",":")).encode("utf-8")
        ).hexdigest()[:24]
        contract={
          "schema":"chacha.dev/platform-component-adapter-registration-contract/v1",
          "registration_id":registration_id,"project":project,"actor":"central-orchestrator",
          "issued_by_project_control":True,"human_approval_verified":True,
          "approval_id":approval_id,"approval_actor":actor,"approval_evidence":evidence,
          "binding_proposal_digest":proposal_digest,
          "component_id":component,"candidate_owner":proposal.get("candidate_owner"),
          "candidate_revision":candidate,"incumbent_revision":proposal.get("incumbent_revision"),
          "candidate_artifact_ref":proposal.get("candidate_artifact_ref"),
          "incumbent_artifact_ref":proposal.get("incumbent_artifact_ref"),
          "adapter_id":binding.get("adapter_id"),
          "registry_path":registry_rel,"registry_key":component,
          "registry_before_digest":canonical_digest(registry),
          "registry_after_digest":canonical_digest(expected_after),
          "exact_registry_binding":copy.deepcopy(binding),
          "registration_authorized":True,
          "registry_mutation_authorized_for_dedicated_writer":True,
          "additive_write_only":True,"overwrite_authorized":False,"delete_authorized":False,
          "default_deny_must_be_preserved":True,"single_use":True,
          "source_integration_authorized":False,
          "post_registration_exact_sha_gates_required":[
            "ChaCha DEV platform adapter binding gate qualification",
            "ChaCha DEV universal evolution coverage sync qualification",
            "ChaCha DEV Sentinel technical assurance"
          ],
          "direct_runtime_mutation_authorized":False,
          "production_activation_authorized":False,"production_deployment_authorized":False,
          "merge_to_production_branch_authorized":False,"automatic_apply":False,
          "control_plane_state_digest":canonical_digest(projection),
          "evidence_ledger_digest":canonical_digest(ledger),
          "automatic_external_spend_eur":0
        }

        output=output.resolve()
        if output.exists():
            try:existing=load(output)
            except Exception:
                return response(project,op,"BLOCKED","Existing registration contract output is invalid.",
                                {"output":str(output)},["ADAPTER_REGISTRATION_OUTPUT_CONFLICT"])
            stable=all((
              existing.get("schema")==contract["schema"],
              existing.get("registration_id")==registration_id,
              existing.get("component_id")==component,
              existing.get("candidate_revision")==candidate,
              existing.get("adapter_id")==binding.get("adapter_id"),
              existing.get("approval_id")==approval_id,
              existing.get("binding_proposal_digest")==proposal_digest,
              existing.get("registry_before_digest")==contract["registry_before_digest"],
              existing.get("registry_after_digest")==contract["registry_after_digest"],
              existing.get("single_use") is True,
              existing.get("registration_authorized") is True,
              existing.get("overwrite_authorized") is False,
              existing.get("delete_authorized") is False,
            ))
            if stable:
                return response(project,op,"OK","Identical adapter registration contract already exists.",
                                {"registration_id":registration_id,"contract":str(output),
                                 "contract_digest":canonical_digest(existing),"idempotent":True},
                                artifacts=[{"type":"platform-component-adapter-registration-contract","path":str(output)}])
            return response(project,op,"BLOCKED","Registration contract output already exists with different content.",
                            {"output":str(output)},["ADAPTER_REGISTRATION_OUTPUT_CONFLICT"])

        with tempfile.TemporaryDirectory(prefix="chacha-platform-adapter-registration-") as td:
            payload=Path(td)/"registration.json";save(payload,contract)
            rc_evt,event_values,out_evt,err_evt=store_record(
              project,"PLATFORM_COMPONENT_ADAPTER_REGISTRATION_ISSUED","central-orchestrator",
              payload,None,None,policy,repo_root
            )
            if rc_evt!=0:
                return response(project,op,"BLOCKED","Adapter registration audit event could not be committed.",
                                {"stdout":out_evt[-2000:],"stderr":err_evt[-1000:]},
                                ["ADAPTER_REGISTRATION_AUDIT_FAILED"])

        rc1,verify1,out1,err1=state_verify_raw(project,policy,repo_root)
        if rc1!=0:
            return response(project,op,"BLOCKED",
                            "Registration audit event committed but integrity recheck failed; no contract emitted.",
                            {"stdout":out1.strip(),"stderr":err1.strip()},
                            ["ADAPTER_REGISTRATION_INTEGRITY_UNCERTAIN"])

        output.parent.mkdir(parents=True,exist_ok=True);save(output,contract)
        return response(project,op,"OK","Protected component adapter registration contract issued.",
                        {"registration_id":registration_id,"contract":str(output),
                         "contract_digest":canonical_digest(contract),"idempotent":False,
                         "event_sequence":event_values.get("EVENT_SEQUENCE"),
                         "event_digest":event_values.get("EVENT_DIGEST"),"integrity":verify1},
                        artifacts=[{"type":"platform-component-adapter-registration-contract","path":str(output)}])


def issue_platform_component_apply_handoff(project: str, promotion_gate: Path, planner_result: Path,
                                           output: Path, policy: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    """Issue the single-use Central Orchestrator source-integration handoff.

    This operation is platform-profile only. It independently revalidates the
    protected human approval in both the Evidence Ledger and the control-plane
    projection, verifies Promotion Gate + controlled-apply plan identity, then
    records an auditable handoff event. It does not execute the integration.
    """
    if project!="chacha-dev-platform":
        return response(project,"issue-platform-component-apply-handoff","BLOCKED",
                        "Platform component apply handoff is restricted to chacha-dev-platform.",
                        blockers=["PLATFORM_CONTROL_PROJECT_REQUIRED"])
    if not promotion_gate.is_file() or not planner_result.is_file():
        return response(project,"issue-platform-component-apply-handoff","BLOCKED",
                        "Promotion Gate and controlled-apply planner evidence are required.",
                        {"promotion_gate":str(promotion_gate),"planner_result":str(planner_result)},
                        ["PLATFORM_APPLY_HANDOFF_INPUT_MISSING"])

    try:
        gate=load(promotion_gate);planner=load(planner_result)
    except Exception as exc:
        return response(project,"issue-platform-component-apply-handoff","BLOCKED",
                        "Platform apply handoff input is invalid.",
                        {"reason":str(exc)},["PLATFORM_APPLY_HANDOFF_INPUT_INVALID"])

    controlled=gate.get("controlled_apply_contract") if isinstance(gate.get("controlled_apply_contract"),dict) else {}
    plan=planner.get("apply_plan") if isinstance(planner.get("apply_plan"),dict) else {}
    p=project_paths(policy,project)
    system_actors={
      "central-orchestrator","guardian","sentinel","curator","bastion","intendant",
      "logician","ergonomist","architecture-council","agent-foundry","branch-foundry",
      "capability-foundry","platform-component-pilot-runner","platform-component-promotion-gate",
      "platform-component-controlled-apply-planner","platform-component-source-integration-executor"
    }

    with project_lock(p["lock"]):
        pending=pending_transactions(p["transactions"])
        if pending:
            return response(project,"issue-platform-component-apply-handoff","BLOCKED",
                            "A control transaction requires recovery before handoff issuance.",
                            blockers=pending)
        rc0,verify0,out0,err0=state_verify_raw(project,policy,repo_root)
        if rc0!=0:
            return response(project,"issue-platform-component-apply-handoff","BLOCKED",
                            "Control-plane integrity failed before handoff issuance.",
                            {"stdout":out0.strip(),"stderr":err0.strip()},
                            ["CONTROL_PLANE_INTEGRITY_FAILED"])
        if not p["state"].is_file() or not p["ledger"].is_file():
            return response(project,"issue-platform-component-apply-handoff","BLOCKED",
                            "Platform control-plane state or Evidence Ledger is missing.",
                            blockers=["PLATFORM_CONTROL_PLANE_NOT_BOOTSTRAPPED"])
        projection=load(p["state"]);ledger=load(p["ledger"])
        identity=((projection.get("state") or {}).get("identity") or {})
        bootstrap=((projection.get("state") or {}).get("evidence") or {})
        approval_id=str(controlled.get("approval_id") or "")
        ledger_approval=((ledger.get("approvals") or {}).get(approval_id) or {}) if approval_id else {}
        state_approval=((((projection.get("state") or {}).get("approvals") or {}).get(approval_id) or {})
                        if approval_id else {})
        actor=str(ledger_approval.get("actor") or "")
        evidence=str(ledger_approval.get("evidence") or "")
        expected_actor=str(controlled.get("approval_actor") or "")
        expected_evidence=str(controlled.get("approval_evidence") or "")
        post_gate=set(str(x) for x in (controlled.get("post_apply_exact_sha_gates_required") or []) if str(x))
        post_plan=set(str(x) for x in (plan.get("post_apply_exact_sha_gates_required") or []) if str(x))
        checks={
          "state_schema":projection.get("schema")==STATE_SCHEMA,
          "ledger_schema":ledger.get("schema")==LEDGER_SCHEMA,
          "state_project":projection.get("project")==project,
          "ledger_project":ledger.get("project")==project,
          "platform_profile":identity.get("control_profile")=="platform",
          "bootstrap_marker":bootstrap.get("control_plane_ledger_initialized") is True,
          "gate_schema":gate.get("schema")=="chacha.dev/platform-component-promotion-gate/v1",
          "gate_status":gate.get("status")=="PROMOTION_AUTHORIZED_FOR_CONTROLLED_APPLY",
          "gate_human_approval_verified":gate.get("human_approval_verified") is True,
          "gate_promotion_authorized":gate.get("promotion_authorized") is True,
          "gate_controlled_contract":controlled.get("schema")=="chacha.dev/platform-component-controlled-apply-contract/v1",
          "gate_source_candidate_only":controlled.get("apply_mode")=="SOURCE_RELEASE_CANDIDATE_INTEGRATION",
          "gate_central_orchestrator_required":controlled.get("central_orchestrator_apply_required") is True,
          "gate_adapter_required":controlled.get("candidate_owner_apply_adapter_required") is True,
          "gate_runtime_mutation_forbidden":controlled.get("direct_runtime_mutation_authorized") is False,
          "gate_production_activation_forbidden":controlled.get("production_activation_authorized") is False,
          "gate_production_deployment_forbidden":controlled.get("production_deployment_authorized") is False,
          "gate_production_merge_forbidden":controlled.get("merge_to_production_branch_authorized") is False,
          "gate_automatic_apply_forbidden":controlled.get("automatic_apply") is False,
          "gate_rollback_required":controlled.get("rollback_required") is True,
          "gate_guardian_post_apply_required":controlled.get("guardian_post_apply_assurance_required") is True,
          "planner_schema":planner.get("schema")=="chacha.dev/platform-component-controlled-apply-planner/v1",
          "planner_ready":planner.get("status")=="READY_FOR_CENTRAL_ORCHESTRATOR_APPLY",
          "planner_plan_ready":planner.get("controlled_apply_plan_ready") is True,
          "planner_did_not_authorize_execution":planner.get("apply_execution_authorized_by_planner") is False,
          "plan_schema":plan.get("schema")=="chacha.dev/platform-component-controlled-apply-plan/v1",
          "plan_source_candidate_only":plan.get("apply_mode")=="SOURCE_RELEASE_CANDIDATE_INTEGRATION",
          "plan_adapter_present":bool(str(plan.get("adapter_id") or "")),
          "plan_rollback_adapter_present":bool(str(plan.get("rollback_adapter_id") or "")),
          "plan_central_orchestrator_required":plan.get("central_orchestrator_apply_required") is True,
          "plan_runtime_mutation_forbidden":plan.get("direct_runtime_mutation") is False,
          "plan_production_activation_forbidden":plan.get("production_activation_allowed") is False,
          "plan_production_deployment_forbidden":plan.get("production_deployment_allowed") is False,
          "plan_production_merge_forbidden":plan.get("merge_to_production_branch_allowed") is False,
          "plan_rollback_required":plan.get("rollback_required") is True,
          "component_matches":plan.get("component_id")==controlled.get("component_id") and bool(plan.get("component_id")),
          "candidate_owner_matches":plan.get("candidate_owner")==controlled.get("candidate_owner") and bool(plan.get("candidate_owner")),
          "candidate_revision_matches":plan.get("candidate_revision")==controlled.get("candidate_revision") and bool(plan.get("candidate_revision")),
          "incumbent_revision_matches":plan.get("incumbent_revision")==controlled.get("incumbent_revision") and bool(plan.get("incumbent_revision")),
          "candidate_artifact_matches":plan.get("candidate_artifact_ref")==controlled.get("candidate_artifact_ref") and bool(plan.get("candidate_artifact_ref")),
          "incumbent_artifact_matches":plan.get("incumbent_artifact_ref")==controlled.get("incumbent_artifact_ref") and bool(plan.get("incumbent_artifact_ref")),
          "source_qualification_matches":plan.get("source_qualification_workflow_name")==controlled.get("qualification_workflow_name") and bool(plan.get("source_qualification_workflow_name")),
          "post_apply_gate_set_matches":bool(post_gate) and post_gate==post_plan,
          "post_apply_sentinel_required":"ChaCha DEV Sentinel technical assurance" in post_plan,
          "approval_id_present":bool(approval_id),
          "ledger_approval_status":ledger_approval.get("status")=="APPROVED",
          "ledger_approval_actor_human":bool(actor) and actor not in system_actors,
          "ledger_approval_actor_matches":bool(expected_actor) and actor==expected_actor,
          "ledger_approval_evidence_matches":bool(expected_evidence) and evidence==expected_evidence,
          "state_approval_status":state_approval.get("status")=="APPROVED",
          "state_approval_actor_matches":bool(actor) and state_approval.get("actor")==actor,
          "state_approval_evidence_matches":bool(evidence) and state_approval.get("evidence")==evidence,
          "planner_approval_id_matches":planner.get("approval_id")==approval_id,
          "planner_approval_actor_matches":planner.get("approval_actor")==actor,
          "planner_review_digest_matches":planner.get("technical_review_digest")==controlled.get("technical_review_digest") and bool(controlled.get("technical_review_digest")),
          "zero_automatic_external_spend":float(controlled.get("automatic_external_spend_eur") or 0)==0 and float(plan.get("automatic_external_spend_eur") or 0)==0,
        }
        blockers=sorted(k for k,v in checks.items() if not v)
        if blockers:
            return response(project,"issue-platform-component-apply-handoff","BLOCKED",
                            "Platform component apply handoff prerequisites are not satisfied.",
                            {"checks":checks},blockers)

        handoff_seed={
          "project":project,"component_id":plan.get("component_id"),
          "candidate_revision":plan.get("candidate_revision"),"incumbent_revision":plan.get("incumbent_revision"),
          "adapter_id":plan.get("adapter_id"),"approval_id":approval_id,
          "controlled_apply_plan_digest":canonical_digest(plan),
          "technical_review_digest":controlled.get("technical_review_digest")
        }
        handoff_id="pcah-"+hashlib.sha256(
          json.dumps(handoff_seed,sort_keys=True,separators=(",",":")).encode("utf-8")
        ).hexdigest()[:24]
        handoff={
          "schema":"chacha.dev/platform-component-central-apply-handoff/v1",
          "handoff_id":handoff_id,"project":project,"actor":"central-orchestrator",
          "issued_by_project_control":True,"human_approval_verified":True,
          "approval_id":approval_id,"approval_actor":actor,"approval_evidence":evidence,
          "technical_review_digest":controlled.get("technical_review_digest"),
          "promotion_gate_digest":canonical_digest(gate),"planner_result_digest":canonical_digest(planner),
          "controlled_apply_plan_digest":canonical_digest(plan),
          "component_id":plan.get("component_id"),"candidate_owner":plan.get("candidate_owner"),
          "candidate_revision":plan.get("candidate_revision"),"incumbent_revision":plan.get("incumbent_revision"),
          "candidate_artifact_ref":plan.get("candidate_artifact_ref"),"incumbent_artifact_ref":plan.get("incumbent_artifact_ref"),
          "adapter_id":plan.get("adapter_id"),"rollback_adapter_id":plan.get("rollback_adapter_id"),
          "adapter_qualification_workflow_name":plan.get("adapter_qualification_workflow_name"),
          "source_qualification_workflow_name":plan.get("source_qualification_workflow_name"),
          "post_apply_exact_sha_gates_required":list(plan.get("post_apply_exact_sha_gates_required") or []),
          "apply_execution_authorized":True,"single_use":True,
          "source_candidate_integration_only":True,
          "rollback_required":True,"guardian_pre_post_required":True,"emergency_stop_required":True,
          "direct_runtime_mutation_authorized":False,
          "production_activation_authorized":False,"production_deployment_authorized":False,
          "merge_to_production_branch_authorized":False,"automatic_apply":False,
          "control_plane_state_digest":canonical_digest(projection),
          "evidence_ledger_digest":canonical_digest(ledger),
          "automatic_external_spend_eur":0
        }

        output=output.resolve()
        if output.exists():
            try:existing=load(output)
            except Exception:
                return response(project,"issue-platform-component-apply-handoff","BLOCKED",
                                "Existing handoff output is invalid.",
                                {"output":str(output)},["HANDOFF_OUTPUT_CONFLICT"])
            stable_match=all((
              existing.get("schema")=="chacha.dev/platform-component-central-apply-handoff/v1",
              existing.get("handoff_id")==handoff_id,
              existing.get("project")==project,
              existing.get("component_id")==handoff.get("component_id"),
              existing.get("candidate_revision")==handoff.get("candidate_revision"),
              existing.get("incumbent_revision")==handoff.get("incumbent_revision"),
              existing.get("adapter_id")==handoff.get("adapter_id"),
              existing.get("approval_id")==approval_id,
              existing.get("approval_actor")==actor,
              existing.get("approval_evidence")==evidence,
              existing.get("technical_review_digest")==handoff.get("technical_review_digest"),
              existing.get("promotion_gate_digest")==handoff.get("promotion_gate_digest"),
              existing.get("planner_result_digest")==handoff.get("planner_result_digest"),
              existing.get("controlled_apply_plan_digest")==handoff.get("controlled_apply_plan_digest"),
              existing.get("single_use") is True,
              existing.get("apply_execution_authorized") is True,
              existing.get("direct_runtime_mutation_authorized") is False,
              existing.get("production_activation_authorized") is False,
              existing.get("production_deployment_authorized") is False,
              existing.get("merge_to_production_branch_authorized") is False,
            ))
            if stable_match:
                return response(project,"issue-platform-component-apply-handoff","OK",
                                "Identical Central Orchestrator handoff already exists.",
                                {"handoff_id":handoff_id,"handoff":str(output),
                                 "handoff_digest":canonical_digest(existing),"idempotent":True},
                                artifacts=[{"type":"platform-component-central-apply-handoff","path":str(output)}])
            return response(project,"issue-platform-component-apply-handoff","BLOCKED",
                            "Handoff output already exists with different content.",
                            {"output":str(output)},["HANDOFF_OUTPUT_CONFLICT"])

        with tempfile.TemporaryDirectory(prefix="chacha-platform-apply-handoff-") as td:
            payload=Path(td)/"handoff.json";save(payload,handoff)
            rc_evt,event_values,out_evt,err_evt=store_record(
              project,"PLATFORM_COMPONENT_APPLY_HANDOFF_ISSUED","central-orchestrator",
              payload,None,None,policy,repo_root
            )
            if rc_evt!=0:
                return response(project,"issue-platform-component-apply-handoff","BLOCKED",
                                "Central apply handoff audit event could not be committed.",
                                {"stdout":out_evt[-2000:],"stderr":err_evt[-1000:]},
                                ["PLATFORM_APPLY_HANDOFF_AUDIT_FAILED"])

        rc1,verify1,out1,err1=state_verify_raw(project,policy,repo_root)
        if rc1!=0:
            return response(project,"issue-platform-component-apply-handoff","BLOCKED",
                            "Handoff audit event committed but integrity recheck failed; no executable handoff was emitted.",
                            {"stdout":out1.strip(),"stderr":err1.strip()},
                            ["PLATFORM_APPLY_HANDOFF_INTEGRITY_UNCERTAIN"])

        output.parent.mkdir(parents=True,exist_ok=True)
        save(output,handoff)
        return response(project,"issue-platform-component-apply-handoff","OK",
                        "Single-use Central Orchestrator source-integration handoff issued.",
                        {"handoff_id":handoff_id,"handoff":str(output),
                         "handoff_digest":canonical_digest(handoff),"idempotent":False,
                         "event_sequence":event_values.get("EVENT_SEQUENCE"),
                         "event_digest":event_values.get("EVENT_DIGEST"),
                         "integrity":verify1},
                        artifacts=[{"type":"platform-component-central-apply-handoff","path":str(output)}])


def record_control_event(project: str, event_type: str, actor: str, payload: Path | None, patch: Path | None,
                         references: Path | None, policy: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    p = project_paths(policy, project)
    txn = policy.get("transaction_policy") or {}
    protected_events = set(txn.get("protected_event_types") or [])
    if event_type in protected_events:
        return response(project, "record-control-event", "BLOCKED", "This event type requires a dedicated controlled operation.",
                        {"event_type": event_type}, [f"PROTECTED_EVENT_TYPE:{event_type}"])
    if patch:
        patch_value = load(patch)
        protected_sections = set(txn.get("protected_state_sections") or [])
        touched = protected_sections & set(patch_value.keys())
        if touched:
            return response(project, "record-control-event", "BLOCKED", "Generic control event cannot mutate protected state sections.",
                            {"protected_sections": sorted(touched)}, [f"PROTECTED_STATE_SECTION:{x}" for x in sorted(touched)])
    with project_lock(p["lock"]):
        rc0, _, out0, err0 = state_verify_raw(project, policy, repo_root)
        if rc0 != 0:
            return response(project, "record-control-event", "BLOCKED", "Control-plane integrity failed before mutation.",
                            {"stdout": out0.strip(), "stderr": err0.strip()}, ["CONTROL_PLANE_INTEGRITY_FAILED"])
        rc, values, stdout, stderr = store_record(project, event_type, actor, payload, patch, references, policy, repo_root)
        if rc != 0:
            return response(project, "record-control-event", "FAILED", "Control-plane event could not be recorded.",
                            {"stdout": stdout.strip(), "stderr": stderr.strip()}, ["CONTROL_EVENT_RECORD_FAILED"])
        rc1, verify_values, out1, err1 = state_verify_raw(project, policy, repo_root)
        if rc1 != 0:
            return response(project, "record-control-event", "BLOCKED", "Event was recorded but integrity recheck failed.",
                            {"stdout": out1.strip(), "stderr": err1.strip(), **values},
                            ["CONTROL_PLANE_POST_WRITE_INTEGRITY_FAILED"])
        return response(project, "record-control-event", "OK", f"Control-plane event {event_type} recorded.",
                        {**values, "integrity": verify_values})


def verify_result_operation(project: str, result_path: Path, graph: Path, method: str, verifier: str,
                            ingest: bool, policy: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    p = project_paths(policy, project)
    refs, tools = policy.get("repository_paths") or {}, policy.get("engine_paths") or {}
    source_result = load(result_path)
    if source_result.get("project") != project:
        return response(project, "verify-result", "BLOCKED", "Task result belongs to a different project.", blockers=["PROJECT_MISMATCH"])
    txid = "ctx-" + uuid.uuid4().hex
    txdir = p["transactions"] / txid
    txdir.mkdir(parents=True, exist_ok=False)
    report = txdir / "verification-report.json"
    verified = txdir / "verified-task-result.json"
    receipt = txdir / "receipt.json"
    rc, stdout, stderr = run_tool(resolve_repo(repo_root, tools["verification_broker"]), [
        "--result", str(result_path), "--graph", str(graph),
        "--policy", str(resolve_repo(repo_root, refs["verification_broker"])),
        "--report", str(report), "--verified-result", str(verified),
        "--verifier", verifier, "--method", method,
    ])
    values, _ = parse_kv(stdout)
    if rc != 0 or not verified.exists():
        write_receipt(receipt, {
            "transaction_id": txid, "project": project, "operation": "verify-result", "status": "FAILED",
            "verification_status": values.get("VERIFICATION_STATUS"), "stdout": stdout.strip(), "stderr": stderr.strip(),
        })
        status = "BLOCKED" if values.get("VERIFICATION_STATUS") == "NEEDS_INDEPENDENT_CHECK" else "FAILED"
        return response(project, "verify-result", status, "Task result did not pass independent verification.",
                        {"transaction_id": txid, "report": str(report), "stdout": stdout.strip(), "stderr": stderr.strip(), **values},
                        [f"VERIFICATION_STATUS:{values.get('VERIFICATION_STATUS') or 'FAILED'}"],
                        artifacts=[{"type": "verification-report", "path": str(report)}])

    graph_value = load(graph)
    adapters_path = resolve_repo(repo_root, refs["provider_adapters"])
    adapters_value = load(adapters_path)
    verified_value = load(verified)
    verified_value, learning_context_status, dispatch_envelope = tdl.enrich_verified_result(
        verified=verified_value,
        source_result_path=result_path,
        graph=graph_value,
        adapters=adapters_value,
    )
    save(verified, verified_value)
    trusted_learning_context = isinstance(verified_value.get("learning_context"), dict)

    # V6.48: independent verification is a trusted Agent Observation Bus boundary.
    try:
        task_id=str(source_result.get("task_id") or "")
        owner_role=""
        capabilities=[]
        for row in graph_value.get("tasks") or []:
            if isinstance(row,dict) and str(row.get("id") or "")==task_id:
                owner_role=str(row.get("owner_role") or "")
                capabilities=[str(x) for x in (row.get("capabilities") or [])]
                break
        if owner_role:
            refs=[str(verified),str(report)]
            if dispatch_envelope:refs.append(str(dispatch_envelope))
            aob.publish({
              "schema":"chacha.dev/agent-observation-event/v1",
              "event_id":"aobs-verify-"+project+"-"+task_id+"-"+txid,
              "event_type":"TASK_RESULT_VERIFIED",
              "source_id":"project-control",
              "source_surface":"project-control:verification-broker",
              "project_id":project,
              "revision":aob.runtime_revision(),
              "task_id":task_id,
              "subject_role":owner_role,
              "outcome":str(verified_value.get("status") or "UNKNOWN").upper(),
              "verification":"VERIFIED",
              "capabilities":capabilities,
              "evidence_refs":refs,
              "details":{"verifier":verifier,"method":method,"producer":verified_value.get("producer"),
                         "learning_context_status":learning_context_status}
            })
    except Exception:
        # Observability must never rewrite verification semantics or block evidence ingestion.
        pass

    if not ingest:
        write_receipt(receipt, {
            "transaction_id": txid, "project": project, "operation": "verify-result", "status": "VERIFIED_ONLY",
            "verification_status": "VERIFIED", "verified_result": str(verified), "report": str(report),
            "learning_context_status": learning_context_status,
            "trusted_learning_context": trusted_learning_context,
            "dispatch_envelope": str(dispatch_envelope) if dispatch_envelope else None,
        })
        return response(project, "verify-result", "OK", "Task result independently verified; Evidence Ledger was not mutated.",
                        {"transaction_id": txid, "verification_status": "VERIFIED", "report": str(report), "verified_result": str(verified),
                         "learning_context_status": learning_context_status,
                         "trusted_learning_context": trusted_learning_context,
                         "dispatch_envelope": str(dispatch_envelope) if dispatch_envelope else None},
                        artifacts=[{"type": "verification-report", "path": str(report)},
                                   {"type": "verified-task-result", "path": str(verified)}])
    if not p["ledger"].exists():
        write_receipt(receipt, {
            "transaction_id": txid, "project": project, "operation": "verify-result", "status": "FAILED",
            "verification_status": "VERIFIED", "failure": "EVIDENCE_LEDGER_MISSING",
            "verified_result": str(verified), "report": str(report),
        })
        return response(project, "verify-result", "BLOCKED", "Evidence ledger missing; verified result retained for later ingestion.",
                        {"transaction_id": txid, "verified_result": str(verified)}, ["EVIDENCE_LEDGER_MISSING"])
    with project_lock(p["lock"]):
        foreign = pending_transactions(p["transactions"])
        if foreign:
            return response(project, "verify-result", "BLOCKED", "Another control transaction requires recovery.", blockers=foreign)
        rc0, _, out0, err0 = state_verify_raw(project, policy, repo_root)
        if rc0 != 0:
            return response(project, "verify-result", "BLOCKED", "Control-plane integrity failed before evidence ingestion.",
                            {"stdout": out0.strip(), "stderr": err0.strip()}, ["CONTROL_PLANE_INTEGRITY_FAILED"])
        original_ledger = load(p["ledger"])
        if original_ledger.get("schema") != LEDGER_SCHEMA:
            return response(project, "verify-result", "BLOCKED", "Evidence ledger schema invalid.", blockers=["EVIDENCE_LEDGER_SCHEMA_INVALID"])
        staged = txdir / "staged-ledger.json"
        shutil.copy2(p["ledger"], staged)
        ingest_args = [
            "ingest", "--graph", str(graph), "--result", str(verified), "--ledger", str(staged),
        ]
        if trusted_learning_context and dispatch_envelope is not None:
            ingest_args += ["--dispatch-envelope", str(dispatch_envelope), "--adapters", str(adapters_path)]
        rc_ing, out_ing, err_ing = run_tool(resolve_repo(repo_root, tools["evidence_collector"]), ingest_args)
        if rc_ing != 0:
            write_receipt(receipt, {
                "transaction_id": txid, "project": project, "operation": "verify-result", "status": "FAILED",
                "verification_status": "VERIFIED", "failure": "EVIDENCE_INGEST_FAILED",
                "stdout": out_ing.strip(), "stderr": err_ing.strip(),
            })
            return response(project, "verify-result", "FAILED", "Verified result could not be staged into Evidence Ledger.",
                            {"transaction_id": txid, "stdout": out_ing.strip(), "stderr": err_ing.strip()},
                            ["EVIDENCE_INGEST_FAILED"])
        new_ledger = load(staged)
        old_digest = canonical_digest(original_ledger)
        new_digest = canonical_digest(new_ledger)
        write_receipt(receipt, {
            "transaction_id": txid, "project": project, "operation": "verify-result", "status": "PREPARED",
            "verification_status": "VERIFIED", "old_ledger_digest": old_digest, "new_ledger_digest": new_digest,
            "verified_result": str(verified), "report": str(report), "staged_ledger": str(staged),
            "learning_context_status": learning_context_status,
            "trusted_learning_context": trusted_learning_context,
            "dispatch_envelope": str(dispatch_envelope) if dispatch_envelope else None,
        })
        payload_path = txdir / "audit-payload.json"
        save(payload_path, {
            "transaction_id": txid,
            "task_id": source_result.get("task_id"),
            "verification_report": str(report),
            "verified_task_result": str(verified),
            "old_ledger_digest": old_digest,
            "new_ledger_digest": new_digest,
            "staged_ledger": str(staged),
            "commit_protocol": "journal-first-ledger-finalize",
        })
        rc_evt, event_values, out_evt, err_evt = store_record(
            project, "EVIDENCE_RECORDED", verifier, payload_path, None, None, policy, repo_root
        )
        if rc_evt != 0:
            write_receipt(receipt, {
                "transaction_id": txid, "project": project, "operation": "verify-result", "status": "FAILED",
                "failure": "EVIDENCE_AUDIT_COMMIT_FAILED", "stdout": out_evt.strip(), "stderr": err_evt.strip(),
                "staged_ledger": str(staged),
            })
            return response(project, "verify-result", "FAILED", "Evidence was staged but audit commit failed.",
                            {"transaction_id": txid, "staged_ledger": str(staged)},
                            ["EVIDENCE_AUDIT_COMMIT_FAILED"])
        p["ledger"].parent.mkdir(parents=True, exist_ok=True)
        fd, ledger_tmp_name = tempfile.mkstemp(prefix="ledger.", suffix=".txn", dir=str(p["ledger"].parent))
        os.close(fd)
        ledger_tmp = Path(ledger_tmp_name)
        try:
            shutil.copy2(staged, ledger_tmp)
            with ledger_tmp.open("rb") as fh:
                os.fsync(fh.fileno())
            os.replace(ledger_tmp, p["ledger"])
        except Exception as exc:
            if ledger_tmp.exists():
                ledger_tmp.unlink()
            write_receipt(receipt, {
                "transaction_id": txid, "project": project, "operation": "verify-result",
                "status": "CONTROL_EVENT_COMMITTED_LEDGER_PENDING",
                "failure": str(exc), "event": event_values, "staged_ledger": str(staged),
                "new_ledger_digest": new_digest,
            })
            return response(project, "verify-result", "BLOCKED",
                            "Evidence audit event committed but ledger finalization requires recovery.",
                            {"transaction_id": txid, "staged_ledger": str(staged), **event_values},
                            ["CONTROL_TRANSACTION_LEDGER_FINALIZE_PENDING"])
        finalized = load(p["ledger"])
        if canonical_digest(finalized) != new_digest:
            write_receipt(receipt, {
                "transaction_id": txid, "project": project, "operation": "verify-result", "status": "COMMIT_UNCERTAIN",
                "event": event_values, "expected_ledger_digest": new_digest,
                "actual_ledger_digest": canonical_digest(finalized),
            })
            return response(project, "verify-result", "BLOCKED", "Evidence Ledger digest does not match staged transaction.",
                            {"transaction_id": txid}, ["CONTROL_TRANSACTION_COMMIT_UNCERTAIN"])
        write_receipt(receipt, {
            "transaction_id": txid, "project": project, "operation": "verify-result", "status": "COMMITTED",
            "verification_status": "VERIFIED", "event_sequence": event_values.get("EVENT_SEQUENCE"),
            "event_digest": event_values.get("EVENT_DIGEST"), "old_ledger_digest": old_digest,
            "new_ledger_digest": new_digest, "verified_result": str(verified), "report": str(report),
        })
        return response(project, "verify-result", "OK", "Task result verified, ingested and audit-linked.",
                        {"transaction_id": txid, "verification_status": "VERIFIED",
                         "event_sequence": event_values.get("EVENT_SEQUENCE"),
                         "event_digest": event_values.get("EVENT_DIGEST"),
                         "ledger_digest": new_digest, "receipt": str(receipt),
                         "learning_context_status": learning_context_status,
                         "trusted_learning_context": trusted_learning_context,
                         "dispatch_envelope": str(dispatch_envelope) if dispatch_envelope else None},
                        artifacts=[{"type": "verification-report", "path": str(report)},
                                   {"type": "verified-task-result", "path": str(verified)},
                                   {"type": "control-transaction-receipt", "path": str(receipt)}])


def main() -> int:
    parser = argparse.ArgumentParser(description="ChaCha DEV HUB unified project control")
    parser.add_argument("--policy", type=Path, default=Path("dev-hub/config/project-control.v1.json"))
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--json", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    for name in ("status", "explain", "verify-state"):
        item = sub.add_parser(name)
        item.add_argument("--project", required=True)

    plan = sub.add_parser("plan-transition")
    plan.add_argument("--project", required=True)
    plan.add_argument("--target")

    sched = sub.add_parser("schedule")
    sched.add_argument("--project", required=True)
    sched.add_argument("--graph", type=Path)

    prep = sub.add_parser("prepare-run")
    prep.add_argument("--project", required=True)
    prep.add_argument("--plan", required=True, type=Path)
    prep.add_argument("--graph", required=True, type=Path)
    prep.add_argument("--workspace")

    dispatch = sub.add_parser("dispatch")
    dispatch.add_argument("--project", required=True)
    dispatch.add_argument("--plan", required=True, type=Path)
    dispatch.add_argument("--graph", required=True, type=Path)
    dispatch.add_argument("--workspace")
    dispatch.add_argument("--execute", action="store_true")

    verify = sub.add_parser("verify-result")
    verify.add_argument("--project", required=True)
    verify.add_argument("--result", required=True, type=Path)
    verify.add_argument("--graph", required=True, type=Path)
    verify.add_argument("--method", choices=["machine", "independent-agent", "human"], default="machine")
    verify.add_argument("--verifier", default="verification-broker")
    verify.add_argument("--ingest", action="store_true")

    bootstrap = sub.add_parser("bootstrap-control-plane")
    bootstrap.add_argument("--project", required=True)
    bootstrap.add_argument("--actor", default="central-orchestrator")
    bootstrap.add_argument("--profile", choices=["project","platform"], default="project")

    registration = sub.add_parser("issue-platform-component-adapter-registration")
    registration.add_argument("--project", required=True)
    registration.add_argument("--binding-gate", type=Path, required=True)
    registration.add_argument("--output", type=Path, required=True)

    handoff = sub.add_parser("issue-platform-component-apply-handoff")
    handoff.add_argument("--project", required=True)
    handoff.add_argument("--promotion-gate", type=Path, required=True)
    handoff.add_argument("--planner-result", type=Path, required=True)
    handoff.add_argument("--output", type=Path, required=True)

    approve = sub.add_parser("record-approval")
    approve.add_argument("--project", required=True)
    approve.add_argument("--approval-id", required=True)
    approve.add_argument("--actor", required=True)
    approve.add_argument("--evidence")

    record = sub.add_parser("record-control-event")
    record.add_argument("--project", required=True)
    record.add_argument("--event-type", required=True)
    record.add_argument("--actor", required=True)
    record.add_argument("--payload", type=Path)
    record.add_argument("--patch", type=Path)
    record.add_argument("--references", type=Path)

    advance = sub.add_parser("advance")
    advance.add_argument("--project", required=True)
    advance.add_argument("--target")
    advance.add_argument("--actor", default="project-owner")

    crypto = sub.add_parser("crypto-verify")
    crypto.add_argument("--project", required=True)
    crypto.add_argument("--checkpoint", required=True, type=Path)
    crypto.add_argument("--public-key", required=True, type=Path)

    args = parser.parse_args()
    policy_path = args.policy if args.policy.is_absolute() else args.repo_root / args.policy
    policy = load(policy_path)
    if policy.get("schema") != POLICY_SCHEMA:
        raise SystemExit(f"POLICY_SCHEMA_INVALID={policy.get('schema')}")

    if args.command in {"status", "explain"}:
        result = status_operation(args.project, policy, args.repo_root)
        result["operation"] = args.command
    elif args.command == "verify-state":
        result = verify_state(args.project, policy, args.repo_root)
    elif args.command == "plan-transition":
        result = plan_transition(args.project, args.target, policy, args.repo_root)
    elif args.command == "schedule":
        result = schedule_operation(args.project, args.graph, policy, args.repo_root)
    elif args.command == "prepare-run":
        result = prepare_or_dispatch(args.project, False, args.plan, args.graph, args.workspace, policy, args.repo_root)
    elif args.command == "dispatch":
        if not args.execute:
            result = response(args.project, "dispatch", "BLOCKED", "Dispatch requires the explicit --execute flag.",
                              blockers=["EXPLICIT_DISPATCH_FLAG_REQUIRED"])
        else:
            result = prepare_or_dispatch(args.project, True, args.plan, args.graph, args.workspace, policy, args.repo_root)
    elif args.command == "verify-result":
        result = verify_result_operation(args.project, args.result, args.graph, args.method, args.verifier,
                                         args.ingest, policy, args.repo_root)
    elif args.command == "bootstrap-control-plane":
        result = bootstrap_control_plane_operation(args.project,args.actor,args.profile,policy,args.repo_root)
    elif args.command == "issue-platform-component-adapter-registration":
        result = issue_platform_component_adapter_registration(
          args.project,args.binding_gate,args.output,policy,args.repo_root
        )
    elif args.command == "issue-platform-component-apply-handoff":
        result = issue_platform_component_apply_handoff(
          args.project,args.promotion_gate,args.planner_result,args.output,policy,args.repo_root
        )
    elif args.command == "record-approval":
        result = record_approval_operation(args.project, args.approval_id, args.actor, args.evidence,
                                           policy, args.repo_root)
    elif args.command == "record-control-event":
        result = record_control_event(args.project, args.event_type, args.actor, args.payload, args.patch,
                                      args.references, policy, args.repo_root)
    elif args.command == "advance":
        result = advance_operation(args.project, args.target, args.actor, policy, args.repo_root)
    elif args.command == "crypto-verify":
        result = crypto_verify(args.project, args.checkpoint, args.public_key, policy, args.repo_root)
    else:
        raise SystemExit("UNKNOWN_COMMAND")

    emit(result, args.json)
    return 0 if result["status"] in {"READY", "OK", "COMPLETE"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
