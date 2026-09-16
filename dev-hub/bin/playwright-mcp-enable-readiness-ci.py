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
WORK = Path(os.environ.get("PLAYWRIGHT_ENABLE_WORKDIR", "/tmp/playwright-mcp-enable-readiness"))
ADAPTER = "playwright-mcp-adapter"
PROVIDER = "playwright-mcp"
PROJECT = "chacha-dev-hub"
TASK_ID = "playwright-mcp-readonly-repeatability"

REQUIRED_ENV = [
    "PLAYWRIGHT_MCP_BIN",
    "PLAYWRIGHT_MCP_TARGET_URL",
    "PLAYWRIGHT_MCP_ALLOWED_ORIGIN",
    "PLAYWRIGHT_MCP_MARKER",
    "PLAYWRIGHT_MCP_PROBE_SCRIPT",
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def save(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def run_probe(index: int) -> tuple[Path, dict]:
    evidence_path = WORK / f"runtime-probe-{index}.json"
    output_dir = WORK / f"browser-output-{index}"
    output_dir.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["PLAYWRIGHT_MCP_EVIDENCE"] = str(evidence_path)
    env["PLAYWRIGHT_MCP_OUTPUT_DIR"] = str(output_dir)
    probe = Path(env["PLAYWRIGHT_MCP_PROBE_SCRIPT"])
    proc = subprocess.run(
        ["node", str(probe)],
        cwd=probe.parent,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
        timeout=180,
    )
    (WORK / f"runtime-probe-{index}.stdout.txt").write_text(proc.stdout, encoding="utf-8")
    (WORK / f"runtime-probe-{index}.stderr.txt").write_text(proc.stderr, encoding="utf-8")
    if proc.returncode != 0:
        raise SystemExit(f"PLAYWRIGHT_RUNTIME_PROBE_FAILED:{index}:rc={proc.returncode}:stderr={proc.stderr[-1200:]}")
    value = load(evidence_path)
    required_true = [
        "runtime_contract_pass",
        "sandbox_only_pass",
        "provisioning_pass",
        "test_origin_navigation_pass",
        "snapshot_pass",
        "eligible_for_pilot",
    ]
    for key in required_true:
        if value.get(key) is not True:
            raise SystemExit(f"PLAYWRIGHT_PROBE_CHECK_FAILED:{index}:{key}")
    if value.get("blockers") != []:
        raise SystemExit(f"PLAYWRIGHT_PROBE_BLOCKERS:{index}:{value.get('blockers')}")
    if value.get("unsafe_tool_invoked") is not False:
        raise SystemExit(f"PLAYWRIGHT_UNSAFE_TOOL_INVOKED:{index}")
    if value.get("production_target") is not False:
        raise SystemExit(f"PLAYWRIGHT_PRODUCTION_TARGET:{index}")
    if value.get("result_trust") != "UNVERIFIED":
        raise SystemExit(f"PLAYWRIGHT_RESULT_TRUST_INVALID:{index}")
    return evidence_path, value


def task_result(index: int, probe_path: Path, probe: dict) -> Path:
    observed_at = now_iso()
    result = {
        "schema": "chacha.dev/task-result/v1",
        "project": PROJECT,
        "task_id": TASK_ID,
        "status": "OK",
        "producer": ADAPTER,
        "observed_at": observed_at,
        "summary": f"Playwright MCP isolated read-only browser verification sample {index} passed navigation, snapshot, find and network observation.",
        "evidence": [
            {
                "kind": "report",
                "source": f"playwright-mcp-runtime-probe-{index}",
                "digest": sha256_file(probe_path),
                "details": {
                    "runtime_surface": probe.get("runtime_surface"),
                    "package_version": probe.get("package_version"),
                    "negotiated_era": probe.get("negotiated_era"),
                    "negotiated_protocol_version": probe.get("negotiated_protocol_version"),
                    "target_origin": probe.get("target_origin"),
                    "unsafe_tool_invoked": probe.get("unsafe_tool_invoked"),
                    "invoked_tools": probe.get("invoked_tools") or [],
                },
            }
        ],
        "verification": {
            "status": "UNVERIFIED",
            "method": "none",
            "verifier": "verification-broker-pending",
            "notes": "Producer result intentionally remains UNVERIFIED until independent verification.",
        },
    }
    path = WORK / f"task-result-{index}.json"
    save(path, result)
    return path


def write_health(probes: list[dict]) -> Path:
    now = now_iso()
    last = probes[-1]
    health = {
        "schema": "chacha.dev/provider-health-snapshot/v1",
        "observed_at": now,
        "providers": {
            PROVIDER: {
                "state": "HEALTHY",
                "source": "playwright-mcp-enable-readiness-live-probes",
                "checked_at": now,
                "latency_ms": None,
                "reason": "Three consecutive isolated Playwright MCP browser verification probes succeeded.",
                "details": {
                    "sample_count": len(probes),
                    "runtime_surface": last.get("runtime_surface"),
                    "package_version": last.get("package_version"),
                    "negotiated_era": last.get("negotiated_era"),
                    "negotiated_protocol_version": last.get("negotiated_protocol_version"),
                    "navigation": "PASS",
                    "snapshot": "PASS",
                    "find": "PASS",
                    "network_observation": "PASS",
                    "unsafe_tool_invoked": False,
                    "production_target": False,
                },
            }
        },
    }
    path = WORK / "provider-health.json"
    save(path, health)
    return path


def main() -> int:
    missing = [name for name in REQUIRED_ENV if not os.environ.get(name)]
    if missing:
        raise SystemExit("PLAYWRIGHT_ENABLE_ENV_MISSING:" + ",".join(missing))

    registry = load(ROOT / "dev-hub/config/provider-adapters.v1.json")
    status = registry.get("adapters", {}).get(ADAPTER, {}).get("status")
    if status != "PILOT":
        raise SystemExit(f"PLAYWRIGHT_NOT_PILOT:{status}")

    WORK.mkdir(parents=True, exist_ok=True)
    probes: list[dict] = []
    results: list[Path] = []
    for index in range(1, 4):
        probe_path, probe = run_probe(index)
        probes.append(probe)
        results.append(task_result(index, probe_path, probe))
        if index < 3:
            time.sleep(1.1)

    result_values = [load(p) for p in results]
    if len({r["observed_at"] for r in result_values}) != 3:
        raise SystemExit("PLAYWRIGHT_REPEATABILITY_TIMESTAMPS_NOT_DISTINCT")
    if len({sha256_file(p) for p in results}) != 3:
        raise SystemExit("PLAYWRIGHT_REPEATABILITY_RESULTS_NOT_DISTINCT")
    if any(r["verification"]["status"] != "UNVERIFIED" for r in result_values):
        raise SystemExit("PLAYWRIGHT_REPEATABILITY_TRUST_DRIFT")

    health_path = write_health(probes)
    readiness_dir = WORK / "readiness"
    cmd = [
        sys.executable,
        "dev-hub/bin/adapter-enable-readiness.py",
        "--registry", "dev-hub/config/provider-adapters.v1.json",
        "--adapter", ADAPTER,
        "--provider", PROVIDER,
        "--health", str(health_path),
        "--rollbacks", "dev-hub/config/adapter-rollbacks.v1.json",
        "--work-dir", str(readiness_dir),
        "--json",
    ]
    for path in results:
        cmd.extend(["--result", str(path)])
    proc = subprocess.run(cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
    (WORK / "adapter-enable-readiness.stdout.json").write_text(proc.stdout, encoding="utf-8")
    (WORK / "adapter-enable-readiness.stderr.txt").write_text(proc.stderr, encoding="utf-8")
    if proc.returncode != 0:
        raise SystemExit(f"PLAYWRIGHT_ENABLE_READINESS_FAILED:rc={proc.returncode}:stderr={proc.stderr[-1200:]}")

    receipt = load(readiness_dir / "enablement-readiness.json")
    if receipt.get("status") != "READY_FOR_ENABLEMENT":
        raise SystemExit(f"PLAYWRIGHT_NOT_READY:{receipt.get('blockers')}")
    if receipt.get("promotion_eligible") is not True:
        raise SystemExit("PLAYWRIGHT_PROMOTION_PLAN_NOT_ELIGIBLE")
    if receipt.get("registry_mutated") is not False:
        raise SystemExit("PLAYWRIGHT_READINESS_MUTATED_REGISTRY")
    if receipt.get("blockers") != []:
        raise SystemExit(f"PLAYWRIGHT_ENABLEMENT_BLOCKERS:{receipt.get('blockers')}")

    final_registry = load(ROOT / "dev-hub/config/provider-adapters.v1.json")
    if final_registry.get("adapters", {}).get(ADAPTER, {}).get("status") != "PILOT":
        raise SystemExit("PLAYWRIGHT_READINESS_CHANGED_CANONICAL_STATUS")

    manifest = {
        "schema": "chacha.dev/playwright-mcp-enable-readiness-ci/v1",
        "adapter": ADAPTER,
        "provider": PROVIDER,
        "status": "READY_FOR_ENABLEMENT",
        "promotion_eligible": True,
        "registry_mutated": False,
        "task_results": [str(p) for p in results],
        "health_snapshot": str(health_path),
        "readiness_receipt": str(readiness_dir / "enablement-readiness.json"),
        "enablement_evidence": str(readiness_dir / "enablement-evidence.json"),
        "promotion_plan": str(readiness_dir / "enablement-promotion-plan.json"),
        "observed_at": now_iso(),
    }
    save(WORK / "manifest.json", manifest)
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
