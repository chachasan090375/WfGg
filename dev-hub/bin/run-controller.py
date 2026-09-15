#!/usr/bin/env python3
"""ChaCha DEV HUB Run Controller / Execution Dispatcher V1.

Consumes an Execution Plan and its source Task Graph. In the default
`dispatch-only` policy it produces immutable dispatch envelopes and a run
record without invoking any provider. The execution path already exists but is
fail-closed: it requires an execute-enabled policy and an ENABLED registered
adapter with an explicit executable. Subprocesses receive JSON on stdin and
are launched with argv only (`shell=False`).

The controller can produce task results, but it deliberately marks them
UNVERIFIED. Independent verification remains the Evidence Collector boundary.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
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
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def require_schema(value: dict[str, Any], expected: str, label: str) -> None:
    if value.get("schema") != expected:
        raise SystemExit(f"SCHEMA_MISMATCH={label}:expected={expected}:actual={value.get('schema')}")


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


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
        and item.get("observed_at")
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
        if not adef.get("executable"):
            errors.append(f"ADAPTER_EXECUTABLE_MISSING:{adapter_id}")
    return {
        "capability": provider_binding.get("capability"),
        "provider": provider,
        "adapter": adapter_id,
        "adapter_kind": adef.get("kind", pdef.get("kind")),
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
        "metadata": {
            "prepared_at": now_iso(),
            "controller": "run-controller-v1",
        },
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


def acquire_lock(project: str, policy: dict[str, Any]) -> tuple[Path, int]:
    root = Path(((policy.get("locking") or {}).get("root") or "/tmp/chacha-dev-locks"))
    root.mkdir(parents=True, exist_ok=True)
    lock = root / f"{project}.lock"
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    try:
        fd = os.open(lock, flags, 0o600)
    except FileExistsError:
        raise RuntimeError(f"PROJECT_LOCKED:{lock}")
    os.write(fd, json.dumps({"pid": os.getpid(), "created_at": now_iso()}).encode("utf-8"))
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
    output_status = "OK" if status == "OK" else "UNVERIFIED"
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
            "notes": "Run Controller cannot self-verify its own execution result."
        },
        "outputs": [
            {"type": o.get("type"), "id": o.get("id"), "status": output_status}
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
        return proc.returncode, proc.stdout[:max_bytes], proc.stderr[:max_bytes], None
    except subprocess.TimeoutExpired as exc:
        out = (exc.stdout or b"")[:max_bytes]
        err = (exc.stderr or b"")[:max_bytes]
        return None, out, err, "timeout"
    except OSError as exc:
        return None, b"", str(exc).encode("utf-8")[:max_bytes], "adapter-start-failed"


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
    for path in (envelopes_dir, results_dir, logs_dir):
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
        "metadata": {"execution_plan": str(args.plan), "task_graph": str(args.graph)},
    }

    max_bytes = int(((policy.get("logs") or {}).get("max_bytes_per_stream") or 1048576))
    max_attempts = int(((policy.get("dispatch") or {}).get("max_attempts") or 1))
    write_permissions = set(((policy.get("locking") or {}).get("write_permissions") or []))

    for wave in plan.get("waves") or []:
        wave_record = {"index": int(wave.get("index", len(record["waves"]) + 1)), "tasks": []}
        for scheduled in wave.get("tasks") or []:
            tid = str(scheduled.get("task_id"))
            source = source_tasks.get(tid)
            if not source:
                wave_record["tasks"].append({"task_id": tid, "status": "BLOCKED", "provider_bindings": [], "dispatch_envelope": None, "task_result": None, "attempts": 0, "exit_code": None, "failure_class": "task-not-in-graph", "started_at": None, "finished_at": now_iso(), "stdout_digest": None, "stderr_digest": None, "blockers": ["TASK_NOT_IN_GRAPH"]})
                record["summary"]["blocked"] += 1
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
            blockers = task_blockers(envelope, ledger, policy, binding_errors)
            envelope_path = envelopes_dir / (tid.replace("/", "_").replace(":", "_") + ".json")
            save(envelope_path, envelope)
            task_rec = {
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
            }
            if blockers:
                task_rec["finished_at"] = now_iso()
                record["summary"]["blocked"] += 1
                wave_record["tasks"].append(task_rec)
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
                executable = bindings[0].get("executable") if bindings else None
                if not executable:
                    raise RuntimeError("NO_EXECUTABLE_ADAPTER")
                timeout = int((envelope.get("policy_context") or {}).get("timeout_seconds") or 300)
                exit_code: int | None = None
                stdout = b""
                stderr = b""
                failure_class: str | None = None
                for attempt in range(1, max_attempts + 1):
                    task_rec["attempts"] = attempt
                    exit_code, stdout, stderr, failure_class = execute_adapter(str(executable), envelope, timeout, max_bytes)
                    if failure_class == "timeout" and attempt < max_attempts:
                        time.sleep(min(20, 5 * attempt))
                        continue
                    break
                stdout_path = logs_dir / (tid.replace(":", "_") + ".stdout.log")
                stderr_path = logs_dir / (tid.replace(":", "_") + ".stderr.log")
                stdout_path.write_bytes(stdout)
                stderr_path.write_bytes(stderr)
                task_rec["stdout_digest"] = sha256_bytes(stdout)
                task_rec["stderr_digest"] = sha256_bytes(stderr)
                task_rec["exit_code"] = exit_code
                task_rec["failure_class"] = failure_class
                success = exit_code == 0 and failure_class is None
                task_rec["status"] = "SUCCEEDED" if success else ("TIMED_OUT" if failure_class == "timeout" else "FAILED")
                task_rec["finished_at"] = now_iso()
                result = create_unverified_result(
                    str(plan.get("project")),
                    source,
                    "OK" if success else "FAILED",
                    f"run-controller:{bindings[0].get('provider') if bindings else 'unknown'}",
                    "Adapter exited successfully; independent verification pending." if success else f"Adapter failed: {failure_class or exit_code}",
                    [
                        {"kind": "command", "source": str(envelope_path), "digest": sha256_bytes(envelope_path.read_bytes()), "details": {"exit_code": exit_code}},
                        {"kind": "file", "source": str(stdout_path), "digest": task_rec["stdout_digest"], "details": {"stream": "stdout"}},
                        {"kind": "file", "source": str(stderr_path), "digest": task_rec["stderr_digest"], "details": {"stream": "stderr"}},
                    ],
                )
                result_path = results_dir / (tid.replace("/", "_").replace(":", "_") + ".task-result.json")
                save(result_path, result)
                task_rec["task_result"] = str(result_path)
                if success:
                    record["summary"]["succeeded"] += 1
                else:
                    record["summary"]["failed"] += 1
            except Exception as exc:
                task_rec["status"] = "FAILED"
                task_rec["failure_class"] = str(exc)
                task_rec["finished_at"] = now_iso()
                record["summary"]["failed"] += 1
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
