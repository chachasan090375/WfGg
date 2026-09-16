#!/usr/bin/env python3
"""ChaCha DEV HUB Adapter Enablement Readiness V1.

Prepares PILOT->ENABLED promotion without mutating provider-adapters.v1.json.
It hardens repeatability preconditions, derives canonical enablement evidence,
and asks adapter-promotion.py for an eligibility plan.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA = "chacha.dev/adapter-enable-readiness/v1"
TASK_RESULT_SCHEMA = "chacha.dev/task-result/v1"
REGISTRY_SCHEMA = "chacha.dev/provider-adapters/v1"


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


def digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def file_digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def execution_kinds(registry: dict[str, Any], adapter: str) -> set[str]:
    return {
        str(item.get("execution"))
        for item in (registry.get("providers") or {}).values()
        if isinstance(item, dict) and item.get("adapter") == adapter and item.get("execution")
    }


def run(argv: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        cwd=str(REPO_ROOT),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
        shell=False,
        env=os.environ.copy(),
    )


def validate_results(adapter: str, paths: list[Path]) -> tuple[list[str], list[dict[str, Any]]]:
    blockers: list[str] = []
    records: list[dict[str, Any]] = []
    identities: set[tuple[str, str]] = set()
    observed: set[str] = set()
    digests: set[str] = set()

    if len(paths) < 3:
        blockers.append(f"REPEATABILITY_RESULT_COUNT_INSUFFICIENT:{len(paths)}")

    for path in paths:
        value = load(path)
        verification = value.get("verification") if isinstance(value.get("verification"), dict) else {}
        evidence = value.get("evidence") if isinstance(value.get("evidence"), list) else []
        item_digest = digest(value)
        project = str(value.get("project") or "")
        task_id = str(value.get("task_id") or "")
        observed_at = str(value.get("observed_at") or "")
        item_blockers: list[str] = []

        if value.get("schema") != TASK_RESULT_SCHEMA:
            item_blockers.append("TASK_RESULT_SCHEMA_INVALID")
        if value.get("producer") != adapter:
            item_blockers.append("TASK_RESULT_PRODUCER_MISMATCH")
        if value.get("status") != "OK":
            item_blockers.append(f"TASK_RESULT_NOT_OK:{value.get('status')}")
        if verification.get("status") != "UNVERIFIED":
            item_blockers.append(f"TASK_RESULT_VERIFICATION_INVALID:{verification.get('status')}")
        if not project or not task_id:
            item_blockers.append("TASK_RESULT_IDENTITY_MISSING")
        if not observed_at:
            item_blockers.append("TASK_RESULT_OBSERVED_AT_MISSING")
        if not evidence:
            item_blockers.append("TASK_RESULT_EVIDENCE_MISSING")

        identities.add((project, task_id))
        if observed_at in observed:
            item_blockers.append("TASK_RESULT_OBSERVED_AT_DUPLICATE")
        observed.add(observed_at)
        if item_digest in digests:
            item_blockers.append("TASK_RESULT_DIGEST_DUPLICATE")
        digests.add(item_digest)

        blockers.extend(f"{path}:{x}" for x in item_blockers)
        records.append({
            "path": str(path),
            "project": project,
            "task_id": task_id,
            "observed_at": observed_at,
            "digest": item_digest,
            "status": value.get("status"),
            "verification_status": verification.get("status"),
            "evidence_count": len(evidence),
            "valid": not item_blockers,
        })

    if len(identities) != 1:
        blockers.append(f"REPEATABILITY_TASK_IDENTITY_NOT_STABLE:{len(identities)}")
    if len(observed) < 3:
        blockers.append(f"REPEATABILITY_DISTINCT_TIMESTAMPS_INSUFFICIENT:{len(observed)}")
    if len(digests) < 3:
        blockers.append(f"REPEATABILITY_DISTINCT_RESULTS_INSUFFICIENT:{len(digests)}")
    return sorted(set(blockers)), records


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare PILOT->ENABLED adapter promotion readiness")
    parser.add_argument("--registry", type=Path, default=Path("dev-hub/config/provider-adapters.v1.json"))
    parser.add_argument("--adapter", required=True)
    parser.add_argument("--provider", required=True)
    parser.add_argument("--result", action="append", type=Path, default=[])
    parser.add_argument("--health", required=True, type=Path)
    parser.add_argument("--rollbacks", type=Path, default=Path("dev-hub/config/adapter-rollbacks.v1.json"))
    parser.add_argument("--work-dir", required=True, type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    registry = load(args.registry)
    blockers: list[str] = []
    if registry.get("schema") != REGISTRY_SCHEMA:
        blockers.append(f"REGISTRY_SCHEMA_INVALID:{registry.get('schema')}")

    entry = (registry.get("adapters") or {}).get(args.adapter)
    if not isinstance(entry, dict):
        blockers.append("ADAPTER_NOT_REGISTERED")
        current_status = "UNKNOWN"
        executable = None
    else:
        current_status = str(entry.get("status") or "UNKNOWN")
        executable = entry.get("executable")
        if current_status != "PILOT":
            blockers.append(f"ADAPTER_STATUS_NOT_PILOT:{current_status}")

    kinds = execution_kinds(registry, args.adapter)
    bound = (registry.get("providers") or {}).get(args.provider)
    if not isinstance(bound, dict) or bound.get("adapter") != args.adapter:
        blockers.append("PROVIDER_ADAPTER_BINDING_MISMATCH")

    executable_digest = None
    if "vps" in kinds:
        if not isinstance(executable, str) or not Path(executable).is_absolute():
            blockers.append("PILOT_EXECUTABLE_INVALID")
        else:
            p = Path(executable)
            if not p.is_file():
                blockers.append("PILOT_EXECUTABLE_MISSING")
            elif not os.access(p, os.X_OK):
                blockers.append("PILOT_EXECUTABLE_NOT_EXECUTABLE")
            else:
                executable_digest = file_digest(p)

    result_blockers, records = validate_results(args.adapter, args.result)
    blockers.extend(result_blockers)

    args.work_dir.mkdir(parents=True, exist_ok=True)
    evidence_path = args.work_dir / "enablement-evidence.json"
    plan_path = args.work_dir / "enablement-promotion-plan.json"
    receipt_path = args.work_dir / "enablement-readiness.json"

    process_records: list[dict[str, Any]] = []
    promotion_plan: dict[str, Any] | None = None

    if not blockers:
        cmd = [
            "python3", "dev-hub/bin/adapter-enablement-evidence.py",
            "--adapter", args.adapter,
            "--provider", args.provider,
            "--health", str(args.health),
            "--rollbacks", str(args.rollbacks),
            "--output", str(evidence_path),
        ]
        for path in args.result:
            cmd += ["--result", str(path)]
        proc = run(cmd)
        process_records.append({"stage": "enablement-evidence", "exit_code": proc.returncode, "stdout": proc.stdout[-4096:], "stderr": proc.stderr[-4096:]})
        if proc.returncode != 0:
            blockers.append("ENABLEMENT_EVIDENCE_FAILED")

    if not blockers:
        cmd = [
            "python3", "dev-hub/bin/adapter-promotion.py",
            "--registry", str(args.registry),
            "--evidence", str(evidence_path),
            "--json", "plan",
            "--adapter", args.adapter,
            "--target", "ENABLED",
        ]
        proc = run(cmd)
        process_records.append({"stage": "promotion-plan", "exit_code": proc.returncode, "stdout": proc.stdout[-4096:], "stderr": proc.stderr[-4096:]})
        try:
            promotion_plan = json.loads(proc.stdout)
        except json.JSONDecodeError:
            promotion_plan = {"eligible": False, "blockers": ["PROMOTION_PLAN_NOT_JSON"]}
        save(plan_path, promotion_plan)
        if proc.returncode != 0 or promotion_plan.get("eligible") is not True:
            for item in promotion_plan.get("blockers") or []:
                blockers.append(f"PROMOTION:{item}")
            if not promotion_plan.get("blockers"):
                blockers.append("PROMOTION_NOT_ELIGIBLE")

    evidence_digest = digest(load(evidence_path)) if evidence_path.exists() else None
    plan_digest = digest(promotion_plan) if promotion_plan is not None else None
    receipt = {
        "schema": SCHEMA,
        "adapter": args.adapter,
        "provider": args.provider,
        "current_status": current_status,
        "target_status": "ENABLED",
        "status": "READY_FOR_ENABLEMENT" if not blockers else "BLOCKED",
        "registry_mutated": False,
        "execution_kinds": sorted(kinds),
        "executable": executable,
        "executable_digest": executable_digest,
        "repeatability_results": records,
        "health_snapshot": str(args.health),
        "health_snapshot_digest": digest(load(args.health)),
        "rollback_registry": str(args.rollbacks),
        "rollback_registry_digest": digest(load(args.rollbacks)),
        "enablement_evidence": str(evidence_path) if evidence_path.exists() else None,
        "enablement_evidence_digest": evidence_digest,
        "promotion_plan": str(plan_path) if promotion_plan is not None else None,
        "promotion_plan_digest": plan_digest,
        "promotion_eligible": bool(promotion_plan and promotion_plan.get("eligible") is True),
        "blockers": sorted(set(blockers)),
        "processes": process_records,
        "observed_at": now_iso(),
    }
    save(receipt_path, receipt)

    if args.json:
        print(json.dumps(receipt, indent=2, ensure_ascii=False))
    else:
        print(f"ADAPTER={args.adapter}")
        print(f"PROVIDER={args.provider}")
        print(f"STATUS={receipt['status']}")
        print(f"PROMOTION_ELIGIBLE={'YES' if receipt['promotion_eligible'] else 'NO'}")
        print(f"READINESS_RECEIPT={receipt_path}")
        for blocker in receipt["blockers"]:
            print(f"BLOCKER={blocker}")
    return 0 if not blockers else 2


if __name__ == "__main__":
    raise SystemExit(main())
