from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from mcp.server import MCPServer

from .audit import append_audit
from .policy import PolicyError, load_policy

mcp = MCPServer("ChaCha Remote Operator")
POLICY = load_policy()


def _guard(tool: str) -> None:
    try:
        POLICY.require_operational()
    except Exception:
        append_audit(POLICY.audit_log, tool, "BLOCKED", {"reason": "STOP_OR_POLICY"})
        raise


def _bounded_text(raw: bytes, limit: int) -> str:
    if len(raw) > limit:
        raw = raw[:limit] + b"\n[TRUNCATED]\n"
    return raw.decode("utf-8", "replace")


@mcp.tool()
def operator_health() -> dict[str, Any]:
    """Return operator mode and safety state without mutating the host."""
    status = {
        "status": "PASS",
        "mode": POLICY.raw.get("mode"),
        "stop_active": POLICY.stop_active(),
        "command_execution_enabled": POLICY.raw.get("command_execution_enabled") is True,
        "file_write_enabled": POLICY.raw.get("file_write_enabled") is True,
        "destructive_operations_enabled": POLICY.raw.get("destructive_operations_enabled") is True,
        "automatic_external_spend_eur": 0,
    }
    append_audit(POLICY.audit_log, "operator_health", "PASS")
    return status


@mcp.tool()
def system_status() -> dict[str, Any]:
    """Return bounded local system status."""
    _guard("system_status")
    root = shutil.disk_usage("/")
    load = os.getloadavg() if hasattr(os, "getloadavg") else (0.0, 0.0, 0.0)
    result = {
        "hostname": os.uname().nodename,
        "kernel": os.uname().release,
        "load_1m": load[0],
        "load_5m": load[1],
        "load_15m": load[2],
        "root_total_bytes": root.total,
        "root_used_bytes": root.used,
        "root_free_bytes": root.free,
    }
    append_audit(POLICY.audit_log, "system_status", "PASS")
    return result


@mcp.tool()
def file_read(path: str, max_bytes: int | None = None) -> dict[str, Any]:
    """Read a UTF-8/text file under an allowlisted root with a strict size bound."""
    _guard("file_read")
    target = POLICY.resolve_read_path(path)
    if not target.is_file():
        raise PolicyError("FILE_NOT_FOUND")
    ceiling = int(POLICY.raw.get("max_read_bytes", 262144))
    limit = max(1, min(int(max_bytes or ceiling), ceiling))
    with target.open("rb") as handle:
        raw = handle.read(limit + 1)
    truncated = len(raw) > limit
    raw = raw[:limit]
    append_audit(POLICY.audit_log, "file_read", "PASS", {"path": str(target), "bytes": len(raw)})
    return {"path": str(target), "content": raw.decode("utf-8", "replace"), "truncated": truncated}


@mcp.tool()
def directory_list(path: str, limit: int = 200) -> dict[str, Any]:
    """List one allowlisted directory without recursion."""
    _guard("directory_list")
    target = POLICY.resolve_read_path(path)
    if not target.is_dir():
        raise PolicyError("DIRECTORY_NOT_FOUND")
    cap = max(1, min(int(limit), 500))
    entries = []
    for child in sorted(target.iterdir(), key=lambda p: p.name)[:cap]:
        entries.append({"name": child.name, "is_dir": child.is_dir(), "is_file": child.is_file()})
    append_audit(POLICY.audit_log, "directory_list", "PASS", {"path": str(target), "count": len(entries)})
    return {"path": str(target), "entries": entries, "limit": cap}


@mcp.tool()
def file_search(root: str, name_contains: str, limit: int | None = None) -> dict[str, Any]:
    """Find paths by filename substring under an allowlisted root. Does not inspect file contents."""
    _guard("file_search")
    base = POLICY.resolve_read_path(root)
    if not base.is_dir():
        raise PolicyError("SEARCH_ROOT_NOT_DIRECTORY")
    query = str(name_contains or "").strip().lower()
    if not query:
        raise PolicyError("SEARCH_QUERY_EMPTY")
    ceiling = int(POLICY.raw.get("max_search_results", 100))
    cap = max(1, min(int(limit or ceiling), ceiling))
    hits: list[str] = []
    for path in base.rglob("*"):
        if query in path.name.lower():
            try:
                POLICY.resolve_read_path(str(path))
            except PolicyError:
                continue
            hits.append(str(path))
            if len(hits) >= cap:
                break
    append_audit(POLICY.audit_log, "file_search", "PASS", {"root": str(base), "count": len(hits)})
    return {"root": str(base), "query": query, "results": hits, "limit": cap}


@mcp.tool()
def process_list(limit: int = 100) -> dict[str, Any]:
    """List local processes from /proc with bounded metadata."""
    _guard("process_list")
    cap = max(1, min(int(limit), 300))
    rows = []
    for proc in sorted(Path("/proc").glob("[0-9]*"), key=lambda p: int(p.name)):
        if len(rows) >= cap:
            break
        try:
            comm = (proc / "comm").read_text(encoding="utf-8", errors="replace").strip()
            rows.append({"pid": int(proc.name), "command": comm[:200]})
        except Exception:
            continue
    append_audit(POLICY.audit_log, "process_list", "PASS", {"count": len(rows)})
    return {"processes": rows, "limit": cap}


@mcp.tool()
def service_status(service: str) -> dict[str, Any]:
    """Return active/enabled status for an explicitly allowlisted systemd unit."""
    _guard("service_status")
    if not POLICY.service_allowed(service):
        raise PolicyError("SERVICE_NOT_ALLOWLISTED")
    def run(verb: str) -> str:
        p = subprocess.run(["systemctl", verb, service], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           text=True, check=False, timeout=10, shell=False)
        return p.stdout.strip()[:1000]
    result = {"service": service, "active": run("is-active"), "enabled": run("is-enabled")}
    append_audit(POLICY.audit_log, "service_status", "PASS", {"service": service})
    return result


@mcp.tool()
def command_run(argv: list[str], cwd: str | None = None) -> dict[str, Any]:
    """Run an argv-only command when a later policy explicitly enables its allowlisted prefix."""
    _guard("command_run")
    if not POLICY.command_allowed(argv):
        append_audit(POLICY.audit_log, "command_run", "BLOCKED", {"executable": argv[0] if argv else None})
        raise PolicyError("COMMAND_EXECUTION_DISABLED_OR_NOT_ALLOWLISTED")
    workdir = POLICY.resolve_read_path(cwd) if cwd else None
    timeout = int(POLICY.raw.get("max_command_seconds", 20))
    output_cap = int(POLICY.raw.get("max_command_output_bytes", 131072))
    p = subprocess.run(argv, cwd=str(workdir) if workdir else None, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, check=False, timeout=timeout, shell=False)
    append_audit(POLICY.audit_log, "command_run", "PASS", {"executable": argv[0], "argc": len(argv), "returncode": p.returncode})
    return {"returncode": p.returncode, "output": _bounded_text(p.stdout, output_cap)}


def main() -> None:
    mcp.run(
        transport="streamable-http",
        host=str(POLICY.raw.get("bind_host", "127.0.0.1")),
        port=int(POLICY.raw.get("port", 8765)),
        streamable_http_path=str(POLICY.raw.get("mcp_path", "/mcp")),
        json_response=True,
        stateless_http=True,
    )


if __name__ == "__main__":
    main()
