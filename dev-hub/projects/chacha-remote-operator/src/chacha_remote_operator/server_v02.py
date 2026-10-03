from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from mcp.server import MCPServer

from .operations import run_governed_operation
from .adaptive_operations import guardian_check_event as run_guardian_check_event
from .direct_operator_bridge import read_job as run_direct_operator_job
from .direct_operator_bridge import submit_intent as run_direct_operator_intent
from .policy import V02_OPERATION_IDS, OperatorPolicy, load_policy


V02_TOOL_NAMES = V02_OPERATION_IDS
EXPOSURE_TOOL_NAMES = ("direct_operator_intent", "direct_operator_job")


def _v02_policy_path() -> Path:
    configured = os.environ.get("CHACHA_REMOTE_OPERATOR_POLICY", "").strip()
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[2] / "config" / "policy.v3.json"


POLICY: OperatorPolicy = load_policy(_v02_policy_path())
mcp = MCPServer("ChaCha Remote Operator V0.3")


@mcp.tool()
def git_status(repository: str) -> dict[str, Any]:
    """Return git status for an allowlisted repository using a server-constructed argv."""
    return run_governed_operation(POLICY, "git_status", cwd=repository)


@mcp.tool()
def git_head(repository: str) -> dict[str, Any]:
    """Return HEAD for an allowlisted repository using a server-constructed argv."""
    return run_governed_operation(POLICY, "git_head", cwd=repository)


@mcp.tool()
def git_tree(repository: str) -> dict[str, Any]:
    """Return HEAD tree for an allowlisted repository using a server-constructed argv."""
    return run_governed_operation(POLICY, "git_tree", cwd=repository)


@mcp.tool()
def service_is_active(service: str) -> dict[str, Any]:
    """Return systemd active state for an allowlisted service."""
    return run_governed_operation(POLICY, "service_is_active", service=service)


@mcp.tool()
def service_is_enabled(service: str) -> dict[str, Any]:
    """Return systemd enabled state for an allowlisted service."""
    return run_governed_operation(POLICY, "service_is_enabled", service=service)


@mcp.tool()
def uptime() -> dict[str, Any]:
    """Return host uptime using the fixed server-side uptime command."""
    return run_governed_operation(POLICY, "uptime")


@mcp.tool()
def free_bytes() -> dict[str, Any]:
    """Return memory figures in bytes using the fixed server-side free -b command."""
    return run_governed_operation(POLICY, "free_bytes")


@mcp.tool()
def uname() -> dict[str, Any]:
    """Return kernel/system identity using the fixed server-side uname -a command."""
    return run_governed_operation(POLICY, "uname")


@mcp.tool()
def guardian_check_event(event_path: str) -> dict[str, Any]:
    """Submit one allowlisted immutable governance event to Guardian; no shell or arbitrary argv."""
    return run_guardian_check_event(POLICY, event_path)


@mcp.tool()
def direct_operator_intent(text: str, project: str, client_request_id: str) -> dict[str, Any]:
    """Submit functional BUILD intent through the canonical Direct Operator M2M route; disabled until the exposure contract is activated."""
    return run_direct_operator_intent(POLICY, text, project, client_request_id)


@mcp.tool()
def direct_operator_job(job_id: str) -> dict[str, Any]:
    """Read one job owned by the Remote Operator service identity; disabled until the exposure contract is activated."""
    return run_direct_operator_job(POLICY, job_id)


def main() -> None:
    # V0.2 policy loading already enforces localhost-only binding and fail-closed invariants.
    mcp.run(
        transport="streamable-http",
        host=str(POLICY.raw["bind_host"]),
        port=int(POLICY.raw.get("port", 8766)),
        streamable_http_path=str(POLICY.raw.get("mcp_path", "/mcp")),
        json_response=True,
        stateless_http=True,
    )


if __name__ == "__main__":
    main()
