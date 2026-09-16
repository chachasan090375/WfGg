#!/usr/bin/env python3
"""ChaCha DEV HUB Chrome DevTools MCP Adapter V1.

Provider-specific, read-only adapter. The caller never chooses MCP methods or
tool names. One high-level operation, inspect_current_page, is translated to a
fixed safe sequence against an isolated Chrome session:
list_pages -> take_snapshot -> list_console_messages -> list_network_requests.

No navigation or browser interaction is performed by this adapter. Upstream
compatibility is explicitly pinned to MCP 2025-11-25; DEV HUB global baseline
remains 2026-07-28.
"""
from __future__ import annotations

import hashlib
import json
import os
import selectors
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

INPUT_SCHEMA = "chacha.dev/dispatch-envelope/v1"
OUTPUT_SCHEMA = "chacha.dev/task-result/v1"
ADAPTER_ID = "chrome-devtools-mcp-adapter"
PROVIDER_ID = "chrome-devtools-mcp"
UPSTREAM_PROTOCOL = "2025-11-25"
SAFE_TOOLS = (
    "list_pages",
    "take_snapshot",
    "list_console_messages",
    "list_network_requests",
)
ALLOWED_METADATA_KEYS = {"operation"}
DENIED_INPUT_KEYS = {
    "tool", "tool_name", "method", "mcp_method", "arguments", "args",
    "command", "script", "javascript", "code", "filename", "output_file",
    "url", "target_url", "browser_url", "ws_endpoint", "websocket_endpoint",
    "allowed_origins", "server", "workdir", "click", "fill", "type",
}
DEFAULT_TIMEOUT = 30
MAX_TIMEOUT = 60
MAX_PROVIDER_TEXT = 1_000_000


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()


def env_required(name: str) -> str | None:
    value = os.environ.get(name, "").strip()
    return value or None


