#!/usr/bin/env python3
"""ChaCha DEV HUB canonical project-manifest orchestrator V1.

Turns a provider-agnostic project manifest into a Task Graph, asks Project Control
for scheduling/dispatch, and—when execution is explicit—feeds the independent
provider result to the provider-aware Verification Broker through Project Control.
The manifest never selects a provider or executable.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

MANIFEST_SCHEMA = "chacha.dev/project-manifest/v1"
CONTRACT_SCHEMA = "chacha.dev/project-manifest-contract/v1"
GRAPH_SCHEMA = "chacha.dev/task-graph/v1"
REGISTRY_SCHEMA = "chacha.dev/capability-registry/v1"
PROJECT_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$")


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


def resolve(repo: Path, value: str) -> Path:
    p = Path(value)
    return p if p.is_absolute() else repo / p


def run(argv: list[str], cwd: Path, env: dict[str, str] | None = None, expect: set[int] = {0}, timeout: int = 900) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(argv, cwd=str(cwd), env=env or os.environ.copy(), stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, text=True, shell=False, check=False, timeout=timeout)
    if proc.returncode not in expect:
        raise SystemExit(f"COMMAND_FAILED={proc.returncode}:{' '.join(argv)}\nSTDOUT={proc.stdout}\nSTDERR={proc.stderr}")
    return proc


def project_control(repo: Path, policy: Path, args: list[str], env: dict[str, str] | None = None,
                    expect: set[int] = {0}) -> dict[str, Any]:
    proc = run(["python3", "dev-hub/bin/project-control.py", "--policy", str(policy),
                "--repo-root", str(repo), "--json", *args], repo, env=env, expect=expect)
    try:
        value = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"PROJECT_CONTROL_JSON_INVALID={exc}:{proc.stdout}:{proc.stderr}")
    if not isinstance(value, dict):
        raise SystemExit("PROJECT_CONTROL_RESPONSE_NOT_OBJECT")
    return value


def canonical_url(raw: str, schemes: set[str]) -> str:
    try:
        p = urlsplit(raw)
    except ValueError as exc:
        raise SystemExit("MANIFEST_TARGET_URL_INVALID") from exc
    if p.scheme not in schemes or not p.hostname or p.username or p.password:
        raise SystemExit("MANIFEST_TARGET_URL_DENIED")
    return raw


def validate_manifest(manifest: dict[str, Any], contract: dict[str, Any]) -> tuple[str, str, list[dict[str, Any]]]:
    if manifest.get("schema") != MANIFEST_SCHEMA:
        raise SystemExit(f"MANIFEST_SCHEMA_INVALID={manifest.get('schema')}")
    if contract.get("schema") != CONTRACT_SCHEMA or contract.get("manifest_schema") != MANIFEST_SCHEMA:
        raise SystemExit("MANIFEST_CONTRACT_INVALID")
    project = str(manifest.get("project") or "")
    if not PROJECT_RE.match(project):
        raise SystemExit("MANIFEST_PROJECT_INVALID")
    env_class = str(((manifest.get("environment") or {}).get("class")) or "")
    if env_class not in set(contract.get("environment_classes") or []):
        raise SystemExit(f"MANIFEST_ENVIRONMENT_CLASS_DENIED={env_class}")
    workflows = manifest.get("workflows")
    if not isinstance(workflows, list) or not workflows:
        raise SystemExit("MANIFEST_WORKFLOWS_REQUIRED")
    seen: set[str] = set()
    schemes = set(((contract.get("target_policy") or {}).get("allowed_schemes") or []))
    normalized: list[dict[str, Any]] = []
    for item in workflows:
        if not isinstance(item, dict):
            raise SystemExit("MANIFEST_WORKFLOW_INVALID")
        wid = str(item.get("id") or "")
        kind = str(item.get("kind") or "")
        if not wid or wid in seen:
            raise SystemExit(f"MANIFEST_WORKFLOW_ID_INVALID={wid}")
        seen.add(wid)
        definition = ((contract.get("workflow_kinds") or {}).get(kind))
        if not isinstance(definition, dict):
            raise SystemExit(f"MANIFEST_WORKFLOW_KIND_UNSUPPORTED={kind}")
        target = item.get("target") if isinstance(item.get("target"), dict) else {}
        url = canonical_url(str(target.get("url") or ""), schemes)
        expected = target.get("expected_text")
        if expected is not None and (not isinstance(expected, str) or not expected or len(expected) > 512):
            raise SystemExit(f"MANIFEST_EXPECTED_TEXT_INVALID={wid}")
        normalized.append({"id": wid, "kind": kind, "url": url, "expected_text": expected, "definition": definition})
    return project, env_class, normalized


def require_capabilities(registry: dict[str, Any], workflows: list[dict[str, Any]]) -> None:
    if registry.get("schema") != REGISTRY_SCHEMA:
        raise SystemExit("CANONICAL_CAPABILITY_REGISTRY_SCHEMA_INVALID")
    caps = registry.get("capabilities") if isinstance(registry.get("capabilities"), dict) else {}
    required: set[str] = set()
    for wf in workflows:
        required.add(str(wf["definition"]["source_capability"]))
        required.add(str(wf["definition"]["independent_capability"]))
    missing = sorted(x for x in required if x not in caps)
    if missing:
        raise SystemExit("CANONICAL_CAPABILITY_MISSING=" + ",".join(missing))


def build_graph(project: str, workflows: list[dict[str, Any]]) -> dict[str, Any]:
    tasks: list[dict[str, Any]] = []
    for wf in workflows:
        wid, url = wf["id"], wf["url"]
        definition = wf["definition"]
        subject: dict[str, Any] = {"kind": "browser-page", "target_url": url}
        if wf.get("expected_text") is not None:
            subject["expected_text"] = wf["expected_text"]
        chrome_meta: dict[str, Any] = {"operation": "inspect_url", "url": url}
        if wf.get("expected_text") is not None:
            chrome_meta["expected_text"] = wf["expected_text"]
        source_id = f"{wid}:source"
        independent_id = f"{wid}:independent"
        tasks.append({
            "id": source_id, "kind": "artifact", "description": f"Manifest source observation for {wid}",
            "owner_role": "orchestrator", "capabilities": [definition["source_capability"]],
            "permission": definition.get("permission", "read"), "depends_on": [],
            "outputs": [{"type": "artifact", "id": "chrome-devtools-mcp-controlled-diagnostics"}],
            "verification": {"mode": definition.get("source_verification_mode", "independent-agent"),
                             "self_certification_allowed": False, "required_evidence": ["source", "timestamp", "digest"]},
            "blocking": True, "parallel_group": f"manifest-{wid}",
            "metadata": {"verification_subject": subject, "chrome_devtools_mcp": chrome_meta}
        })
        tasks.append({
            "id": independent_id, "kind": "gate", "description": f"Manifest independent observation for {wid}",
            "owner_role": "verification-broker", "capabilities": [definition["independent_capability"]],
            "permission": definition.get("permission", "read"), "depends_on": [source_id],
            "outputs": [{"type": "gate", "id": "playwright-readonly-browser-verification"}],
            "verification": {"mode": definition.get("independent_verification_mode", "machine"),
                             "self_certification_allowed": False, "required_evidence": ["source", "timestamp", "digest"]},
            "blocking": True, "parallel_group": f"manifest-{wid}",
            "metadata": {"verification_subject": subject, "target_url": url}
        })
    return {
        "schema": GRAPH_SCHEMA, "project": project, "transition": "MANIFEST->VERIFIED",
        "generated_at": now_iso(), "tasks": tasks,
        "summary": {"task_count": len(tasks), "artifact_tasks": len(workflows), "gate_tasks": len(workflows),
                    "approval_tasks": 0, "blocking_tasks": len(tasks)}
    }


def result_paths(record: dict[str, Any]) -> dict[str, Path]:
    out: dict[str, Path] = {}
    for wave in record.get("waves") or []:
        if not isinstance(wave, dict):
            continue
        for task in wave.get("tasks") or []:
            if isinstance(task, dict) and task.get("task_id") and task.get("task_result"):
                out[str(task["task_id"])] = Path(str(task["task_result"]))
    return out


def bootstrap(repo: Path, project: str, policy: dict[str, Any], policy_path: Path) -> None:
    runtime = policy.get("runtime") or {}
    state = Path(str(runtime.get("state_root"))) / project / "state.json"
    ledger = Path(str(runtime.get("evidence_root"))) / project / "ledger.json"
    refs = policy.get("repository_paths") or {}
    state_policy = resolve(repo, str(refs["control_plane_state"]))
    state_policy_value = load(state_policy)
    state_root = Path(str(((state_policy_value.get("storage") or {}).get("runtime_root"))))
    if not state.exists():
        run(["python3", "dev-hub/bin/control-plane-store.py", "--policy", str(state_policy),
             "--root", str(state_root), "init", "--project", project, "--actor", "manifest-orchestrator"], repo)
    if not ledger.exists():
        run(["python3", "dev-hub/bin/evidence-collector.py", "init", "--project", project, "--ledger", str(ledger)], repo)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True, type=Path)
    ap.add_argument("--repo-root", type=Path, default=Path.cwd())
    ap.add_argument("--project-control-policy", type=Path, default=Path("dev-hub/config/project-control.v1.json"))
    ap.add_argument("--contract", type=Path, default=Path("dev-hub/config/project-manifest-contract.v1.json"))
    ap.add_argument("--bootstrap", action="store_true")
    ap.add_argument("--execute", action="store_true")
    ap.add_argument("--output", type=Path)
    args = ap.parse_args()

    repo = args.repo_root.resolve()
    manifest = load(args.manifest.resolve())
    contract = load(resolve(repo, str(args.contract)))
    policy_path = resolve(repo, str(args.project_control_policy))
    policy = load(policy_path)
    project, env_class, workflows = validate_manifest(manifest, contract)
    registry_path = resolve(repo, str((policy.get("repository_paths") or {}).get("capability_registry")))
    registry = load(registry_path)
    require_capabilities(registry, workflows)

    runtime = policy.get("runtime") or {}
    plans_root = Path(str(runtime.get("plans_root"))) / project
    graph_path = plans_root / "manifest.task-graph.json"
    save(graph_path, build_graph(project, workflows))
    if args.bootstrap:
        bootstrap(repo, project, policy, policy_path)

    schedule = project_control(repo, policy_path, ["schedule", "--project", project, "--graph", str(graph_path)])
    if schedule.get("status") != "OK":
        raise SystemExit("MANIFEST_SCHEDULE_BLOCKED=" + json.dumps(schedule, ensure_ascii=False))
    plan_path = Path(str((schedule.get("details") or {}).get("execution_plan") or ""))
    receipt: dict[str, Any] = {
        "schema": "chacha.dev/project-manifest-run/v1", "project": project, "environment_class": env_class,
        "observed_at": now_iso(), "manifest": str(args.manifest.resolve()), "task_graph": str(graph_path),
        "execution_plan": str(plan_path), "capability_registry": str(registry_path),
        "provider_selection_owned_by_scheduler": True, "executed": False, "verified_workflows": [], "blockers": []
    }
    if not args.execute:
        receipt["status"] = "PLANNED"
        if args.output:
            save(args.output, receipt)
        print("MANIFEST_RUN_STATUS=PLANNED")
        print(f"TASK_GRAPH={graph_path}")
        print(f"EXECUTION_PLAN={plan_path}")
        return 0

    env = os.environ.copy()
    dispatch = project_control(repo, policy_path, ["dispatch", "--project", project, "--plan", str(plan_path),
                                                     "--graph", str(graph_path), "--execute"], env=env)
    if dispatch.get("status") != "OK":
        raise SystemExit("MANIFEST_DISPATCH_FAILED=" + json.dumps(dispatch, ensure_ascii=False))
    run_record_path = Path(str((dispatch.get("details") or {}).get("RUN_RECORD") or ""))
    run_id = str((dispatch.get("details") or {}).get("RUN_ID") or "")
    record = load(run_record_path)
    results = result_paths(record)
    verified_workflows: list[dict[str, Any]] = []
    for wf in workflows:
        source_id, independent_id = f"{wf['id']}:source", f"{wf['id']}:independent"
        source_path, independent_path = results.get(source_id), results.get(independent_id)
        if not source_path or not independent_path:
            raise SystemExit(f"MANIFEST_RESULT_MISSING={wf['id']}")
        source, independent = load(source_path), load(independent_path)
        if (source.get("verification") or {}).get("status") != "UNVERIFIED":
            raise SystemExit(f"MANIFEST_SOURCE_SELF_VERIFICATION_DENIED={wf['id']}")
        if (independent.get("verification") or {}).get("status") != "UNVERIFIED":
            raise SystemExit(f"MANIFEST_INDEPENDENT_SELF_VERIFICATION_DENIED={wf['id']}")
        verify_env = env.copy()
        verify_env["CHACHA_DEV_INDEPENDENT_RESULT"] = str(independent_path.resolve())
        verified = project_control(repo, policy_path, ["verify-result", "--project", project,
            "--result", str(source_path), "--graph", str(graph_path), "--method", "independent-agent",
            "--verifier", "verification-broker", "--ingest"], env=verify_env)
        if verified.get("status") != "OK" or (verified.get("details") or {}).get("verification_status") != "VERIFIED":
            raise SystemExit("MANIFEST_VERIFICATION_FAILED=" + json.dumps(verified, ensure_ascii=False))
        verified_workflows.append({"id": wf["id"], "source_task": source_id, "independent_task": independent_id,
                                   "source_producer": source.get("producer"), "independent_producer": independent.get("producer"),
                                   "verification_status": "VERIFIED"})

    integrity = project_control(repo, policy_path, ["verify-state", "--project", project])
    if integrity.get("status") != "OK":
        raise SystemExit("MANIFEST_AUDIT_INTEGRITY_FAILED=" + json.dumps(integrity, ensure_ascii=False))
    receipt.update({"status": "VERIFIED", "executed": True, "run_id": run_id,
                    "run_record": str(run_record_path), "verified_workflows": verified_workflows,
                    "audit_integrity": "PASS"})
    if args.output:
        save(args.output, receipt)
    print("MANIFEST_RUN_STATUS=VERIFIED")
    print(f"RUN_ID={run_id}")
    print(f"VERIFIED_WORKFLOWS={len(verified_workflows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
