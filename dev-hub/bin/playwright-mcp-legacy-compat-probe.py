#!/usr/bin/env python3
"""Provider-specific legacy MCP compatibility probe for Playwright MCP.

This probe does not change DEV HUB's 2026-07-28 baseline. It proves that the
provider-specific adapter can encapsulate a 2025-11-25 upstream session safely.
"""
from __future__ import annotations

import argparse
import hashlib
import http.server
import json
import selectors
import socketserver
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = "chacha.dev/playwright-mcp-legacy-compat-probe/v1"
UPSTREAM_PROTOCOL = "2025-11-25"
SAFE_CALLS = ["browser_navigate", "browser_snapshot", "browser_console_messages", "browser_network_requests", "browser_close"]
DENY = {
    "browser_run_code_unsafe", "browser_evaluate", "browser_click", "browser_type",
    "browser_fill_form", "browser_file_upload", "browser_drop", "browser_drag",
    "browser_handle_dialog", "browser_hover", "browser_press_key", "browser_select_option",
    "browser_webmcp_call", "browser_webmcp_list"
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return "sha256:" + hashlib.sha256(raw).hexdigest()


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/api/ping":
            body = b'{"ok":true,"source":"playwright-legacy-compat"}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        body = b"""<!doctype html><html><head><title>Playwright Legacy Compat Fixture</title></head>
<body><h1>Playwright Legacy Compat Fixture</h1><p>fixture-ready</p>
<script>console.log('legacy-console-ok'); fetch('/api/ping').then(r => r.json()).then(x => console.log('legacy-network-ok', x.ok));</script>
</body></html>"""
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format: str, *_args: Any) -> None:
        return


class Server(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


class Client:
    def __init__(self, argv: list[str], cwd: Path, timeout: float = 30.0):
        self.timeout = timeout
        self.proc = subprocess.Popen(
            argv, cwd=str(cwd), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", bufsize=1,
        )
        assert self.proc.stdin and self.proc.stdout and self.proc.stderr
        self.sel = selectors.DefaultSelector()
        self.sel.register(self.proc.stdout, selectors.EVENT_READ)
        self.stderr: list[str] = []
        threading.Thread(target=self._drain_err, daemon=True).start()

    def _drain_err(self) -> None:
        assert self.proc.stderr
        for line in self.proc.stderr:
            if line.strip():
                self.stderr.append(line.strip()[:1000])
                self.stderr[:] = self.stderr[-100:]

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
            for _key, _mask in self.sel.select(0.5):
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


def content_text(msg: dict[str, Any]) -> str:
    result = msg.get("result") or {}
    content = result.get("content") if isinstance(result, dict) else None
    if isinstance(content, list):
        return "\n".join(str(x.get("text")) for x in content if isinstance(x, dict) and isinstance(x.get("text"), str))
    return json.dumps(result, ensure_ascii=False)


def call(client: Client, counter: int, name: str, args: dict[str, Any]) -> tuple[dict[str, Any], str]:
    msg = client.request(str(counter), "tools/call", {"name": name, "arguments": args})
    return msg, content_text(msg)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--server", required=True, type=Path)
    p.add_argument("--workdir", required=True, type=Path)
    p.add_argument("--package-version", required=True)
    p.add_argument("--browser-version", required=True)
    p.add_argument("--output", required=True, type=Path)
    args = p.parse_args()

    evidence: dict[str, Any] = {
        "schema": SCHEMA,
        "observed_at": now_iso(),
        "provider": "playwright-mcp",
        "adapter": "playwright-mcp-adapter",
        "compatibility_mode": "EXPLICIT_PROVIDER_COMPATIBILITY",
        "dev_hub_protocol_baseline": "2026-07-28",
        "upstream_protocol_requested": UPSTREAM_PROTOCOL,
        "package_version": args.package_version,
        "browser_version": args.browser_version,
        "execution_surface": "github-actions-ephemeral",
        "credentials_used": False,
        "production_target": False,
        "vps_modified": False,
        "called_tools": [],
        "deny_policy": sorted(DENY),
        "checks": {},
        "promotion": {"automatic": False, "eligible_for_compat_pilot": False, "blockers": []},
    }
    blockers: list[str] = []
    web: Server | None = None
    client: Client | None = None
    try:
        web = Server(("127.0.0.1", 0), Handler)
        port = int(web.server_address[1])
        origin = f"http://127.0.0.1:{port}"
        evidence["target_origin"] = origin
        threading.Thread(target=web.serve_forever, daemon=True).start()

        client = Client([
            str(args.server), "--headless", "--isolated", "--block-service-workers",
            "--browser=chromium", f"--allowed-origins={origin}", "--codegen=none",
        ], args.workdir)

        init = client.request("init", "initialize", {
            "protocolVersion": UPSTREAM_PROTOCOL,
            "capabilities": {},
            "clientInfo": {"name": "chacha-dev-playwright-compat", "version": "1.0.0"},
        })
        init_result = init.get("result") or {}
        negotiated = init_result.get("protocolVersion")
        evidence["upstream_protocol_negotiated"] = negotiated
        evidence["server_info"] = init_result.get("serverInfo")
        init_ok = "error" not in init and negotiated == UPSTREAM_PROTOCOL
        evidence["checks"]["legacy_initialize"] = {"pass": init_ok, "error": init.get("error")}
        if not init_ok:
            blockers.append("LEGACY_2025_11_25_INITIALIZE_FAILED")
            raise RuntimeError("LEGACY_INITIALIZE_BLOCKED")
        client.notify("notifications/initialized")

        tools = client.request("tools", "tools/list")
        items = ((tools.get("result") or {}).get("tools") or [])
        names = sorted(str(x.get("name")) for x in items if isinstance(x, dict) and x.get("name"))
        evidence["tools_exposed"] = names
        missing = [name for name in SAFE_CALLS if name not in names]
        evidence["checks"]["tools_list"] = {"pass": "error" not in tools and not missing, "missing": missing, "count": len(names)}
        if "error" in tools or missing:
            blockers.extend("SAFE_TOOL_MISSING:" + name for name in missing)
            if "error" in tools:
                blockers.append("TOOLS_LIST_FAILED")
            raise RuntimeError("TOOLS_BLOCKED")

        n = 10
        nav, text = call(client, n, "browser_navigate", {"url": origin + "/"}); n += 1
        evidence["called_tools"].append("browser_navigate")
        ok = "error" not in nav and "Playwright Legacy Compat Fixture" in text
        evidence["checks"]["navigate"] = {"pass": ok}
        if not ok: blockers.append("NAVIGATE_FAILED")

        snap, text = call(client, n, "browser_snapshot", {}); n += 1
        evidence["called_tools"].append("browser_snapshot")
        ok = "error" not in snap and "Playwright Legacy Compat Fixture" in text and "fixture-ready" in text
        evidence["checks"]["snapshot"] = {"pass": ok, "digest": "sha256:" + hashlib.sha256(text.encode()).hexdigest()}
        if not ok: blockers.append("SNAPSHOT_FAILED")

        con, text = call(client, n, "browser_console_messages", {"level": "info", "all": True}); n += 1
        evidence["called_tools"].append("browser_console_messages")
        ok = "error" not in con and "legacy-console-ok" in text
        evidence["checks"]["console"] = {"pass": ok, "marker": "legacy-console-ok" in text}
        if not ok: blockers.append("CONSOLE_FAILED")

        net, text = call(client, n, "browser_network_requests", {"includeStatic": True}); n += 1
        evidence["called_tools"].append("browser_network_requests")
        ok = "error" not in net and "/api/ping" in text
        evidence["checks"]["network"] = {"pass": ok, "marker": "/api/ping" in text}
        if not ok: blockers.append("NETWORK_FAILED")

        close, _ = call(client, n, "browser_close", {})
        evidence["called_tools"].append("browser_close")
        ok = "error" not in close
        evidence["checks"]["close"] = {"pass": ok}
        if not ok: blockers.append("CLOSE_FAILED")

        denied_called = sorted(set(evidence["called_tools"]) & DENY)
        evidence["checks"]["deny_boundary"] = {"pass": not denied_called, "called_denied": denied_called}
        if denied_called: blockers.append("DENIED_TOOL_CALLED")

    except Exception as exc:
        evidence["probe_exception"] = str(exc)
        if not blockers:
            blockers.append("COMPAT_PROBE_INFRASTRUCTURE_FAILURE")
    finally:
        if client:
            evidence["server_stderr_tail"] = client.stderr[-20:]
            client.close()
        if web:
            web.shutdown(); web.server_close()

    evidence["promotion"] = {
        "automatic": False,
        "eligible_for_compat_pilot": not blockers,
        "blockers": sorted(set(blockers)),
    }
    evidence["evidence_digest"] = digest({k: v for k, v in evidence.items() if k != "evidence_digest"})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"PLAYWRIGHT_LEGACY_COMPAT_EVIDENCE={args.output}")
    print(f"ELIGIBLE_FOR_COMPAT_PILOT={'YES' if not blockers else 'NO'}")
    for blocker in sorted(set(blockers)):
        print(f"BLOCKER={blocker}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
