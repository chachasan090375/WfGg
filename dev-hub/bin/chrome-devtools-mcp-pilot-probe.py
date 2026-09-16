#!/usr/bin/env python3
"""Chrome DevTools MCP modern protocol qualification probe.

Evidence-only: never mutates provider lifecycle state and never launches a browser.
The DEV HUB 2026-07-28 server/discover gate must pass before any browser runtime test.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import selectors
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = "chacha.dev/chrome-devtools-mcp-direct-probe/v1"
PROTOCOL = "2026-07-28"
META = {
    "io.modelcontextprotocol/protocolVersion": PROTOCOL,
    "io.modelcontextprotocol/clientInfo": {"name": "chacha-dev-chrome-devtools-probe", "version": "1.0.0"},
    "io.modelcontextprotocol/clientCapabilities": {},
}
READ_ONLY_EXPECTED = {
    "list_pages",
    "take_snapshot",
    "take_screenshot",
    "list_console_messages",
    "get_console_message",
    "list_network_requests",
    "get_network_request",
}
DENIED = {
    "evaluate_script", "click", "click_at", "drag", "fill", "fill_form", "handle_dialog",
    "hover", "press_key", "type_text", "upload_file", "navigate_page", "new_page", "close_page",
    "resize_page", "emulate", "lighthouse_audit", "performance_start_trace", "performance_stop_trace",
    "performance_analyze_insight",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return "sha256:" + hashlib.sha256(raw).hexdigest()


class MCPProcess:
    def __init__(self, argv: list[str], cwd: Path, timeout: float = 25.0):
        self.timeout = timeout
        self.proc = subprocess.Popen(
            argv, cwd=str(cwd), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", bufsize=1,
        )
        assert self.proc.stdin and self.proc.stdout and self.proc.stderr
        self.selector = selectors.DefaultSelector()
        self.selector.register(self.proc.stdout, selectors.EVENT_READ)
        self.stderr_lines: list[str] = []
        threading.Thread(target=self._drain_stderr, daemon=True).start()

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
        payload = {"jsonrpc": "2.0", "id": req_id, "method": method, "params": {**(params or {}), "_meta": META}}
        self.proc.stdin.write(json.dumps(payload, separators=(",", ":")) + "\n")
        self.proc.stdin.flush()
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            if self.proc.poll() is not None:
                raise RuntimeError(f"MCP_SERVER_EXITED:{self.proc.returncode}")
            for _key, _mask in self.selector.select(min(0.5, max(0.1, deadline - time.monotonic()))):
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


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--server", required=True, type=Path)
    p.add_argument("--workdir", required=True, type=Path)
    p.add_argument("--package-version", required=True)
    p.add_argument("--output", required=True, type=Path)
    args = p.parse_args()

    evidence: dict[str, Any] = {
        "schema": SCHEMA,
        "observed_at": now_iso(),
        "provider": "chrome-devtools-mcp",
        "adapter": "chrome-devtools-mcp-adapter",
        "execution_surface": "github-actions-ephemeral",
        "package": "chrome-devtools-mcp",
        "package_version": args.package_version,
        "protocol_required": PROTOCOL,
        "browser_launched": False,
        "browser_downloaded": False,
        "credentials_used": False,
        "production_target": False,
        "vps_modified": False,
        "workspace_write_expected": False,
        "repository_write_expected": False,
        "called_tools": [],
        "read_only_expected": sorted(READ_ONLY_EXPECTED),
        "denied_tools": sorted(DENIED),
        "checks": {},
        "promotion": {"automatic": False, "eligible_for_pilot": False, "blockers": []},
    }
    blockers: list[str] = []
    client: MCPProcess | None = None

    try:
        argv = [
            str(args.server),
            "--headless=true",
            "--isolated=true",
            "--no-javascript-evaluation",
            "--no-performance-crux",
            "--no-usage-statistics",
            "--redact-network-headers",
            "--no-source-maps",
        ]
        client = MCPProcess(argv, args.workdir)

        discover = client.request("discover", "server/discover")
        evidence["checks"]["server_discover"] = {
            "pass": "error" not in discover,
            "error": discover.get("error"),
            "result_digest": digest(discover.get("result")) if discover.get("result") is not None else None,
        }
        if "error" in discover:
            blockers.append("MCP_2026_07_28_SERVER_DISCOVER_UNSUPPORTED")
            raise RuntimeError("SERVER_DISCOVER_BLOCKED")

        result = discover.get("result") or {}
        supported = result.get("supportedVersions") or []
        evidence["server_identity"] = result.get("serverInfo") or result.get("server")
        evidence["supported_protocol_versions"] = supported
        if PROTOCOL not in supported:
            blockers.append("MCP_2026_07_28_NOT_ADVERTISED")
            raise RuntimeError("PROTOCOL_VERSION_BLOCKED")

        tools = client.request("tools", "tools/list")
        if "error" in tools:
            blockers.append("TOOLS_LIST_FAILED")
            raise RuntimeError("TOOLS_LIST_BLOCKED")
        items = ((tools.get("result") or {}).get("tools") or [])
        names = sorted(str(x.get("name")) for x in items if isinstance(x, dict) and x.get("name"))
        evidence["tools_exposed"] = names
        missing_read = sorted(READ_ONLY_EXPECTED - set(names))
        denied_exposed = sorted(DENIED & set(names))
        evidence["checks"]["tools_list"] = {
            "pass": not missing_read,
            "tool_count": len(names),
            "missing_read_only_expected": missing_read,
            "denied_tools_exposed": denied_exposed,
            "note": "Exposure alone does not authorize denied tools; adapter allowlist remains authoritative.",
        }
        if missing_read:
            blockers.extend("EXPECTED_READ_TOOL_MISSING:" + x for x in missing_read)

    except Exception as exc:
        evidence["probe_exception"] = str(exc)
        if not blockers:
            blockers.append("PROBE_INFRASTRUCTURE_FAILURE")
    finally:
        if client:
            evidence["server_stderr_tail"] = client.stderr_lines[-20:]
            client.close()

    evidence["promotion"] = {
        "automatic": False,
        "eligible_for_pilot": not blockers,
        "blockers": sorted(set(blockers)),
    }
    evidence["evidence_digest"] = digest({k: v for k, v in evidence.items() if k != "evidence_digest"})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"CHROME_DEVTOOLS_MCP_PROBE_EVIDENCE={args.output}")
    print(f"ELIGIBLE_FOR_PILOT={'YES' if not blockers else 'NO'}")
    for blocker in sorted(set(blockers)):
        print(f"BLOCKER={blocker}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
