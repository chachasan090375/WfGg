#!/usr/bin/env python3
"""ChaCha DEV HUB Adapter Enablement Evidence V1.

Derives the evidence required for PILOT->ENABLED from repeated concrete task
results, normalized provider health, and a machine-readable rollback plan.
It never mutates provider-adapters.v1.json and never creates human approval.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

POLICY_SCHEMA = "chacha.dev/adapter-enablement/v1"
TASK_RESULT_SCHEMA = "chacha.dev/task-result/v1"
HEALTH_SCHEMA = "chacha.dev/provider-health-snapshot/v1"
ROLLBACK_SCHEMA = "chacha.dev/adapter-rollbacks/v1"
OUTPUT_SCHEMA = "chacha.dev/adapter-promotion-evidence/v1"


def now() -> datetime:
    return datetime.now(timezone.utc)


def now_iso() -> str:
    return now().isoformat()


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


def parse_time(value: str) -> datetime | None:
    try:
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            return None
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def evidence_item(status: str, source: str, details: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": status,
        "source": source,
        "observed_at": now_iso(),
        "details": details,
    }


def evaluate_repeatability(adapter: str, paths: list[Path], policy: dict[str, Any]) -> dict[str, Any]:
    cfg = policy.get("repeatability") or {}
    minimum = int(cfg.get("minimum_successful_runs") or 3)
    required_status = str(cfg.get("required_task_status") or "OK")
    required_verification = str(cfg.get("required_verification_status") or "UNVERIFIED")
    require_distinct = bool(cfg.get("distinct_observed_at_required", True))

    checks: list[dict[str, Any]] = []
    observed_times: set[str] = set()
    signatures: list[str] = []
    passed = 0
    for path in paths:
        value = load(path)
        verification = value.get("verification") if isinstance(value.get("verification"), dict) else {}
        observed = str(value.get("observed_at") or "")
        valid_time = parse_time(observed) is not None
        ok = (
            value.get("schema") == TASK_RESULT_SCHEMA
            and value.get("producer") == adapter
            and value.get("status") == required_status
            and verification.get("status") == required_verification
            and valid_time
        )
        if ok:
            passed += 1
            observed_times.add(observed)
        signature_basis = {
            "status": value.get("status"),
            "producer": value.get("producer"),
            "summary": value.get("summary"),
            "evidence": value.get("evidence") or [],
            "outputs": value.get("outputs") or [],
        }
        signatures.append(digest(signature_basis))
        checks.append({
            "path": str(path),
            "ok": ok,
            "status": value.get("status"),
            "producer": value.get("producer"),
            "verification_status": verification.get("status"),
            "observed_at": observed,
            "digest": digest(value),
        })

    enough = passed >= minimum
    distinct = len(observed_times) >= minimum if require_distinct else True
    status = "PASS" if enough and distinct else "FAIL"
    return evidence_item(status, "adapter-enablement:repeatability", {
        "minimum_successful_runs": minimum,
        "provided_runs": len(paths),
        "successful_runs": passed,
        "distinct_observed_at": len(observed_times),
        "distinct_required": require_distinct,
        "result_signatures": signatures,
        "runs": checks,
    })


def evaluate_health(provider: str, path: Path, policy: dict[str, Any]) -> dict[str, Any]:
    cfg = policy.get("provider_health") or {}
    required = str(cfg.get("required_state") or "HEALTHY")
    max_age = int(cfg.get("maximum_age_seconds") or 300)
    future_skew = int(cfg.get("maximum_future_skew_seconds") or 60)
    snapshot = load(path)
    item = (snapshot.get("providers") or {}).get(provider) if isinstance(snapshot.get("providers"), dict) else None
    blockers: list[str] = []
    if snapshot.get("schema") != HEALTH_SCHEMA:
        blockers.append(f"HEALTH_SCHEMA_INVALID:{snapshot.get('schema')}")
    if not isinstance(item, dict):
        blockers.append(f"PROVIDER_HEALTH_MISSING:{provider}")
        state = None
        checked_at = None
        age = None
    else:
        state = item.get("state")
        checked_at = str(item.get("checked_at") or "")
        dt = parse_time(checked_at)
        if dt is None:
            blockers.append("PROVIDER_HEALTH_TIME_INVALID")
            age = None
        else:
            age = (now() - dt).total_seconds()
            if age < -future_skew:
                blockers.append("PROVIDER_HEALTH_FUTURE_DATED")
            elif age > max_age:
                blockers.append("PROVIDER_HEALTH_STALE")
        if state != required:
            blockers.append(f"PROVIDER_HEALTH_NOT_{required}:{state}")
    status = "PASS" if not blockers else "FAIL"
    return evidence_item(status, f"provider-health-snapshot:{path}", {
        "provider": provider,
        "required_state": required,
        "observed_state": state,
        "checked_at": checked_at,
        "age_seconds": None if age is None else round(max(0, age), 3),
        "maximum_age_seconds": max_age,
        "blockers": blockers,
        "snapshot_digest": digest(snapshot),
    })


def evaluate_rollback(adapter: str, path: Path, policy: dict[str, Any]) -> dict[str, Any]:
    cfg = policy.get("rollback") or {}
    required_target = str(cfg.get("required_target_status") or "DISABLED")
    minimum_steps = int(cfg.get("minimum_steps") or 2)
    verification_required = bool(cfg.get("verification_required", True))
    registry = load(path)
    blockers: list[str] = []
    if registry.get("schema") != ROLLBACK_SCHEMA:
        blockers.append(f"ROLLBACK_SCHEMA_INVALID:{registry.get('schema')}")
    entry = (registry.get("adapters") or {}).get(adapter) if isinstance(registry.get("adapters"), dict) else None
    if not isinstance(entry, dict):
        blockers.append(f"ROLLBACK_MISSING:{adapter}")
        steps: list[Any] = []
        verification: list[Any] = []
        target = None
        enabled = False
    else:
        enabled = entry.get("enabled") is True
        target = entry.get("target_status")
        steps = entry.get("steps") if isinstance(entry.get("steps"), list) else []
        verification = entry.get("verification") if isinstance(entry.get("verification"), list) else []
        if not enabled:
            blockers.append("ROLLBACK_NOT_ENABLED")
        if target != required_target:
            blockers.append(f"ROLLBACK_TARGET_INVALID:{target}")
        if len(steps) < minimum_steps or any(not isinstance(x, str) or not x.strip() for x in steps):
            blockers.append("ROLLBACK_STEPS_INSUFFICIENT")
        if verification_required and (not verification or any(not isinstance(x, str) or not x.strip() for x in verification)):
            blockers.append("ROLLBACK_VERIFICATION_MISSING")
    status = "PASS" if not blockers else "FAIL"
    return evidence_item(status, f"adapter-rollbacks:{path}", {
        "adapter": adapter,
        "enabled": enabled,
        "target_status": target,
        "required_target_status": required_target,
        "steps": len(steps),
        "verification_checks": len(verification),
        "blockers": blockers,
        "rollback_digest": digest(registry),
    })


def main() -> int:
    parser = argparse.ArgumentParser(description="Derive PILOT->ENABLED adapter promotion evidence")
    parser.add_argument("--policy", type=Path, default=Path("dev-hub/config/adapter-enablement.v1.json"))
    parser.add_argument("--adapter", required=True)
    parser.add_argument("--provider", required=True)
    parser.add_argument("--result", action="append", type=Path, default=[])
    parser.add_argument("--health", required=True, type=Path)
    parser.add_argument("--rollbacks", type=Path, default=Path("dev-hub/config/adapter-rollbacks.v1.json"))
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    policy = load(args.policy)
    if policy.get("schema") != POLICY_SCHEMA:
        raise SystemExit(f"POLICY_SCHEMA_INVALID={policy.get('schema')}")

    evidence = {
        "repeatable-pass": evaluate_repeatability(args.adapter, args.result, policy),
        "provider-health-pass": evaluate_health(args.provider, args.health, policy),
        "rollback-defined": evaluate_rollback(args.adapter, args.rollbacks, policy),
    }
    output = {
        "schema": OUTPUT_SCHEMA,
        "adapter": args.adapter,
        "observed_at": now_iso(),
        "evidence": evidence,
        "approvals": [],
        "notes": [
            "PILOT->ENABLED evidence derived from repeated concrete runtime results, normalized health, and rollback policy.",
            "No registry mutation and no approval creation occurred."
        ],
    }
    save(args.output, output)
    failed = [key for key, item in evidence.items() if item.get("status") != "PASS"]
    print(f"ADAPTER_ENABLEMENT_EVIDENCE={args.output}")
    print(f"ADAPTER={args.adapter}")
    print(f"PROVIDER={args.provider}")
    print(f"EVIDENCE_STATUS={'PASS' if not failed else 'FAIL'}")
    for key in failed:
        print(f"EVIDENCE_FAILED={key}")
    return 0 if not failed else 2


if __name__ == "__main__":
    raise SystemExit(main())
