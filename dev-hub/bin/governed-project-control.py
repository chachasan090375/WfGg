#!/usr/bin/env python3
"""Governed Project Control boundary for Canonical Path + anti-loop execution.

Only schedule/prepare-run/dispatch are gated. All other operations are delegated
unchanged to the existing project-control.py. No repository search, network
fallback or automatic recovery execution occurs here.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

GATED_COMMANDS = frozenset({"schedule", "prepare-run", "dispatch"})
RESPONSE_SCHEMA = "chacha.dev/project-control-response/v1"
LEDGER_SCHEMA = "chacha.dev/canonical-run-gate-ledger/v1"
GATE_CONTRACT = "chacha.dev/canonical-project-control-gate/v1"
DEFAULT_REPO_ROOT = Path("/opt/chacha-dev/platform/current")
DEFAULT_RUNTIME_ROOT = Path("/opt/chacha-dev/runtime")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _file_digest(path: Path) -> str | None:
    try:
        return _sha256_bytes(path.read_bytes()) if path.is_file() else None
    except OSError:
        return None


def _json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return value if isinstance(value, dict) else None


def _value(argv: list[str], flag: str) -> str | None:
    try:
        idx = argv.index(flag)
    except ValueError:
        return None
    return argv[idx + 1] if idx + 1 < len(argv) else None


def _command(argv: list[str]) -> str | None:
    for token in argv:
        if token in GATED_COMMANDS:
            return token
    return None


def _repo_root(argv: list[str]) -> Path:
    return Path(_value(argv, "--repo-root") or str(DEFAULT_REPO_ROOT)).resolve()


def _project(argv: list[str]) -> str:
    return str(_value(argv, "--project") or "").strip()


def _runtime_root(registry: Any, project: str) -> Path:
    override = os.environ.get("CHACHA_RUNTIME_ROOT")
    if override:
        return Path(override).resolve()
    component = registry.get_component(project) or {}
    raw = ((component.get("paths") or {}).get("runtime_root")) if isinstance(component, dict) else None
    return Path(str(raw)).resolve() if isinstance(raw, str) and raw.startswith("/") else DEFAULT_RUNTIME_ROOT


def _state_root(registry: Any, project: str, runtime_root: Path) -> Path:
    component = registry.get_component(project) or {}
    raw = ((component.get("paths") or {}).get("state_root")) if isinstance(component, dict) else None
    if isinstance(raw, str) and raw.startswith("/"):
        return Path(raw)
    return runtime_root / "state" / project


def _safe_read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8").strip() if path.is_file() else None
    except OSError:
        return None


def _projection_signal(path: Path) -> dict[str, Any]:
    value = _json(path) or {}
    state = value.get("state") if isinstance(value.get("state"), dict) else {}
    lifecycle = state.get("lifecycle") if isinstance(state.get("lifecycle"), dict) else {}
    return {
        "last_event_digest": value.get("last_event_digest"),
        "last_event_sequence": value.get("last_event_sequence"),
        "lifecycle_stage": lifecycle.get("stage"),
    }


def _workspace_signal(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    root = path.resolve(strict=False)
    git = root / ".git"
    head = _safe_read_text(git / "HEAD")
    resolved_ref = None
    if head and head.startswith("ref: "):
        ref = head.split(":", 1)[1].strip()
        resolved_ref = _safe_read_text(git / ref)
    return {"path": str(root), "git_head": head, "git_ref_value": resolved_ref}


def _normalised_inputs(argv: list[str]) -> dict[str, Any]:
    values: list[Any] = []
    idx = 0
    digest_flags = {"--graph", "--plan", "--result", "--adapters"}
    path_flags = {"--workspace"}
    ignored_flags = {"--repo-root", "--project"}
    while idx < len(argv):
        token = argv[idx]
        if token == "--json":
            idx += 1
            continue
        if token in ignored_flags and idx + 1 < len(argv):
            idx += 2
            continue
        if token in digest_flags and idx + 1 < len(argv):
            path = Path(argv[idx + 1])
            values.append({token: _file_digest(path) or f"MISSING:{path.name}"})
            idx += 2
            continue
        if token in path_flags and idx + 1 < len(argv):
            values.append({token: _workspace_signal(Path(argv[idx + 1]))})
            idx += 2
            continue
        values.append(token)
        idx += 1
    return {"argv": values}


def _fleet_signature(agents: Any) -> list[dict[str, Any]]:
    return [
        {
            "agent_id": a.agent_id,
            "capabilities": sorted(a.capabilities),
            "enabled": bool(a.enabled),
            "healthy": bool(a.healthy),
        }
        for a in sorted(agents, key=lambda item: item.agent_id)
    ]


def _emergency_stop(runtime_root: Path) -> bool:
    value = _json(runtime_root / "control/emergency-stop.json") or {}
    return bool(value.get("active"))


def _emit_block(argv: list[str], project: str, operation: str, summary: str,
                blockers: list[str], details: dict[str, Any]) -> int:
    payload = {
        "schema": RESPONSE_SCHEMA,
        "project": project,
        "operation": operation,
        "status": "BLOCKED",
        "observed_at": _now(),
        "summary": summary,
        "details": {**details, "downstream_invoked": False, "automatic_external_spend_eur": 0},
        "blockers": blockers,
        "next_actions": ["provide materially new state, evidence or strategy; do not replay the identical request"],
        "artifacts": [],
    }
    if "--json" in argv:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(f"PROJECT={project}")
        print(f"OPERATION={operation}")
        print("STATUS=BLOCKED")
        print(f"SUMMARY={summary}")
        for blocker in blockers:
            print(f"BLOCKER={blocker}")
        print("DOWNSTREAM_INVOKED=False")
    return 2


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(value, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def _load_ledger(path: Path) -> dict[str, Any]:
    value = _json(path)
    if not value or value.get("schema") != LEDGER_SCHEMA or not isinstance(value.get("entries"), dict):
        return {"schema": LEDGER_SCHEMA, "entries": {}}
    return value


def _snapshot_to_dict(snapshot: Any) -> dict[str, Any]:
    return {
        "action": snapshot.action,
        "inputs": dict(snapshot.inputs),
        "state": dict(snapshot.state),
        "evidence": dict(snapshot.evidence),
        "strategy": dict(snapshot.strategy),
        "hypothesis_id": snapshot.hypothesis_id,
    }


def _snapshot_from_dict(cls: Any, value: Any) -> Any | None:
    if not isinstance(value, dict):
        return None
    try:
        return cls(
            action=str(value["action"]),
            inputs=dict(value["inputs"]),
            state=dict(value["state"]),
            evidence=dict(value["evidence"]),
            strategy=dict(value["strategy"]),
            hypothesis_id=str(value["hypothesis_id"]),
        )
    except Exception:
        return None


def _record_attempt(path: Path, run_key: str, snapshot: Any, *,
                    decision: str, reason: str, outcome: dict[str, Any] | None = None) -> None:
    ledger = _load_ledger(path)
    ledger["entries"][run_key] = {
        "snapshot": _snapshot_to_dict(snapshot),
        "decision": decision,
        "reason": reason,
        "recorded_at": _now(),
        "outcome": outcome or {},
    }
    _atomic_json(path, ledger)


def _preflight(argv: list[str]) -> tuple[dict[str, Any], Any | None]:
    repo_root = _repo_root(argv)
    project = _project(argv)
    operation = _command(argv) or "UNKNOWN"

    src_root = repo_root / "dev-hub/projects/canonical-path-resolution/src"
    adapters_root = repo_root / "dev-hub/adapters"
    sys.path.insert(0, str(src_root))
    sys.path.insert(0, str(adapters_root))

    from canonical_component_registry_read import (
        FilesystemRuntimePathObserver,
        FleetObservatoryCatalogue,
        JsonCanonicalComponentRegistry,
    )
    from canonical_path_resolution.non_progress import AttemptSnapshot, NonProgressDetector
    from canonical_path_resolution.recovery import MultiAgentRecoveryRouter
    from canonical_path_resolution.resolver import CanonicalPathResolver
    from canonical_path_resolution.run_gate import GovernedRunGate

    registry_path = Path(
        os.environ.get(
            "CHACHA_CANONICAL_COMPONENT_REGISTRY",
            str(repo_root / "dev-hub/config/canonical-component-registry.v1.json"),
        )
    )
    registry = JsonCanonicalComponentRegistry(registry_path)
    observer = FilesystemRuntimePathObserver(registry)
    resolver = CanonicalPathResolver(registry, observer)
    resolution = resolver.resolve(project, "source_root", verify=True)

    runtime_root = _runtime_root(registry, project)
    state_root = _state_root(registry, project, runtime_root)
    ledger_path = state_root / "canonical-path-run-gate.json"
    fleet_path = runtime_root / "agent-evolution/fleet-observatory-latest.json"
    catalogue = FleetObservatoryCatalogue(fleet_path)
    agents = tuple(catalogue.agents())

    if not resolution.ok:
        return {
            "action": "BLOCKED",
            "reason": resolution.reason or resolution.status.value,
            "project": project,
            "operation": operation,
            "resolution": {
                "status": resolution.status.value,
                "declared": resolution.declared,
                "observed": resolution.observed,
                "reason": resolution.reason,
            },
            "runtime_root": runtime_root,
            "ledger_path": ledger_path,
        }, None

    if _emergency_stop(runtime_root):
        return {
            "action": "BLOCKED",
            "reason": "EMERGENCY_STOP_ACTIVE",
            "project": project,
            "operation": operation,
            "resolution": {
                "status": resolution.status.value,
                "declared": resolution.declared,
                "observed": resolution.observed,
                "reason": resolution.reason,
            },
            "runtime_root": runtime_root,
            "ledger_path": ledger_path,
        }, None

    inputs = _normalised_inputs(argv)
    projection = _projection_signal(state_root / "state.json")
    workspace_raw = _value(argv, "--workspace")
    workspace = _workspace_signal(Path(workspace_raw)) if workspace_raw else None
    registry_digest = _file_digest(registry_path)
    graph_raw = _value(argv, "--graph")
    plan_raw = _value(argv, "--plan")

    state = {
        "platform_revision": _safe_read_text(repo_root / ".revision"),
        "platform_tree": _safe_read_text(repo_root / ".tree"),
        "canonical_source_root": resolution.declared,
        "canonical_status": resolution.status.value,
        "control_projection": projection,
        "workspace": workspace,
        "emergency_stop_active": False,
    }
    evidence = {
        "canonical_registry": registry_digest,
        "graph": _file_digest(Path(graph_raw)) if graph_raw else None,
        "plan": _file_digest(Path(plan_raw)) if plan_raw else None,
        "fleet_capabilities": _fleet_signature(agents),
    }
    strategy = {
        "contract": GATE_CONTRACT,
        "required_capabilities": ["technical-assurance"],
        "optional_capabilities": [],
        "generic_repository_search": False,
        "automatic_recovery_execution": False,
        "capability_source": "fleet-observatory",
    }
    hypothesis_raw = json.dumps(
        {"operation": operation, "project": project, "inputs": inputs},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    hypothesis_id = hashlib.sha256(hypothesis_raw).hexdigest()

    current = AttemptSnapshot(
        action=operation,
        inputs=inputs,
        state=state,
        evidence=evidence,
        strategy=strategy,
        hypothesis_id=hypothesis_id,
    )
    run_key = current.action_fingerprint
    ledger = _load_ledger(ledger_path)
    previous_record = ledger["entries"].get(run_key) or {}
    previous = _snapshot_from_dict(AttemptSnapshot, previous_record.get("snapshot"))

    gate = GovernedRunGate(
        NonProgressDetector(),
        MultiAgentRecoveryRouter(catalogue),
    )
    decision = gate.decide(
        previous=previous,
        current=current,
        incident_id=f"{project}:{operation}:{run_key[:16]}",
        required_capabilities=("technical-assurance",),
        optional_capabilities=(),
        require_architecture_arbitration=False,
    )
    recovery = None
    if decision.recovery_plan is not None:
        recovery = {
            "status": decision.recovery_plan.status,
            "coordinator": decision.recovery_plan.coordinator,
            "participants": list(decision.recovery_plan.participants),
            "capability_assignments": dict(decision.recovery_plan.capability_assignments),
            "missing_capabilities": list(decision.recovery_plan.missing_capabilities),
            "reason": decision.recovery_plan.reason,
        }

    return {
        "action": decision.action,
        "reason": decision.reason,
        "project": project,
        "operation": operation,
        "resolution": {
            "status": resolution.status.value,
            "declared": resolution.declared,
            "observed": resolution.observed,
            "reason": resolution.reason,
        },
        "runtime_root": runtime_root,
        "ledger_path": ledger_path,
        "run_key": run_key,
        "recovery_plan": recovery,
    }, current


def _delegate(core: Path, argv: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(core), *argv],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
        timeout=3700,
    )


def main() -> int:
    argv = sys.argv[1:]
    repo_root = _repo_root(argv)
    core = repo_root / "dev-hub/bin/project-control.py"
    operation = _command(argv)

    if operation not in GATED_COMMANDS:
        if not core.is_file():
            print(f"PROJECT_CONTROL_CORE_NOT_FOUND={core}", file=sys.stderr)
            return 127
        os.execv(sys.executable, [sys.executable, str(core), *argv])
        return 127

    project = _project(argv)
    if not project:
        return _emit_block(argv, "UNKNOWN", operation, "Project identity is missing.",
                           ["PROJECT_ID_MISSING"], {})

    try:
        gate, current = _preflight(argv)
    except Exception as exc:
        return _emit_block(
            argv,
            project,
            operation,
            "Canonical Path / Run Gate preflight failed closed.",
            ["CANONICAL_RUN_GATE_PREFLIGHT_FAILED"],
            {"reason": f"{type(exc).__name__}:{exc}"},
        )

    if gate["action"] != "EXECUTE" or current is None:
        blockers = [f"CANONICAL_RUN_GATE_{gate['action']}", str(gate["reason"])]
        return _emit_block(
            argv,
            project,
            operation,
            "Governed Run Gate prevented downstream execution.",
            blockers,
            {
                "canonical_resolution": gate.get("resolution"),
                "run_gate_action": gate.get("action"),
                "run_gate_reason": gate.get("reason"),
                "recovery_plan": gate.get("recovery_plan"),
                "run_key": gate.get("run_key"),
            },
        )

    if not core.is_file():
        return _emit_block(argv, project, operation, "Project Control core is missing.",
                           ["PROJECT_CONTROL_CORE_NOT_FOUND"], {"path": str(core)})

    ledger_path = Path(gate["ledger_path"])
    run_key = str(gate["run_key"])
    _record_attempt(
        ledger_path,
        run_key,
        current,
        decision="EXECUTE",
        reason=str(gate["reason"]),
        outcome={"status": "STARTED", "downstream_invoked": True},
    )

    try:
        proc = _delegate(core, argv)
    except subprocess.TimeoutExpired:
        _record_attempt(
            ledger_path,
            run_key,
            current,
            decision="EXECUTE",
            reason=str(gate["reason"]),
            outcome={"status": "TIMEOUT", "downstream_invoked": True},
        )
        return _emit_block(argv, project, operation, "Project Control core timed out.",
                           ["PROJECT_CONTROL_CORE_TIMEOUT"], {"run_key": run_key})

    _record_attempt(
        ledger_path,
        run_key,
        current,
        decision="EXECUTE",
        reason=str(gate["reason"]),
        outcome={
            "status": "COMPLETED",
            "returncode": proc.returncode,
            "downstream_invoked": True,
            "stdout_digest": _sha256_bytes(proc.stdout.encode("utf-8")),
            "stderr_digest": _sha256_bytes(proc.stderr.encode("utf-8")),
        },
    )
    sys.stdout.write(proc.stdout)
    sys.stderr.write(proc.stderr)
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
