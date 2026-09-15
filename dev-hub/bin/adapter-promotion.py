#!/usr/bin/env python3
"""ChaCha DEV HUB Adapter Provisioning & Promotion V1.1.

Evaluates and, only with an explicit apply flag, mutates an adapter status in a
provider-adapter registry. Promotion is evidence-driven, adjacency-constrained,
and approval-gated for production-capable enablement. Local executable binding
is required only for execution kinds configured as local (currently VPS).
External-only adapters remain executable=null and require provider-specific
runtime evidence instead of an invented local bridge.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REGISTRY_SCHEMA = "chacha.dev/provider-adapters/v1"
CONTRACT_SCHEMA = "chacha.dev/adapter-contract/v1"
POLICY_SCHEMA = "chacha.dev/adapter-promotion/v1"
EVIDENCE_SCHEMA = "chacha.dev/adapter-promotion-evidence/v1"
REPORT_SCHEMA = "chacha.dev/adapter-promotion-report/v1"


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


def require_schema(value: dict[str, Any], expected: str, label: str) -> None:
    if value.get("schema") != expected:
        raise SystemExit(f"SCHEMA_MISMATCH={label}:expected={expected}:actual={value.get('schema')}")


def canonical_digest(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def atomic_save(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(value, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def parse_time(value: str) -> datetime | None:
    try:
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def evidence_fresh(observed_at: str, policy: dict[str, Any]) -> tuple[bool, str]:
    settings = policy.get("evidence") or {}
    max_age = int(settings.get("max_age_seconds") or 604800)
    future_skew = int(settings.get("maximum_future_skew_seconds") or 60)
    dt = parse_time(observed_at)
    if dt is None:
        return False, "timestamp-invalid"
    age = (datetime.now(timezone.utc) - dt).total_seconds()
    if age < -future_skew:
        return False, "timestamp-future"
    if age > max_age:
        return False, "timestamp-stale"
    return True, "fresh"


def production_capable(entry: dict[str, Any], policy: dict[str, Any]) -> bool:
    protected = set(policy.get("production_capable_permissions") or [])
    return bool(protected & set(entry.get("supports") or []))


def adapter_execution_kinds(registry: dict[str, Any], adapter: str) -> set[str]:
    kinds: set[str] = set()
    for item in (registry.get("providers") or {}).values():
        if isinstance(item, dict) and item.get("adapter") == adapter:
            execution = item.get("execution")
            if isinstance(execution, str) and execution:
                kinds.add(execution)
    return kinds


def valid_approval(evidence: dict[str, Any], adapter: str, target: str,
                   approval_id: str | None, policy: dict[str, Any]) -> tuple[bool, str | None]:
    settings = policy.get("approval") or {}
    if not approval_id:
        return False, None
    expected_type = str(settings.get("type") or "adapter-production-enable")
    for item in evidence.get("approvals") or []:
        if not isinstance(item, dict) or item.get("id") != approval_id:
            continue
        if item.get("type") != expected_type:
            return False, approval_id
        if bool(settings.get("must_match_adapter", True)) and item.get("adapter") != adapter:
            return False, approval_id
        if bool(settings.get("must_match_target", True)) and item.get("target_status") != target:
            return False, approval_id
        if not item.get("actor"):
            return False, approval_id
        fresh, _ = evidence_fresh(str(item.get("approved_at") or ""), policy)
        if not fresh:
            return False, approval_id
        return True, approval_id
    return False, approval_id


def evaluate(adapter: str, target: str, registry: dict[str, Any], contract: dict[str, Any],
             policy: dict[str, Any], evidence: dict[str, Any], executable: str | None,
             approval_id: str | None) -> dict[str, Any]:
    adapters = registry.get("adapters") or {}
    entry = adapters.get(adapter)
    blockers: list[str] = []
    if not isinstance(entry, dict):
        entry = {"status": "UNKNOWN", "executable": None, "supports": []}
        blockers.append(f"ADAPTER_NOT_REGISTERED:{adapter}")

    execution_kinds = adapter_execution_kinds(registry, adapter)
    if not execution_kinds:
        blockers.append("ADAPTER_PROVIDER_BINDING_MISSING")

    current = str(entry.get("status") or "UNKNOWN")
    target = target.upper()
    transition = f"{current}->{target}"
    lifecycle = set(contract.get("status_lifecycle") or [])
    if current not in lifecycle:
        blockers.append(f"CURRENT_STATUS_UNKNOWN:{current}")
    if target not in lifecycle:
        blockers.append(f"TARGET_STATUS_UNKNOWN:{target}")

    requirements = (contract.get("promotion") or {}).get(transition)
    if not isinstance(requirements, list):
        requirements = []
        blockers.append(f"TRANSITION_NOT_ALLOWED:{transition}")

    if evidence.get("adapter") != adapter:
        blockers.append(f"EVIDENCE_ADAPTER_MISMATCH:{evidence.get('adapter')}")
    fresh, reason = evidence_fresh(str(evidence.get("observed_at") or ""), policy)
    if not fresh:
        blockers.append(f"EVIDENCE_{reason.upper().replace('-', '_')}")

    observed: dict[str, Any] = {}
    evidence_map = evidence.get("evidence") or {}
    for requirement in requirements:
        item = evidence_map.get(requirement)
        if not isinstance(item, dict):
            observed[requirement] = {"status": "MISSING"}
            blockers.append(f"EVIDENCE_MISSING:{requirement}")
            continue
        status = str(item.get("status") or "UNKNOWN")
        source = item.get("source")
        item_time = str(item.get("observed_at") or evidence.get("observed_at") or "")
        item_fresh, item_reason = evidence_fresh(item_time, policy)
        observed[requirement] = {
            "status": status,
            "source": source,
            "observed_at": item_time,
            "fresh": item_fresh,
        }
        if status != str((policy.get("evidence") or {}).get("pass_state") or "PASS"):
            blockers.append(f"EVIDENCE_NOT_PASS:{requirement}:{status}")
        if not source:
            blockers.append(f"EVIDENCE_SOURCE_MISSING:{requirement}")
        if not item_fresh:
            blockers.append(f"EVIDENCE_NOT_FRESH:{requirement}:{item_reason}")

    before_exec = entry.get("executable")
    after_exec = executable if executable is not None else before_exec
    if executable is not None and not Path(executable).is_absolute():
        blockers.append("EXECUTABLE_MUST_BE_ABSOLUTE")

    runtime_statuses = set(policy.get("runtime_statuses_require_executable") or [])
    required_execution_kinds = set(policy.get("executable_required_execution_kinds") or ["vps"])
    needs_local_executable = target in runtime_statuses and bool(execution_kinds & required_execution_kinds)
    external_only = execution_kinds == {"external"}
    if needs_local_executable:
        if not isinstance(after_exec, str) or not after_exec.startswith("/"):
            blockers.append(f"RUNTIME_EXECUTABLE_REQUIRED_FOR:{target}")
    if (
        target in runtime_statuses
        and external_only
        and bool(policy.get("external_only_executable_must_be_null", True))
        and after_exec not in {None, ""}
    ):
        blockers.append("EXTERNAL_ONLY_ADAPTER_MUST_NOT_BIND_LOCAL_EXECUTABLE")

    prod = production_capable(entry, policy)
    approval_required = bool(prod and target == str((policy.get("approval") or {}).get("required_target") or "ENABLED"))
    approval_ok = True
    matched_approval: str | None = None
    if approval_required:
        approval_ok, matched_approval = valid_approval(evidence, adapter, target, approval_id, policy)
        if not approval_id:
            blockers.append("EXPLICIT_PRODUCTION_APPROVAL_ID_REQUIRED")
        elif not approval_ok:
            blockers.append(f"PRODUCTION_APPROVAL_INVALID:{approval_id}")

    return {
        "schema": REPORT_SCHEMA,
        "adapter": adapter,
        "current_status": current,
        "target_status": target,
        "transition": transition,
        "execution_kinds": sorted(execution_kinds),
        "requires_local_executable": needs_local_executable,
        "eligible": not blockers,
        "applied": False,
        "production_capable": prod,
        "approval_required": approval_required,
        "approval_id": matched_approval if approval_ok else approval_id,
        "executable_before": before_exec,
        "executable_after": after_exec,
        "required_evidence": requirements,
        "observed_evidence": observed,
        "blockers": blockers,
        "actor": None,
        "registry_digest_before": canonical_digest(registry),
        "registry_digest_after": None,
        "receipt": None,
        "observed_at": now_iso(),
    }


def emit(report: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return
    print(f"ADAPTER={report['adapter']}")
    print(f"TRANSITION={report['transition']}")
    print(f"EXECUTION_KINDS={','.join(report.get('execution_kinds') or [])}")
    print(f"REQUIRES_LOCAL_EXECUTABLE={'YES' if report.get('requires_local_executable') else 'NO'}")
    print(f"ELIGIBLE={'YES' if report['eligible'] else 'NO'}")
    print(f"APPLIED={'YES' if report['applied'] else 'NO'}")
    print(f"PRODUCTION_CAPABLE={'YES' if report.get('production_capable') else 'NO'}")
    print(f"APPROVAL_REQUIRED={'YES' if report.get('approval_required') else 'NO'}")
    for blocker in report.get("blockers") or []:
        print(f"BLOCKER={blocker}")


def main() -> int:
    parser = argparse.ArgumentParser(description="ChaCha DEV HUB adapter provisioning and promotion")
    parser.add_argument("--registry", type=Path, default=Path("dev-hub/config/provider-adapters.v1.json"))
    parser.add_argument("--contract", type=Path, default=Path("dev-hub/config/adapter-contract.v1.json"))
    parser.add_argument("--policy", type=Path, default=Path("dev-hub/config/adapter-promotion.v1.json"))
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--json", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    plan = sub.add_parser("plan")
    plan.add_argument("--adapter", required=True)
    plan.add_argument("--target", required=True)
    plan.add_argument("--executable")
    plan.add_argument("--approval-id")

    apply = sub.add_parser("apply")
    apply.add_argument("--adapter", required=True)
    apply.add_argument("--target", required=True)
    apply.add_argument("--executable")
    apply.add_argument("--approval-id")
    apply.add_argument("--actor", required=True)
    apply.add_argument("--receipt", required=True, type=Path)
    apply.add_argument("--apply", action="store_true")

    args = parser.parse_args()
    registry = load(args.registry)
    contract = load(args.contract)
    policy = load(args.policy)
    evidence = load(args.evidence)
    require_schema(registry, REGISTRY_SCHEMA, "registry")
    require_schema(contract, CONTRACT_SCHEMA, "contract")
    require_schema(policy, POLICY_SCHEMA, "policy")
    require_schema(evidence, EVIDENCE_SCHEMA, "evidence")

    report = evaluate(
        args.adapter, args.target, registry, contract, policy, evidence,
        args.executable, args.approval_id,
    )

    if args.command == "apply":
        report["actor"] = args.actor
        report["receipt"] = str(args.receipt)
        if not args.apply:
            report["blockers"].append("EXPLICIT_APPLY_FLAG_REQUIRED")
            report["eligible"] = False
        if report["eligible"]:
            before = dict((registry.get("adapters") or {})[args.adapter])
            updated = json.loads(json.dumps(registry))
            target_entry = (updated.get("adapters") or {})[args.adapter]
            target_entry["status"] = report["target_status"]
            if args.executable is not None:
                target_entry["executable"] = args.executable
            atomic_save(args.registry, updated)
            report["applied"] = True
            report["registry_digest_after"] = canonical_digest(updated)
            receipt = {
                **report,
                "receipt_schema": "chacha.dev/adapter-promotion-receipt/v1",
                "previous_entry": before,
                "new_entry": dict(target_entry),
                "evidence_digest": canonical_digest(evidence),
                "committed_at": now_iso(),
            }
            atomic_save(args.receipt, receipt)
    if args.report:
        atomic_save(args.report, report)
    emit(report, args.json)
    return 0 if report["eligible"] and (args.command == "plan" or report["applied"]) else 2


if __name__ == "__main__":
    raise SystemExit(main())
