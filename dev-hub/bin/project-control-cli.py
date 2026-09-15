#!/usr/bin/env python3
"""ChaCha DEV HUB unified Project Control CLI router V1.3.

Routes standard operations to project-control.py, transaction inspection /
recovery to transaction-recovery.py, and platform certification to
platform-readiness.py while preserving the Project Control response contract.
Recovery is inspect-only unless --apply is explicit. Readiness is read-only.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

POLICY_SCHEMA = "chacha.dev/project-control/v1"
RESPONSE_SCHEMA = "chacha.dev/project-control-response/v1"
RECOVERY_OPERATIONS = {"transactions", "recover-transaction"}
ROUTED_OPERATIONS = RECOVERY_OPERATIONS | {"platform-readiness"}


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


def resolve(repo_root: Path, configured: str) -> Path:
    p = Path(configured)
    return p if p.is_absolute() else repo_root / p


def response(project: str, operation: str, status: str, summary: str,
             details: dict[str, Any] | None = None, blockers: list[str] | None = None,
             next_actions: list[str] | None = None, artifacts: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "schema": RESPONSE_SCHEMA,
        "project": project,
        "operation": operation,
        "status": status,
        "observed_at": now_iso(),
        "summary": summary,
        "details": details or {},
        "blockers": blockers or [],
        "next_actions": next_actions or [],
        "artifacts": artifacts or [],
    }


def emit(value: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(value, indent=2, ensure_ascii=False))
        return
    print(f"PROJECT={value.get('project')}")
    print(f"OPERATION={value.get('operation')}")
    print(f"STATUS={value.get('status')}")
    print(f"SUMMARY={value.get('summary')}")
    for blocker in value.get("blockers") or []:
        print(f"BLOCKER={blocker}")
    for action in value.get("next_actions") or []:
        print(f"NEXT={action}")


def run_json(tool: Path, argv: list[str], timeout: int = 120) -> tuple[int, dict[str, Any] | None, str, str]:
    try:
        proc = subprocess.run(
            [sys.executable, str(tool), *argv],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            shell=False,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return 124, None, "", f"TOOL_TIMEOUT={tool}"
    try:
        payload = json.loads(proc.stdout) if proc.stdout.strip() else None
    except json.JSONDecodeError:
        payload = None
    return proc.returncode, payload, proc.stdout, proc.stderr


def routed_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ChaCha DEV HUB unified Project Control")
    parser.add_argument("--policy", type=Path, default=Path("dev-hub/config/project-control.v1.json"))
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--json", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    txs = sub.add_parser("transactions")
    txs.add_argument("--project", required=True)

    recover = sub.add_parser("recover-transaction")
    recover.add_argument("--project", required=True)
    recover.add_argument("--transaction-id", required=True)
    recover.add_argument("--actor", default="recovery-engineer")
    recover.add_argument("--apply", action="store_true")
    recover.add_argument("--report", type=Path)

    ready = sub.add_parser("platform-readiness")
    ready.add_argument("--project", required=True)
    ready.add_argument("--profile", choices=["contract", "development", "production"], default="development")
    ready.add_argument("--provider-health", type=Path)
    ready.add_argument("--storage-preflight", type=Path)
    ready.add_argument("--adapter-contract-report", type=Path)
    ready.add_argument("--recovery-drill-report", type=Path)
    ready.add_argument("--run-recovery-drill", action="store_true")
    ready.add_argument("--required-provider", action="append", default=[])
    ready.add_argument("--report", type=Path)
    return parser


def routed_command(argv: list[str]) -> str | None:
    for token in argv:
        if token in ROUTED_OPERATIONS:
            return token
    return None


def handle_recovery(args: argparse.Namespace, policy: dict[str, Any]) -> int:
    refs = policy.get("repository_paths") or {}
    tools = policy.get("engine_paths") or {}
    recovery_policy = resolve(args.repo_root, str(refs.get("transaction_recovery")))
    recovery_engine = resolve(args.repo_root, str(tools.get("transaction_recovery")))

    if args.command == "transactions":
        _rc, payload, stdout, stderr = run_json(
            recovery_engine,
            ["--policy", str(recovery_policy), "--repo-root", str(args.repo_root), "--json", "list", "--project", args.project],
        )
        if payload is None:
            result = response(args.project, args.command, "FAILED", "Transaction listing failed.",
                              {"stdout": stdout.strip(), "stderr": stderr.strip()}, ["TRANSACTION_LIST_FAILED"])
        else:
            summary = payload.get("summary") or {}
            blocking = int(summary.get("blocking") or 0)
            result = response(
                args.project,
                args.command,
                "BLOCKED" if blocking else "OK",
                f"Found {summary.get('count', 0)} control transaction(s); {blocking} require recovery.",
                {"transaction_summary": summary, "transactions": payload.get("transactions") or []},
                [f"CONTROL_TRANSACTIONS_REQUIRE_RECOVERY:{blocking}"] if blocking else [],
                ["inspect or recover blocking transactions"] if blocking else [],
            )
        emit(result, args.json)
        return 0 if result["status"] == "OK" else 2

    engine_args = [
        "--policy", str(recovery_policy), "--repo-root", str(args.repo_root), "--json",
        "recover", "--project", args.project, "--transaction-id", args.transaction_id,
        "--actor", args.actor,
    ]
    if args.apply:
        engine_args.append("--apply")
    if args.report:
        engine_args += ["--report", str(args.report)]
    _rc, payload, stdout, stderr = run_json(recovery_engine, engine_args)
    if payload is None:
        result = response(args.project, args.command, "FAILED", "Transaction recovery engine returned no valid report.",
                          {"stdout": stdout.strip(), "stderr": stderr.strip()}, ["TRANSACTION_RECOVERY_FAILED"])
    else:
        blockers = list(payload.get("blockers") or [])
        assessment = str(payload.get("assessment") or "INVALID")
        outcome = payload.get("recovery_outcome")
        if blockers:
            status = "BLOCKED"
        elif args.apply and (outcome or assessment == "TERMINAL"):
            status = "OK"
        elif assessment in {"SAFE_TO_ABORT", "SAFE_TO_FINALIZE", "ALREADY_EFFECTIVE", "REPAIRABLE", "TERMINAL"}:
            status = "READY"
        else:
            status = "BLOCKED"
        next_actions: list[str] = []
        if not args.apply and status == "READY" and assessment != "TERMINAL":
            next_actions.append(f"recover transaction {args.transaction_id} with explicit --apply")
        if blockers:
            next_actions.append("resolve blockers manually; no authoritative audit event will be rewritten")
        result = response(
            args.project,
            args.command,
            status,
            f"Transaction {args.transaction_id}: assessment={assessment}" + (f", outcome={outcome}" if outcome else ""),
            {"recovery_report": payload},
            blockers,
            next_actions,
            [{"type": "transaction-recovery-report", "path": str(args.report)}] if args.report else [],
        )
    emit(result, args.json)
    return 0 if result["status"] in {"OK", "READY"} else 2


def handle_readiness(args: argparse.Namespace, policy: dict[str, Any]) -> int:
    refs = policy.get("repository_paths") or {}
    tools = policy.get("engine_paths") or {}
    readiness_policy = resolve(args.repo_root, str(refs.get("platform_readiness")))
    readiness_engine = resolve(args.repo_root, str(tools.get("platform_readiness")))
    engine_args = [
        "--repo-root", str(args.repo_root),
        "--policy", str(readiness_policy),
        "--profile", args.profile,
        "--project", args.project,
        "--json",
    ]
    for value, flag in (
        (args.provider_health, "--provider-health"),
        (args.storage_preflight, "--storage-preflight"),
        (args.adapter_contract_report, "--adapter-contract-report"),
        (args.recovery_drill_report, "--recovery-drill-report"),
        (args.report, "--output"),
    ):
        if value:
            engine_args += [flag, str(value)]
    if args.run_recovery_drill:
        engine_args.append("--run-recovery-drill")
    for provider in args.required_provider:
        engine_args += ["--required-provider", provider]

    _rc, payload, stdout, stderr = run_json(readiness_engine, engine_args, timeout=300)
    if payload is None:
        result = response(args.project, args.command, "FAILED", "Platform readiness engine returned no valid report.",
                          {"stdout": stdout.strip(), "stderr": stderr.strip()}, ["PLATFORM_READINESS_FAILED"])
    else:
        blockers = list(payload.get("blockers") or [])
        profile = str(payload.get("profile") or args.profile)
        ready = payload.get("ready_for_execution") == "YES"
        contract_ok = profile == "contract" and payload.get("status") == "PASS"
        status = "READY" if ready else ("OK" if contract_ok else "BLOCKED")
        if ready:
            summary = f"DEV HUB is certified ready for {profile} execution."
        elif contract_ok:
            summary = "DEV HUB contract certification passed; runtime execution is not authorized by the contract profile."
        else:
            summary = f"DEV HUB is not ready for {profile} execution."
        next_actions = ["resolve readiness blockers and re-run certification"] if blockers else []
        result = response(
            args.project,
            args.command,
            status,
            summary,
            {"platform_readiness": payload},
            blockers,
            next_actions,
            [{"type": "platform-readiness-report", "path": str(args.report)}] if args.report else [],
        )
    emit(result, args.json)
    return 0 if result["status"] in {"OK", "READY"} else 2


def main() -> int:
    argv = sys.argv[1:]
    command = routed_command(argv)
    if command:
        args = routed_parser().parse_args(argv)
        policy_path = args.policy if args.policy.is_absolute() else args.repo_root / args.policy
        policy = load(policy_path)
        if policy.get("schema") != POLICY_SCHEMA:
            raise SystemExit(f"POLICY_SCHEMA_INVALID={policy.get('schema')}")
        if command in RECOVERY_OPERATIONS:
            return handle_recovery(args, policy)
        return handle_readiness(args, policy)

    core = Path(__file__).with_name("project-control.py")
    os.execv(sys.executable, [sys.executable, str(core), *argv])
    return 127


if __name__ == "__main__":
    raise SystemExit(main())
