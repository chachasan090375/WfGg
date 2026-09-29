from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from .audit import append_audit
from .governance import GuardianError, guardian_gate, new_action_id
from .lease import LeaseBusy, command_lease
from .policy import OperatorPolicy, PolicyError


def _operation_argv(policy: OperatorPolicy, operation_id: str, cwd: str | None, service: str | None) -> tuple[list[str], Path | None]:
    if not policy.governed_operation_allowed(operation_id):
        raise PolicyError("GOVERNED_OPERATION_NOT_ALLOWLISTED")
    workdir = policy.resolve_read_path(cwd) if cwd else None
    if operation_id == "git_status":
        if workdir is None:
            raise PolicyError("GIT_OPERATION_REQUIRES_CWD")
        return ["git", "status", "--short", "--branch"], workdir
    if operation_id == "git_head":
        if workdir is None:
            raise PolicyError("GIT_OPERATION_REQUIRES_CWD")
        return ["git", "rev-parse", "HEAD"], workdir
    if operation_id == "git_tree":
        if workdir is None:
            raise PolicyError("GIT_OPERATION_REQUIRES_CWD")
        return ["git", "rev-parse", "HEAD^{tree}"], workdir
    if operation_id in {"service_is_active", "service_is_enabled"}:
        if not service or not policy.service_allowed(service):
            raise PolicyError("SERVICE_NOT_ALLOWLISTED")
        verb = "is-active" if operation_id == "service_is_active" else "is-enabled"
        return ["systemctl", verb, service], None
    if operation_id == "uptime":
        return ["uptime"], None
    if operation_id == "free_bytes":
        return ["free", "-b"], None
    if operation_id == "uname":
        return ["uname", "-a"], None
    raise PolicyError("GOVERNED_OPERATION_UNKNOWN")


def run_governed_operation(policy: OperatorPolicy, operation_id: str, cwd: str | None = None,
                           service: str | None = None) -> dict[str, Any]:
    policy.require_operational()
    argv, workdir = _operation_argv(policy, operation_id, cwd, service)
    action_id = new_action_id(operation_id)
    timeout = int(policy.raw.get("max_command_seconds", 20))
    output_cap = int(policy.raw.get("max_command_output_bytes", 131072))
    try:
        with command_lease(policy.runtime_root, operation_id) as lease:
            lease_id = str(lease["lease_id"])
            guardian_gate(policy, "PRE_ACTION", action_id, operation_id, lease_id, {"executable": argv[0]})
            policy.require_operational()
            proc = subprocess.run(
                argv,
                cwd=str(workdir) if workdir else None,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
                timeout=timeout,
                shell=False,
            )
            guardian_gate(
                policy,
                "POST_ACTION",
                action_id,
                operation_id,
                lease_id,
                {"executable": argv[0], "returncode": proc.returncode},
            )
            raw = proc.stdout[:output_cap]
            truncated = len(proc.stdout) > output_cap
            append_audit(
                policy.audit_log,
                "governed_operation",
                "PASS",
                {
                    "action_id": action_id,
                    "lease_id": lease_id,
                    "operation_id": operation_id,
                    "returncode": proc.returncode,
                },
            )
            return {
                "action_id": action_id,
                "lease_id": lease_id,
                "operation_id": operation_id,
                "returncode": proc.returncode,
                "output": raw.decode("utf-8", "replace"),
                "truncated": truncated,
            }
    except LeaseBusy as exc:
        append_audit(policy.audit_log, "governed_operation", "BLOCKED", {"reason": "LEASE_BUSY", "operation_id": operation_id})
        raise PolicyError("REMOTE_OPERATOR_COMMAND_LEASE_BUSY") from exc
    except GuardianError as exc:
        append_audit(policy.audit_log, "governed_operation", "BLOCKED", {"reason": str(exc), "operation_id": operation_id})
        raise PolicyError(str(exc)) from exc
