#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORK = Path(os.environ.get("PLAYWRIGHT_ENABLE_WORKDIR", "/tmp/playwright-mcp-strict-enable-readiness"))
ADAPTER = "playwright-mcp-adapter"
PROVIDER = "playwright-mcp"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def save(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def digest_file(path: Path) -> str:
    h = hashlib.sha256(path.read_bytes()).hexdigest()
    return "sha256:" + h


def run_adapter(index: int, dispatch: Path) -> Path:
    output = WORK / f"task-result-{index}.json"
    stderr = WORK / f"adapter-{index}.stderr.txt"
    with dispatch.open("rb") as inp, output.open("wb") as out, stderr.open("wb") as err:
        proc = subprocess.run(
            [sys.executable, "dev-hub/adapters/playwright-mcp-adapter.py"],
            cwd=ROOT,
            stdin=inp,
            stdout=out,
            stderr=err,
            env=os.environ.copy(),
            check=False,
            timeout=180,
        )
    if proc.returncode != 0:
        raise SystemExit(f"PLAYWRIGHT_STRICT_ADAPTER_RUN_FAILED:{index}:rc={proc.returncode}")
    value = load(output)
    if value.get("schema") != "chacha.dev/task-result/v1":
        raise SystemExit(f"PLAYWRIGHT_STRICT_TASK_RESULT_SCHEMA:{index}")
    if value.get("status") != "OK":
        raise SystemExit(f"PLAYWRIGHT_STRICT_TASK_RESULT_NOT_OK:{index}:{value.get('summary')}")
    if value.get("producer") != ADAPTER:
        raise SystemExit(f"PLAYWRIGHT_STRICT_TASK_RESULT_PRODUCER:{index}")
    if (value.get("verification") or {}).get("status") != "UNVERIFIED":
        raise SystemExit(f"PLAYWRIGHT_STRICT_TASK_RESULT_TRUST:{index}")
    evidence = value.get("evidence") or []
    if len(evidence) != 1:
        raise SystemExit(f"PLAYWRIGHT_STRICT_TASK_RESULT_EVIDENCE:{index}")
    details = evidence[0].get("details") or {}
    if details.get("upstream_protocol") != "2025-11-25":
        raise SystemExit(f"PLAYWRIGHT_STRICT_UPSTREAM_PROTOCOL:{index}")
    if details.get("production_target") is not False:
        raise SystemExit(f"PLAYWRIGHT_STRICT_PRODUCTION_TARGET:{index}")
    if details.get("workspace_write") is not False:
        raise SystemExit(f"PLAYWRIGHT_STRICT_WORKSPACE_WRITE:{index}")
    expected = [
        "browser_navigate", "browser_snapshot", "browser_console_messages",
        "browser_network_requests", "browser_close",
    ]
    if details.get("called_tools") != expected:
        raise SystemExit(f"PLAYWRIGHT_STRICT_TOOL_SEQUENCE:{index}")
    if "?" in str(evidence[0].get("source") or ""):
        raise SystemExit(f"PLAYWRIGHT_STRICT_QUERY_LEAK:{index}")
    return output


def write_health(results: list[Path]) -> Path:
    checked = now_iso()
    health = {
        "schema": "chacha.dev/provider-health-snapshot/v1",
        "observed_at": checked,
        "providers": {
            PROVIDER: {
                "state": "HEALTHY",
                "source": "playwright-mcp-strict-real-adapter-repeatability",
                "checked_at": checked,
                "latency_ms": None,
                "reason": "Three consecutive real dispatch-envelope to task-result Playwright MCP adapter runs succeeded on isolated ephemeral runtime.",
                "details": {
                    "sample_count": len(results),
                    "adapter": ADAPTER,
                    "runtime_surface": "github-actions-ephemeral",
                    "package_version": os.environ.get("CHACHA_PLAYWRIGHT_MCP_PACKAGE_VERSION", "unknown"),
                    "dev_hub_protocol_baseline": "2026-07-28",
                    "upstream_protocol": "2025-11-25",
                    "compatibility_mode": "EXPLICIT_PROVIDER_COMPATIBILITY",
                    "generic_legacy_fallback": False,
                    "unsafe_tool_invoked": False,
                    "production_target": False,
                    "task_result_digests": [digest_file(p) for p in results],
                },
            }
        },
    }
    path = WORK / "provider-health.json"
    save(path, health)
    return path


def main() -> int:
    dispatch_raw = os.environ.get("PLAYWRIGHT_STRICT_DISPATCH_FILE", "")
    if not dispatch_raw:
        raise SystemExit("PLAYWRIGHT_STRICT_DISPATCH_FILE_MISSING")
    dispatch = Path(dispatch_raw)
    if not dispatch.is_file():
        raise SystemExit("PLAYWRIGHT_STRICT_DISPATCH_FILE_INVALID")

    required_env = [
        "CHACHA_PLAYWRIGHT_MCP_SERVER",
        "CHACHA_PLAYWRIGHT_MCP_WORKDIR",
        "CHACHA_PLAYWRIGHT_ALLOWED_ORIGIN",
        "CHACHA_PLAYWRIGHT_TARGET_CLASS",
        "CHACHA_PLAYWRIGHT_MCP_PACKAGE_VERSION",
    ]
    missing = [name for name in required_env if not os.environ.get(name)]
    if missing:
        raise SystemExit("PLAYWRIGHT_STRICT_ENV_MISSING:" + ",".join(missing))

    registry = load(ROOT / "dev-hub/config/provider-adapters.v1.json")
    adapter = registry["adapters"][ADAPTER]
    if adapter.get("status") != "PILOT":
        raise SystemExit(f"PLAYWRIGHT_STRICT_NOT_PILOT:{adapter.get('status')}")
    if adapter.get("supports") != ["read"] or adapter.get("executable") is not None:
        raise SystemExit("PLAYWRIGHT_STRICT_ADAPTER_BOUNDARY_DRIFT")

    WORK.mkdir(parents=True, exist_ok=True)
    results: list[Path] = []
    for index in (1, 2, 3):
        results.append(run_adapter(index, dispatch))
        if index != 3:
            time.sleep(1.1)

    values = [load(p) for p in results]
    identities = {(v.get("project"), v.get("task_id")) for v in values}
    observed = {v.get("observed_at") for v in values}
    digests = {digest_file(p) for p in results}
    if len(identities) != 1:
        raise SystemExit("PLAYWRIGHT_STRICT_TASK_IDENTITY_DRIFT")
    if len(observed) != 3:
        raise SystemExit("PLAYWRIGHT_STRICT_TIMESTAMPS_NOT_DISTINCT")
    if len(digests) != 3:
        raise SystemExit("PLAYWRIGHT_STRICT_RESULTS_NOT_DISTINCT")

    health = write_health(results)
    readiness = WORK / "readiness"
    cmd = [
        sys.executable, "dev-hub/bin/adapter-enable-readiness.py",
        "--registry", "dev-hub/config/provider-adapters.v1.json",
        "--adapter", ADAPTER,
        "--provider", PROVIDER,
        "--health", str(health),
        "--rollbacks", "dev-hub/config/adapter-rollbacks.v1.json",
        "--work-dir", str(readiness),
        "--json",
    ]
    for result in results:
        cmd.extend(["--result", str(result)])
    proc = subprocess.run(cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
    (WORK / "adapter-enable-readiness.stdout.json").write_text(proc.stdout, encoding="utf-8")
    (WORK / "adapter-enable-readiness.stderr.txt").write_text(proc.stderr, encoding="utf-8")
    if proc.returncode != 0:
        raise SystemExit(f"PLAYWRIGHT_STRICT_ENABLE_READINESS_FAILED:rc={proc.returncode}:{proc.stderr[-1000:]}")

    receipt = load(readiness / "enablement-readiness.json")
    evidence = load(readiness / "enablement-evidence.json")
    plan = load(readiness / "enablement-promotion-plan.json")
    if receipt.get("status") != "READY_FOR_ENABLEMENT" or receipt.get("promotion_eligible") is not True:
        raise SystemExit(f"PLAYWRIGHT_STRICT_NOT_READY:{receipt.get('blockers')}")
    if receipt.get("registry_mutated") is not False:
        raise SystemExit("PLAYWRIGHT_STRICT_READINESS_MUTATED_REGISTRY")
    if receipt.get("blockers") != [] or plan.get("blockers") != [] or plan.get("eligible") is not True:
        raise SystemExit("PLAYWRIGHT_STRICT_READINESS_BLOCKERS")
    for label in ("repeatable-pass", "provider-health-pass", "rollback-defined"):
        if (evidence.get("evidence") or {}).get(label, {}).get("status") != "PASS":
            raise SystemExit(f"PLAYWRIGHT_STRICT_ENABLEMENT_EVIDENCE_FAIL:{label}")

    final_registry = load(ROOT / "dev-hub/config/provider-adapters.v1.json")
    if final_registry["adapters"][ADAPTER]["status"] != "PILOT":
        raise SystemExit("PLAYWRIGHT_STRICT_CANONICAL_STATUS_CHANGED")

    manifest = {
        "schema": "chacha.dev/playwright-mcp-strict-enable-readiness/v1",
        "adapter": ADAPTER,
        "provider": PROVIDER,
        "status": "READY_FOR_ENABLEMENT",
        "promotion_eligible": True,
        "registry_mutated": False,
        "sample_count": 3,
        "task_result_digests": [digest_file(p) for p in results],
        "health_snapshot": str(health),
        "readiness_receipt": str(readiness / "enablement-readiness.json"),
        "enablement_evidence": str(readiness / "enablement-evidence.json"),
        "promotion_plan": str(readiness / "enablement-promotion-plan.json"),
        "observed_at": now_iso(),
    }
    save(WORK / "manifest.json", manifest)
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
