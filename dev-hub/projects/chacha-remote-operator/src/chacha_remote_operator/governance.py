from __future__ import annotations

import json
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any


class GuardianError(RuntimeError):
    pass


def _write_event(runtime_root: Path, event: dict[str, Any]) -> Path:
    root = runtime_root / "guardian-events"
    root.mkdir(parents=True, exist_ok=True)
    path = root / (str(event["event_id"]) + ".json")
    path.write_text(json.dumps(event, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _last_json(stdout: str) -> dict[str, Any]:
    for line in reversed(stdout.splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            value = json.loads(line)
        except Exception:
            continue
        if isinstance(value, dict):
            return value
    raise GuardianError("GUARDIAN_RESULT_JSON_MISSING")


def guardian_gate(policy: Any, phase: str, action_id: str, operation_id: str,
                  lease_id: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    if policy.raw.get("guardian_required_for_governed_operations") is not True:
        raise GuardianError("GUARDIAN_REQUIRED_FOR_GOVERNED_OPERATIONS")
    client = Path(str(policy.raw.get("guardian_client_path") or ""))
    guardian_policy = Path(str(policy.raw.get("guardian_policy_path") or ""))
    if not client.is_file() or not guardian_policy.is_file():
        raise GuardianError("GUARDIAN_RUNTIME_DEPENDENCY_MISSING")
    phase = str(phase)
    if phase not in {"PRE_ACTION", "POST_ACTION"}:
        raise GuardianError("GUARDIAN_PHASE_INVALID")
    event_id = f"{action_id}-{'pre' if phase == 'PRE_ACTION' else 'post'}"
    event = {
        "schema": "chacha.dev/governance-action/v1",
        "event_id": event_id,
        "action_id": action_id,
        "phase": phase,
        "actor": "remote-operator-gateway-agent",
        "subject_role": "remote-operator-gateway-agent",
        "action": "EXECUTE_GOVERNED_REMOTE_READ_OPERATION",
        "task_kind": "remote-operator-read-operation",
        "permission": "read",
        "project_id": "chacha-remote-operator",
        "run_id": action_id,
        "adapters": [],
        "evidence": {
            "human_approval": False,
            "operation_id": operation_id,
            "lease_id": lease_id,
            "argv_user_supplied": False,
            "shell": False,
            "destructive_operation": False,
            "automatic_external_spend_eur": 0,
            **(details or {}),
        },
        "context": {
            "resource_class": "light",
            "human_approval_required": False,
            "storage_preflight_required": False,
        },
    }
    event_path = _write_event(policy.runtime_root, event)
    proc = subprocess.run(
        [sys.executable, str(client), "--policy", str(guardian_policy), "check", "--event", str(event_path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
        timeout=int(policy.raw.get("guardian_timeout_seconds", 10)),
        shell=False,
    )
    result = _last_json(proc.stdout)
    if proc.returncode != 0 or str(result.get("verdict") or "") not in {"PASS", "WARNING"}:
        raise GuardianError("GUARDIAN_GATE_BLOCKED")
    if result.get("remediation_required") is True or result.get("stop_recommended") is True:
        raise GuardianError("GUARDIAN_REMEDIATION_OR_STOP_REQUIRED")
    return result


def new_action_id(operation_id: str) -> str:
    return "cro-" + operation_id + "-" + str(int(time.time())) + "-" + uuid.uuid4().hex[:12]
