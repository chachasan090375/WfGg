#!/usr/bin/env python3
"""ChaCha DEV HUB Playwright MCP Adapter V1.

Provider-specific read-only browser inspection adapter. Input is exactly one
chacha.dev/dispatch-envelope/v1 JSON object on stdin and output is exactly one
chacha.dev/task-result/v1 JSON object on stdout.

The caller never chooses MCP methods or tool names. The adapter maps one
high-level operation (inspect) to a fixed sequence of safe Playwright MCP calls:
navigate -> snapshot -> console_messages -> network_requests -> close.

Upstream Playwright MCP 0.0.81 currently uses the explicitly qualified legacy
MCP 2025-11-25 handshake. This provider-specific compatibility does not change
DEV HUB's global MCP 2026-07-28 baseline.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import selectors
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

INPUT_SCHEMA = "chacha.dev/dispatch-envelope/v1"
OUTPUT_SCHEMA = "chacha.dev/task-result/v1"
ADAPTER_ID = "playwright-mcp-adapter"
PROVIDER_ID = "playwright-mcp"
UPSTREAM_PROTOCOL = "2025-11-25"
SAFE_TOOLS = (
    "browser_navigate",
    "browser_snapshot",
    "browser_console_messages",
    "browser_network_requests",
    "browser_close",
)
DENIED_INPUT_KEYS = {
    "tool", "tool_name", "method", "mcp_method", "arguments", "args", "command",
    "script", "javascript", "code", "filename", "output_file", "config",
    "allowed_origins", "browser", "executable", "server", "workdir",
}
ALLOWED_METADATA_KEYS = {"operation", "url", "expected_text"}
DEFAULT_TIMEOUT = 30
MAX_TIMEOUT = 60
MAX_PROVIDER_TEXT = 2_000_000
FINAL_URL_PATTERNS = (
    re.compile(r"Page URL:\s*(\S+)", re.IGNORECASE),
    re.compile(r"URL:\s*(https?://\S+)", re.IGNORECASE),
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()


def safe_url(url: str) -> str:
    parsed = urlsplit(url)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path or "/", "", ""))


def origin(url: str) -> str | None:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return None
    if parsed.username is not None or parsed.password is not None:
        return None
    host = parsed.hostname.lower().rstrip(".")
    default_port = 80 if parsed.scheme == "http" else 443
    port = parsed.port or default_port
    suffix = "" if port == default_port else f":{port}"
    return f"{parsed.scheme}://{host}{suffix}"


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


def block(request: dict[str, Any], reason: str) -> int:
    return emit(task_result(request, "BLOCKED", reason, [{
        "kind": "report",
        "source": "playwright-mcp-adapter-policy",
        "digest": sha256_text(reason),
        "details": {"reason": reason},
    }]))


def validate_request(request: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    if request.get("schema") != INPUT_SCHEMA:
        return None, "INPUT_SCHEMA_INVALID"
    if not request.get("project"):
        return None, "PROJECT_MISSING"
    task = request.get("task")
    if not isinstance(task, dict) or not task.get("id"):
        return None, "TASK_ID_MISSING"
    if task.get("permission") != "read":
        return None, "PLAYWRIGHT_MCP_REQUIRES_READ_PERMISSION"
    bindings = request.get("bindings")
    if not isinstance(bindings, list) or not any(
        isinstance(item, dict)
        and item.get("provider") == PROVIDER_ID
        and item.get("adapter") == ADAPTER_ID
        for item in bindings
    ):
        return None, "PLAYWRIGHT_MCP_BINDING_MISSING"
    metadata = request.get("metadata")
    inspect = metadata.get("playwright_mcp") if isinstance(metadata, dict) else None
    if not isinstance(inspect, dict):
        return None, "PLAYWRIGHT_MCP_METADATA_MISSING"
    unknown = sorted(set(inspect) - ALLOWED_METADATA_KEYS)
    if unknown:
        return None, "PLAYWRIGHT_MCP_METADATA_KEY_FORBIDDEN:" + ",".join(unknown)
    if set(inspect) & DENIED_INPUT_KEYS:
        return None, "PLAYWRIGHT_MCP_DIRECT_TOOL_CONTROL_FORBIDDEN"
    if inspect.get("operation") != "inspect":
        return None, "PLAYWRIGHT_MCP_OPERATION_NOT_ALLOWED"
    url = inspect.get("url")
    if not isinstance(url, str) or not url:
        return None, "PLAYWRIGHT_MCP_URL_MISSING"
    expected = inspect.get("expected_text")
    if expected is not None and (not isinstance(expected, str) or not expected or len(expected) > 500):
        return None, "PLAYWRIGHT_MCP_EXPECTED_TEXT_INVALID"
    return inspect, None


class MCPClient:
    def __init__(self, executable: str, workdir: str, allowed_origin: str, timeout: int):
        argv = [
            executable,
            "--headless",
            "--isolated",
            "--block-service-workers",
            "--browser=chromium",
            f"--allowed-origins={allowed_origin}",
            "--codegen=none",
        ]
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
        )
        assert self.proc.stdin and self.proc.stdout and self.proc.stderr
        self.selector = selectors.DefaultSelector()
        self.selector.register(self.proc.stdout, selectors.EVENT_READ)
        self.stderr_tail: list[str] = []
        threading = __import__("threading")
        threading.Thread(target=self._drain_stderr, daemon=True).start()

    def _drain_stderr(self) -> None:
        assert self.proc.stderr
        for line in self.proc.stderr:
            clean = line.rstrip("\n")
            if clean:
                # Never place provider stderr into task-result evidence.
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


def tool_call(client: MCPClient, counter: int, name: str, arguments: dict[str, Any]) -> tuple[dict[str, Any], str]:
    if name not in SAFE_TOOLS:
        raise RuntimeError(f"INTERNAL_TOOL_NOT_ALLOWLISTED:{name}")
    msg = client.request(str(counter), "tools/call", {"name": name, "arguments": arguments})
    return msg, result_text(msg)


def extract_final_url(*texts: str) -> str | None:
    for text in texts:
        for pattern in FINAL_URL_PATTERNS:
            matches = pattern.findall(text)
            if matches:
                return str(matches[-1]).rstrip("`),.;")
    return None


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

    server = env_required("CHACHA_PLAYWRIGHT_MCP_SERVER")
    workdir = env_required("CHACHA_PLAYWRIGHT_MCP_WORKDIR")
    allowed_origin_raw = env_required("CHACHA_PLAYWRIGHT_ALLOWED_ORIGIN")
    target_class = env_required("CHACHA_PLAYWRIGHT_TARGET_CLASS")
    package_version = env_required("CHACHA_PLAYWRIGHT_MCP_PACKAGE_VERSION") or "unknown"
    if not server or not workdir or not allowed_origin_raw:
        return block(request, "PLAYWRIGHT_MCP_RUNTIME_BINDING_MISSING")
    if target_class not in {"test", "preview"}:
        return block(request, "PLAYWRIGHT_MCP_TARGET_CLASS_NOT_ALLOWED")
    if not Path(server).is_absolute() or not Path(server).exists():
        return block(request, "PLAYWRIGHT_MCP_SERVER_INVALID")
    if not Path(workdir).is_absolute() or not Path(workdir).is_dir():
        return block(request, "PLAYWRIGHT_MCP_WORKDIR_INVALID")

    allowed = origin(allowed_origin_raw)
    target = str(inspect["url"])
    target_origin = origin(target)
    if not allowed or not target_origin:
        return block(request, "PLAYWRIGHT_MCP_ORIGIN_INVALID")
    if target_origin != allowed:
        return block(request, "PLAYWRIGHT_MCP_TARGET_ORIGIN_NOT_ALLOWED")

    policy = request.get("policy_context") if isinstance(request.get("policy_context"), dict) else {}
    try:
        timeout = min(max(int(policy.get("timeout_seconds") or DEFAULT_TIMEOUT), 5), MAX_TIMEOUT)
    except Exception:
        timeout = DEFAULT_TIMEOUT

    expected_text = inspect.get("expected_text")
    client: MCPClient | None = None
    called: list[str] = []
    started = time.monotonic()
    try:
        client = MCPClient(server, workdir, allowed, timeout)
        init = client.request("init", "initialize", {
            "protocolVersion": UPSTREAM_PROTOCOL,
            "capabilities": {},
            "clientInfo": {"name": "chacha-dev-playwright-adapter", "version": "1.0.0"},
        })
        init_result = init.get("result") or {}
        if "error" in init or init_result.get("protocolVersion") != UPSTREAM_PROTOCOL:
            return block(request, "PLAYWRIGHT_MCP_LEGACY_INITIALIZE_FAILED")
        client.notify("notifications/initialized")

        tools = client.request("tools", "tools/list")
        if "error" in tools:
            return block(request, "PLAYWRIGHT_MCP_TOOLS_LIST_FAILED")
        tool_items = ((tools.get("result") or {}).get("tools") or [])
        names = {str(x.get("name")) for x in tool_items if isinstance(x, dict) and x.get("name")}
        missing = [name for name in SAFE_TOOLS if name not in names]
        if missing:
            return block(request, "PLAYWRIGHT_MCP_SAFE_TOOL_MISSING:" + ",".join(missing))

        counter = 10
        nav, nav_text = tool_call(client, counter, "browser_navigate", {"url": target}); counter += 1
        called.append("browser_navigate")
        if "error" in nav:
            return block(request, "PLAYWRIGHT_MCP_NAVIGATION_FAILED")

        snap, snap_text = tool_call(client, counter, "browser_snapshot", {}); counter += 1
        called.append("browser_snapshot")
        if "error" in snap:
            return block(request, "PLAYWRIGHT_MCP_SNAPSHOT_FAILED")

        final_url = extract_final_url(nav_text, snap_text)
        if not final_url:
            return block(request, "PLAYWRIGHT_MCP_FINAL_URL_UNOBSERVED")
        if origin(final_url) != allowed:
            return block(request, "PLAYWRIGHT_MCP_REDIRECT_ORIGIN_NOT_ALLOWED")

        if expected_text is not None and expected_text not in snap_text:
            return emit(task_result(request, "FAILED", "PLAYWRIGHT_MCP_EXPECTED_TEXT_NOT_FOUND", [{
                "kind": "url",
                "source": safe_url(final_url),
                "digest": sha256_text(snap_text),
                "details": {
                    "operation": "inspect",
                    "target_class": target_class,
                    "expected_text_digest": sha256_text(expected_text),
                    "snapshot_digest": sha256_text(snap_text),
                    "upstream_protocol": UPSTREAM_PROTOCOL,
                    "package_version": package_version,
                    "called_tools": list(called),
                },
            }]))

        console, console_text = tool_call(client, counter, "browser_console_messages", {"level": "info", "all": True}); counter += 1
        called.append("browser_console_messages")
        if "error" in console:
            return block(request, "PLAYWRIGHT_MCP_CONSOLE_READ_FAILED")

        network, network_text = tool_call(client, counter, "browser_network_requests", {"includeStatic": True}); counter += 1
        called.append("browser_network_requests")
        if "error" in network:
            return block(request, "PLAYWRIGHT_MCP_NETWORK_READ_FAILED")

        close, _close_text = tool_call(client, counter, "browser_close", {})
        called.append("browser_close")
        if "error" in close:
            return block(request, "PLAYWRIGHT_MCP_CLOSE_FAILED")

        elapsed_ms = round((time.monotonic() - started) * 1000, 2)
        evidence = [{
            "kind": "url",
            "source": safe_url(final_url),
            "digest": sha256_text(snap_text),
            "details": {
                "operation": "inspect",
                "target_class": target_class,
                "upstream_protocol": UPSTREAM_PROTOCOL,
                "package_version": package_version,
                "snapshot_digest": sha256_text(snap_text),
                "console_digest": sha256_text(console_text),
                "network_digest": sha256_text(network_text),
                "called_tools": list(called),
                "elapsed_ms": elapsed_ms,
                "credentials_used": False,
                "production_target": False,
                "workspace_write": False,
            },
        }]
        outputs = [{
            "type": "artifact",
            "id": "playwright-mcp-inspection",
            "status": "OK",
            "reason": "Read-only browser inspection completed on approved test/preview origin.",
        }]
        return emit(task_result(request, "OK", "PLAYWRIGHT_MCP_INSPECTION_OK", evidence, outputs))
    except (OSError, RuntimeError, TimeoutError) as exc:
        return block(request, f"PLAYWRIGHT_MCP_RUNTIME_FAILED:{type(exc).__name__}")
    finally:
        if client:
            client.close()


if __name__ == "__main__":
    raise SystemExit(main())
