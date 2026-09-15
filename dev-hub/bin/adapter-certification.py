#!/usr/bin/env python3
"""ChaCha DEV HUB Adapter Certification Evidence V1.

Transforms real static/runtime contract results plus a successful sandbox task
result into chacha.dev/adapter-promotion-evidence/v1. It executes no adapter,
does not mutate the registry, and cannot grant approvals.
"""
from __future__ import annotations

import argparse
import ipaddress
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

CONTRACT_REPORT_SCHEMA = "chacha.dev/adapter-contract-report/v1"
DISPATCH_SCHEMA = "chacha.dev/dispatch-envelope/v1"
TASK_RESULT_SCHEMA = "chacha.dev/task-result/v1"
PROMOTION_EVIDENCE_SCHEMA = "chacha.dev/adapter-promotion-evidence/v1"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit(f"FILE_NOT_FOUND={path}")
    except json.JSONDecodeError as exc:
        raise SystemExit(f"JSON_INVALID={path}:{exc.lineno}:{exc.colno}:{exc.msg}")
    if not isinstance(value, dict):
        raise SystemExit(f"JSON_ROOT_NOT_OBJECT={path}")
    return value


def save(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def loopback_host(host: str | None) -> bool:
    if not host:
        return False
    normalized = host.lower().rstrip(".")
    if normalized == "localhost":
        return True
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False


def evidence_item(status: str, source: str, details: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": status,
        "source": source,
        "observed_at": now_iso(),
        "details": details,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Derive adapter promotion evidence from certification artifacts")
    parser.add_argument("--adapter", required=True)
    parser.add_argument("--contract-report", required=True, type=Path)
    parser.add_argument("--fixture", required=True, type=Path)
    parser.add_argument("--task-result", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    contract = load(args.contract_report)
    fixture = load(args.fixture)
    task_result = load(args.task_result)

    if contract.get("schema") != CONTRACT_REPORT_SCHEMA:
        raise SystemExit(f"CONTRACT_REPORT_SCHEMA_INVALID={contract.get('schema')}")
    if fixture.get("schema") != DISPATCH_SCHEMA:
        raise SystemExit(f"FIXTURE_SCHEMA_INVALID={fixture.get('schema')}")
    if task_result.get("schema") != TASK_RESULT_SCHEMA:
        raise SystemExit(f"TASK_RESULT_SCHEMA_INVALID={task_result.get('schema')}")

    static = contract.get("static") or {}
    static_ok = static.get("status") == "PASS" and int(static.get("failures") or 0) == 0

    runtime_matches = [
        item for item in (contract.get("runtime") or [])
        if isinstance(item, dict) and item.get("adapter") == args.adapter
    ]
    runtime_ok = bool(runtime_matches) and all(item.get("status") == "PASS" for item in runtime_matches)

    task = fixture.get("task") if isinstance(fixture.get("task"), dict) else {}
    identity_ok = (
        task_result.get("project") == fixture.get("project")
        and task_result.get("task_id") == task.get("id")
        and task_result.get("producer") == args.adapter
    )
    verification = task_result.get("verification") if isinstance(task_result.get("verification"), dict) else {}
    result_ok = task_result.get("status") == "OK" and identity_ok and verification.get("status") == "UNVERIFIED"

    metadata = fixture.get("metadata") if isinstance(fixture.get("metadata"), dict) else {}
    smoke = metadata.get("http_smoke") if isinstance(metadata.get("http_smoke"), dict) else {}
    cert = metadata.get("certification") if isinstance(metadata.get("certification"), dict) else {}
    parsed = urlsplit(str(smoke.get("url") or ""))
    policy_context = fixture.get("policy_context") if isinstance(fixture.get("policy_context"), dict) else {}
    sandbox_ok = (
        cert.get("sandbox") is True
        and cert.get("network_scope") == "loopback-only"
        and loopback_host(parsed.hostname)
        and task.get("permission") == "read"
        and policy_context.get("human_approval_required") is False
    )

    evidence = {
        "static-contract-pass": evidence_item(
            "PASS" if static_ok else "FAIL",
            f"adapter-contract-report:{args.contract_report}",
            {"static_status": static.get("status"), "failures": static.get("failures")},
        ),
        "runtime-contract-pass": evidence_item(
            "PASS" if runtime_ok and result_ok else "FAIL",
            f"adapter-runtime:{args.contract_report}",
            {
                "runtime_contract_pass": runtime_ok,
                "task_result_status": task_result.get("status"),
                "identity_match": identity_ok,
                "producer": task_result.get("producer"),
                "self_verified": verification.get("status") != "UNVERIFIED",
            },
        ),
        "sandbox-only": evidence_item(
            "PASS" if sandbox_ok else "FAIL",
            f"dispatch-fixture:{args.fixture}",
            {
                "sandbox_declared": cert.get("sandbox"),
                "network_scope": cert.get("network_scope"),
                "host_is_loopback": loopback_host(parsed.hostname),
                "permission": task.get("permission"),
                "human_approval_required": policy_context.get("human_approval_required"),
            },
        ),
    }

    output = {
        "schema": PROMOTION_EVIDENCE_SCHEMA,
        "adapter": args.adapter,
        "observed_at": now_iso(),
        "evidence": evidence,
        "approvals": [],
        "notes": [
            "Evidence derived from contract harness + concrete sandbox execution.",
            "No adapter status was changed and no approval was generated."
        ],
    }
    save(args.output, output)
    failed = [key for key, item in evidence.items() if item.get("status") != "PASS"]
    print(f"ADAPTER_CERTIFICATION_EVIDENCE={args.output}")
    print(f"ADAPTER={args.adapter}")
    print(f"EVIDENCE_STATUS={'PASS' if not failed else 'FAIL'}")
    for key in failed:
        print(f"EVIDENCE_FAILED={key}")
    return 0 if not failed else 2


if __name__ == "__main__":
    raise SystemExit(main())
