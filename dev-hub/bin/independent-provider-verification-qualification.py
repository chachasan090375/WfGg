#!/usr/bin/env python3
"""Qualify Chrome -> Playwright -> Broker verification through Project Control."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT = "dev-hub-v5-independent-provider-verification"


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


def run(argv: list[str], cwd: Path, expect: set[int] = {0}, env: dict[str, str] | None = None,
        timeout: int = 300) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(argv, cwd=str(cwd), env=env or os.environ.copy(), stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, text=True, shell=False, check=False, timeout=timeout)
    if proc.returncode not in expect:
        raise SystemExit(f"COMMAND_FAILED={proc.returncode}:{' '.join(argv)}\nSTDOUT={proc.stdout}\nSTDERR={proc.stderr}")
    return proc


def pc(repo: Path, policy: Path, args: list[str], expect: set[int] = {0}, env: dict[str, str] | None = None) -> dict[str, Any]:
    proc = run(["python3", "dev-hub/bin/project-control.py", "--policy", str(policy),
                "--repo-root", str(repo), "--json", *args], repo, expect, env, 600)
    try:
        value = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"PROJECT_CONTROL_JSON_INVALID={exc}:{proc.stdout}:{proc.stderr}")
    if not isinstance(value, dict):
        raise SystemExit("PROJECT_CONTROL_RESPONSE_NOT_OBJECT")
    return value


def graph(path: Path, target_url: str) -> None:
    subject = {"kind": "browser-page", "target_url": target_url}
    save(path, {
        "schema": "chacha.dev/task-graph/v1",
        "project": PROJECT,
        "transition": "IDEA->DESIGN",
        "generated_at": now_iso(),
        "tasks": [
            {
                "id": "observe:chrome",
                "kind": "artifact",
                "description": "Observe target with Chrome DevTools MCP",
                "owner_role": "orchestrator",
                "capabilities": ["browser-diagnostics-external"],
                "permission": "read",
                "depends_on": [],
                "outputs": [{"type": "artifact", "id": "chrome-devtools-mcp-controlled-diagnostics"}],
                "verification": {"mode": "independent-agent", "self_certification_allowed": False,
                                 "required_evidence": ["source", "timestamp", "digest"]},
                "blocking": True,
                "parallel_group": "cross-provider",
                "metadata": {
                    "verification_subject": subject,
                    "chrome_devtools_mcp": {"operation": "inspect_url", "url": target_url}
                }
            },
            {
                "id": "corroborate:playwright",
                "kind": "gate",
                "description": "Independently observe the same target with Playwright MCP",
                "owner_role": "verification-broker",
                "capabilities": ["browser-independent-verification-external"],
                "permission": "read",
                "depends_on": ["observe:chrome"],
                "outputs": [{"type": "gate", "id": "playwright-readonly-browser-verification"}],
                "verification": {"mode": "machine", "self_certification_allowed": False,
                                 "required_evidence": ["source", "timestamp", "digest"]},
                "blocking": True,
                "parallel_group": "cross-provider",
                "metadata": {"verification_subject": subject, "target_url": target_url}
            }
        ],
        "summary": {"task_count": 2, "artifact_tasks": 1, "gate_tasks": 1,
                    "approval_tasks": 0, "blocking_tasks": 2}
    })


def result_paths(record: dict[str, Any]) -> dict[str, Path]:
    found: dict[str, Path] = {}
    for wave in record.get("waves") or []:
        if not isinstance(wave, dict):
            continue
        for item in wave.get("tasks") or []:
            if isinstance(item, dict) and item.get("task_id") and item.get("task_result"):
                found[str(item["task_id"])] = Path(str(item["task_result"]))
    return found


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", required=True, type=Path)
    ap.add_argument("--work-dir", required=True, type=Path)
    ap.add_argument("--target-url", required=True)
    ap.add_argument("--output", required=True, type=Path)
    args = ap.parse_args()
    repo, root = args.repo_root.resolve(), args.work_dir.resolve()
    root.mkdir(parents=True, exist_ok=True)

    canonical = load(repo / "dev-hub/config/provider-adapters.v1.json")
    for aid in ("chrome-devtools-mcp-adapter", "playwright-mcp-adapter"):
        item = (canonical.get("adapters") or {}).get(aid) or {}
        if item.get("status") != "ENABLED" or item.get("executable") is not None or item.get("supports") != ["read"]:
            raise SystemExit(f"CANONICAL_EXTERNAL_ADAPTER_INVARIANT_FAILED:{aid}:{item}")

    state_root, evidence_root = root / "state", root / "evidence"
    plans_root, health_root, runs_root = root / "plans", root / "health", root / "runs"
    tx_root, locks_root = root / "transactions", root / "locks"

    state_policy = load(repo / "dev-hub/config/control-plane-state.v1.json")
    state_policy["storage"]["runtime_root"] = str(state_root)
    state_policy["storage"]["transaction_root"] = str(tx_root)
    state_policy_path = root / "control-plane-state.json"; save(state_policy_path, state_policy)

    scheduler_policy = load(repo / "dev-hub/config/execution-scheduler.v1.json")
    scheduler_policy_path = root / "execution-scheduler.json"; save(scheduler_policy_path, scheduler_policy)
    run_policy = load(repo / "dev-hub/config/run-controller.v1.json")
    run_policy["mode"] = "execute-enabled"
    run_policy["locking"]["root"] = str(locks_root / "dispatch")
    run_policy_path = root / "run-controller.json"; save(run_policy_path, run_policy)

    registry_path = root / "capability-registry.json"
    save(registry_path, {
        "schema": "chacha.dev/capability-registry/v1",
        "policy": {"provider_selection": "best-fit-with-fallback", "production_change_requires_approval": True,
                   "record_provider_for_consequential_decisions": True, "health_required_for_execution": True},
        "capabilities": {
            "browser-diagnostics-external": {"class": "verification", "providers": [{
                "id": "chrome-devtools-mcp", "status": "ADOPT", "health": "runtime",
                "cost_class": "free", "scope": "ci-isolated", "fallback": []}]},
            "browser-independent-verification-external": {"class": "verification", "providers": [{
                "id": "playwright-mcp", "status": "ADOPT", "health": "runtime",
                "cost_class": "free", "scope": "ci-isolated", "fallback": []}]}
        }
    })

    project_policy = load(repo / "dev-hub/config/project-control.v1.json")
    project_policy["runtime"].update({"state_root": str(state_root), "evidence_root": str(evidence_root),
        "plans_root": str(plans_root), "health_root": str(health_root), "runs_root": str(runs_root),
        "transactions_root": str(tx_root), "locks_root": str(locks_root / "control")})
    project_policy["repository_paths"]["capability_registry"] = str(registry_path)
    project_policy["repository_paths"]["execution_scheduler"] = str(scheduler_policy_path)
    project_policy["repository_paths"]["run_controller"] = str(run_policy_path)
    project_policy["repository_paths"]["control_plane_state"] = str(state_policy_path)
    project_policy_path = root / "project-control.json"; save(project_policy_path, project_policy)

    graph_path = root / "task-graph.json"; graph(graph_path, args.target_url)
    save(health_root / PROJECT / "providers.json", {
        "schema": "chacha.dev/provider-health-snapshot/v1", "observed_at": now_iso(),
        "providers": {
            "chrome-devtools-mcp": {"state": "HEALTHY", "source": "cross-provider-qualification", "checked_at": now_iso()},
            "playwright-mcp": {"state": "HEALTHY", "source": "cross-provider-qualification", "checked_at": now_iso()}
        }
    })

    run(["python3", "dev-hub/bin/control-plane-store.py", "--policy", str(state_policy_path),
         "--root", str(state_root), "init", "--project", PROJECT, "--actor", "qualification-harness"], repo)
    ledger = evidence_root / PROJECT / "ledger.json"
    run(["python3", "dev-hub/bin/evidence-collector.py", "init", "--project", PROJECT, "--ledger", str(ledger)], repo)

    schedule = pc(repo, project_policy_path, ["schedule", "--project", PROJECT, "--graph", str(graph_path)])
    if schedule.get("status") != "OK":
        raise SystemExit(f"CROSS_PROVIDER_SCHEDULE_FAILED={schedule}")
    plan_path = Path(str((schedule.get("details") or {}).get("execution_plan") or ""))
    plan = load(plan_path)
    providers = [b.get("provider") for w in plan.get("waves") or [] for t in w.get("tasks") or []
                 for b in t.get("provider_bindings") or [] if isinstance(b, dict)]
    if providers != ["chrome-devtools-mcp", "playwright-mcp"]:
        raise SystemExit(f"CROSS_PROVIDER_SELECTION_INVALID={providers}")

    env = os.environ.copy()
    dispatch = pc(repo, project_policy_path, ["dispatch", "--project", PROJECT, "--plan", str(plan_path),
                                                   "--graph", str(graph_path), "--execute"], env=env)
    if dispatch.get("status") != "OK":
        raise SystemExit(f"CROSS_PROVIDER_DISPATCH_FAILED={dispatch}")
    run_record_path = Path(str((dispatch.get("details") or {}).get("RUN_RECORD") or ""))
    run_id = str((dispatch.get("details") or {}).get("RUN_ID") or "")
    record = load(run_record_path)
    if (record.get("summary") or {}).get("succeeded") != 2:
        raise SystemExit(f"CROSS_PROVIDER_RUN_FAILED={record.get('summary')}")
    results = result_paths(record)
    chrome_path = results.get("observe:chrome"); playwright_path = results.get("corroborate:playwright")
    if not chrome_path or not playwright_path:
        raise SystemExit(f"CROSS_PROVIDER_RESULTS_MISSING={results}")
    chrome, playwright = load(chrome_path), load(playwright_path)
    if chrome.get("status") != "OK" or chrome.get("producer") != "chrome-devtools-mcp-adapter":
        raise SystemExit(f"CHROME_RESULT_INVALID={chrome}")
    if playwright.get("status") != "OK" or playwright.get("producer") != "playwright-mcp-adapter":
        raise SystemExit(f"PLAYWRIGHT_RESULT_INVALID={playwright}")
    if (chrome.get("verification") or {}).get("status") != "UNVERIFIED" or (playwright.get("verification") or {}).get("status") != "UNVERIFIED":
        raise SystemExit("PROVIDER_SELF_VERIFICATION_BOUNDARY_FAILED")

    # No independent result: source must remain blocked.
    no_independent_env = env.copy(); no_independent_env.pop("CHACHA_DEV_INDEPENDENT_RESULT", None)
    no_independent = pc(repo, project_policy_path, ["verify-result", "--project", PROJECT,
        "--result", str(chrome_path), "--graph", str(graph_path), "--method", "independent-agent",
        "--verifier", "verification-broker"], expect={2}, env=no_independent_env)
    if no_independent.get("status") != "BLOCKED":
        raise SystemExit(f"MISSING_INDEPENDENT_RESULT_NOT_BLOCKED={no_independent}")

    # A second result cannot masquerade as the producer.
    bad = deepcopy(playwright); bad["producer"] = "chrome-devtools-mcp-adapter"
    bad_path = root / "bad-independent-result.json"; save(bad_path, bad)
    bad_env = env.copy(); bad_env["CHACHA_DEV_INDEPENDENT_RESULT"] = str(bad_path)
    bad_resp = pc(repo, project_policy_path, ["verify-result", "--project", PROJECT,
        "--result", str(chrome_path), "--graph", str(graph_path), "--method", "independent-agent",
        "--verifier", "verification-broker"], expect={2}, env=bad_env)
    if bad_resp.get("status") != "FAILED":
        raise SystemExit(f"SAME_PRODUCER_NOT_REJECTED={bad_resp}")

    # Correct independent observation: Broker alone promotes source to VERIFIED and Project Control ingests it.
    verify_env = env.copy(); verify_env["CHACHA_DEV_INDEPENDENT_RESULT"] = str(playwright_path)
    verified = pc(repo, project_policy_path, ["verify-result", "--project", PROJECT,
        "--result", str(chrome_path), "--graph", str(graph_path), "--method", "independent-agent",
        "--verifier", "verification-broker", "--ingest"], env=verify_env)
    if verified.get("status") != "OK" or (verified.get("details") or {}).get("verification_status") != "VERIFIED":
        raise SystemExit(f"CROSS_PROVIDER_VERIFICATION_FAILED={verified}")
    ledger_value = load(ledger)
    artifact = (ledger_value.get("artifacts") or {}).get("chrome-devtools-mcp-controlled-diagnostics") or {}
    if artifact.get("status") != "OK" or artifact.get("producer") != "chrome-devtools-mcp-adapter" or artifact.get("verifier") != "verification-broker" or artifact.get("verification_method") != "independent-agent":
        raise SystemExit(f"CROSS_PROVIDER_LEDGER_INVALID={artifact}")
    integrity = pc(repo, project_policy_path, ["verify-state", "--project", PROJECT])
    if integrity.get("status") != "OK":
        raise SystemExit(f"CROSS_PROVIDER_AUDIT_INVALID={integrity}")

    out = {
        "schema": "chacha.dev/independent-provider-verification-qualification/v1",
        "project": PROJECT, "observed_at": now_iso(), "status": "PASS",
        "run_id": run_id, "run_record": str(run_record_path),
        "source_provider": "chrome-devtools-mcp", "source_adapter": "chrome-devtools-mcp-adapter",
        "independent_provider": "playwright-mcp", "independent_adapter": "playwright-mcp-adapter",
        "source_result": str(chrome_path), "independent_result": str(playwright_path),
        "source_entered_unverified": True, "independent_result_remained_unverified": True,
        "missing_independent_result_blocked": True, "same_producer_rejected": True,
        "broker_final_status": "VERIFIED", "ledger_status": artifact.get("status"),
        "audit_integrity": "PASS", "repository_mutated": False, "production_touched": False,
        "blockers": []
    }
    save(args.output, out)
    print(f"INDEPENDENT_PROVIDER_VERIFICATION_QUALIFICATION={args.output}")
    print("INDEPENDENT_PROVIDER_VERIFICATION_STATUS=PASS")
    print(f"RUN_ID={run_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
