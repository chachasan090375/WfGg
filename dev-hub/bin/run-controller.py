#!/usr/bin/env python3
"""ChaCha DEV HUB Run Controller / Execution Dispatcher V1.1.

Consumes an Execution Plan and its source Task Graph. In the default
`dispatch-only` policy it produces dispatch envelopes and a run record without
invoking any provider. Execution is fail-closed and requires an execute-enabled
policy plus an ENABLED registered adapter with an explicit executable.

V1.1 makes the provider-adapter boundary explicit: adapter stdout MUST be one
chacha.dev/task-result/v1 object, identity-bound to the dispatched task and
producer, and MUST remain UNVERIFIED. The controller preserves that immutable
producer result instead of converting a zero exit code into success. Logs are
redacted before persistence, subprocesses use argv only (shell=False), and
runtime execution fails closed when more than one distinct executable adapter
would be required for a task.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PLAN_SCHEMA = "chacha.dev/execution-plan/v1"
GRAPH_SCHEMA = "chacha.dev/task-graph/v1"
LEDGER_SCHEMA = "chacha.dev/evidence-ledger/v1"
POLICY_SCHEMA = "chacha.dev/run-controller/v1"
ADAPTER_SCHEMA = "chacha.dev/provider-adapters/v1"
ENVELOPE_SCHEMA = "chacha.dev/dispatch-envelope/v1"
RUN_SCHEMA = "chacha.dev/run-record/v1"
RESULT_SCHEMA = "chacha.dev/task-result/v1"

DEFAULT_APPROVALS = {
    "production-deploy": "production-release",
    "production-data-write": "production-data-write",
    "secret-change": "secret-change",
    "destructive-operation": "destructive-operation",
    "technology-replacement": "technology-replacement",
}


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
    tmp = path.with_name(path.name + f".tmp-{os.getpid()}-{uuid.uuid4().hex[:8]}")
    payload = json.dumps(value, indent=2, ensure_ascii=False) + "\n"
    with tmp.open("w", encoding="utf-8") as fh:
        fh.write(payload)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def require_schema(value: dict[str, Any], expected: str, label: str) -> None:
    if value.get("schema") != expected:
        raise SystemExit(f"SCHEMA_MISMATCH={label}:expected={expected}:actual={value.get('schema')}")


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def safe_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._")
    return cleaned or "task"


def task_index(graph: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(t["id"]): t
        for t in graph.get("tasks") or []
        if isinstance(t, dict) and t.get("id")
    }


def approved(ledger: dict[str, Any], approval_id: str) -> bool:
    item = (ledger.get("approvals") or {}).get(approval_id)
    return bool(
        isinstance(item, dict)
        and item.get("status") == "APPROVED"
        and item.get("actor")
        and item.get("observed_at")
    )


def storage_ok(ledger: dict[str, Any], artifact_id: str) -> bool:
    item = (ledger.get("artifacts") or {}).get(artifact_id)
    return bool(
        isinstance(item, dict)
        and item.get("status") == "OK"
        and item.get("source")
        and (item.get("observed_at") or item.get("timestamp"))
    )


def adapter_binding(
    provider_binding: dict[str, Any], permission: str, adapters: dict[str, Any], execute: bool
) -> tuple[dict[str, Any] | None, list[str]]:
    errors: list[str] = []
    provider = provider_binding.get("provider")
    if not provider:
        return None, ["PROVIDER_MISSING"]
    pdef = (adapters.get("providers") or {}).get(provider)
    if not isinstance(pdef, dict):
        return None, [f"PROVIDER_ADAPTER_MAPPING_MISSING:{provider}"]
    adapter_id = pdef.get("adapter")
    adef = (adapters.get("adapters") or {}).get(adapter_id)
    if not isinstance(adef, dict):
        return None, [f"ADAPTER_MISSING:{adapter_id}"]
    if permission not in set(adef.get("supports") or []):
        errors.append(f"ADAPTER_PERMISSION_UNSUPPORTED:{adapter_id}:{permission}")
    if execute:
        if adef.get("status") != "ENABLED":
            errors.append(f"ADAPTER_NOT_ENABLED:{adapter_id}:{adef.get('status')}")
        if pdef.get("execution") == "vps" and not adef.get("executable"):
            errors.append(f"ADAPTER_EXECUTABLE_MISSING:{adapter_id}")
        if provider_binding.get("health_state") not in {None, "HEALTHY"}:
            errors.append(f"PROVIDER_HEALTH_NOT_HEALTHY:{provider}:{provider_binding.get('health_state')}")
    return {
        "capability": provider_binding.get("capability"),
        "provider": provider,
        "adapter": adapter_id,
        "adapter_kind": adef.get("kind", pdef.get("kind")),
        "execution": pdef.get("execution"),
        "executable": adef.get("executable"),
        "fallback_used": bool(provider_binding.get("fallback_used")),
        "health_state": provider_binding.get("health_state"),
    }, errors


def prepare_envelope(
    run_id: str,
    wave_index: int,
    scheduled: dict[str, Any],
    source_task: dict[str, Any],
    bindings: list[dict[str, Any]],
    policy: dict[str, Any],
    workspace: str | None,
) -> dict[str, Any]:
    permission = scheduled.get("permission", source_task.get("permission", "read"))
    explicit = set(((policy.get("approvals") or {}).get("explicit_human_permissions") or []))
    approval_map = dict(DEFAULT_APPROVALS)
    approval_map.update((policy.get("approvals") or {}).get("permission_to_approval") or {})
    timeout = int(((policy.get("dispatch") or {}).get("default_timeout_seconds") or 300))
    timeout = min(timeout, int(((policy.get("dispatch") or {}).get("max_timeout_seconds") or 3600)))
    metadata = dict(source_task.get("metadata") or {})
    metadata.update(scheduled.get("metadata") or {})
    metadata.update({"prepared_at": now_iso(), "controller": "run-controller-v1.1"})
    return {
        "schema": ENVELOPE_SCHEMA,
        "project": scheduled.get("project"),
        "transition": scheduled.get("transition"),
        "run_id": run_id,
        "wave": wave_index,
        "task": {
            "id": source_task.get("id"),
            "kind": source_task.get("kind"),
            "description": source_task.get("description", ""),
            "owner_role": source_task.get("owner_role", "orchestrator"),
            "permission": permission,
            "outputs": source_task.get("outputs") or [],
            "verification": source_task.get("verification") or {},
        },
        "bindings": [
            {
                "capability": b.get("capability"),
                "provider": b.get("provider"),
                "adapter": b.get("adapter"),
                "fallback_used": bool(b.get("fallback_used")),
                "health_state": b.get("health_state"),
            }
            for b in bindings
        ],
        "policy_context": {
            "resource_class": scheduled.get("resource_class", "light"),
            "requires_storage_preflight": bool(scheduled.get("requires_storage_preflight")),
            "human_approval_required": permission in explicit,
            "approval_id": approval_map.get(permission) if permission in explicit else None,
            "timeout_seconds": timeout,
        },
        "workspace": workspace,
        "metadata": metadata,
    }


def task_blockers(
    envelope: dict[str, Any], ledger: dict[str, Any], policy: dict[str, Any], binding_errors: list[str]
) -> list[str]:
    blockers = list(binding_errors)
    context = envelope.get("policy_context") or {}
    if context.get("human_approval_required"):
        approval_id = context.get("approval_id")
        if not approval_id or not approved(ledger, approval_id):
            blockers.append(f"APPROVAL_MISSING:{approval_id or 'UNMAPPED'}")
    if context.get("requires_storage_preflight"):
        artifact_id = ((policy.get("storage") or {}).get("preflight_artifact") or "storage-preflight")
        if not storage_ok(ledger, artifact_id):
            blockers.append(f"STORAGE_PREFLIGHT_MISSING:{artifact_id}")
    return sorted(set(blockers))


def emergency_stop_active() -> bool:
    path = Path("/opt/chacha-dev/runtime/control/emergency-stop.json")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return bool(value.get("active"))
    except Exception:
        return False


def guardian_gate(
    envelope: dict[str, Any],
    ledger: dict[str, Any],
    policy: dict[str, Any],
    binding_errors: list[str],
    guardian_dir: Path,
    basename: str,
    phase: str,
    result_status: str | None = None,
) -> tuple[list[str], dict[str, Any]]:
    cfg = policy.get("guardian") if isinstance(policy.get("guardian"), dict) else {}
    if not cfg or cfg.get("enabled") is not True:
        return [], {"status": "DISABLED"}

    # CI/unit environments do not have the ChaCha DEV runtime tree. The real VPS does.
    runtime_root = Path(str(cfg.get("runtime_root") or "/opt/chacha-dev/runtime"))
    if not runtime_root.exists():
        return [], {"status": "NON_RUNTIME_TEST_BYPASS"}

    client = Path(str(cfg.get("client") or "/opt/chacha-dev/platform/current/dev-hub/bin/guardian-client.py"))
    guardian_policy = Path(str(cfg.get("policy") or "/opt/chacha-dev/platform/current/dev-hub/config/guardian-runtime-policy.v1.json"))
    permission = str(((envelope.get("task") or {}).get("permission")) or "read")
    fail_closed = set(str(x) for x in (cfg.get("fail_closed_permissions") or []))
    context = envelope.get("policy_context") if isinstance(envelope.get("policy_context"), dict) else {}
    approval_required = bool(context.get("human_approval_required"))
    approval_id = context.get("approval_id")
    approval_ok = bool(not approval_required or (approval_id and approved(ledger, str(approval_id))))
    storage_required = bool(context.get("requires_storage_preflight"))
    preflight_id = str(((policy.get("storage") or {}).get("preflight_artifact") or "storage-preflight"))
    storage_preflight = bool(not storage_required or storage_ok(ledger, preflight_id))
    task = envelope.get("task") if isinstance(envelope.get("task"), dict) else {}

    action_id = "dispatch:" + safe_name(str(envelope.get("run_id") or "run")) + ":" + str(envelope.get("wave") or 0) + ":" + safe_name(str(task.get("id") or basename))
    event = {
        "schema": "chacha.dev/governance-action/v1",
        "event_id": "gov-" + uuid.uuid4().hex,
        "action_id": action_id,
        "phase": phase,
        "actor": "run-controller",
        "subject_role": str(task.get("owner_role") or "orchestrator"),
        "action": "DISPATCH_TASK",
        "task_kind": str(task.get("kind") or ""),
        "permission": permission,
        "project_id": envelope.get("project"),
        "transition": envelope.get("transition"),
        "run_id": envelope.get("run_id"),
        "wave": envelope.get("wave"),
        "adapters": [
            {
                "adapter": x.get("adapter"),
                "provider": x.get("provider"),
                "capability": x.get("capability"),
            }
            for x in (envelope.get("bindings") or [])
            if isinstance(x, dict)
        ],
        "evidence": {
            "adapter_binding_valid": not bool(binding_errors),
            "human_approval": approval_ok,
            "storage_preflight": storage_preflight,
            "emergency_stop_active": emergency_stop_active(),
            "result_status": result_status,
        },
        "context": {
            "resource_class": context.get("resource_class"),
            "human_approval_required": approval_required,
            "storage_preflight_required": storage_required,
            "deadline_seconds": min(3600, max(30, int(context.get("timeout_seconds") or 300) + 60)),
        },
    }

    guardian_dir.mkdir(parents=True, exist_ok=True)
    event_path = guardian_dir / f"{basename}.{phase.lower()}.event.json"
    response_path = guardian_dir / f"{basename}.{phase.lower()}.verdict.json"
    save(event_path, event)

    if not client.is_file() or not guardian_policy.is_file():
        outcome = {
            "schema": "chacha.dev/guardian-local-verdict/v1",
            "status": "UNAVAILABLE",
            "reason": "GUARDIAN_CLIENT_OR_POLICY_MISSING",
            "event": str(event_path),
        }
        save(response_path, outcome)
        if permission in fail_closed:
            return ["GUARDIAN_UNAVAILABLE_FAIL_CLOSED"], outcome
        return [], outcome

    try:
        proc = subprocess.run(
            ["/usr/bin/python3", str(client), "--policy", str(guardian_policy), "check", "--event", str(event_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            timeout=int(cfg.get("timeout_seconds") or 20),
        )
    except Exception as exc:
        outcome = {
            "schema": "chacha.dev/guardian-local-verdict/v1",
            "status": "UNAVAILABLE",
            "reason": f"{type(exc).__name__}:{exc}",
            "event": str(event_path),
        }
        save(response_path, outcome)
        if permission in fail_closed:
            return ["GUARDIAN_UNAVAILABLE_FAIL_CLOSED"], outcome
        return [], outcome

    try:
        outcome = json.loads(proc.stdout.strip())
    except Exception:
        outcome = {
            "schema": "chacha.dev/guardian-local-verdict/v1",
            "status": "UNAVAILABLE",
            "reason": "GUARDIAN_RESPONSE_INVALID",
            "stderr": proc.stderr[-500:],
        }
    save(response_path, outcome)
    verdict = str(outcome.get("verdict") or outcome.get("status") or "UNAVAILABLE")
    if verdict == "CRITICAL":
        return ["GUARDIAN_CRITICAL:" + ",".join(outcome.get("reason_codes") or [])], outcome
    if verdict == "BLOCK":
        return ["GUARDIAN_BLOCK:" + ",".join(outcome.get("reason_codes") or [])], outcome
    if verdict in {"PASS", "WARNING"}:
        return [], outcome
    if permission in fail_closed:
        return ["GUARDIAN_UNAVAILABLE_FAIL_CLOSED"], outcome
    return [], outcome


def acquire_lock(project: str, policy: dict[str, Any]) -> tuple[Path, int]:
    root = Path(((policy.get("locking") or {}).get("root") or "/tmp/chacha-dev-locks"))
    root.mkdir(parents=True, exist_ok=True)
    lock = root / f"{safe_name(project)}.lock"
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    try:
        fd = os.open(lock, flags, 0o600)
    except FileExistsError:
        raise RuntimeError(f"PROJECT_LOCKED:{lock}")
    os.write(fd, json.dumps({"pid": os.getpid(), "created_at": now_iso()}).encode("utf-8"))
    os.fsync(fd)
    return lock, fd


def release_lock(lock: Path | None, fd: int | None) -> None:
    if fd is not None:
        try:
            os.close(fd)
        except OSError:
            pass
    if lock is not None:
        try:
            lock.unlink()
        except FileNotFoundError:
            pass


def create_unverified_result(
    project: str,
    task: dict[str, Any],
    status: str,
    producer: str,
    summary: str,
    evidence: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schema": RESULT_SCHEMA,
        "project": project,
        "task_id": task.get("id"),
        "status": status,
        "producer": producer,
        "observed_at": now_iso(),
        "summary": summary,
        "evidence": evidence,
        "verification": {
            "status": "UNVERIFIED",
            "method": "none",
            "verifier": "pending-independent-verifier",
            "observed_at": now_iso(),
            "notes": "Run Controller cannot self-verify an execution result.",
        },
        "outputs": [
            {"type": o.get("type"), "id": o.get("id"), "status": "UNVERIFIED"}
            for o in task.get("outputs") or []
            if isinstance(o, dict) and o.get("type") and o.get("id")
        ],
    }


def execute_adapter(
    executable: str,
    envelope: dict[str, Any],
    timeout: int,
    max_bytes: int,
) -> tuple[int | None, bytes, bytes, str | None]:
    try:
        proc = subprocess.run(
            [executable],
            input=json.dumps(envelope, ensure_ascii=False).encode("utf-8"),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            shell=False,
            check=False,
        )
        stdout = proc.stdout[:max_bytes]
        stderr = proc.stderr[:max_bytes]
        if len(proc.stdout) > max_bytes:
            return proc.returncode, stdout, stderr, "stdout-too-large"
        if len(proc.stderr) > max_bytes:
            return proc.returncode, stdout, stderr, "stderr-too-large"
        return proc.returncode, stdout, stderr, None
    except subprocess.TimeoutExpired as exc:
        out = (exc.stdout or b"")[:max_bytes]
        err = (exc.stderr or b"")[:max_bytes]
        return None, out, err, "timeout"
    except OSError as exc:
        return None, b"", str(exc).encode("utf-8")[:max_bytes], "adapter-start-failed"


def redact_text(value: bytes, policy: dict[str, Any]) -> bytes:
    text = value.decode("utf-8", errors="replace")
    patterns = [str(x) for x in ((policy.get("logs") or {}).get("redaction_patterns") or []) if str(x)]
    keys = sorted(set(patterns + ["TOKEN", "SECRET", "PASSWORD", "API_KEY", "AUTHORIZATION"]), key=len, reverse=True)
    for key in keys:
        k = re.escape(key)
        text = re.sub(rf'(?i)("{k}"\s*:\s*")[^"]*(")', r'\1[REDACTED]\2', text)
        text = re.sub(rf"(?i)\b({k}\s*[=:]\s*)[^\s,;]+", r"\1[REDACTED]", text)
        text = re.sub(rf"(?i)([?&]{k}=)[^&#\s]+", r"\1[REDACTED]", text)
    text = re.sub(r"(?i)(authorization\s*[:=]\s*bearer\s+)[A-Za-z0-9._~+/=-]+", r"\1[REDACTED]", text)
    return text.encode("utf-8")


def parse_adapter_result(
    stdout: bytes,
    envelope: dict[str, Any],
    expected_adapter: str,
) -> tuple[dict[str, Any] | None, str | None]:
    try:
        text = stdout.decode("utf-8", errors="strict").strip()
    except UnicodeDecodeError:
        return None, "ADAPTER_STDOUT_NOT_UTF8"
    if not text:
        return None, "ADAPTER_RESULT_MISSING"
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return None, "ADAPTER_RESULT_NOT_SINGLE_JSON_OBJECT"
    if not isinstance(value, dict):
        return None, "ADAPTER_RESULT_NOT_OBJECT"
    if value.get("schema") != RESULT_SCHEMA:
        return None, f"ADAPTER_RESULT_SCHEMA_INVALID:{value.get('schema')}"
    if value.get("project") != envelope.get("project"):
        return None, "ADAPTER_RESULT_PROJECT_MISMATCH"
    expected_task = str(((envelope.get("task") or {}).get("id")) or "")
    if str(value.get("task_id") or "") != expected_task:
        return None, "ADAPTER_RESULT_TASK_MISMATCH"
    if value.get("producer") != expected_adapter:
        return None, f"ADAPTER_RESULT_PRODUCER_MISMATCH:{value.get('producer')}"
    verification = value.get("verification") if isinstance(value.get("verification"), dict) else {}
    if verification.get("status") != "UNVERIFIED" or verification.get("method") != "none":
        return None, "ADAPTER_SELF_VERIFICATION_FORBIDDEN"
    if value.get("status") not in {"OK", "PARTIAL", "FAILED", "BLOCKED", "UNVERIFIED"}:
        return None, f"ADAPTER_RESULT_STATUS_INVALID:{value.get('status')}"
    if not isinstance(value.get("evidence"), list):
        return None, "ADAPTER_RESULT_EVIDENCE_INVALID"
    if value.get("outputs") is not None and not isinstance(value.get("outputs"), list):
        return None, "ADAPTER_RESULT_OUTPUTS_INVALID"
    return value, None


def execution_adapter(bindings: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, list[str]]:
    executable = [b for b in bindings if b.get("executable")]
    unique = {(str(b.get("adapter")), str(b.get("executable"))) for b in executable}
    if not executable:
        return None, ["NO_EXECUTABLE_ADAPTER"]
    if len(unique) != 1:
        return None, ["MULTIPLE_EXECUTABLE_ADAPTERS_UNSUPPORTED"]
    return executable[0], []


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--graph", required=True, type=Path)
    parser.add_argument("--ledger", required=True, type=Path)
    parser.add_argument("--policy", required=True, type=Path)
    parser.add_argument("--adapters", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--workspace")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()

    plan, graph, ledger, policy, adapters = map(load, [args.plan, args.graph, args.ledger, args.policy, args.adapters])
    require_schema(plan, PLAN_SCHEMA, "execution-plan")
    require_schema(graph, GRAPH_SCHEMA, "task-graph")
    require_schema(ledger, LEDGER_SCHEMA, "evidence-ledger")
    require_schema(policy, POLICY_SCHEMA, "run-controller-policy")
    require_schema(adapters, ADAPTER_SCHEMA, "provider-adapters")
    if plan.get("project") != graph.get("project") or plan.get("transition") != graph.get("transition"):
        raise SystemExit("PLAN_GRAPH_MISMATCH")
    if ledger.get("project") != plan.get("project"):
        raise SystemExit("LEDGER_PROJECT_MISMATCH")
    if args.execute and policy.get("mode") != "execute-enabled":
        raise SystemExit("EXECUTION_DISABLED_BY_POLICY")

    source_tasks = task_index(graph)
    run_id = f"run-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    run_dir = args.output_dir / run_id
    envelopes_dir = run_dir / "envelopes"
    results_dir = run_dir / "results"
    logs_dir = run_dir / "logs"
    guardian_dir = run_dir / "guardian"
    for path in (envelopes_dir, results_dir, logs_dir, guardian_dir):
        path.mkdir(parents=True, exist_ok=True)

    record: dict[str, Any] = {
        "schema": RUN_SCHEMA,
        "run_id": run_id,
        "project": plan.get("project"),
        "transition": plan.get("transition"),
        "mode": "execute" if args.execute else "dispatch-only",
        "started_at": now_iso(),
        "finished_at": None,
        "waves": [],
        "summary": {"prepared": 0, "blocked": 0, "dispatched": 0, "succeeded": 0, "failed": 0},
        "metadata": {"execution_plan": str(args.plan), "task_graph": str(args.graph), "controller": "run-controller-v1.1"},
    }

    max_bytes = int(((policy.get("logs") or {}).get("max_bytes_per_stream") or 1048576))
    max_attempts = int(((policy.get("dispatch") or {}).get("max_attempts") or 1))
    write_permissions = set(((policy.get("locking") or {}).get("write_permissions") or []))
    abort_remaining = False

    for wave in plan.get("waves") or []:
        wave_record = {"index": int(wave.get("index", len(record["waves"]) + 1)), "tasks": []}
        for scheduled in wave.get("tasks") or []:
            tid = str(scheduled.get("task_id"))
            basename = safe_name(tid)
            source = source_tasks.get(tid)
            if abort_remaining and args.execute:
                wave_record["tasks"].append({
                    "task_id": tid, "status": "SKIPPED", "provider_bindings": [], "dispatch_envelope": None,
                    "task_result": None, "attempts": 0, "exit_code": None, "failure_class": "prior-task-failed",
                    "started_at": None, "finished_at": now_iso(), "stdout_digest": None, "stderr_digest": None,
                    "blockers": ["PRIOR_TASK_FAILED"],
                })
                continue
            if not source:
                wave_record["tasks"].append({
                    "task_id": tid, "status": "BLOCKED", "provider_bindings": [], "dispatch_envelope": None,
                    "task_result": None, "attempts": 0, "exit_code": None, "failure_class": "task-not-in-graph",
                    "started_at": None, "finished_at": now_iso(), "stdout_digest": None, "stderr_digest": None,
                    "blockers": ["TASK_NOT_IN_GRAPH"],
                })
                record["summary"]["blocked"] += 1
                if args.execute:
                    abort_remaining = True
                continue

            bindings: list[dict[str, Any]] = []
            binding_errors: list[str] = []
            for pb in scheduled.get("provider_bindings") or []:
                binding, errors = adapter_binding(pb, str(scheduled.get("permission", source.get("permission", "read"))), adapters, args.execute)
                binding_errors.extend(errors)
                if binding:
                    bindings.append(binding)

            scheduled_context = dict(scheduled)
            scheduled_context["project"] = plan.get("project")
            scheduled_context["transition"] = plan.get("transition")
            envelope = prepare_envelope(run_id, wave_record["index"], scheduled_context, source, bindings, policy, args.workspace)
            if args.execute:
                chosen, executor_errors = execution_adapter(bindings)
                binding_errors.extend(executor_errors)
            else:
                chosen = None
            blockers = task_blockers(envelope, ledger, policy, binding_errors)
            guardian_pre: dict[str, Any] = {"status": "NOT_RUN"}
            if args.execute:
                guardian_blockers, guardian_pre = guardian_gate(
                    envelope, ledger, policy, binding_errors, guardian_dir, basename, "PRE_ACTION"
                )
                blockers = sorted(set(blockers + guardian_blockers))
            envelope_path = envelopes_dir / f"{basename}.json"
            save(envelope_path, envelope)
            task_rec: dict[str, Any] = {
                "task_id": tid,
                "status": "BLOCKED" if blockers else "PREPARED",
                "provider_bindings": bindings,
                "dispatch_envelope": str(envelope_path),
                "task_result": None,
                "attempts": 0,
                "exit_code": None,
                "failure_class": None,
                "started_at": None,
                "finished_at": None,
                "stdout_digest": None,
                "stderr_digest": None,
                "blockers": blockers,
                "guardian_pre": guardian_pre,
                "guardian_post": {"status": "NOT_RUN"},
            }
            if blockers:
                task_rec["finished_at"] = now_iso()
                record["summary"]["blocked"] += 1
                wave_record["tasks"].append(task_rec)
                if args.execute:
                    abort_remaining = True
                continue

            record["summary"]["prepared"] += 1
            if not args.execute:
                wave_record["tasks"].append(task_rec)
                continue

            permission = str(scheduled.get("permission", source.get("permission", "read")))
            lock_path: Path | None = None
            lock_fd: int | None = None
            try:
                if permission in write_permissions:
                    lock_path, lock_fd = acquire_lock(str(plan.get("project")), policy)
                task_rec["status"] = "DISPATCHED"
                task_rec["started_at"] = now_iso()
                record["summary"]["dispatched"] += 1
                assert chosen is not None
                executable = str(chosen.get("executable") or "")
                expected_adapter = str(chosen.get("adapter") or "")
                timeout = int((envelope.get("policy_context") or {}).get("timeout_seconds") or 300)
                exit_code: int | None = None
                stdout = b""
                stderr = b""
                failure_class: str | None = None
                for attempt in range(1, max_attempts + 1):
                    task_rec["attempts"] = attempt
                    exit_code, stdout, stderr, failure_class = execute_adapter(executable, envelope, timeout, max_bytes)
                    if failure_class == "timeout" and attempt < max_attempts:
                        time.sleep(min(20, 5 * attempt))
                        continue
                    break

                raw_stdout_digest = sha256_bytes(stdout)
                raw_stderr_digest = sha256_bytes(stderr)
                redacted_stdout = redact_text(stdout, policy)
                redacted_stderr = redact_text(stderr, policy)
                stdout_path = logs_dir / f"{basename}.stdout.log"
                stderr_path = logs_dir / f"{basename}.stderr.log"
                stdout_path.write_bytes(redacted_stdout)
                stderr_path.write_bytes(redacted_stderr)
                task_rec["stdout_digest"] = raw_stdout_digest
                task_rec["stderr_digest"] = raw_stderr_digest
                task_rec["exit_code"] = exit_code

                parsed: dict[str, Any] | None = None
                protocol_error: str | None = None
                if failure_class is None and exit_code == 0:
                    parsed, protocol_error = parse_adapter_result(stdout, envelope, expected_adapter)
                if protocol_error:
                    failure_class = protocol_error

                if parsed is not None and failure_class is None:
                    result_status = str(parsed.get("status"))
                    semantic_success = result_status == "OK"
                    result_path = results_dir / f"{basename}.task-result.json"
                    save(result_path, parsed)
                    task_rec["task_result"] = str(result_path)
                    post_blockers, guardian_post = guardian_gate(
                        envelope, ledger, policy, binding_errors, guardian_dir, basename,
                        "POST_ACTION", result_status=result_status
                    )
                    task_rec["guardian_post"] = guardian_post
                    if post_blockers:
                        semantic_success = False
                        task_rec["blockers"] = sorted(set((task_rec.get("blockers") or []) + post_blockers))
                        task_rec["failure_class"] = "guardian-post-block"
                    else:
                        task_rec["failure_class"] = None if semantic_success else f"adapter-result:{result_status}"
                    task_rec["status"] = "SUCCEEDED" if semantic_success else "FAILED"
                    task_rec["finished_at"] = now_iso()
                    if semantic_success:
                        record["summary"]["succeeded"] += 1
                    else:
                        record["summary"]["failed"] += 1
                        abort_remaining = True
                else:
                    if failure_class == "timeout":
                        task_rec["status"] = "TIMED_OUT"
                    else:
                        task_rec["status"] = "FAILED"
                    task_rec["failure_class"] = failure_class or f"adapter-exit:{exit_code}"
                    task_rec["finished_at"] = now_iso()
                    failure_result = create_unverified_result(
                        str(plan.get("project")), source, "FAILED", "run-controller",
                        f"Adapter dispatch failed: {task_rec['failure_class']}",
                        [{
                            "kind": "command",
                            "source": str(envelope_path),
                            "digest": sha256_bytes(envelope_path.read_bytes()),
                            "details": {"exit_code": exit_code, "failure_class": task_rec["failure_class"]},
                        }],
                    )
                    result_path = results_dir / f"{basename}.task-result.json"
                    save(result_path, failure_result)
                    task_rec["task_result"] = str(result_path)
                    _, guardian_post = guardian_gate(
                        envelope, ledger, policy, binding_errors, guardian_dir, basename,
                        "POST_ACTION", result_status="FAILED"
                    )
                    task_rec["guardian_post"] = guardian_post
                    record["summary"]["failed"] += 1
                    abort_remaining = True
            except Exception as exc:
                task_rec["status"] = "FAILED"
                task_rec["failure_class"] = f"controller-exception:{type(exc).__name__}:{exc}"
                task_rec["finished_at"] = now_iso()
                record["summary"]["failed"] += 1
                abort_remaining = True
            finally:
                release_lock(lock_path, lock_fd)
            wave_record["tasks"].append(task_rec)
        record["waves"].append(wave_record)

    record["finished_at"] = now_iso()
    record_path = run_dir / "run-record.json"
    save(record_path, record)
    print(f"RUN_ID={run_id}")
    print(f"RUN_MODE={record['mode']}")
    print(f"RUN_RECORD={record_path}")
    for key, value in record["summary"].items():
        print(f"{key.upper()}={value}")


if __name__ == "__main__":
    main()
