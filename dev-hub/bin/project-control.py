#!/usr/bin/env python3
"""ChaCha DEV HUB Project Control V1.

Unified local control surface for one project. It does not expose a network
listener. The control-plane state projection is canonical; existing engines are
invoked as isolated subprocesses with structured argv and no shell.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

POLICY_SCHEMA = "chacha.dev/project-control/v1"
STATE_SCHEMA = "chacha.dev/control-plane-state/v1"
LEDGER_SCHEMA = "chacha.dev/evidence-ledger/v1"
RESPONSE_SCHEMA = "chacha.dev/project-control-response/v1"


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
    print(f"PROJECT={value['project']}")
    print(f"OPERATION={value['operation']}")
    print(f"STATUS={value['status']}")
    print(f"SUMMARY={value['summary']}")
    for item in value.get("blockers") or []:
        print(f"BLOCKER={item}")
    for item in value.get("next_actions") or []:
        print(f"NEXT={item}")
    for key, item in (value.get("details") or {}).items():
        if isinstance(item, (str, int, float, bool)) or item is None:
            print(f"{key.upper()}={item}")


def resolve_repo(repo_root: Path, configured: str) -> Path:
    path = Path(configured)
    return path if path.is_absolute() else repo_root / path


def project_paths(policy: dict[str, Any], project: str) -> dict[str, Path]:
    runtime = policy.get("runtime") or {}
    state_root = Path(str(runtime.get("state_root", "/opt/chacha-dev/runtime/state")))
    evidence_root = Path(str(runtime.get("evidence_root", "/opt/chacha-dev/runtime/evidence")))
    plans_root = Path(str(runtime.get("plans_root", "/opt/chacha-dev/runtime/plans")))
    health_root = Path(str(runtime.get("health_root", "/opt/chacha-dev/runtime/health")))
    runs_root = Path(str(runtime.get("runs_root", "/opt/chacha-dev/runtime/runs")))
    return {
        "state": state_root / project / "state.json",
        "journal": state_root / project / "audit.jsonl",
        "ledger": evidence_root / project / "ledger.json",
        "plans": plans_root / project,
        "health": health_root / project / "providers.json",
        "runs": runs_root / project,
    }


def run_tool(tool: Path, argv: list[str], timeout: int = 60) -> tuple[int, str, str]:
    if not tool.exists():
        return 127, "", f"TOOL_NOT_FOUND={tool}"
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
        return 124, "", f"TOOL_TIMEOUT={tool}"
    return proc.returncode, proc.stdout, proc.stderr


def parse_kv(text: str) -> tuple[dict[str, str], list[str]]:
    values: dict[str, str] = {}
    blockers: list[str] = []
    for line in text.splitlines():
        if line.startswith("BLOCKER="):
            blockers.append(line.split("=", 1)[1])
        elif "=" in line and not line.startswith("==="):
            key, value = line.split("=", 1)
            if key and " " not in key:
                values[key] = value
    return values, blockers


def next_stage(lifecycle: dict[str, Any], current: str) -> str | None:
    stages = list(lifecycle.get("stages") or [])
    if current not in stages:
        return None
    idx = stages.index(current)
    return stages[idx + 1] if idx + 1 < len(stages) else None


def lifecycle_check(project: str, target: str, projection: dict[str, Any], ledger: Path,
                    lifecycle: Path, quality: Path, engine: Path) -> tuple[dict[str, str], list[str], int, str]:
    stage = str(((projection.get("state") or {}).get("lifecycle") or {}).get("stage") or "UNKNOWN")
    with tempfile.TemporaryDirectory(prefix="chacha-project-control-") as td:
        ephemeral = Path(td) / "lifecycle-state.json"
        save(ephemeral, {
            "schema": "chacha.dev/project-lifecycle-state/v1",
            "project": project,
            "current_stage": stage,
            "created_at": projection.get("created_at") or now_iso(),
            "updated_at": projection.get("updated_at") or now_iso(),
            "history": [],
        })
        rc, out, err = run_tool(engine, [
            "--lifecycle", str(lifecycle),
            "check",
            "--state", str(ephemeral),
            "--target", target,
            "--evidence", str(ledger),
            "--quality-gates", str(quality),
        ])
    values, blockers = parse_kv(out)
    return values, blockers, rc, err.strip()


def status_operation(project: str, policy: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    p = project_paths(policy, project)
    if not p["state"].exists():
        return response(project, "status", "UNKNOWN", "Control-plane state is not initialized.",
                        {"state": str(p["state"])}, ["CONTROL_PLANE_STATE_MISSING"], ["initialize project control-plane state"])
    projection = load(p["state"])
    if projection.get("schema") != STATE_SCHEMA:
        return response(project, "status", "BLOCKED", "Control-plane state schema is invalid.",
                        {"schema": projection.get("schema")}, ["CONTROL_PLANE_STATE_SCHEMA_INVALID"])
    stage = str(((projection.get("state") or {}).get("lifecycle") or {}).get("stage") or "UNKNOWN")
    lifecycle_path = resolve_repo(repo_root, (policy.get("repository_paths") or {})["lifecycle"])
    lifecycle = load(lifecycle_path)
    target = next_stage(lifecycle, stage)
    details = {
        "stage": stage,
        "version": projection.get("version"),
        "last_event_sequence": projection.get("last_event_sequence"),
        "last_event_digest": projection.get("last_event_digest"),
        "next_stage": target,
        "state": str(p["state"]),
        "ledger": str(p["ledger"]),
    }
    if target is None:
        if stage == "RETIRE":
            return response(project, "status", "COMPLETE", "Project lifecycle is complete.", details)
        return response(project, "status", "BLOCKED", "Current lifecycle stage is invalid.", details, [f"CURRENT_STAGE_INVALID:{stage}"])
    if not p["ledger"].exists():
        return response(project, "status", "BLOCKED", "Evidence ledger is missing.", details,
                        ["EVIDENCE_LEDGER_MISSING"], ["initialize evidence ledger"])
    ledger_value = load(p["ledger"])
    if ledger_value.get("schema") != LEDGER_SCHEMA:
        return response(project, "status", "BLOCKED", "Evidence ledger schema is invalid.", details,
                        ["EVIDENCE_LEDGER_SCHEMA_INVALID"])
    refs = policy.get("repository_paths") or {}
    tools = policy.get("engine_paths") or {}
    values, blockers, rc, err = lifecycle_check(
        project, target, projection, p["ledger"], lifecycle_path,
        resolve_repo(repo_root, refs["quality_gates"]),
        resolve_repo(repo_root, tools["lifecycle_engine"]),
    )
    details.update({"transition": f"{stage}->{target}", "transition_allowed": values.get("ALLOWED") == "YES"})
    if err:
        details["engine_error"] = err
    if not blockers and rc == 0:
        return response(project, "status", "READY", f"Project is ready for transition {stage}->{target}.", details,
                        next_actions=[f"plan transition {stage}->{target}"])
    approval_blockers = [x for x in blockers if x.startswith("APPROVAL_")]
    non_approval = [x for x in blockers if not x.startswith("APPROVAL_")]
    state = "AWAITING_APPROVAL" if approval_blockers and not non_approval else "BLOCKED"
    return response(project, "status", state, f"Project cannot transition {stage}->{target} yet.", details,
                    blockers, ["satisfy listed blockers", f"recheck transition {stage}->{target}"])


def plan_transition(project: str, target: str | None, policy: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    p = project_paths(policy, project)
    projection = load(p["state"])
    stage = str(((projection.get("state") or {}).get("lifecycle") or {}).get("stage") or "UNKNOWN")
    lifecycle_path = resolve_repo(repo_root, (policy.get("repository_paths") or {})["lifecycle"])
    lifecycle = load(lifecycle_path)
    target = target or next_stage(lifecycle, stage)
    if not target:
        return response(project, "plan-transition", "BLOCKED", "No next lifecycle stage exists.", {"stage": stage}, ["NO_NEXT_STAGE"])
    transition = f"{stage}->{target.upper()}"
    out = p["plans"] / (transition.replace("->", "-to-") + ".task-graph.json")
    refs, tools = policy.get("repository_paths") or {}, policy.get("engine_paths") or {}
    rc, stdout, stderr = run_tool(resolve_repo(repo_root, tools["task_graph_engine"]), [
        "--project", project,
        "--transition", transition,
        "--lifecycle", str(lifecycle_path),
        "--quality", str(resolve_repo(repo_root, refs["quality_gates"])),
        "--catalog", str(resolve_repo(repo_root, refs["evidence_catalog"])),
        "--orchestration", str(resolve_repo(repo_root, refs["orchestration"])),
        "--output", str(out),
    ])
    if rc != 0:
        return response(project, "plan-transition", "FAILED", "Task Graph generation failed.",
                        {"transition": transition, "stderr": stderr.strip(), "stdout": stdout.strip()}, ["TASK_GRAPH_GENERATION_FAILED"])
    return response(project, "plan-transition", "OK", f"Task Graph prepared for {transition}.",
                    {"transition": transition, "task_graph": str(out)}, artifacts=[{"type": "task-graph", "path": str(out)}])


def schedule_operation(project: str, graph: Path | None, policy: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    p = project_paths(policy, project)
    if not p["state"].exists():
        return response(project, "schedule", "BLOCKED", "Control-plane state missing.", blockers=["CONTROL_PLANE_STATE_MISSING"])
    projection = load(p["state"])
    stage = str(((projection.get("state") or {}).get("lifecycle") or {}).get("stage") or "UNKNOWN")
    lifecycle = load(resolve_repo(repo_root, (policy.get("repository_paths") or {})["lifecycle"]))
    target = next_stage(lifecycle, stage)
    if not target:
        return response(project, "schedule", "BLOCKED", "No schedulable next transition.", blockers=["NO_NEXT_STAGE"])
    transition = f"{stage}->{target}"
    graph = graph or p["plans"] / (transition.replace("->", "-to-") + ".task-graph.json")
    if not graph.exists():
        return response(project, "schedule", "BLOCKED", "Task Graph does not exist.", {"task_graph": str(graph)}, ["TASK_GRAPH_MISSING"], ["run plan-transition"])
    if not p["health"].exists():
        return response(project, "schedule", "BLOCKED", "Provider health snapshot does not exist.", {"health": str(p["health"])}, ["PROVIDER_HEALTH_SNAPSHOT_MISSING"])
    out = p["plans"] / (transition.replace("->", "-to-") + ".execution-plan.json")
    refs, tools = policy.get("repository_paths") or {}, policy.get("engine_paths") or {}
    rc, stdout, stderr = run_tool(resolve_repo(repo_root, tools["execution_scheduler"]), [
        "--graph", str(graph),
        "--registry", str(resolve_repo(repo_root, refs["capability_registry"])),
        "--health", str(p["health"]),
        "--policy", str(resolve_repo(repo_root, refs["execution_scheduler"])),
        "--output", str(out),
    ])
    if rc != 0:
        return response(project, "schedule", "FAILED", "Execution scheduling failed.",
                        {"stderr": stderr.strip(), "stdout": stdout.strip()}, ["EXECUTION_SCHEDULER_FAILED"])
    plan = load(out)
    blocked = [f"TASK_BLOCKED:{x.get('task_id')}:{'|'.join(x.get('reasons') or [])}" for x in plan.get("blocked_tasks") or []]
    status = "BLOCKED" if blocked else "OK"
    return response(project, "schedule", status, f"Execution plan prepared for {transition}.",
                    {"execution_plan": str(out), "summary": plan.get("summary")}, blocked,
                    artifacts=[{"type": "execution-plan", "path": str(out)}])


def prepare_or_dispatch(project: str, execute: bool, plan: Path, graph: Path, workspace: str | None,
                        policy: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    p = project_paths(policy, project)
    if not p["ledger"].exists():
        return response(project, "dispatch" if execute else "prepare-run", "BLOCKED", "Evidence ledger missing.", blockers=["EVIDENCE_LEDGER_MISSING"])
    refs, tools = policy.get("repository_paths") or {}, policy.get("engine_paths") or {}
    argv = [
        "--plan", str(plan), "--graph", str(graph), "--ledger", str(p["ledger"]),
        "--policy", str(resolve_repo(repo_root, refs["run_controller"])),
        "--adapters", str(resolve_repo(repo_root, refs["provider_adapters"])),
        "--output-dir", str(p["runs"]),
    ]
    if workspace:
        argv += ["--workspace", workspace]
    if execute:
        argv.append("--execute")
    rc, stdout, stderr = run_tool(resolve_repo(repo_root, tools["run_controller"]), argv, timeout=3700 if execute else 120)
    values, blockers = parse_kv(stdout)
    operation = "dispatch" if execute else "prepare-run"
    if rc != 0:
        detail = {"stdout": stdout.strip(), "stderr": stderr.strip(), **values}
        if execute and "EXECUTION_DISABLED_BY_POLICY" in stderr + stdout:
            blockers.append("EXECUTION_DISABLED_BY_POLICY")
        return response(project, operation, "BLOCKED" if blockers else "FAILED", "Run Controller did not complete.", detail, blockers or ["RUN_CONTROLLER_FAILED"])
    return response(project, operation, "OK", "Run Controller completed in requested mode.", values,
                    artifacts=[{"type": "run-record", "path": values.get("RUN_RECORD")}])


def verify_state(project: str, policy: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    refs, tools = policy.get("repository_paths") or {}, policy.get("engine_paths") or {}
    state_policy = resolve_repo(repo_root, refs["control_plane_state"])
    root = Path(str((load(state_policy).get("storage") or {}).get("runtime_root", "/opt/chacha-dev/runtime/state")))
    rc, stdout, stderr = run_tool(resolve_repo(repo_root, tools["control_plane_store"]), [
        "--policy", str(state_policy), "--root", str(root), "verify", "--project", project,
    ])
    values, blockers = parse_kv(stdout)
    if rc != 0:
        return response(project, "verify-state", "FAILED", "Control-plane integrity verification failed.",
                        {"stdout": stdout.strip(), "stderr": stderr.strip(), **values}, blockers or ["CONTROL_PLANE_INTEGRITY_FAILED"])
    return response(project, "verify-state", "OK", "Control-plane projection and audit chain verify.", values)


def crypto_verify(project: str, checkpoint: Path, public_key: Path, policy: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    refs, tools = policy.get("repository_paths") or {}, policy.get("engine_paths") or {}
    rc, stdout, stderr = run_tool(resolve_repo(repo_root, tools["crypto_trust"]), [
        "--policy", str(resolve_repo(repo_root, refs["cryptographic_trust"])),
        "verify", "--checkpoint", str(checkpoint), "--public-key", str(public_key),
    ])
    values, _ = parse_kv(stdout)
    if rc != 0:
        errors = values.get("ERRORS", "SIGNATURE_VERIFICATION_FAILED").split(",")
        return response(project, "crypto-verify", "FAILED", "Signed checkpoint verification failed.",
                        {"stdout": stdout.strip(), "stderr": stderr.strip(), **values}, errors)
    return response(project, "crypto-verify", "OK", "Signed checkpoint is cryptographically valid.", values)


def main() -> int:
    parser = argparse.ArgumentParser(description="ChaCha DEV HUB unified project control")
    parser.add_argument("--policy", type=Path, default=Path("dev-hub/config/project-control.v1.json"))
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--json", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    for name in ("status", "explain", "verify-state"):
        item = sub.add_parser(name)
        item.add_argument("--project", required=True)

    plan = sub.add_parser("plan-transition")
    plan.add_argument("--project", required=True)
    plan.add_argument("--target")

    sched = sub.add_parser("schedule")
    sched.add_argument("--project", required=True)
    sched.add_argument("--graph", type=Path)

    prep = sub.add_parser("prepare-run")
    prep.add_argument("--project", required=True)
    prep.add_argument("--plan", required=True, type=Path)
    prep.add_argument("--graph", required=True, type=Path)
    prep.add_argument("--workspace")

    dispatch = sub.add_parser("dispatch")
    dispatch.add_argument("--project", required=True)
    dispatch.add_argument("--plan", required=True, type=Path)
    dispatch.add_argument("--graph", required=True, type=Path)
    dispatch.add_argument("--workspace")
    dispatch.add_argument("--execute", action="store_true")

    crypto = sub.add_parser("crypto-verify")
    crypto.add_argument("--project", required=True)
    crypto.add_argument("--checkpoint", required=True, type=Path)
    crypto.add_argument("--public-key", required=True, type=Path)

    args = parser.parse_args()
    policy_path = args.policy if args.policy.is_absolute() else args.repo_root / args.policy
    policy = load(policy_path)
    if policy.get("schema") != POLICY_SCHEMA:
        raise SystemExit(f"POLICY_SCHEMA_INVALID={policy.get('schema')}")

    if args.command in {"status", "explain"}:
        result = status_operation(args.project, policy, args.repo_root)
        result["operation"] = args.command
    elif args.command == "verify-state":
        result = verify_state(args.project, policy, args.repo_root)
    elif args.command == "plan-transition":
        result = plan_transition(args.project, args.target, policy, args.repo_root)
    elif args.command == "schedule":
        result = schedule_operation(args.project, args.graph, policy, args.repo_root)
    elif args.command == "prepare-run":
        result = prepare_or_dispatch(args.project, False, args.plan, args.graph, args.workspace, policy, args.repo_root)
    elif args.command == "dispatch":
        if not args.execute:
            result = response(args.project, "dispatch", "BLOCKED", "Dispatch requires the explicit --execute flag.", blockers=["EXPLICIT_DISPATCH_FLAG_REQUIRED"])
        else:
            result = prepare_or_dispatch(args.project, True, args.plan, args.graph, args.workspace, policy, args.repo_root)
    elif args.command == "crypto-verify":
        result = crypto_verify(args.project, args.checkpoint, args.public_key, policy, args.repo_root)
    else:
        raise SystemExit("UNKNOWN_COMMAND")

    emit(result, args.json)
    return 0 if result["status"] in {"READY", "OK", "COMPLETE"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
