#!/usr/bin/env python3
"""Qualify runner-owned external runtime bindings through Project Control.

This harness is CI-only. It builds an isolated control-plane runtime under /tmp,
uses the canonical ENABLED chrome-devtools-mcp adapter mapping, schedules one
read task, dispatches it through Project Control and proves fail-closed behavior
for missing, tampered and expired runtime bindings.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT = "dev-hub-v5-external-runtime-binding-qualification"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit(f"JSON_ROOT_NOT_OBJECT={path}")
    return value


def save(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def run(argv: list[str], cwd: Path, expect: set[int] = {0}, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        argv, cwd=str(cwd), env=env or os.environ.copy(),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        shell=False, check=False, timeout=180,
    )
    if proc.returncode not in expect:
        raise SystemExit(
            f"COMMAND_FAILED={proc.returncode}:{' '.join(argv)}\nSTDOUT={proc.stdout}\nSTDERR={proc.stderr}"
        )
    return proc


def project_control(repo: Path, policy: Path, args: list[str], expect: set[int] = {0}, env: dict[str, str] | None = None) -> dict[str, Any]:
    proc = run(
        ["python3", "dev-hub/bin/project-control.py", "--policy", str(policy), "--repo-root", str(repo), "--json", *args],
        repo, expect=expect, env=env,
    )
    try:
        value = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"PROJECT_CONTROL_JSON_INVALID={exc}:{proc.stdout}:{proc.stderr}")
    if not isinstance(value, dict):
        raise SystemExit("PROJECT_CONTROL_RESPONSE_NOT_OBJECT")
    return value


def task_graph(path: Path, target_url: str) -> None:
    save(path, {
        "schema": "chacha.dev/task-graph/v1",
        "project": PROJECT,
        "transition": "IDEA->DESIGN",
        "generated_at": now_iso(),
        "tasks": [{
            "id": "external-runtime:chrome-devtools",
            "kind": "artifact",
            "description": "Qualify external runtime binding with Chrome DevTools MCP",
            "owner_role": "orchestrator",
            "capabilities": ["external-runtime-test"],
            "permission": "read",
            "depends_on": [],
            "outputs": [{"type": "artifact", "id": "external-runtime-binding-report"}],
            "verification": {
                "mode": "machine",
                "self_certification_allowed": False,
                "required_evidence": ["source", "timestamp", "digest"]
            },
            "blocking": True,
            "parallel_group": "external-runtime",
            "metadata": {
                "chrome_devtools_mcp": {
                    "operation": "inspect_url",
                    "url": target_url,
                    "expected_text": "CHACHA_EXTERNAL_RUNTIME_OK"
                }
            }
        }],
        "summary": {
            "task_count": 1,
            "artifact_tasks": 1,
            "gate_tasks": 0,
            "approval_tasks": 0,
            "blocking_tasks": 1
        }
    })


def find_result(run_record: dict[str, Any]) -> Path:
    for wave in run_record.get("waves") or []:
        if not isinstance(wave, dict):
            continue
        for task in wave.get("tasks") or []:
            if isinstance(task, dict) and task.get("task_id") == "external-runtime:chrome-devtools":
                raw = task.get("task_result")
                if raw:
                    return Path(str(raw))
    raise SystemExit("EXTERNAL_RUNTIME_TASK_RESULT_MISSING")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", required=True, type=Path)
    parser.add_argument("--work-dir", required=True, type=Path)
    parser.add_argument("--target-url", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    repo = args.repo_root.resolve()
    root = args.work_dir.resolve()
    root.mkdir(parents=True, exist_ok=True)

    binding_file = os.environ.get("CHACHA_DEV_RUNTIME_BINDINGS", "").strip()
    if not binding_file:
        raise SystemExit("QUALIFICATION_RUNTIME_BINDING_ENV_MISSING")
    binding_path = Path(binding_file)
    if not binding_path.is_file():
        raise SystemExit("QUALIFICATION_RUNTIME_BINDING_FILE_MISSING")

    canonical_adapters = load(repo / "dev-hub/config/provider-adapters.v1.json")
    chrome_static = (canonical_adapters.get("adapters") or {}).get("chrome-devtools-mcp-adapter") or {}
    if chrome_static.get("status") != "ENABLED" or chrome_static.get("executable") is not None:
        raise SystemExit(f"CANONICAL_CHROME_EXTERNAL_INVARIANT_FAILED={chrome_static}")

    state_root = root / "state"
    evidence_root = root / "evidence"
    plans_root = root / "plans"
    health_root = root / "health"
    runs_root = root / "runs"
    tx_root = root / "transactions"
    locks_root = root / "locks"

    state_policy = load(repo / "dev-hub/config/control-plane-state.v1.json")
    state_policy["storage"]["runtime_root"] = str(state_root)
    state_policy["storage"]["transaction_root"] = str(tx_root)
    state_policy_path = root / "control-plane-state.json"
    save(state_policy_path, state_policy)

    scheduler_policy = load(repo / "dev-hub/config/execution-scheduler.v1.json")
    scheduler_policy_path = root / "execution-scheduler.json"
    save(scheduler_policy_path, scheduler_policy)

    run_policy = load(repo / "dev-hub/config/run-controller.v1.json")
    run_policy["mode"] = "execute-enabled"
    run_policy["locking"]["root"] = str(locks_root / "dispatch")
    run_policy_path = root / "run-controller.json"
    save(run_policy_path, run_policy)

    registry_path = root / "capability-registry.json"
    save(registry_path, {
        "schema": "chacha.dev/capability-registry/v1",
        "policy": {
            "provider_selection": "best-fit-with-fallback",
            "production_change_requires_approval": True,
            "record_provider_for_consequential_decisions": True,
            "health_required_for_execution": True
        },
        "capabilities": {
            "external-runtime-test": {
                "class": "verification",
                "providers": [{
                    "id": "chrome-devtools-mcp",
                    "status": "ADOPT",
                    "health": "runtime",
                    "cost_class": "free",
                    "scope": "ci-isolated",
                    "fallback": []
                }]
            }
        }
    })

    project_policy = load(repo / "dev-hub/config/project-control.v1.json")
    project_policy["runtime"].update({
        "state_root": str(state_root),
        "evidence_root": str(evidence_root),
        "plans_root": str(plans_root),
        "health_root": str(health_root),
        "runs_root": str(runs_root),
        "transactions_root": str(tx_root),
        "locks_root": str(locks_root / "control")
    })
    project_policy["repository_paths"]["capability_registry"] = str(registry_path)
    project_policy["repository_paths"]["execution_scheduler"] = str(scheduler_policy_path)
    project_policy["repository_paths"]["run_controller"] = str(run_policy_path)
    project_policy["repository_paths"]["control_plane_state"] = str(state_policy_path)
    project_policy_path = root / "project-control.json"
    save(project_policy_path, project_policy)

    graph_path = root / "task-graph.json"
    task_graph(graph_path, args.target_url)

    health_path = health_root / PROJECT / "providers.json"
    save(health_path, {
        "schema": "chacha.dev/provider-health-snapshot/v1",
        "observed_at": now_iso(),
        "providers": {
            "chrome-devtools-mcp": {
                "state": "HEALTHY",
                "source": "external-runtime-binding-qualification",
                "checked_at": now_iso()
            }
        }
    })

    run([
        "python3", "dev-hub/bin/control-plane-store.py",
        "--policy", str(state_policy_path), "--root", str(state_root),
        "init", "--project", PROJECT, "--actor", "qualification-harness"
    ], repo)
    ledger_path = evidence_root / PROJECT / "ledger.json"
    run([
        "python3", "dev-hub/bin/evidence-collector.py", "init",
        "--project", PROJECT, "--ledger", str(ledger_path)
    ], repo)

    schedule = project_control(repo, project_policy_path, [
        "schedule", "--project", PROJECT, "--graph", str(graph_path)
    ])
    if schedule.get("status") != "OK":
        raise SystemExit(f"EXTERNAL_RUNTIME_SCHEDULE_FAILED={schedule}")
    plan_path = Path(str((schedule.get("details") or {}).get("execution_plan") or ""))
    if not plan_path.is_file():
        raise SystemExit("EXTERNAL_RUNTIME_PLAN_MISSING")
    plan = load(plan_path)
    bindings = (((plan.get("waves") or [{}])[0].get("tasks") or [{}])[0].get("provider_bindings") or [])
    if not any(x.get("provider") == "chrome-devtools-mcp" for x in bindings if isinstance(x, dict)):
        raise SystemExit(f"EXTERNAL_RUNTIME_PROVIDER_NOT_SELECTED={bindings}")

    env = os.environ.copy()
    dispatch = project_control(repo, project_policy_path, [
        "dispatch", "--project", PROJECT, "--plan", str(plan_path), "--graph", str(graph_path), "--execute"
    ], env=env)
    if dispatch.get("status") != "OK":
        raise SystemExit(f"EXTERNAL_RUNTIME_DISPATCH_FAILED={dispatch}")
    details = dispatch.get("details") or {}
    run_id = details.get("RUN_ID")
    run_record_path = Path(str(details.get("RUN_RECORD") or ""))
    if not run_id or not run_record_path.is_file():
        raise SystemExit(f"EXTERNAL_RUNTIME_RUN_CORRELATION_FAILED={details}")
    run_record = load(run_record_path)
    if (run_record.get("summary") or {}).get("succeeded") != 1:
        raise SystemExit(f"EXTERNAL_RUNTIME_RUN_NOT_SUCCESS={run_record.get('summary')}")
    result_path = find_result(run_record)
    result = load(result_path)
    if result.get("status") != "OK" or result.get("producer") != "chrome-devtools-mcp-adapter":
        raise SystemExit(f"EXTERNAL_RUNTIME_PROVIDER_RESULT_INVALID={result}")
    verification = result.get("verification") if isinstance(result.get("verification"), dict) else {}
    if verification.get("status") != "UNVERIFIED" or verification.get("method") != "none":
        raise SystemExit(f"EXTERNAL_RUNTIME_TRUST_BOUNDARY_FAILED={verification}")

    # Missing runner binding must block before Run Controller execution.
    missing_env = env.copy()
    missing_env.pop("CHACHA_DEV_RUNTIME_BINDINGS", None)
    missing = project_control(repo, project_policy_path, [
        "dispatch", "--project", PROJECT, "--plan", str(plan_path), "--graph", str(graph_path), "--execute"
    ], expect={2}, env=missing_env)
    if missing.get("status") != "BLOCKED" or "EXTERNAL_RUNTIME_BINDING_PATH_MISSING" not in "|".join(missing.get("blockers") or []):
        raise SystemExit(f"EXTERNAL_RUNTIME_MISSING_BINDING_NOT_BLOCKED={missing}")

    original_binding = load(binding_path)
    bad_digest = deepcopy(original_binding)
    bad_digest["bindings"]["chrome-devtools-mcp-adapter"]["digest"] = "sha256:" + "0" * 64
    bad_digest_path = root / "runtime-bindings-bad-digest.json"
    save(bad_digest_path, bad_digest)
    bad_env = env.copy(); bad_env["CHACHA_DEV_RUNTIME_BINDINGS"] = str(bad_digest_path)
    bad = project_control(repo, project_policy_path, [
        "dispatch", "--project", PROJECT, "--plan", str(plan_path), "--graph", str(graph_path), "--execute"
    ], expect={2}, env=bad_env)
    if bad.get("status") != "BLOCKED" or "EXTERNAL_RUNTIME_DIGEST_MISMATCH" not in "|".join(bad.get("blockers") or []):
        raise SystemExit(f"EXTERNAL_RUNTIME_BAD_DIGEST_NOT_BLOCKED={bad}")

    expired = deepcopy(original_binding)
    expired["issued_at"] = "2026-01-01T00:00:00+00:00"
    expired["expires_at"] = "2026-01-01T00:10:00+00:00"
    expired_path = root / "runtime-bindings-expired.json"
    save(expired_path, expired)
    expired_env = env.copy(); expired_env["CHACHA_DEV_RUNTIME_BINDINGS"] = str(expired_path)
    expired_resp = project_control(repo, project_policy_path, [
        "dispatch", "--project", PROJECT, "--plan", str(plan_path), "--graph", str(graph_path), "--execute"
    ], expect={2}, env=expired_env)
    if expired_resp.get("status") != "BLOCKED" or "EXTERNAL_RUNTIME_BINDING_EXPIRED" not in "|".join(expired_resp.get("blockers") or []):
        raise SystemExit(f"EXTERNAL_RUNTIME_EXPIRED_BINDING_NOT_BLOCKED={expired_resp}")

    evidence = {
        "schema": "chacha.dev/external-runtime-binding-qualification/v1",
        "project": PROJECT,
        "observed_at": now_iso(),
        "status": "PASS",
        "provider": "chrome-devtools-mcp",
        "adapter": "chrome-devtools-mcp-adapter",
        "canonical_registry_status": chrome_static.get("status"),
        "canonical_registry_executable": chrome_static.get("executable"),
        "runtime_binding_source": original_binding.get("source"),
        "runtime_binding_file_outside_repository": True,
        "run_id": run_id,
        "run_record": str(run_record_path),
        "provider_result": str(result_path),
        "provider_result_status": result.get("status"),
        "provider_result_verification": verification.get("status"),
        "schedule_provider_selected": True,
        "project_control_dispatch_pass": True,
        "missing_binding_blocked": True,
        "digest_mismatch_blocked": True,
        "expired_binding_blocked": True,
        "task_selected_executable": False,
        "registry_mutated": False,
        "production_touched": False,
        "blockers": []
    }
    save(args.output, evidence)
    print(f"EXTERNAL_RUNTIME_BINDING_QUALIFICATION={args.output}")
    print("EXTERNAL_RUNTIME_BINDING_STATUS=PASS")
    print(f"RUN_ID={run_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
