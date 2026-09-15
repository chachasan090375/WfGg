#!/usr/bin/env python3
"""ChaCha DEV HUB Adapter Contract Test Harness V1.

Performs static registry checks and optional sandbox runtime contract tests.
It never promotes adapter status automatically.
"""
from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REGISTRY_SCHEMA = "chacha.dev/provider-adapters/v1"
POLICY_SCHEMA = "chacha.dev/adapter-contract/v1"
INPUT_SCHEMA = "chacha.dev/dispatch-envelope/v1"
OUTPUT_SCHEMA = "chacha.dev/task-result/v1"
KNOWN_STATUSES = {"DESIGNED", "CONTRACT_OK", "PILOT", "ENABLED", "DEGRADED", "DISABLED", "RETIRED"}


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


def check(checks: list[dict[str, str]], cid: str, ok: bool, detail: str) -> None:
    checks.append({"id": cid, "status": "PASS" if ok else "FAIL", "detail": detail})


def static_checks(registry: dict[str, Any], policy: dict[str, Any]) -> list[dict[str, str]]:
    checks: list[dict[str, str]] = []
    providers = registry.get("providers") or {}
    adapters = registry.get("adapters") or {}
    known_permissions = set(policy.get("known_permissions") or [])
    known_exec = set(policy.get("known_execution_kinds") or [])

    protocol = registry.get("protocol") or {}
    check(checks, "protocol-input-schema", protocol.get("input") == INPUT_SCHEMA, str(protocol.get("input")))
    check(checks, "protocol-output-schema", protocol.get("output") == OUTPUT_SCHEMA, str(protocol.get("output")))
    check(checks, "protocol-shell-disabled", protocol.get("shell") is False, f"shell={protocol.get('shell')}")

    for pid, item in sorted(providers.items()):
        adapter_id = item.get("adapter") if isinstance(item, dict) else None
        check(checks, f"provider:{pid}:adapter-exists", adapter_id in adapters, f"adapter={adapter_id}")
        execution = item.get("execution") if isinstance(item, dict) else None
        check(checks, f"provider:{pid}:execution-known", execution in known_exec, f"execution={execution}")

    for aid, item in sorted(adapters.items()):
        if not isinstance(item, dict):
            check(checks, f"adapter:{aid}:object", False, "adapter entry is not object")
            continue
        status = item.get("status")
        supports = item.get("supports") or []
        executable = item.get("executable")
        check(checks, f"adapter:{aid}:status-known", status in KNOWN_STATUSES, f"status={status}")
        check(checks, f"adapter:{aid}:supports-nonempty", isinstance(supports, list) and bool(supports), f"supports={supports}")
        unknown = sorted(set(supports) - known_permissions) if isinstance(supports, list) else ["invalid-supports"]
        check(checks, f"adapter:{aid}:permissions-known", not unknown, f"unknown={unknown}")
        if status == "DESIGNED":
            check(checks, f"adapter:{aid}:designed-no-executable", executable in {None, ""}, f"executable={executable}")
        if status in {"PILOT", "ENABLED", "DEGRADED"}:
            check(checks, f"adapter:{aid}:runtime-executable", isinstance(executable, str) and executable.startswith("/"), f"executable={executable}")
    return checks


def fixture_task_id(fixture: dict[str, Any]) -> str | None:
    direct = fixture.get("task_id")
    if isinstance(direct, str) and direct:
        return direct
    task = fixture.get("task")
    if isinstance(task, dict):
        nested = task.get("id")
        if isinstance(nested, str) and nested:
            return nested
    return None


