#!/usr/bin/env python3
"""Playwright MCP provider-specific read-only adapter V2.

Extends the qualified Playwright MCP adapter from local CI fixtures to controlled
HTTP(S) test/preview origins. The caller still selects no MCP tool, runtime,
allowlist, browser endpoint, script, or executable.

Security boundary:
- target class and exact allowed origin are trusted-runner environment inputs;
- task target must match that exact origin before browser launch;
- upstream --allowed-origins is defence in depth only and is NOT trusted as a
  redirect boundary;
- browser_navigate response must expose the final page URL, and the adapter
  independently revalidates its exact origin before any further page reads;
- cross-origin redirects and unobserved final URLs fail closed.

Provider results remain UNVERIFIED until the Verification Broker independently
verifies them.
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
UPSTREAM_PROTOCOL = "2025-11-25"
PROVIDER = "playwright-mcp"
ADAPTER = "playwright-mcp-adapter"
PRODUCER = "playwright-mcp-adapter"
SAFE_TOOLS = [
    "browser_navigate",
    "browser_snapshot",
    "browser_console_messages",
    "browser_network_requests",
    "browser_close",
]
DENIED_TOOLS = {
    "browser_run_code_unsafe",
    "browser_evaluate",
    "browser_click",
    "browser_type",
    "browser_fill_form",
    "browser_file_upload",
    "browser_drop",
    "browser_drag",
    "browser_handle_dialog",
    "browser_hover",
    "browser_press_key",
    "browser_select_option",
    "browser_webmcp_call",
    "browser_webmcp_list",
}
PAGE_URL_RE = re.compile(r"(?mi)^\s*(?:[-*]\s*)?Page URL:\s*(https?://\S+)\s*$")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def digest_json(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def content_text(message: dict[str, Any]) -> str:
    result = message.get("result") or {}
    content = result.get("content") if isinstance(result, dict) else None
    if isinstance(content, list):
        return "\n".join(
            str(item.get("text"))
            for item in content
            if isinstance(item, dict) and isinstance(item.get("text"), str)
        )
    return json.dumps(result, ensure_ascii=False)


def origin(raw: str) -> str | None:
    try:
        p = urlsplit(raw)
        if p.scheme not in {"http", "https"} or not p.hostname:
            return None
        if p.username is not None or p.password is not None:
            return None
        host = p.hostname.lower().rstrip(".")
        default_port = 80 if p.scheme == "http" else 443
        port = p.port or default_port
        suffix = "" if port == default_port else f":{port}"
        return f"{p.scheme}://{host}{suffix}"
    except ValueError:
        return None


def safe_url(raw: str) -> str:
    try:
        p = urlsplit(raw)
        return urlunsplit((p.scheme, p.netloc, p.path or "/", "", ""))
    except ValueError:
        return "invalid-url"


def final_page_url(text: str) -> str | None:
    matches = PAGE_URL_RE.findall(text)
    if not matches:
        return None
    return matches[-1].rstrip(".,;)")


class MCPClient:
    def __init__(self, argv: list[str], cwd: Path, timeout: float):
        self.timeout = timeout
        self.proc = subprocess.Popen(
            argv,
            cwd=str(cwd),
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
        self.stderr: list[str] = []
        threading.Thread(target=self._drain_stderr, daemon=True).start()

    def _drain_stderr(self) -> None:
        assert self.proc.stderr
        for line in self.proc.stderr:
            if line.strip():
                self.stderr.append(line.strip()[:1000])
                self.stderr[:] = self.stderr[-40:]

    def send(self, payload: dict[str, Any]) -> None:
        assert self.proc.stdin
        self.proc.stdin.write(json.dumps(payload, separators=(",", ":")) + "\n")
        self.proc.stdin.flush()

    def request(self, request_id: str, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self.send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}})
        deadline = time.monotonic() + self.timeout
        assert self.proc.stdout
        while time.monotonic() < deadline:
            if self.proc.poll() is not None:
                raise RuntimeError(f"MCP_SERVER_EXITED:{self.proc.returncode}")
            for _key, _mask in self.selector.select(0.25):
                line = self.proc.stdout.readline()
                if not line:
                    continue
                try:
                    message = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if str(message.get("id")) == str(request_id):
                    return message
        raise TimeoutError(f"MCP_RESPONSE_TIMEOUT:{method}")

    def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        self.send({"jsonrpc": "2.0", "method": method, "params": params or {}})

    def call_tool(self, request_id: str, name: str, arguments: dict[str, Any]) -> tuple[dict[str, Any], str]:
        if name not in SAFE_TOOLS or name in DENIED_TOOLS:
            raise RuntimeError(f"TOOL_POLICY_DENIED:{name}")
        message = self.request(request_id, "tools/call", {"name": name, "arguments": arguments})
        return message, content_text(message)

    def close(self) -> None:
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=5)


def base_result(envelope: dict[str, Any], status: str, summary: str, evidence: list[dict[str, Any]]) -> dict[str, Any]:
    task = envelope.get("task") if isinstance(envelope.get("task"), dict) else {}
    return {
        "schema": OUTPUT_SCHEMA,
        "project": str(envelope.get("project") or "unknown"),
        "task_id": str(task.get("id") or "unknown"),
        "status": status,
        "producer": PRODUCER,
        "observed_at": now_iso(),
        "summary": summary,
        "evidence": evidence,
        "verification": {
            "status": "UNVERIFIED",
            "method": "none",
            "verifier": "verification-broker",
            "notes": "Producer result only; independent Verification Broker assessment is required.",
        },
        "outputs": [
            {
                "type": "gate",
                "id": "playwright-readonly-browser-verification",
                "status": "UNVERIFIED",
                "reason": "Provider evidence requires independent Verification Broker assessment.",
            }
        ],
    }


def emit(result: dict[str, Any]) -> int:
    sys.stdout.write(json.dumps(result, ensure_ascii=False, separators=(",", ":")) + "\n")
    sys.stdout.flush()
    return 0


def policy_block(envelope: dict[str, Any], code: str, details: dict[str, Any] | None = None) -> int:
    payload = {"policy_block": code, "provider": PROVIDER, "adapter": ADAPTER}
    if details:
        payload.update(details)
    evidence = [{"kind": "report", "source": "playwright-mcp-adapter:policy", "digest": digest_json(payload), "details": payload}]
    return emit(base_result(envelope, "BLOCKED", code, evidence))


def validate_envelope(envelope: dict[str, Any]) -> str | None:
    if envelope.get("schema") != INPUT_SCHEMA:
        return "INPUT_SCHEMA_INVALID"
    task = envelope.get("task")
    if not isinstance(task, dict) or not isinstance(task.get("id"), str) or not task.get("id"):
        return "TASK_ID_MISSING"
    if task.get("permission") != "read":
        return "READ_PERMISSION_REQUIRED"
    bindings = envelope.get("bindings")
    if not isinstance(bindings, list):
        return "BINDINGS_INVALID"
    expected = [
        b for b in bindings
        if isinstance(b, dict) and b.get("provider") == PROVIDER and b.get("adapter") == ADAPTER
    ]
    if len(expected) != 1:
        return "PLAYWRIGHT_BINDING_REQUIRED"
    policy = envelope.get("policy_context")
    if not isinstance(policy, dict):
        return "POLICY_CONTEXT_INVALID"
    if policy.get("human_approval_required") is True:
        return "HUMAN_APPROVAL_BOUNDARY"
    metadata = envelope.get("metadata")
    if not isinstance(metadata, dict) or not isinstance(metadata.get("target_url"), str):
        return "TARGET_URL_REQUIRED"
    if origin(metadata["target_url"]) is None:
        return "TARGET_URL_DENIED"
    return None


def main() -> int:
    try:
        envelope = json.loads(sys.stdin.read())
    except Exception:
        envelope = {"project": "unknown", "task": {"id": "unknown"}}
        return policy_block(envelope, "INPUT_JSON_INVALID")
    if not isinstance(envelope, dict):
        return policy_block({"project": "unknown", "task": {"id": "unknown"}}, "INPUT_ROOT_INVALID")

    block = validate_envelope(envelope)
    if block:
        return policy_block(envelope, block)

    server = os.environ.get("PLAYWRIGHT_MCP_SERVER", "").strip()
    workdir = Path(os.environ.get("PLAYWRIGHT_MCP_WORKDIR", "").strip())
    target_class = os.environ.get("PLAYWRIGHT_MCP_TARGET_CLASS", "").strip()
    allowed_raw = os.environ.get("PLAYWRIGHT_MCP_ALLOWED_ORIGIN", "").strip()
    if not server or not Path(server).is_file():
        return policy_block(envelope, "PROVIDER_SERVER_REFERENCE_INVALID")
    if not workdir.is_dir():
        return policy_block(envelope, "PROVIDER_WORKDIR_REFERENCE_INVALID")
    if target_class not in {"test", "preview"}:
        return policy_block(envelope, "PLAYWRIGHT_MCP_TARGET_CLASS_NOT_ALLOWED")
    allowed = origin(allowed_raw)
    if not allowed:
        return policy_block(envelope, "PLAYWRIGHT_MCP_ALLOWED_ORIGIN_INVALID")

    metadata = envelope["metadata"]
    target_url = metadata["target_url"]
    target_origin = origin(target_url)
    if target_origin != allowed:
        return policy_block(
            envelope,
            "PLAYWRIGHT_MCP_TARGET_ORIGIN_NOT_ALLOWED",
            {"target_origin": target_origin or "invalid", "allowed_origin": allowed},
        )

    timeout = float((envelope.get("policy_context") or {}).get("timeout_seconds") or 30)
    timeout = max(1.0, min(timeout, 60.0))

    called: list[str] = []
    checks: dict[str, Any] = {}
    client: MCPClient | None = None
    try:
        client = MCPClient(
            [
                server,
                "--headless",
                "--isolated",
                "--block-service-workers",
                "--browser=chromium",
                f"--allowed-origins={allowed}",
                "--codegen=none",
            ],
            workdir,
            timeout,
        )
        init = client.request(
            "init",
            "initialize",
            {
                "protocolVersion": UPSTREAM_PROTOCOL,
                "capabilities": {},
                "clientInfo": {"name": "chacha-dev-playwright-adapter", "version": "2.0.0"},
            },
        )
        init_result = init.get("result") or {}
        negotiated = init_result.get("protocolVersion")
        if "error" in init or negotiated != UPSTREAM_PROTOCOL:
            raise RuntimeError("UPSTREAM_INITIALIZE_FAILED")
        client.notify("notifications/initialized")
        checks["upstream_protocol"] = negotiated
        checks["server_info"] = init_result.get("serverInfo")

        tools = client.request("tools", "tools/list")
        items = ((tools.get("result") or {}).get("tools") or [])
        names = sorted(str(x.get("name")) for x in items if isinstance(x, dict) and x.get("name"))
        missing = [name for name in SAFE_TOOLS if name not in names]
        if "error" in tools or missing:
            raise RuntimeError("SAFE_TOOL_INVENTORY_FAILED:" + ",".join(missing))
        checks["tools_exposed_count"] = len(names)
        checks["safe_tools_present"] = True

        nav, nav_text = client.call_tool("10", "browser_navigate", {"url": target_url})
        called.append("browser_navigate")
        if "error" in nav:
            raise RuntimeError("NAVIGATE_FAILED")
        observed_final = final_page_url(nav_text)
        if not observed_final:
            return policy_block(envelope, "PLAYWRIGHT_MCP_FINAL_URL_UNOBSERVED")
        observed_origin = origin(observed_final)
        if observed_origin != allowed:
            return policy_block(
                envelope,
                "PLAYWRIGHT_MCP_FINAL_ORIGIN_NOT_ALLOWED",
                {
                    "initial_url": safe_url(target_url),
                    "final_url": safe_url(observed_final),
                    "allowed_origin": allowed,
                },
            )
        checks["navigate"] = True
        checks["initial_url"] = safe_url(target_url)
        checks["final_url"] = safe_url(observed_final)
        checks["final_origin_revalidated"] = True

        snap, snap_text = client.call_tool("11", "browser_snapshot", {})
        called.append("browser_snapshot")
        if "error" in snap:
            raise RuntimeError("SNAPSHOT_FAILED")
        checks["snapshot_digest"] = "sha256:" + hashlib.sha256(snap_text.encode("utf-8")).hexdigest()

        console, console_text = client.call_tool("12", "browser_console_messages", {"level": "info", "all": True})
        called.append("browser_console_messages")
        if "error" in console:
            raise RuntimeError("CONSOLE_READ_FAILED")
        checks["console_observed"] = bool(console_text)

        network, network_text = client.call_tool("13", "browser_network_requests", {"includeStatic": True})
        called.append("browser_network_requests")
        if "error" in network:
            raise RuntimeError("NETWORK_READ_FAILED")
        checks["network_observed"] = bool(network_text)

        close, _ = client.call_tool("14", "browser_close", {})
        called.append("browser_close")
        if "error" in close:
            raise RuntimeError("BROWSER_CLOSE_FAILED")

        if set(called) & DENIED_TOOLS:
            raise RuntimeError("DENIED_TOOL_CALLED")

        evidence_details = {
            "compatibility_mode": "EXPLICIT_PROVIDER_COMPATIBILITY",
            "dev_hub_protocol_baseline": "2026-07-28",
            "upstream_protocol": UPSTREAM_PROTOCOL,
            "target_class": target_class,
            "allowed_origin_source": "trusted-runner-environment",
            "allowed_origin": allowed,
            "initial_target_origin": target_origin,
            "final_target_origin": observed_origin,
            "final_origin_revalidated": True,
            "upstream_allowed_origins_is_security_boundary": False,
            "called_tools": called,
            "checks": checks,
            "credentials_used": False,
            "production_target": False,
            "workspace_write": False,
            "repository_write": False,
        }
        evidence = [
            {
                "kind": "report",
                "source": "playwright-mcp-adapter:runtime-v2",
                "digest": digest_json(evidence_details),
                "details": evidence_details,
            }
        ]
        return emit(base_result(envelope, "OK", "Playwright MCP controlled read-only browser verification completed.", evidence))
    except Exception as exc:
        details = {
            "error": str(exc),
            "called_tools": called,
            "target_class": target_class,
            "allowed_origin": allowed,
            "credentials_used": False,
            "production_target": False,
            "workspace_write": False,
            "repository_write": False,
        }
        evidence = [{"kind": "report", "source": "playwright-mcp-adapter:runtime-v2", "digest": digest_json(details), "details": details}]
        return emit(base_result(envelope, "FAILED", f"Playwright MCP runtime V2 failed: {exc}", evidence))
    finally:
        if client:
            client.close()


if __name__ == "__main__":
    raise SystemExit(main())
