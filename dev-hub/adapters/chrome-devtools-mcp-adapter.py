#!/usr/bin/env python3
"""ChaCha DEV HUB Chrome DevTools MCP Adapter V2.

Provider-specific, read-only diagnostics adapter. The caller never chooses MCP
methods or tool names. Two high-level operations are supported:

- inspect_current_page: inspect the isolated browser's selected page without
  navigation.
- inspect_url: navigate the selected isolated page to one approved test/preview
  URL, then inspect it.

For inspect_url, navigation is performed internally by the adapter with
navigate_page. The caller cannot supply pageId, MCP arguments, initScript,
methods, tool names, browser endpoints, or allowlists. The adapter enforces an
exact approved origin from environment and also configures Chrome DevTools MCP
with --allowed-url-pattern as defence in depth. Redirects are re-observed and
revalidated after navigation.

Upstream compatibility is explicitly pinned to MCP 2025-11-25; DEV HUB global
baseline remains 2026-07-28.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import selectors
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

INPUT_SCHEMA = "chacha.dev/dispatch-envelope/v1"
OUTPUT_SCHEMA = "chacha.dev/task-result/v1"
ADAPTER_ID = "chrome-devtools-mcp-adapter"
PROVIDER_ID = "chrome-devtools-mcp"
UPSTREAM_PROTOCOL = "2025-11-25"
READ_TOOLS = (
    "list_pages",
    "take_snapshot",
    "list_console_messages",
    "list_network_requests",
)
INTERNAL_TOOLS = set(READ_TOOLS) | {"navigate_page"}
ALLOWED_METADATA_KEYS = {"operation", "url", "expected_text"}
DENIED_INPUT_KEYS = {
    "tool", "tool_name", "method", "mcp_method", "arguments", "args",
    "command", "script", "javascript", "code", "filename", "output_file",
    "pageId", "page_id", "browser_url", "ws_endpoint", "websocket_endpoint",
    "allowed_origins", "allowed_url_pattern", "allowedUrlPattern", "server",
    "workdir", "click", "fill", "type", "initScript", "init_script",
}
DEFAULT_TIMEOUT = 30
MAX_TIMEOUT = 60
MAX_PROVIDER_TEXT = 1_000_000
MIN_ALLOWED_URL_PATTERN_CHROME_MAJOR = 149
PAGE_LINE_RE = re.compile(r"(?m)^(\d+):\s+.*?(?:\s+\[selected\])?\s*$")
SELECTED_PAGE_LINE_RE = re.compile(r"(?m)^(\d+):\s+.*\[selected\]\s*$")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()


def env_required(name: str) -> str | None:
    value = os.environ.get(name, "").strip()
    return value or None


def safe_url(url: str) -> str:
    parsed = urlsplit(url)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path or "/", "", ""))


def origin(url: str) -> str | None:
    try:
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
    except ValueError:
        return None


def browser_major(version: str) -> int | None:
    match = re.search(r"(?:Chrome|Chromium)\s+(\d+)", version)
    if not match:
        return None
    return int(match.group(1))


def selected_page_id(text: str) -> int | None:
    match = SELECTED_PAGE_LINE_RE.search(text)
    if match:
        return int(match.group(1))
    match = PAGE_LINE_RE.search(text)
    return int(match.group(1)) if match else None


def selected_page_url(text: str, page_id: int) -> str | None:
    # list_pages format in upstream 1.9.0 is e.g.
    # "1: My page (https://example.test/) [selected]".
    for line in text.splitlines():
        if not line.startswith(f"{page_id}:"):
            continue
        matches = re.findall(r"\((https?://[^)]+)\)", line)
        if matches:
            return matches[-1]
    return None


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
    operation = inspect.get("operation")
    if operation not in {"inspect_current_page", "inspect_url"}:
        return None, "CHROME_DEVTOOLS_MCP_OPERATION_NOT_ALLOWED"
    if operation == "inspect_current_page" and ("url" in inspect or "expected_text" in inspect):
        return None, "CHROME_DEVTOOLS_MCP_CURRENT_PAGE_ARGUMENT_FORBIDDEN"
    if operation == "inspect_url":
        url = inspect.get("url")
        if not isinstance(url, str) or not url:
            return None, "CHROME_DEVTOOLS_MCP_URL_MISSING"
        if origin(url) is None:
            return None, "CHROME_DEVTOOLS_MCP_URL_NOT_HTTP_OR_HTTPS"
        expected = inspect.get("expected_text")
        if expected is not None and (not isinstance(expected, str) or not expected or len(expected) > 500):
            return None, "CHROME_DEVTOOLS_MCP_EXPECTED_TEXT_INVALID"
    return inspect, None


class MCPClient:
    def __init__(self, executable: str, workdir: str, timeout: int,
                 allowed_origin: str | None = None):
        argv = [
            executable,
            "--headless=true",
            "--isolated=true",
            "--no-javascript-evaluation",
            "--no-performance-crux",
            "--no-usage-statistics",
            "--redact-network-headers",
            "--no-source-maps",
        ]
        if allowed_origin:
            # Upstream URLPattern guard is defence in depth. The adapter also
            # validates the requested and observed final origins itself.
            argv.extend([
                "--allowed-url-pattern=about:blank",
                f"--allowed-url-pattern={allowed_origin}/*",
            ])
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


def tool_call(client: MCPClient, counter: int, name: str,
              arguments: dict[str, Any] | None = None) -> tuple[dict[str, Any], str]:
    if name not in INTERNAL_TOOLS:
        raise RuntimeError(f"INTERNAL_TOOL_NOT_ALLOWLISTED:{name}")
    msg = client.request(str(counter), "tools/call", {
        "name": name,
        "arguments": arguments or {},
    })
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
    allowed_origin_raw = env_required("CHACHA_CHROME_DEVTOOLS_ALLOWED_ORIGIN")
    if not server or not workdir:
        return block(request, "CHROME_DEVTOOLS_MCP_RUNTIME_BINDING_MISSING")
    if target_class not in {"test", "preview"}:
        return block(request, "CHROME_DEVTOOLS_MCP_TARGET_CLASS_NOT_ALLOWED")
    if not Path(server).is_absolute() or not Path(server).exists():
        return block(request, "CHROME_DEVTOOLS_MCP_SERVER_INVALID")
    if not Path(workdir).is_absolute() or not Path(workdir).is_dir():
        return block(request, "CHROME_DEVTOOLS_MCP_WORKDIR_INVALID")

    operation = str(inspect["operation"])
    target: str | None = None
    allowed: str | None = None
    if operation == "inspect_url":
        if not allowed_origin_raw:
            return block(request, "CHROME_DEVTOOLS_MCP_ALLOWED_ORIGIN_MISSING")
        allowed = origin(allowed_origin_raw)
        target = str(inspect["url"])
        target_origin = origin(target)
        if not allowed or not target_origin:
            return block(request, "CHROME_DEVTOOLS_MCP_ORIGIN_INVALID")
        if target_origin != allowed:
            return block(request, "CHROME_DEVTOOLS_MCP_TARGET_ORIGIN_NOT_ALLOWED")
        major = browser_major(browser_version)
        if major is None or major < MIN_ALLOWED_URL_PATTERN_CHROME_MAJOR:
            return block(request, "CHROME_DEVTOOLS_MCP_BROWSER_TOO_OLD_FOR_ALLOWED_URL_PATTERN")

    policy = request.get("policy_context") if isinstance(request.get("policy_context"), dict) else {}
    try:
        timeout = min(max(int(policy.get("timeout_seconds") or DEFAULT_TIMEOUT), 5), MAX_TIMEOUT)
    except Exception:
        timeout = DEFAULT_TIMEOUT

    client: MCPClient | None = None
    called: list[str] = []
    started = time.monotonic()
    try:
        client = MCPClient(server, workdir, timeout, allowed)
        init = client.request("init", "initialize", {
            "protocolVersion": UPSTREAM_PROTOCOL,
            "capabilities": {},
            "clientInfo": {"name": "chacha-dev-chrome-devtools-adapter", "version": "2.0.0"},
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
        required = list(READ_TOOLS) + (["navigate_page"] if operation == "inspect_url" else [])
        missing = [name for name in required if name not in names]
        if missing:
            return block(request, "CHROME_DEVTOOLS_MCP_SAFE_TOOL_MISSING:" + ",".join(missing))

        counter = 10
        pages, pages_text = tool_call(client, counter, "list_pages"); counter += 1
        called.append("list_pages")
        if "error" in pages:
            return block(request, "CHROME_DEVTOOLS_MCP_LIST_PAGES_FAILED")
        page_id = selected_page_id(pages_text)
        if page_id is None:
            return block(request, "CHROME_DEVTOOLS_MCP_SELECTED_PAGE_ID_UNOBSERVED")

        if operation == "inspect_url":
            assert target is not None and allowed is not None
            nav, _nav_text = tool_call(client, counter, "navigate_page", {
                "pageId": page_id,
                "type": "url",
                "url": target,
                "timeout": timeout * 1000,
            }); counter += 1
            called.append("navigate_page")
            if "error" in nav:
                return block(request, "CHROME_DEVTOOLS_MCP_CONTROLLED_NAVIGATION_FAILED")

            pages_after, pages_after_text = tool_call(client, counter, "list_pages"); counter += 1
            called.append("list_pages")
            if "error" in pages_after:
                return block(request, "CHROME_DEVTOOLS_MCP_POST_NAV_LIST_PAGES_FAILED")
            final_url = selected_page_url(pages_after_text, page_id)
            if not final_url:
                return block(request, "CHROME_DEVTOOLS_MCP_FINAL_URL_UNOBSERVED")
            if origin(final_url) != allowed:
                return block(request, "CHROME_DEVTOOLS_MCP_REDIRECT_ORIGIN_NOT_ALLOWED")
        else:
            final_url = selected_page_url(pages_text, page_id)

        digests: dict[str, str] = {}
        snapshot, snapshot_text = tool_call(client, counter, "take_snapshot", {"pageId": page_id}); counter += 1
        called.append("take_snapshot")
        if "error" in snapshot:
            return block(request, "CHROME_DEVTOOLS_MCP_READ_TOOL_FAILED:take_snapshot")
        digests["take_snapshot"] = sha256_text(snapshot_text)

        expected = inspect.get("expected_text")
        if expected is not None and expected not in snapshot_text:
            return emit(task_result(request, "FAILED", "CHROME_DEVTOOLS_MCP_EXPECTED_TEXT_NOT_FOUND", [{
                "kind": "url" if final_url else "report",
                "source": safe_url(final_url) if final_url else "chrome-devtools-mcp-adapter-runtime",
                "digest": sha256_text(snapshot_text),
                "details": {
                    "operation": operation,
                    "target_class": target_class,
                    "expected_text_digest": sha256_text(str(expected)),
                    "snapshot_digest": sha256_text(snapshot_text),
                    "called_tools": list(called),
                },
            }]))

        console, console_text = tool_call(client, counter, "list_console_messages", {"pageId": page_id}); counter += 1
        called.append("list_console_messages")
        if "error" in console:
            return block(request, "CHROME_DEVTOOLS_MCP_READ_TOOL_FAILED:list_console_messages")
        digests["list_console_messages"] = sha256_text(console_text)

        network, network_text = tool_call(client, counter, "list_network_requests", {"pageId": page_id}); counter += 1
        called.append("list_network_requests")
        if "error" in network:
            return block(request, "CHROME_DEVTOOLS_MCP_READ_TOOL_FAILED:list_network_requests")
        digests["list_network_requests"] = sha256_text(network_text)

        elapsed_ms = round((time.monotonic() - started) * 1000, 2)
        source = safe_url(final_url) if final_url and origin(final_url) else "chrome-devtools-mcp-adapter-runtime"
        evidence = [{
            "kind": "url" if source.startswith("http") else "report",
            "source": source,
            "digest": sha256_text(json.dumps(digests, sort_keys=True)),
            "details": {
                "operation": operation,
                "target_class": target_class,
                "upstream_protocol": UPSTREAM_PROTOCOL,
                "package_version": package_version,
                "browser_version": browser_version,
                "called_tools": list(called),
                "tool_result_digests": digests,
                "elapsed_ms": elapsed_ms,
                "credentials_used": False,
                "production_target": False,
                "navigation_performed": operation == "inspect_url",
                "navigation_caller_controlled_tool": False,
                "allowed_origin": allowed,
                "final_origin_revalidated": operation != "inspect_url" or origin(final_url or "") == allowed,
                "browser_interaction": False,
                "javascript_evaluation": False,
                "workspace_write": False,
                "repository_write": False,
            },
        }]
        outputs = [{
            "type": "artifact",
            "id": "chrome-devtools-mcp-controlled-diagnostics",
            "status": "OK",
            "reason": "Read-only diagnostics completed with adapter-controlled navigation policy.",
        }]
        return emit(task_result(request, "OK", "CHROME_DEVTOOLS_MCP_INSPECTION_OK", evidence, outputs))
    except (OSError, RuntimeError, TimeoutError) as exc:
        return block(request, f"CHROME_DEVTOOLS_MCP_RUNTIME_FAILED:{type(exc).__name__}")
    finally:
        if client:
            client.close()


if __name__ == "__main__":
    raise SystemExit(main())
