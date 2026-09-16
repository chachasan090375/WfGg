#!/usr/bin/env python3
"""Independent normalized health probe for Playwright MCP.

The probe never invokes playwright-mcp-adapter. It delegates the raw upstream
MCP/browser check to the provider-specific legacy compatibility probe, then
normalizes the result to chacha.dev/provider-probe-result/v1.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = "chacha.dev/provider-probe-result/v1"
PROVIDER = "playwright-mcp"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit(f"JSON_ROOT_NOT_OBJECT={path}")
    return value


def digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Independent Playwright MCP provider health probe")
    parser.add_argument("--server", required=True, type=Path)
    parser.add_argument("--workdir", required=True, type=Path)
    parser.add_argument("--package-version", required=True)
    parser.add_argument("--browser-version", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--raw-output", required=True, type=Path)
    args = parser.parse_args()

    cmd = [
        "python3", "dev-hub/bin/playwright-mcp-legacy-compat-probe.py",
        "--server", str(args.server),
        "--workdir", str(args.workdir),
        "--package-version", args.package_version,
        "--browser-version", args.browser_version,
        "--output", str(args.raw_output),
    ]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, shell=False, check=False)
    blockers: list[str] = []
    raw: dict[str, Any] = {}
    try:
        raw = load(args.raw_output)
    except Exception as exc:
        blockers.append(f"RAW_PROBE_EVIDENCE_INVALID:{type(exc).__name__}")

    if raw:
        if raw.get("schema") != "chacha.dev/playwright-mcp-legacy-compat-probe/v1":
            blockers.append("RAW_PROBE_SCHEMA_INVALID")
        if raw.get("provider") != PROVIDER:
            blockers.append("RAW_PROBE_PROVIDER_MISMATCH")
        if raw.get("compatibility_mode") != "EXPLICIT_PROVIDER_COMPATIBILITY":
            blockers.append("RAW_PROBE_COMPATIBILITY_MODE_INVALID")
        if raw.get("dev_hub_protocol_baseline") != "2026-07-28":
            blockers.append("DEV_HUB_PROTOCOL_BASELINE_INVALID")
        if raw.get("upstream_protocol_negotiated") != "2025-11-25":
            blockers.append("UPSTREAM_PROTOCOL_NEGOTIATION_INVALID")
        promotion = raw.get("promotion") if isinstance(raw.get("promotion"), dict) else {}
        if promotion.get("eligible_for_compat_pilot") is not True:
            blockers.extend(str(x) for x in (promotion.get("blockers") or ["RAW_PROBE_NOT_HEALTHY"]))
        checks = raw.get("checks") if isinstance(raw.get("checks"), dict) else {}
        required_checks = ["legacy_initialize", "tools_list", "navigate", "snapshot", "console", "network", "close", "deny_boundary"]
        for key in required_checks:
            item = checks.get(key)
            if not isinstance(item, dict) or item.get("pass") is not True:
                blockers.append(f"RAW_CHECK_NOT_PASS:{key}")
        if set(raw.get("called_tools") or []) != {
            "browser_navigate", "browser_snapshot", "browser_console_messages", "browser_network_requests", "browser_close"
        }:
            blockers.append("SAFE_TOOL_SEQUENCE_INVALID")
        if set(raw.get("called_tools") or []) & set(raw.get("deny_policy") or []):
            blockers.append("DENIED_TOOL_CALLED")
        if raw.get("credentials_used") is not False or raw.get("production_target") is not False or raw.get("vps_modified") is not False:
            blockers.append("SANDBOX_BOUNDARY_INVALID")

    if proc.returncode != 0 and not blockers:
        blockers.append(f"RAW_PROBE_PROCESS_FAILED:{proc.returncode}")

    blockers = sorted(set(blockers))
    state = "HEALTHY" if not blockers else "UNAVAILABLE"
    basis = {
        "provider": PROVIDER,
        "state": state,
        "package_version": args.package_version,
        "browser_version": args.browser_version,
        "raw_evidence_digest": raw.get("evidence_digest"),
        "blockers": blockers,
    }
    payload = {
        "schema": SCHEMA,
        "provider": PROVIDER,
        "state": state,
        "source": "playwright-mcp-independent-provider-specific-probe",
        "checked_at": now_iso(),
        "latency_ms": None,
        "reason": "healthy" if not blockers else ";".join(blockers),
        "details": {
            "independent_from_adapter_execution": True,
            "execution_surface": "github-actions-ephemeral",
            "package": "@playwright/mcp",
            "package_version": args.package_version,
            "browser_version": args.browser_version,
            "dev_hub_protocol_baseline": "2026-07-28",
            "upstream_protocol": "2025-11-25",
            "compatibility_mode": "EXPLICIT_PROVIDER_COMPATIBILITY",
            "safe_inspection": True,
            "credentials_used": False,
            "production_target": False,
            "vps_modified": False,
            "raw_evidence_digest": raw.get("evidence_digest"),
            "blockers": blockers,
        },
        "evidence_digest": digest(basis),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"PROVIDER_PROBE_RESULT={args.output}")
    print(f"PROVIDER={PROVIDER}")
    print(f"STATE={state}")
    for blocker in blockers:
        print(f"BLOCKER={blocker}")
    return 0 if not blockers else 2


if __name__ == "__main__":
    raise SystemExit(main())
