#!/usr/bin/env python3
"""Playwright MCP live qualification probe for ChaCha DEV HUB.

The probe is evidence-only. It never mutates provider lifecycle state.
It requires MCP 2026-07-28 server/discover before any browser tool call.
"""
from __future__ import annotations

import argparse
import hashlib
import http.server
import json
import os
import selectors
import socketserver
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = "chacha.dev/playwright-mcp-direct-probe/v1"
PROTOCOL = "2026-07-28"
META = {
    "io.modelcontextprotocol/protocolVersion": PROTOCOL,
    "io.modelcontextprotocol/clientInfo": {"name": "chacha-dev-playwright-probe", "version": "1.0.0"},
    "io.modelcontextprotocol/clientCapabilities": {},
}
SAFE_CALLS = [
    "browser_navigate",
    "browser_snapshot",
    "browser_console_messages",
    "browser_network_requests",
    "browser_close",
]
NEVER_CALL = {
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


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return "sha256:" + hashlib.sha256(raw).hexdigest()


class FixtureHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/api/ping":
            body = b'{"ok":true,"source":"playwright-mcp-pilot"}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        body = b"""<!doctype html><html><head><title>Playwright MCP Pilot Fixture</title></head>
<body><h1>Playwright MCP Pilot Fixture</h1><p id='probe'>fixture-ready</p>
<script>console.log('pilot-console-ok'); fetch('/api/ping').then(r => r.json()).then(x => console.log('pilot-network-ok', x.ok));</script>
</body></html>"""
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format: str, *_args: Any) -> None:
        return


class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


class MCPProcess:
    def __init__(self, argv: list[str], cwd: Path, timeout: float = 30.0):
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
        )
        assert self.proc.stdin and self.proc.stdout and self.proc.stderr
        self.selector = selectors.DefaultSelector()
        self.selector.register(self.proc.stdout, selectors.EVENT_READ)
        self.stderr_lines: list[str] = []
        self._stderr_thread = threading.Thread(target=self._drain_stderr, daemon=True)
        self._stderr_thread.start()

    def _drain_stderr(self) -> None:
        assert self.proc.stderr
        for line in self.proc.stderr:
            clean = line.rstrip("\n")
            if clean:
                self.stderr_lines.append(clean[:1000])
                if len(self.stderr_lines) > 100:
                    self.stderr_lines.pop(0)

    def request(self, req_id: str, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        assert self.proc.stdin and self.proc.stdout
        payload = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": {**(params or {}), "_meta": META},
        }
        self.proc.stdin.write(json.dumps(payload, separators=(",", ":")) + "\n")
        self.proc.stdin.flush()
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            if self.proc.poll() is not None:
                raise RuntimeError(f"MCP_SERVER_EXITED:{self.proc.returncode}")
            remaining = max(0.1, deadline - time.monotonic())
            events = self.selector.select(min(0.5, remaining))
            for _key, _mask in events:
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

    def close(self) -> None:
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=5)


def result_text(message: dict[str, Any]) -> str:
    result = message.get("result") or {}
    content = result.get("content") if isinstance(result, dict) else None
    if isinstance(content, list):
        chunks = []
        for item in content:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                chunks.append(item["text"])
        return "\n".join(chunks)
    return json.dumps(result, ensure_ascii=False)


def tool_call(client: MCPProcess, counter: int, name: str, arguments: dict[str, Any]) -> tuple[dict[str, Any], str]:
    response = client.request(str(counter), "tools/call", {"name": name, "arguments": arguments})
    return response, result_text(response)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", required=True, type=Path)
    parser.add_argument("--workdir", required=True, type=Path)
    parser.add_argument("--package-version", required=True)
    parser.add_argument("--browser-version", default="unknown")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    evidence: dict[str, Any] = {
        "schema": SCHEMA,
        "observed_at": now_iso(),
        "provider": "playwright-mcp",
        "adapter": "playwright-mcp-adapter",
        "execution_surface": "github-actions-ephemeral",
        "package": "@playwright/mcp",
        "package_version": args.package_version,
        "browser_version": args.browser_version,
        "protocol_required": PROTOCOL,
        "credentials_used": False,
        "production_target": False,
        "vps_modified": False,
        "workspace_write_expected": False,
        "called_tools": [],
        "never_call_policy": sorted(NEVER_CALL),
        "checks": {},
        "promotion": {"automatic": False, "eligible_for_pilot": False, "blockers": []},
    }
    blockers: list[str] = []
    server: ThreadedTCPServer | None = None
    client: MCPProcess | None = None

    try:
        server = ThreadedTCPServer(("127.0.0.1", 0), FixtureHandler)
        port = int(server.server_address[1])
        origin = f"http://127.0.0.1:{port}"
        target = origin + "/"
        evidence["target_origin"] = origin
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        argv = [
            str(args.server),
            "--headless",
            "--isolated",
            "--block-service-workers",
            "--browser=chromium",
            f"--allowed-origins={origin}",
            "--codegen=none",
        ]
        client = MCPProcess(argv, args.workdir)

        discover = client.request("discover", "server/discover")
        evidence["checks"]["server_discover"] = {
            "pass": "error" not in discover,
            "error": discover.get("error"),
            "result_digest": canonical_digest(discover.get("result")) if discover.get("result") is not None else None,
        }
        if "error" in discover:
            blockers.append("MCP_2026_07_28_SERVER_DISCOVER_UNSUPPORTED")
            raise RuntimeError("SERVER_DISCOVER_BLOCKED")

        discover_result = discover.get("result") or {}
        supported = discover_result.get("supportedVersions") or []
        evidence["server_identity"] = discover_result.get("serverInfo") or discover_result.get("server")
        evidence["supported_protocol_versions"] = supported
        if PROTOCOL not in supported:
            blockers.append("MCP_2026_07_28_NOT_ADVERTISED")
            raise RuntimeError("PROTOCOL_VERSION_BLOCKED")

        tools = client.request("tools", "tools/list")
        if "error" in tools:
            blockers.append("TOOLS_LIST_FAILED")
            raise RuntimeError("TOOLS_LIST_BLOCKED")
        tool_items = ((tools.get("result") or {}).get("tools") or [])
        tool_names = sorted(str(x.get("name")) for x in tool_items if isinstance(x, dict) and x.get("name"))
        evidence["tools_exposed"] = tool_names
        required = ["browser_navigate", "browser_snapshot", "browser_close"]
        missing = [name for name in required if name not in tool_names]
        evidence["checks"]["tools_list"] = {"pass": not missing, "required_missing": missing, "tool_count": len(tool_names)}
        if missing:
            blockers.extend("REQUIRED_TOOL_MISSING:" + name for name in missing)
            raise RuntimeError("TOOLS_REQUIRED_BLOCKED")

        counter = 10
        nav, nav_text = tool_call(client, counter, "browser_navigate", {"url": target})
        counter += 1
        evidence["called_tools"].append("browser_navigate")
        nav_ok = "error" not in nav and "Playwright MCP Pilot Fixture" in nav_text
        evidence["checks"]["navigate"] = {"pass": nav_ok, "result_digest": canonical_digest(nav.get("result"))}
        if not nav_ok:
            blockers.append("TEST_ORIGIN_NAVIGATION_FAILED")

        snap, snap_text = tool_call(client, counter, "browser_snapshot", {})
        counter += 1
        evidence["called_tools"].append("browser_snapshot")
        snap_ok = "error" not in snap and "Playwright MCP Pilot Fixture" in snap_text and "fixture-ready" in snap_text
        evidence["checks"]["snapshot"] = {"pass": snap_ok, "snapshot_digest": "sha256:" + hashlib.sha256(snap_text.encode()).hexdigest()}
        if not snap_ok:
            blockers.append("SNAPSHOT_FAILED")

        if "browser_console_messages" in tool_names:
            console, console_text = tool_call(client, counter, "browser_console_messages", {})
            counter += 1
            evidence["called_tools"].append("browser_console_messages")
            console_ok = "error" not in console and "pilot-console-ok" in console_text
            evidence["checks"]["console"] = {"pass": console_ok, "contains_fixture_marker": "pilot-console-ok" in console_text}
            if not console_ok:
                blockers.append("CONSOLE_READ_FAILED")
        else:
            evidence["checks"]["console"] = {"pass": False, "reason": "tool-not-exposed"}
            blockers.append("CONSOLE_TOOL_MISSING")

        if "browser_network_requests" in tool_names:
            network, network_text = tool_call(client, counter, "browser_network_requests", {})
            counter += 1
            evidence["called_tools"].append("browser_network_requests")
            network_ok = "error" not in network and "/api/ping" in network_text
            evidence["checks"]["network"] = {"pass": network_ok, "contains_fixture_request": "/api/ping" in network_text}
            if not network_ok:
                blockers.append("NETWORK_READ_FAILED")
        else:
            evidence["checks"]["network"] = {"pass": False, "reason": "tool-not-exposed"}
            blockers.append("NETWORK_TOOL_MISSING")

        close, _close_text = tool_call(client, counter, "browser_close", {})
        evidence["called_tools"].append("browser_close")
        close_ok = "error" not in close
        evidence["checks"]["browser_close"] = {"pass": close_ok}
        if not close_ok:
            blockers.append("BROWSER_CLOSE_FAILED")

        called_denied = sorted(set(evidence["called_tools"]) & NEVER_CALL)
        evidence["checks"]["deny_boundary"] = {"pass": not called_denied, "called_denied_tools": called_denied}
        if called_denied:
            blockers.append("DENIED_TOOL_CALLED")

    except Exception as exc:  # probe must still emit machine evidence on a controlled blocker
        evidence["probe_exception"] = str(exc)
        if not blockers:
            blockers.append("PROBE_INFRASTRUCTURE_FAILURE")
    finally:
        if client:
            evidence["server_stderr_tail"] = client.stderr_lines[-20:]
            client.close()
        if server:
            server.shutdown()
            server.server_close()

    evidence["promotion"] = {
        "automatic": False,
        "eligible_for_pilot": not blockers,
        "blockers": sorted(set(blockers)),
    }
    evidence["evidence_digest"] = canonical_digest({k: v for k, v in evidence.items() if k != "evidence_digest"})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"PLAYWRIGHT_MCP_PROBE_EVIDENCE={args.output}")
    print(f"ELIGIBLE_FOR_PILOT={'YES' if not blockers else 'NO'}")
    for blocker in sorted(set(blockers)):
        print(f"BLOCKER={blocker}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
