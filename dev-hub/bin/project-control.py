#!/usr/bin/env python3
"""ChaCha DEV HUB Project Control V1.1.

Unified local control surface for one project. It does not expose a network
listener. The control-plane journal/projection is canonical. Mutating operations
are serialized per project, recheck integrity, and delegate to specialist
engines using structured argv without shell interpolation.
"""
from __future__ import annotations

import argparse
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
    lifecycle_path = resolve_repo(repo_root, (policy.get("repository_paths") or {})["lifecycle"])
    lifecycle = load(lifecycle_path)
    target = next_stage(lifecycle, stage)
    tx_blockers = pending_transactions(p["transactions"])
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
        if rc_check != 0 or blockers:
            details = {"transition": f"{current}->{target}", "engine_error": err_check, **values}
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
                         "post_version": post.get("version"), "receipt": str(receipt)},
                        artifacts=[{"type": "control-transaction-receipt", "path": str(receipt)}])


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
    if not ingest:
        write_receipt(receipt, {
            "transaction_id": txid, "project": project, "operation": "verify-result", "status": "VERIFIED_ONLY",
            "verification_status": "VERIFIED", "verified_result": str(verified), "report": str(report),
        })
        return response(project, "verify-result", "OK", "Task result independently verified; Evidence Ledger was not mutated.",
                        {"transaction_id": txid, "verification_status": "VERIFIED", "report": str(report), "verified_result": str(verified)},
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
        rc_ing, out_ing, err_ing = run_tool(resolve_repo(repo_root, tools["evidence_collector"]), [
            "ingest", "--graph", str(graph), "--result", str(verified), "--ledger", str(staged),
        ])
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
                         "ledger_digest": new_digest, "receipt": str(receipt)},
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
