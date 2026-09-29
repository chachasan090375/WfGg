from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Any

from .audit import V02_AUDIT_SCHEMA, append_audit
from .governance import GuardianError, guardian_gate, new_action_id
from .lease import LeaseBusy, command_lease
from .policy import OperatorPolicy, PolicyError, V02_OPERATION_IDS


GIT_OPERATIONS = {"git_status", "git_head", "git_tree"}
SERVICE_OPERATIONS = {"service_is_active", "service_is_enabled"}


def _operation_argv(
    policy: OperatorPolicy,
    operation_id: str,
    cwd: str | None,
    service: str | None,
) -> tuple[list[str], Path | None]:
    if operation_id not in V02_OPERATION_IDS or not policy.governed_operation_allowed(operation_id):
        raise PolicyError("GOVERNED_OPERATION_NOT_ALLOWLISTED")
    if operation_id not in GIT_OPERATIONS and cwd is not None:
        raise PolicyError("UNEXPECTED_CWD_PARAMETER")
    if operation_id not in SERVICE_OPERATIONS and service is not None:
        raise PolicyError("UNEXPECTED_SERVICE_PARAMETER")

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
    if operation_id in SERVICE_OPERATIONS:
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


def _audit_details(
    action_id: str,
    operation_id: str,
    *,
    lease_id: str | None = None,
    argv: list[str] | None = None,
    workdir: Path | None = None,
    guardian_pre: dict[str, Any] | None = None,
    guardian_post: dict[str, Any] | None = None,
    returncode: int | None = None,
    duration_ms: float | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    details: dict[str, Any] = {
        "action_id": action_id,
        "operation_id": operation_id,
        "lease_id": lease_id,
        "argv": argv,
        "cwd": str(workdir) if workdir else None,
        "argv_user_supplied": False,
        "shell": False,
        "guardian_pre_verdict": (guardian_pre or {}).get("verdict"),
        "guardian_post_verdict": (guardian_post or {}).get("verdict"),
        "returncode": returncode,
        "duration_ms": duration_ms,
    }
    if reason is not None:
        details["reason"] = reason
    return details


def run_governed_operation(
    policy: OperatorPolicy,
    operation_id: str,
    cwd: str | None = None,
    service: str | None = None,
) -> dict[str, Any]:
    action_id = new_action_id(operation_id)
    lease_id: str | None = None
    argv: list[str] | None = None
    workdir: Path | None = None
    guardian_pre: dict[str, Any] | None = None
    guardian_post: dict[str, Any] | None = None
    proc: subprocess.CompletedProcess[bytes] | None = None
    started_ns: int | None = None

    try:
        policy.require_operational()
        argv, workdir = _operation_argv(policy, operation_id, cwd, service)
        timeout = int(policy.raw.get("max_command_seconds", 20))
        output_cap = int(policy.raw.get("max_command_output_bytes", 131072))

        with command_lease(policy.runtime_root, operation_id) as lease:
            lease_id = str(lease["lease_id"])
            guardian_pre = guardian_gate(
                policy,
                "PRE_ACTION",
                action_id,
                operation_id,
                lease_id,
                {"executable": argv[0], "argv_user_supplied": False, "shell": False},
            )

            execution_error: Exception | None = None
            started_ns = time.monotonic_ns()
            try:
                # STOP is checked again inside the exclusive lease after Guardian PRE.
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
            except Exception as exc:  # POST Guardian must still run for every PRE-approved attempt.
                execution_error = exc
            finally:
                elapsed_ms = (time.monotonic_ns() - started_ns) / 1_000_000
                guardian_post = guardian_gate(
                    policy,
                    "POST_ACTION",
                    action_id,
                    operation_id,
                    lease_id,
                    {
                        "executable": argv[0],
                        "executed": proc is not None,
                        "returncode": proc.returncode if proc is not None else None,
                        "execution_error": type(execution_error).__name__ if execution_error else None,
                        "duration_ms": elapsed_ms,
                    },
                )

            if execution_error is not None:
                if isinstance(execution_error, PolicyError):
                    raise execution_error
                if isinstance(execution_error, subprocess.TimeoutExpired):
                    raise PolicyError("GOVERNED_OPERATION_TIMEOUT") from execution_error
                raise PolicyError("GOVERNED_OPERATION_EXECUTION_FAILED") from execution_error
            if proc is None:
                raise PolicyError("GOVERNED_OPERATION_NO_RESULT")

            raw = proc.stdout[:output_cap]
            truncated = len(proc.stdout) > output_cap
            duration_ms = (time.monotonic_ns() - started_ns) / 1_000_000 if started_ns is not None else None
            append_audit(
                policy.audit_log,
                operation_id,
                "PASS",
                _audit_details(
                    action_id,
                    operation_id,
                    lease_id=lease_id,
                    argv=argv,
                    workdir=workdir,
                    guardian_pre=guardian_pre,
                    guardian_post=guardian_post,
                    returncode=proc.returncode,
                    duration_ms=duration_ms,
                ),
                schema=V02_AUDIT_SCHEMA,
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
        reason = "LEASE_BUSY"
        append_audit(
            policy.audit_log,
            operation_id,
            "BLOCKED",
            _audit_details(action_id, operation_id, argv=argv, workdir=workdir, reason=reason),
            schema=V02_AUDIT_SCHEMA,
        )
        raise PolicyError("REMOTE_OPERATOR_COMMAND_LEASE_BUSY") from exc
    except GuardianError as exc:
        reason = str(exc)
        append_audit(
            policy.audit_log,
            operation_id,
            "BLOCKED",
            _audit_details(
                action_id,
                operation_id,
                lease_id=lease_id,
                argv=argv,
                workdir=workdir,
                guardian_pre=guardian_pre,
                guardian_post=guardian_post,
                returncode=proc.returncode if proc is not None else None,
                reason=reason,
            ),
            schema=V02_AUDIT_SCHEMA,
        )
        raise PolicyError(reason) from exc
    except PolicyError as exc:
        reason = str(exc)
        append_audit(
            policy.audit_log,
            operation_id,
            "BLOCKED",
            _audit_details(
                action_id,
                operation_id,
                lease_id=lease_id,
                argv=argv,
                workdir=workdir,
                guardian_pre=guardian_pre,
                guardian_post=guardian_post,
                returncode=proc.returncode if proc is not None else None,
                reason=reason,
            ),
            schema=V02_AUDIT_SCHEMA,
        )
        raise
    except Exception as exc:
        reason = "GOVERNED_OPERATION_INTERNAL_ERROR:" + type(exc).__name__
        append_audit(
            policy.audit_log,
            operation_id,
            "ERROR",
            _audit_details(
                action_id,
                operation_id,
                lease_id=lease_id,
                argv=argv,
                workdir=workdir,
                guardian_pre=guardian_pre,
                guardian_post=guardian_post,
                returncode=proc.returncode if proc is not None else None,
                reason=reason,
            ),
            schema=V02_AUDIT_SCHEMA,
        )
        raise PolicyError("GOVERNED_OPERATION_INTERNAL_ERROR") from exc
