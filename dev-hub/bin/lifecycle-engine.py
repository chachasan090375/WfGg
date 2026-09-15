#!/usr/bin/env python3
"""ChaCha DEV HUB Lifecycle & Orchestration Engine V1.

Deterministic lifecycle state machine for project promotion. The engine only
changes its local state file; it never deploys, installs or mutates production.
A transition is allowed only when the configured evidence, approvals and gate
status requirements are satisfied.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LIFECYCLE_SCHEMA = "chacha.dev/lifecycle/v1"
STATE_SCHEMA = "chacha.dev/project-lifecycle-state/v1"
LEDGER_SCHEMA = "chacha.dev/evidence-ledger/v1"
QUALITY_SCHEMA = "chacha.dev/quality-gates/v1"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit(f"FILE_NOT_FOUND={path}")
    except json.JSONDecodeError as exc:
        raise SystemExit(f"JSON_INVALID={path}:{exc.lineno}:{exc.colno}:{exc.msg}")
    if not isinstance(value, dict):
        raise SystemExit(f"JSON_ROOT_NOT_OBJECT={path}")
    return value


def save_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def require_schema(value: dict[str, Any], expected: str, label: str) -> None:
    actual = value.get("schema")
    if actual != expected:
        raise SystemExit(f"SCHEMA_MISMATCH={label}:expected={expected}:actual={actual}")


def transition_key(current: str, target: str) -> str:
    return f"{current}->{target}"


def init_state(project: str, stage: str) -> dict[str, Any]:
    return {
        "schema": STATE_SCHEMA,
        "project": project,
        "current_stage": stage,
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "history": [
            {
                "from": None,
                "to": stage,
                "status": "INITIALIZED",
                "actor": "lifecycle-engine",
                "observed_at": now_iso(),
                "evidence_digest": None,
            }
        ],
    }


def artifact_blockers(rule: dict[str, Any], ledger: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    artifacts = ledger.get("artifacts") or {}
    for artifact_id in rule.get("required_artifacts") or []:
        item = artifacts.get(artifact_id)
        if not isinstance(item, dict):
            blockers.append(f"ARTIFACT_MISSING:{artifact_id}")
            continue
        status = item.get("status")
        source = item.get("source")
        observed_at = item.get("observed_at")
        if status != "OK":
            blockers.append(f"ARTIFACT_NOT_OK:{artifact_id}:{status or 'UNKNOWN'}")
        if not source:
            blockers.append(f"ARTIFACT_SOURCE_MISSING:{artifact_id}")
        if not observed_at:
            blockers.append(f"ARTIFACT_TIMESTAMP_MISSING:{artifact_id}")
    return blockers


def approval_blockers(rule: dict[str, Any], ledger: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    approvals = ledger.get("approvals") or {}
    for approval_id in rule.get("required_approvals") or []:
        item = approvals.get(approval_id)
        if not isinstance(item, dict):
            blockers.append(f"APPROVAL_MISSING:{approval_id}")
            continue
        if item.get("status") != "APPROVED":
            blockers.append(f"APPROVAL_NOT_APPROVED:{approval_id}:{item.get('status') or 'UNKNOWN'}")
        if not item.get("actor"):
            blockers.append(f"APPROVAL_ACTOR_MISSING:{approval_id}")
        if not item.get("observed_at"):
            blockers.append(f"APPROVAL_TIMESTAMP_MISSING:{approval_id}")
    return blockers


def risk_accepted(gate: str, ledger: dict[str, Any]) -> bool:
    for item in ledger.get("risk_acceptances") or []:
        if not isinstance(item, dict):
            continue
        if item.get("gate") == gate and item.get("status") == "APPROVED" and item.get("actor") and item.get("observed_at"):
            return True
    return False


def required_gate_blockers(rule: dict[str, Any], ledger: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    gates = ledger.get("gates") or {}
    allowed = {"OK", "NOT_APPLICABLE"}
    for gate in rule.get("required_gates") or []:
        item = gates.get(gate)
        if not isinstance(item, dict):
            blockers.append(f"GATE_MISSING:{gate}")
            continue
        status = item.get("status")
        if status not in allowed:
            blockers.append(f"GATE_BLOCKING:{gate}:{status or 'UNKNOWN'}")
        if status == "NOT_APPLICABLE" and not item.get("reason"):
            blockers.append(f"GATE_NA_REASON_MISSING:{gate}")
    return blockers


def release_gate_blockers(
    lifecycle: dict[str, Any], quality: dict[str, Any], ledger: dict[str, Any]
) -> list[str]:
    blockers: list[str] = []
    policy = lifecycle.get("release_policy") or {}
    gates = ledger.get("gates") or {}
    definitions = quality.get("gates") or {}
    allowed_blocking = set(policy.get("allowed_blocking_statuses") or [])
    allowed_non_blocking = set(policy.get("allowed_non_blocking_statuses") or [])
    forbidden = set(policy.get("forbidden_statuses") or [])

    for gate, definition in definitions.items():
        item = gates.get(gate)
        if not isinstance(item, dict):
            blockers.append(f"GATE_MISSING:{gate}")
            continue
        status = item.get("status")
        if status in forbidden or status is None:
            blockers.append(f"GATE_FORBIDDEN:{gate}:{status or 'UNKNOWN'}")
            continue
        blocking = bool(definition.get("default_blocking"))
        if blocking and status not in allowed_blocking:
            blockers.append(f"GATE_BLOCKING:{gate}:{status}")
        if not blocking and status not in allowed_non_blocking:
            blockers.append(f"GATE_NOT_RELEASE_READY:{gate}:{status}")
        if status == "NOT_APPLICABLE" and not item.get("reason"):
            blockers.append(f"GATE_NA_REASON_MISSING:{gate}")
        if (
            not blocking
            and status == "PARTIAL"
            and policy.get("risk_acceptance_required_for_non_blocking_partial")
            and not risk_accepted(gate, ledger)
        ):
            blockers.append(f"RISK_ACCEPTANCE_MISSING:{gate}")
    return blockers


def gate_blockers(
    rule: dict[str, Any], lifecycle: dict[str, Any], quality: dict[str, Any], ledger: dict[str, Any]
) -> list[str]:
    policy = rule.get("gate_policy", "none")
    if policy in {"none", "defined"}:
        return []
    if policy == "required-gates":
        return required_gate_blockers(rule, ledger)
    if policy == "release":
        return release_gate_blockers(lifecycle, quality, ledger)
    return [f"UNKNOWN_GATE_POLICY:{policy}"]


def validate_ledger(ledger: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    if ledger.get("schema") != LEDGER_SCHEMA:
        blockers.append(f"LEDGER_SCHEMA_INVALID:{ledger.get('schema')}")
    return blockers


def transition_check(
    state: dict[str, Any],
    target: str,
    lifecycle: dict[str, Any],
    quality: dict[str, Any],
    ledger: dict[str, Any],
) -> dict[str, Any]:
    current = state.get("current_stage")
    stages = lifecycle.get("stages") or []
    if current not in stages:
        return {"allowed": False, "transition": transition_key(str(current), target), "blockers": [f"CURRENT_STAGE_INVALID:{current}"]}
    if target not in stages:
        return {"allowed": False, "transition": transition_key(str(current), target), "blockers": [f"TARGET_STAGE_INVALID:{target}"]}

    key = transition_key(current, target)
    rule = (lifecycle.get("transitions") or {}).get(key)
    if not isinstance(rule, dict):
        return {"allowed": False, "transition": key, "blockers": [f"TRANSITION_NOT_ALLOWED:{key}"]}

    blockers = validate_ledger(ledger)
    blockers.extend(artifact_blockers(rule, ledger))
    blockers.extend(approval_blockers(rule, ledger))
    blockers.extend(gate_blockers(rule, lifecycle, quality, ledger))
    blockers = sorted(set(blockers))
    return {
        "allowed": not blockers,
        "transition": key,
        "current_stage": current,
        "target_stage": target,
        "gate_policy": rule.get("gate_policy"),
        "required_artifacts": rule.get("required_artifacts") or [],
        "required_approvals": rule.get("required_approvals") or [],
        "required_gates": rule.get("required_gates") or [],
        "blockers": blockers,
    }


def ledger_digest(ledger: dict[str, Any]) -> str:
    import hashlib

    payload = json.dumps(ledger, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def print_check(result: dict[str, Any]) -> None:
    print("=== LIFECYCLE TRANSITION CHECK ===")
    print(f"TRANSITION={result.get('transition')}")
    print(f"ALLOWED={'YES' if result.get('allowed') else 'NO'}")
    print(f"GATE_POLICY={result.get('gate_policy', '')}")
    blockers = result.get("blockers") or []
    print(f"BLOCKERS={len(blockers)}")
    for blocker in blockers:
        print(f"BLOCKER={blocker}")


def cmd_init(args: argparse.Namespace) -> int:
    lifecycle = load_json(Path(args.lifecycle))
    require_schema(lifecycle, LIFECYCLE_SCHEMA, "lifecycle")
    stage = args.stage.upper()
    if stage not in (lifecycle.get("stages") or []):
        raise SystemExit(f"STAGE_INVALID={stage}")
    path = Path(args.state)
    if path.exists() and not args.force:
        raise SystemExit(f"STATE_EXISTS={path}")
    save_json(path, init_state(args.project, stage))
    print("LIFECYCLE_STATE_CREATED=OK")
    print(f"PROJECT={args.project}")
    print(f"STAGE={stage}")
    print(f"STATE={path}")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    state = load_json(Path(args.state))
    require_schema(state, STATE_SCHEMA, "state")
    print("=== PROJECT LIFECYCLE STATUS ===")
    print(f"PROJECT={state.get('project')}")
    print(f"CURRENT_STAGE={state.get('current_stage')}")
    print(f"UPDATED_AT={state.get('updated_at')}")
    print(f"TRANSITIONS={max(0, len(state.get('history') or []) - 1)}")
    return 0


def common_check(args: argparse.Namespace) -> tuple[dict[str, Any], dict[str, Any]]:
    state = load_json(Path(args.state))
    lifecycle = load_json(Path(args.lifecycle))
    quality = load_json(Path(args.quality_gates))
    ledger = load_json(Path(args.evidence))
    require_schema(state, STATE_SCHEMA, "state")
    require_schema(lifecycle, LIFECYCLE_SCHEMA, "lifecycle")
    require_schema(quality, QUALITY_SCHEMA, "quality-gates")
    return state, transition_check(state, args.target.upper(), lifecycle, quality, ledger)


def cmd_check(args: argparse.Namespace) -> int:
    _, result = common_check(args)
    print_check(result)
    return 0 if result["allowed"] else 2


def cmd_advance(args: argparse.Namespace) -> int:
    state, result = common_check(args)
    print_check(result)
    if not result["allowed"]:
        print("STATE_CHANGED=NO")
        return 2
    ledger = load_json(Path(args.evidence))
    previous = state.get("current_stage")
    target = args.target.upper()
    event = {
        "from": previous,
        "to": target,
        "status": "PROMOTED",
        "actor": args.actor,
        "observed_at": now_iso(),
        "evidence_digest": ledger_digest(ledger),
    }
    state["current_stage"] = target
    state["updated_at"] = event["observed_at"]
    state.setdefault("history", []).append(event)
    if args.dry_run:
        print("STATE_CHANGED=NO_DRY_RUN")
        print(json.dumps(event, indent=2, ensure_ascii=False))
        return 0
    save_json(Path(args.state), state)
    print("STATE_CHANGED=YES")
    print(f"NEW_STAGE={target}")
    return 0


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="ChaCha DEV HUB lifecycle state machine")
    p.add_argument("--lifecycle", default="dev-hub/config/lifecycle.v1.json")
    sub = p.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init")
    init.add_argument("--project", required=True)
    init.add_argument("--state", required=True)
    init.add_argument("--stage", default="IDEA")
    init.add_argument("--force", action="store_true")
    init.set_defaults(func=cmd_init)

    status = sub.add_parser("status")
    status.add_argument("--state", required=True)
    status.set_defaults(func=cmd_status)

    for name, func in (("check", cmd_check), ("advance", cmd_advance)):
        item = sub.add_parser(name)
        item.add_argument("--state", required=True)
        item.add_argument("--target", required=True)
        item.add_argument("--evidence", required=True)
        item.add_argument("--quality-gates", default="dev-hub/config/quality-gates.v1.json")
        if name == "advance":
            item.add_argument("--actor", default="project-owner")
            item.add_argument("--dry-run", action="store_true")
        item.set_defaults(func=func)

    return p


def main() -> int:
    args = parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
