#!/usr/bin/env python3
"""ChaCha DEV HUB generic project bootstrap V1.

Creates the runtime skeleton for a provider-agnostic project manifest, derives a
canonical provider-eligibility health snapshot, and then delegates planning or
explicit execution to the canonical manifest orchestrator. Provider selection
remains Scheduler-owned; external runtime availability remains dispatch-owned.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MANIFEST_SCHEMA = "chacha.dev/project-manifest/v1"
CONTRACT_SCHEMA = "chacha.dev/project-manifest-contract/v1"
REGISTRY_SCHEMA = "chacha.dev/capability-registry/v1"
ADAPTER_SCHEMA = "chacha.dev/provider-adapters/v1"
HEALTH_SCHEMA = "chacha.dev/provider-health-snapshot/v1"
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


def resolve(repo: Path, raw: str) -> Path:
    p = Path(raw)
    return p if p.is_absolute() else repo / p


def run(argv: list[str], repo: Path, timeout: int = 900) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(argv, cwd=str(repo), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          text=True, shell=False, check=False, timeout=timeout)
    if proc.returncode != 0:
        raise SystemExit(f"BOOTSTRAP_COMMAND_FAILED={proc.returncode}:{' '.join(argv)}\nSTDOUT={proc.stdout}\nSTDERR={proc.stderr}")
    return proc


def manifest_requirements(manifest: dict[str, Any], contract: dict[str, Any]) -> tuple[str, str, set[str]]:
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
    capabilities: set[str] = set()
    for item in workflows:
        if not isinstance(item, dict):
            raise SystemExit("MANIFEST_WORKFLOW_INVALID")
        kind = str(item.get("kind") or "")
        definition = ((contract.get("workflow_kinds") or {}).get(kind))
        if not isinstance(definition, dict):
            raise SystemExit(f"MANIFEST_WORKFLOW_KIND_UNSUPPORTED={kind}")
        for key in ("source_capability", "independent_capability"):
            value = definition.get(key)
            if not isinstance(value, str) or not value:
                raise SystemExit(f"MANIFEST_WORKFLOW_CAPABILITY_INVALID={kind}:{key}")
            capabilities.add(value)
    return project, env_class, capabilities


def provider_snapshot(capabilities: set[str], registry: dict[str, Any], adapters: dict[str, Any]) -> dict[str, Any]:
    if registry.get("schema") != REGISTRY_SCHEMA:
        raise SystemExit("CANONICAL_CAPABILITY_REGISTRY_SCHEMA_INVALID")
    if adapters.get("schema") != ADAPTER_SCHEMA:
        raise SystemExit("CANONICAL_PROVIDER_ADAPTER_SCHEMA_INVALID")
    caps = registry.get("capabilities") if isinstance(registry.get("capabilities"), dict) else {}
    provider_defs = adapters.get("providers") if isinstance(adapters.get("providers"), dict) else {}
    adapter_defs = adapters.get("adapters") if isinstance(adapters.get("adapters"), dict) else {}
    provider_ids: set[str] = set()
    for capability in sorted(capabilities):
        definition = caps.get(capability)
        if not isinstance(definition, dict):
            raise SystemExit(f"CANONICAL_CAPABILITY_MISSING={capability}")
        for provider in definition.get("providers") or []:
            if isinstance(provider, dict) and isinstance(provider.get("id"), str):
                provider_ids.add(provider["id"])
    observed = now_iso()
    snapshot: dict[str, Any] = {}
    for provider_id in sorted(provider_ids):
        pdef = provider_defs.get(provider_id) if isinstance(provider_defs, dict) else None
        adapter_id = pdef.get("adapter") if isinstance(pdef, dict) else None
        adef = adapter_defs.get(adapter_id) if isinstance(adapter_id, str) and isinstance(adapter_defs, dict) else None
        eligible = isinstance(adef, dict) and adef.get("status") == "ENABLED" and "read" in set(adef.get("supports") or [])
        snapshot[provider_id] = {
            "state": "HEALTHY" if eligible else "UNKNOWN",
            "source": "canonical-adapter-eligibility",
            "checked_at": observed,
            "adapter": adapter_id,
            "adapter_status": adef.get("status") if isinstance(adef, dict) else None,
            "runtime_availability_verified": False,
        }
    return {"schema": HEALTH_SCHEMA, "observed_at": observed, "providers": snapshot}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True, type=Path)
    ap.add_argument("--repo-root", type=Path, default=Path.cwd())
    ap.add_argument("--project-control-policy", type=Path, default=Path("dev-hub/config/project-control.v1.json"))
    ap.add_argument("--contract", type=Path, default=Path("dev-hub/config/project-manifest-contract.v1.json"))
    ap.add_argument("--execute", action="store_true")
    ap.add_argument("--output", type=Path)
    args = ap.parse_args()

    repo = args.repo_root.resolve()
    manifest_path = args.manifest.resolve()
    manifest = load(manifest_path)
    policy_path = resolve(repo, str(args.project_control_policy))
    policy = load(policy_path)
    contract_path = resolve(repo, str(args.contract))
    contract = load(contract_path)
    project, env_class, capabilities = manifest_requirements(manifest, contract)
    refs = policy.get("repository_paths") or {}
    registry_path = resolve(repo, str(refs["capability_registry"]))
    adapters_path = resolve(repo, str(refs["provider_adapters"]))
    registry = load(registry_path)
    adapters = load(adapters_path)

    runtime = policy.get("runtime") or {}
    roots = {
        "state": Path(str(runtime.get("state_root"))) / project,
        "evidence": Path(str(runtime.get("evidence_root"))) / project,
        "plans": Path(str(runtime.get("plans_root"))) / project,
        "health": Path(str(runtime.get("health_root"))) / project,
        "runs": Path(str(runtime.get("runs_root"))) / project,
        "transactions": Path(str(runtime.get("transactions_root"))) / project,
        "locks": Path(str(runtime.get("locks_root"))),
    }
    for path in roots.values():
        path.mkdir(parents=True, exist_ok=True)

    state_path = roots["state"] / "state.json"
    ledger_path = roots["evidence"] / "ledger.json"
    health_path = roots["health"] / "providers.json"
    state_policy = resolve(repo, str(refs["control_plane_state"]))
    state_policy_value = load(state_policy)
    state_root = Path(str(((state_policy_value.get("storage") or {}).get("runtime_root"))))

    state_created = not state_path.exists()
    ledger_created = not ledger_path.exists()
    if state_created:
        run(["python3", "dev-hub/bin/control-plane-store.py", "--policy", str(state_policy),
             "--root", str(state_root), "init", "--project", project, "--actor", "project-bootstrap"], repo, 120)
    if ledger_created:
        run(["python3", "dev-hub/bin/evidence-collector.py", "init", "--project", project,
             "--ledger", str(ledger_path)], repo, 120)

    health = provider_snapshot(capabilities, registry, adapters)
    save(health_path, health)
    provider_states = {pid: item.get("state") for pid, item in (health.get("providers") or {}).items()}
    blockers = [f"PROVIDER_NOT_CANONICALLY_ELIGIBLE:{pid}" for pid, state in provider_states.items() if state != "HEALTHY"]
    if blockers:
        receipt = {
            "schema": "chacha.dev/project-bootstrap-receipt/v1", "project": project,
            "environment_class": env_class, "observed_at": now_iso(), "status": "BLOCKED",
            "state_created": state_created, "ledger_created": ledger_created,
            "required_capabilities": sorted(capabilities), "provider_states": provider_states,
            "runtime_availability_verified": False, "paths": {name: str(path) for name, path in roots.items()},
            "state": str(state_path), "ledger": str(ledger_path), "health": str(health_path), "blockers": blockers,
        }
        if args.output:
            save(args.output, receipt)
        print("PROJECT_BOOTSTRAP_STATUS=BLOCKED")
        for blocker in blockers:
            print(f"BLOCKER={blocker}")
        return 2

    manifest_run_path = roots["plans"] / "manifest-run.json"
    command = [
        "python3", "dev-hub/bin/project-manifest-orchestrator.py",
        "--repo-root", str(repo), "--project-control-policy", str(policy_path),
        "--contract", str(contract_path), "--manifest", str(manifest_path),
        "--output", str(manifest_run_path),
    ]
    if args.execute:
        command.append("--execute")
    run(command, repo, 1200)
    manifest_run = load(manifest_run_path)
    expected_status = "VERIFIED" if args.execute else "PLANNED"
    if manifest_run.get("status") != expected_status:
        raise SystemExit(f"PROJECT_BOOTSTRAP_MANIFEST_RUN_INVALID={manifest_run.get('status')}:{expected_status}")

    receipt = {
        "schema": "chacha.dev/project-bootstrap-receipt/v1",
        "project": project,
        "environment_class": env_class,
        "observed_at": now_iso(),
        "status": expected_status,
        "executed": bool(args.execute),
        "state_created": state_created,
        "ledger_created": ledger_created,
        "idempotent_existing_state_preserved": not state_created,
        "idempotent_existing_ledger_preserved": not ledger_created,
        "required_capabilities": sorted(capabilities),
        "provider_states": provider_states,
        "runtime_availability_verified": bool(args.execute),
        "provider_selection_owned_by_scheduler": manifest_run.get("provider_selection_owned_by_scheduler") is True,
        "paths": {name: str(path) for name, path in roots.items()},
        "state": str(state_path),
        "ledger": str(ledger_path),
        "health": str(health_path),
        "task_graph": manifest_run.get("task_graph"),
        "execution_plan": manifest_run.get("execution_plan"),
        "manifest_run": str(manifest_run_path),
        "run_id": manifest_run.get("run_id"),
        "verified_workflows": manifest_run.get("verified_workflows") or [],
        "audit_integrity": manifest_run.get("audit_integrity"),
        "blockers": [],
    }
    if args.output:
        save(args.output, receipt)
    print(f"PROJECT_BOOTSTRAP_STATUS={expected_status}")
    print(f"PROJECT={project}")
    print(f"STATE_CREATED={'YES' if state_created else 'NO'}")
    print(f"LEDGER_CREATED={'YES' if ledger_created else 'NO'}")
    print(f"HEALTH_SNAPSHOT={health_path}")
    print(f"MANIFEST_RUN={manifest_run_path}")
    if receipt.get("run_id"):
        print(f"RUN_ID={receipt['run_id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