def runtime_test(adapter_id: str, registry: dict[str, Any], policy: dict[str, Any], fixture: dict[str, Any]) -> dict[str, Any]:
    adapters = registry.get("adapters") or {}
    item = adapters.get(adapter_id)
    if not isinstance(item, dict):
        return {"adapter": adapter_id, "status": "FAIL", "detail": "adapter-not-found"}
    status = item.get("status")
    allowed = set(((policy.get("runtime") or {}).get("allow_runtime_test_statuses") or []))
    if status not in allowed:
        return {"adapter": adapter_id, "status": "SKIP", "detail": f"status-not-runtime-testable:{status}"}
    executable = item.get("executable")
    if not isinstance(executable, str) or not executable.startswith("/"):
        return {"adapter": adapter_id, "status": "FAIL", "detail": "executable-missing"}
    if fixture.get("schema") != INPUT_SCHEMA:
        return {"adapter": adapter_id, "status": "FAIL", "detail": "fixture-schema-invalid"}
    expected_task_id = fixture_task_id(fixture)
    if not expected_task_id:
        return {"adapter": adapter_id, "status": "FAIL", "detail": "fixture-task-id-missing"}
    timeout = int(((policy.get("runtime") or {}).get("default_timeout_seconds") or 30))
    limit = int(((policy.get("runtime") or {}).get("max_output_bytes") or 262144))
    try:
        proc = subprocess.run(
            [executable],
            input=json.dumps(fixture, ensure_ascii=False).encode("utf-8"),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            shell=False,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {"adapter": adapter_id, "status": "FAIL", "detail": "timeout"}
    except OSError as exc:
        return {"adapter": adapter_id, "status": "FAIL", "detail": f"start-failed:{exc}"}
    stdout = proc.stdout[:limit]
    if proc.returncode != 0:
        return {"adapter": adapter_id, "status": "FAIL", "detail": f"exit={proc.returncode}"}
    try:
        result = json.loads(stdout.decode("utf-8"))
    except Exception as exc:
        return {"adapter": adapter_id, "status": "FAIL", "detail": f"invalid-json:{exc}"}
    if not isinstance(result, dict) or result.get("schema") != OUTPUT_SCHEMA:
        return {"adapter": adapter_id, "status": "FAIL", "detail": f"result-schema={getattr(result, 'get', lambda *_: None)('schema')}"}
    if result.get("project") != fixture.get("project") or result.get("task_id") != expected_task_id:
        return {
            "adapter": adapter_id,
            "status": "FAIL",
            "detail": f"identity-mismatch:project={result.get('project')}:{fixture.get('project')}:task={result.get('task_id')}:{expected_task_id}",
        }
    return {"adapter": adapter_id, "status": "PASS", "detail": "runtime-contract-pass"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", required=True, type=Path)
    parser.add_argument("--policy", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--adapter")
    parser.add_argument("--fixture", type=Path)
    parser.add_argument("--runtime", action="store_true")
    args = parser.parse_args()

    registry, policy = load(args.registry), load(args.policy)
    if registry.get("schema") != REGISTRY_SCHEMA:
        raise SystemExit(f"REGISTRY_SCHEMA_INVALID={registry.get('schema')}")
    if policy.get("schema") != POLICY_SCHEMA:
        raise SystemExit(f"POLICY_SCHEMA_INVALID={policy.get('schema')}")

    checks = static_checks(registry, policy)
    static_failures = [c for c in checks if c["status"] == "FAIL"]
    runtime: list[dict[str, Any]] = []
    if args.runtime:
        if not args.adapter or not args.fixture:
            raise SystemExit("RUNTIME_REQUIRES_ADAPTER_AND_FIXTURE")
        runtime.append(runtime_test(args.adapter, registry, policy, load(args.fixture)))

    runtime_failures = [r for r in runtime if r.get("status") == "FAIL"]
    report = {
        "schema": "chacha.dev/adapter-contract-report/v1",
        "observed_at": now_iso(),
        "static": {
            "status": "PASS" if not static_failures else "FAIL",
            "checks": checks,
            "failures": len(static_failures),
        },
        "runtime": runtime,
        "promotion": {
            "automatic": False,
            "eligible_for_contract_ok": not static_failures,
            "eligible_for_runtime_pilot": not static_failures and bool(runtime) and not runtime_failures and all(r.get("status") == "PASS" for r in runtime),
        },
    }
    save(args.report, report)
    print(f"ADAPTER_CONTRACT_REPORT={args.report}")
    print(f"STATIC_STATUS={report['static']['status']}")
    print(f"STATIC_FAILURES={len(static_failures)}")
    if runtime:
        print(f"RUNTIME_STATUS={runtime[0]['status']}")
    print("AUTOMATIC_PROMOTION=NO")
    if static_failures or runtime_failures:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