def task_result(request: dict[str, Any], status: str, summary: str,
                evidence: list[dict[str, Any]] | None = None,
                outputs: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    task = request.get("task") if isinstance(request.get("task"), dict) else {}
    observed = now_iso()
    return {
        "schema": OUTPUT_SCHEMA,
        "project": str(request.get("project") or "unknown"),
        "task_id": str(task.get("id") or "unknown"),
        "status": status,
        "producer": ADAPTER_ID,
        "observed_at": observed,
        "summary": summary,
        "evidence": evidence or [],
        "verification": {
            "status": "UNVERIFIED",
            "method": "none",
            "verifier": "none",
            "observed_at": observed,
            "notes": "Provider output is unverified; Verification Broker must verify independently.",
        },
        "outputs": outputs or [],
    }


def emit(payload: dict[str, Any], code: int = 0) -> int:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
    return code


def block(request: dict[str, Any], reason: str, code: int = 0) -> int:
    return emit(task_result(request, "BLOCKED", reason, [{
        "kind": "report",
        "source": "chrome-devtools-mcp-adapter-policy",
        "digest": sha256_text(reason),
        "details": {"reason": reason},
    }]), code)


def validate_request(request: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    if request.get("schema") != INPUT_SCHEMA:
        return None, "INPUT_SCHEMA_INVALID"
    if not request.get("project"):
        return None, "PROJECT_MISSING"
    task = request.get("task")
    if not isinstance(task, dict) or not task.get("id"):
        return None, "TASK_ID_MISSING"
    if task.get("permission") != "read":
        return None, "CHROME_DEVTOOLS_MCP_REQUIRES_READ_PERMISSION"
    bindings = request.get("bindings")
    if not isinstance(bindings, list) or not any(
        isinstance(item, dict)
        and item.get("provider") == PROVIDER_ID
        and item.get("adapter") == ADAPTER_ID
        for item in bindings
    ):
        return None, "CHROME_DEVTOOLS_MCP_BINDING_MISSING"
    metadata = request.get("metadata")
    inspect = metadata.get("chrome_devtools_mcp") if isinstance(metadata, dict) else None
    if not isinstance(inspect, dict):
        return None, "CHROME_DEVTOOLS_MCP_METADATA_MISSING"
    unknown = sorted(set(inspect) - ALLOWED_METADATA_KEYS)
    if unknown:
        return None, "CHROME_DEVTOOLS_MCP_METADATA_KEY_FORBIDDEN:" + ",".join(unknown)
    if set(inspect) & DENIED_INPUT_KEYS:
        return None, "CHROME_DEVTOOLS_MCP_DIRECT_TOOL_CONTROL_FORBIDDEN"
    if inspect.get("operation") != "inspect_current_page":
        return None, "CHROME_DEVTOOLS_MCP_OPERATION_NOT_ALLOWED"
    return inspect, None


class MCPClient:
    def __init__(self, executable: str, workdir: str, timeout: int):
        argv = [
            executable,
            "--headless=true",
            "--isolated=true",
            "--no-javascript-evaluation",
            "--no-performance-crux",
            "--no-usage-statistics",
            "--redact-network-headers",
        ]
        env = dict(os.environ)
        env["CI"] = "true"
        env["CHROME_DEVTOOLS_MCP_NO_USAGE_STATISTICS"] = "1"
        env["CHROME_DEVTOOLS_MCP_NO_UPDATE_CHECKS"] = "1"
        self.timeout = timeout
        self.proc = subprocess.Popen(
            argv,
            cwd=workdir,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,
            shell=False,
            env=env,
        )
        assert self.proc.stdin and self.proc.stdout and self.proc.stderr
        self.selector = selectors.DefaultSelector()
        self.selector.register(self.proc.stdout, selectors.EVENT_READ)
        self.stderr_tail: list[str] = []
        threading.Thread(target=self._drain_stderr, daemon=True).start()

    def _drain_stderr(self) -> None:
        assert self.proc.stderr
        for line in self.proc.stderr:
            clean = line.rstrip("\n")
            if clean:
                self.stderr_tail.append(clean[:1000])
                self.stderr_tail[:] = self.stderr_tail[-20:]

    def send(self, payload: dict[str, Any]) -> None:
        assert self.proc.stdin
        self.proc.stdin.write(json.dumps(payload, separators=(",", ":")) + "\n")
        self.proc.stdin.flush()

    def request(self, req_id: str, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self.send({"jsonrpc": "2.0", "id": req_id, "method": method, "params": params or {}})
        deadline = time.monotonic() + self.timeout
        assert self.proc.stdout
        while time.monotonic() < deadline:
            if self.proc.poll() is not None:
                raise RuntimeError(f"MCP_SERVER_EXITED:{self.proc.returncode}")
            for _key, _mask in self.selector.select(0.5):
                line = self.proc.stdout.readline()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if str(msg.get("id")) == str(req_id):
                    return msg
        raise TimeoutError(f"MCP_RESPONSE_TIMEOUT:{method}")

    def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        self.send({"jsonrpc": "2.0", "method": method, "params": params or {}})

    def close(self) -> None:
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=5)


def result_text(msg: dict[str, Any]) -> str:
    result = msg.get("result") or {}
    content = result.get("content") if isinstance(result, dict) else None
    chunks: list[str] = []
    if isinstance(content, list):
        for item in content:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                chunks.append(item["text"])
    text = "\n".join(chunks) if chunks else json.dumps(result, ensure_ascii=False)
    return text[:MAX_PROVIDER_TEXT]


def tool_call(client: MCPClient, counter: int, name: str) -> tuple[dict[str, Any], str]:
    if name not in SAFE_TOOLS:
        raise RuntimeError(f"INTERNAL_TOOL_NOT_ALLOWLISTED:{name}")
    msg = client.request(str(counter), "tools/call", {"name": name, "arguments": {}})
    return msg, result_text(msg)


def main() -> int:
    try:
        request = json.load(sys.stdin)
    except Exception as exc:
        minimal = {"project": "unknown", "task": {"id": "unknown"}}
        return emit(task_result(minimal, "BLOCKED", f"INPUT_JSON_INVALID:{type(exc).__name__}"), 2)
    if not isinstance(request, dict):
        minimal = {"project": "unknown", "task": {"id": "unknown"}}
        return emit(task_result(minimal, "BLOCKED", "INPUT_ROOT_NOT_OBJECT"), 2)

    inspect, error = validate_request(request)
    if error:
        return block(request, error)
    assert inspect is not None

    server = env_required("CHACHA_CHROME_DEVTOOLS_MCP_SERVER")
    workdir = env_required("CHACHA_CHROME_DEVTOOLS_MCP_WORKDIR")
    package_version = env_required("CHACHA_CHROME_DEVTOOLS_MCP_PACKAGE_VERSION") or "unknown"
    browser_version = env_required("CHACHA_CHROME_DEVTOOLS_BROWSER_VERSION") or "unknown"
    target_class = env_required("CHACHA_CHROME_DEVTOOLS_TARGET_CLASS")
    if not server or not workdir:
        return block(request, "CHROME_DEVTOOLS_MCP_RUNTIME_BINDING_MISSING")
    if target_class not in {"test", "preview"}:
        return block(request, "CHROME_DEVTOOLS_MCP_TARGET_CLASS_NOT_ALLOWED")
    if not Path(server).is_absolute() or not Path(server).exists():
        return block(request, "CHROME_DEVTOOLS_MCP_SERVER_INVALID")
    if not Path(workdir).is_absolute() or not Path(workdir).is_dir():
        return block(request, "CHROME_DEVTOOLS_MCP_WORKDIR_INVALID")

    policy = request.get("policy_context") if isinstance(request.get("policy_context"), dict) else {}
    try:
        timeout = min(max(int(policy.get("timeout_seconds") or DEFAULT_TIMEOUT), 5), MAX_TIMEOUT)
    except Exception:
        timeout = DEFAULT_TIMEOUT

    client: MCPClient | None = None
    called: list[str] = []
    started = time.monotonic()
    try:
        client = MCPClient(server, workdir, timeout)
        init = client.request("init", "initialize", {
            "protocolVersion": UPSTREAM_PROTOCOL,
            "capabilities": {},
            "clientInfo": {"name": "chacha-dev-chrome-devtools-adapter", "version": "1.0.0"},
        })
        init_result = init.get("result") or {}
        if "error" in init or init_result.get("protocolVersion") != UPSTREAM_PROTOCOL:
            return block(request, "CHROME_DEVTOOLS_MCP_COMPAT_INITIALIZE_FAILED")
        client.notify("notifications/initialized")

        tools = client.request("tools", "tools/list")
        if "error" in tools:
            return block(request, "CHROME_DEVTOOLS_MCP_TOOLS_LIST_FAILED")
        items = ((tools.get("result") or {}).get("tools") or [])
        names = {str(x.get("name")) for x in items if isinstance(x, dict) and x.get("name")}
        missing = [name for name in SAFE_TOOLS if name not in names]
        if missing:
            return block(request, "CHROME_DEVTOOLS_MCP_SAFE_TOOL_MISSING:" + ",".join(missing))

        digests: dict[str, str] = {}
        counter = 10
        for name in SAFE_TOOLS:
            msg, text = tool_call(client, counter, name)
            counter += 1
            called.append(name)
            if "error" in msg:
                return block(request, "CHROME_DEVTOOLS_MCP_READ_TOOL_FAILED:" + name)
            digests[name] = sha256_text(text)

        elapsed_ms = round((time.monotonic() - started) * 1000, 2)
        evidence = [{
            "kind": "report",
            "source": "chrome-devtools-mcp-adapter-runtime",
            "digest": sha256_text(json.dumps(digests, sort_keys=True)),
            "details": {
                "operation": "inspect_current_page",
                "target_class": target_class,
                "upstream_protocol": UPSTREAM_PROTOCOL,
                "package_version": package_version,
                "browser_version": browser_version,
                "called_tools": list(called),
                "tool_result_digests": digests,
                "elapsed_ms": elapsed_ms,
                "credentials_used": False,
                "production_target": False,
                "navigation_performed": False,
                "browser_interaction": False,
                "workspace_write": False,
                "repository_write": False,
            },
        }]
        outputs = [{
            "type": "artifact",
            "id": "chrome-devtools-mcp-current-page-diagnostics",
            "status": "OK",
            "reason": "Read-only diagnostics completed without navigation or interaction.",
        }]
        return emit(task_result(request, "OK", "CHROME_DEVTOOLS_MCP_INSPECTION_OK", evidence, outputs))
    except (OSError, RuntimeError, TimeoutError) as exc:
        return block(request, f"CHROME_DEVTOOLS_MCP_RUNTIME_FAILED:{type(exc).__name__}")
    finally:
        if client:
            client.close()


if __name__ == "__main__":
    raise SystemExit(main())
