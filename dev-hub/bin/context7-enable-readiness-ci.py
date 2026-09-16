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
WORK = Path(os.environ.get("CONTEXT7_ENABLE_WORKDIR", "/tmp/context7-enable-readiness"))
ADAPTER = "context7-mcp-adapter"
PROVIDER = "context7-mcp"
PROJECT = "chacha-dev-hub"
TASK_ID = "context7-mcp-readonly-repeatability"


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
    path = WORK / f"direct-probe-{index}.json"
    env = os.environ.copy()
    env["EVIDENCE_PATH"] = str(path)
    proc = subprocess.run(
        [sys.executable, "dev-hub/bin/context7-mcp-direct-probe.py"],
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise SystemExit(f"CONTEXT7_DIRECT_PROBE_FAILED:{index}:rc={proc.returncode}:stderr={proc.stderr[-1000:]}")
    value = load(path)
    if value.get("promotion", {}).get("eligible_for_pilot") is not True:
        raise SystemExit(f"CONTEXT7_DIRECT_PROBE_NOT_HEALTHY:{index}")
    return path, value


def task_result(index: int, probe_path: Path, probe: dict) -> Path:
    observed_at = str(probe.get("observed_at") or "")
    if not observed_at:
        raise SystemExit(f"CONTEXT7_PROBE_TIMESTAMP_MISSING:{index}")
    checks = probe.get("checks") or {}
    summary = {
        "server_discover": (checks.get("server_discover") or {}).get("http_status"),
        "tools_list": (checks.get("tools_list") or {}).get("http_status"),
        "resolve_library_id": (checks.get("resolve_library_id") or {}).get("http_status"),
        "query_docs": (checks.get("query_docs") or {}).get("http_status"),
    }
    if any(v != 200 for v in summary.values()):
        raise SystemExit(f"CONTEXT7_PROBE_HTTP_NOT_OK:{index}:{summary}")
    result = {
        "schema": "chacha.dev/task-result/v1",
        "project": PROJECT,
        "task_id": TASK_ID,
        "status": "OK",
        "producer": ADAPTER,
        "observed_at": observed_at,
        "summary": f"Context7 direct MCP read-only repeatability sample {index} passed server/discover, tools/list and both allowed tools.",
        "evidence": [
            {
                "kind": "report",
                "source": f"context7-direct-probe-{index}",
                "digest": sha256_file(probe_path),
                "details": {
                    "protocol_version": probe.get("protocol_version"),
                    "anonymous": probe.get("anonymous"),
                    "credentials_used": probe.get("credentials_used"),
                    "http_statuses": summary,
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
    now = datetime.now(timezone.utc).isoformat()
    health = {
        "schema": "chacha.dev/provider-health-snapshot/v1",
        "observed_at": now,
        "providers": {
            PROVIDER: {
                "state": "HEALTHY",
                "source": "context7-enable-readiness-direct-probes",
                "checked_at": now,
                "latency_ms": None,
                "reason": "Three consecutive direct MCP read-only probes succeeded.",
                "details": {
                    "sample_count": len(probes),
                    "protocol_version": probes[-1].get("protocol_version") if probes else None,
                    "server_discover": "PASS",
                    "tools_list": "PASS",
                    "resolve_library_id": "PASS",
                    "query_docs": "PASS",
                },
            }
        },
    }
    path = WORK / "provider-health.json"
    save(path, health)
    return path


def main() -> int:
    WORK.mkdir(parents=True, exist_ok=True)
    probes: list[dict] = []
    results: list[Path] = []
    for index in range(1, 4):
        probe_path, probe = run_probe(index)
        probes.append(probe)
        results.append(task_result(index, probe_path, probe))
        if index < 3:
            time.sleep(1.1)

    if len({load(p)["observed_at"] for p in results}) != 3:
        raise SystemExit("CONTEXT7_REPEATABILITY_TIMESTAMPS_NOT_DISTINCT")
    if len({sha256_file(p) for p in results}) != 3:
        raise SystemExit("CONTEXT7_REPEATABILITY_RESULTS_NOT_DISTINCT")

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
        raise SystemExit(f"CONTEXT7_ENABLE_READINESS_FAILED:rc={proc.returncode}:stderr={proc.stderr[-1000:]}")

    receipt = load(readiness_dir / "enablement-readiness.json")
    if receipt.get("status") != "READY_FOR_ENABLEMENT":
        raise SystemExit(f"CONTEXT7_NOT_READY:{receipt.get('blockers')}")
    if receipt.get("promotion_eligible") is not True:
        raise SystemExit("CONTEXT7_PROMOTION_PLAN_NOT_ELIGIBLE")
    if receipt.get("registry_mutated") is not False:
        raise SystemExit("CONTEXT7_READINESS_MUTATED_REGISTRY")
    if receipt.get("blockers") != []:
        raise SystemExit(f"CONTEXT7_ENABLEMENT_BLOCKERS:{receipt.get('blockers')}")

    manifest = {
        "schema": "chacha.dev/context7-enable-readiness-ci/v1",
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
        "observed_at": datetime.now(timezone.utc).isoformat(),
    }
    save(WORK / "manifest.json", manifest)
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
