#!/usr/bin/env python3
"""ChaCha DEV HUB unified Project Control CLI router V1.4.

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
ROUTED_OPERATIONS = RECOVERY_OPERATIONS | {"platform-readiness", "technical-design", "functional-orchestrate"}


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

    orchestrate = sub.add_parser("functional-orchestrate")
    orchestrate.add_argument("--project", required=True)
    orchestrate.add_argument("--intent", required=True, type=Path)
    orchestrate.add_argument("--output", type=Path)

    design = sub.add_parser("technical-design")
    design.add_argument("--project", required=True)
    design.add_argument("--requirement", required=True, type=Path)
    design.add_argument("--manifest", required=True, type=Path)
    design.add_argument("--output", type=Path)
    design.add_argument("--task-graph-output", type=Path)
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


def handle_functional_orchestrate(args: argparse.Namespace, policy: dict[str, Any]) -> int:
    refs = policy.get("repository_paths") or {}
    tools = policy.get("engine_paths") or {}
    engine = resolve(args.repo_root, str(tools.get("functional_intent_orchestrator")))
    config = resolve(args.repo_root, str(refs.get("domain_orchestration")))
    economics = resolve(args.repo_root, str(refs.get("provider_economics")))
    radar = resolve(args.repo_root, str(refs.get("technology_radar_domain_watch")))

    intent = args.intent if args.intent.is_absolute() else args.repo_root / args.intent
    try:
        intent_value = load(intent)
    except SystemExit as exc:
        result = response(args.project, args.command, "FAILED", "Functional intent could not be loaded.",
                          {"error": str(exc)}, ["FUNCTIONAL_INTENT_INVALID"])
        emit(result, args.json)
        return 2

    intent_project = str(intent_value.get("project") or "")
    if intent_project and intent_project != args.project:
        result = response(
            args.project, args.command, "BLOCKED",
            "Functional intent project does not match requested Project Control project.",
            {"intent_project": intent_project},
            ["FUNCTIONAL_INTENT_PROJECT_MISMATCH"],
        )
        emit(result, args.json)
        return 2

    runtime = policy.get("runtime") or {}
    plans_root = Path(str(runtime.get("plans_root", "/opt/chacha-dev/runtime/plans")))
    out_dir = plans_root / args.project / "domain-orchestration"
    out_dir.mkdir(parents=True, exist_ok=True)
    intent_id = str(intent_value.get("id") or "functional-intent")
    safe_id = "".join(ch if ch.isalnum() or ch in "._-" else "-" for ch in intent_id)
    snapshot = out_dir / f"{safe_id}.intent.json"
    output = args.output or (out_dir / f"{safe_id}.domain-plan.json")
    snapshot.write_bytes(intent.read_bytes())

    proc = subprocess.run(
        [
            sys.executable, str(engine),
            "--config", str(config),
            "--intent", str(snapshot),
            "--output", str(output),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        shell=False,
        timeout=60,
        check=False,
    )
    if proc.returncode != 0 or not output.exists():
        result = response(
            args.project, args.command, "FAILED",
            "Functional intent orchestration failed.",
            {"stdout": proc.stdout.strip(), "stderr": proc.stderr.strip()},
            ["FUNCTIONAL_ORCHESTRATION_FAILED"],
        )
        emit(result, args.json)
        return 2

    plan = load(output)
    if plan.get("schema") != "chacha.dev/domain-plan/v1":
        result = response(args.project, args.command, "FAILED", "Domain plan schema is invalid.",
                          {"schema": plan.get("schema")}, ["DOMAIN_PLAN_SCHEMA_INVALID"])
        emit(result, args.json)
        return 2

    econ = load(economics)
    watch = load(radar)
    zero_cost = int((econ.get("budget_policy") or {}).get("automatic_external_spend_eur", -1)) == 0
    if not zero_cost:
        result = response(args.project, args.command, "BLOCKED",
                          "Automatic external spend policy is not zero.",
                          blockers=["ZERO_INCREMENTAL_COST_POLICY_NOT_ACTIVE"])
        emit(result, args.json)
        return 2

    result = response(
        args.project,
        args.command,
        "READY",
        "Functional intent was decomposed into governed ChaCha DEV domain work packages.",
        {
            "mode": plan.get("mode"),
            "primary_domains": plan.get("primary_domains") or [],
            "review_domains": plan.get("review_domains") or [],
            "packages": plan.get("packages") or [],
            "dependencies": plan.get("dependencies") or [],
            "implementation_allowed_by_intent": bool(plan.get("implementation_allowed")),
            "provider_selection_owner": ((plan.get("provider_selection") or {}).get("owner")),
            "technology_radar_required": bool((plan.get("provider_selection") or {}).get("technology_radar_required")),
            "automatic_external_spend_eur": 0,
            "paid_provider_requires_human_approval": bool((econ.get("budget_policy") or {}).get("paid_provider_requires_human_approval")),
            "technology_radar_mode": watch.get("mode"),
            "production_change_allowed": False,
        },
        [],
        [
            "resolve providers inside each domain using health, economics and Technology Radar recommendations",
            "route implementation packages through technical-design before code generation",
        ],
        [
            {"type": "functional-intent-snapshot", "path": str(snapshot)},
            {"type": "domain-plan", "path": str(output)},
        ],
    )
    emit(result, args.json)
    return 0


def handle_technical_design(args: argparse.Namespace, policy: dict[str, Any]) -> int:
    refs = policy.get("repository_paths") or {}
    tools = policy.get("engine_paths") or {}
    engine = resolve(args.repo_root, str(tools.get("technical_design_router")))
    routing = resolve(args.repo_root, str(refs.get("agent_routing")))
    design_policy = resolve(args.repo_root, str(refs.get("technical_design")))

    requirement = args.requirement if args.requirement.is_absolute() else args.repo_root / args.requirement
    manifest = args.manifest if args.manifest.is_absolute() else args.repo_root / args.manifest
    try:
        req_value = load(requirement)
    except SystemExit as exc:
        result = response(args.project, args.command, "FAILED", "Product requirement could not be loaded.",
                          {"error": str(exc)}, ["PRODUCT_REQUIREMENT_INVALID"])
        emit(result, args.json)
        return 2

    if str(req_value.get("project") or "") != args.project:
        result = response(
            args.project, args.command, "BLOCKED",
            "Product requirement project does not match requested Project Control project.",
            {"requirement_project": req_value.get("project")},
            ["PRODUCT_REQUIREMENT_PROJECT_MISMATCH"],
        )
        emit(result, args.json)
        return 2

    runtime = policy.get("runtime") or {}
    plans_root = Path(str(runtime.get("plans_root", "/opt/chacha-dev/runtime/plans")))
    out_dir = plans_root / args.project / "technical-design"
    req_id = str(req_value.get("id") or "requirement")
    safe_id = "".join(ch if ch.isalnum() or ch in "._-" else "-" for ch in req_id)
    output = args.output or (out_dir / f"{safe_id}.technical-design.json")
    graph = args.task_graph_output or (out_dir / f"{safe_id}.task-graph.json")
    out_dir.mkdir(parents=True, exist_ok=True)

    requirement_snapshot = out_dir / f"{safe_id}.requirement.json"
    manifest_snapshot = out_dir / f"{safe_id}.manifest.v3.json"
    requirement_snapshot.write_bytes(requirement.read_bytes())
    manifest_snapshot.write_bytes(manifest.read_bytes())

    rc, payload, stdout, stderr = run_json(
        engine,
        [
            "--requirement", str(requirement_snapshot),
            "--manifest", str(manifest_snapshot),
            "--routing", str(routing),
            "--policy", str(design_policy),
            "--output", str(output),
            "--task-graph-output", str(graph),
            "--json",
        ],
    )
    if rc != 0 or payload is None or payload.get("status") != "PASS":
        result = response(
            args.project, args.command, "FAILED",
            "Technical design routing failed.",
            {"stdout": stdout.strip(), "stderr": stderr.strip(), "routing_result": payload},
            ["TECHNICAL_DESIGN_ROUTING_FAILED"],
        )
        emit(result, args.json)
        return 2

    blockers = [str(x) for x in payload.get("implementation_blockers") or []]
    roles = [str(x) for x in payload.get("specialist_roles") or []]
    result = response(
        args.project,
        args.command,
        "READY",
        "Product requirement was routed to ChaCha DEV technical-design specialists; implementation remains intentionally gated.",
        {
            "requirement_id": payload.get("requirement_id"),
            "technical_design_plan": str(output),
            "technical_design_task_graph": str(graph),
            "product_requirement_snapshot": str(requirement_snapshot),
            "manifest_snapshot": str(manifest_snapshot),
            "affected_components": payload.get("affected_components") or [],
            "specialist_roles": roles,
            "backend_architect": bool(payload.get("backend_architect")),
            "data_architect": bool(payload.get("data_architect")),
            "code_generation_allowed": False,
            "implementation_blockers": blockers,
        },
        [],
        [
            "complete specialist technical-design fragments and mandatory cross-reviews",
            "record ADRs and resolve architecture decisions before implementation",
        ],
        [
            {"type": "technical-design-plan", "path": str(output)},
            {"type": "task-graph", "path": str(graph)},
            {"type": "product-requirement-snapshot", "path": str(requirement_snapshot)},
            {"type": "project-manifest-snapshot", "path": str(manifest_snapshot)},
        ],
    )
    emit(result, args.json)
    return 0


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
        if command == "functional-orchestrate":
            return handle_functional_orchestrate(args, policy)
        if command == "technical-design":
            return handle_technical_design(args, policy)
        return handle_readiness(args, policy)

    core = Path(__file__).with_name("project-control.py")
    os.execv(sys.executable, [sys.executable, str(core), *argv])
    return 127


if __name__ == "__main__":
    raise SystemExit(main())
