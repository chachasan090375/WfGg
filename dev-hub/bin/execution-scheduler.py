#!/usr/bin/env python3
"""ChaCha DEV HUB Execution Scheduler V1.

Transforms a Task Graph into execution waves. It binds every abstract
capability to a currently eligible provider, applies health/failover policy,
serializes writes, and blocks unsafe work. It plans execution only.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TASK_GRAPH_SCHEMA = "chacha.dev/task-graph/v1"
REGISTRY_SCHEMA = "chacha.dev/capability-registry/v1"
HEALTH_SCHEMA = "chacha.dev/provider-health-snapshot/v1"
POLICY_SCHEMA = "chacha.dev/execution-scheduler/v1"
PLAN_SCHEMA = "chacha.dev/execution-plan/v1"

STATUS_SCORE = {"ADOPT": 60, "PILOT": 50, "WATCH": 40, "ASSESS": 30, "DISCOVER": 20, "DEPRECATE": 10, "RETIRE": 0}
HEALTH_SCORE = {"HEALTHY": 30, "DEGRADED": 20, "UNKNOWN": 5, "UNAVAILABLE": 0}


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


def require(value: dict[str, Any], schema: str, label: str) -> None:
    if value.get("schema") != schema:
        raise SystemExit(f"SCHEMA_MISMATCH={label}:expected={schema}:actual={value.get('schema')}")


def bind(capability: str, permission: str, registry: dict[str, Any], health: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    cap = (registry.get("capabilities") or {}).get(capability)
    if not isinstance(cap, dict):
        return {"capability": capability, "provider": None, "provider_status": None, "health_state": None,
                "state": "BLOCKED", "fallback_used": False, "reason": "capability-not-registered"}
    providers = [p for p in (cap.get("providers") or []) if isinstance(p, dict) and p.get("status") != "RETIRE"]
    if not providers:
        return {"capability": capability, "provider": None, "provider_status": None, "health_state": None,
                "state": "BLOCKED", "fallback_used": False, "reason": "no-provider"}
    primary = providers[0].get("id")
    selection = policy.get("provider_selection") or {}
    prod = permission in {"production-deploy", "production-data-write", "secret-change", "destructive-operation", "technology-replacement"}
    allow_degraded = bool(selection.get("allow_degraded_for_production" if prod else "allow_degraded_for_non_production", False))
    allow_unknown = bool(selection.get("allow_unknown", False))
    candidates: list[tuple[int, dict[str, Any], dict[str, Any]]] = []
    for provider in providers:
        pid = provider.get("id")
        snap = (health.get("providers") or {}).get(pid) or {}
        hstate = snap.get("state", "UNKNOWN")
        if hstate == "UNAVAILABLE":
            continue
        if hstate == "UNKNOWN" and not allow_unknown:
            continue
        if hstate == "DEGRADED" and not allow_degraded:
            continue
        score = STATUS_SCORE.get(provider.get("status", ""), -100) + HEALTH_SCORE.get(hstate, -100)
        if pid == primary:
            score += 3
        candidates.append((score, provider, snap))
    if not candidates:
        return {"capability": capability, "provider": None, "provider_status": None, "health_state": None,
                "state": "BLOCKED", "fallback_used": False, "reason": "no-healthy-eligible-provider"}
    candidates.sort(key=lambda x: (x[0], x[1].get("id", "")), reverse=True)
    _, provider, snap = candidates[0]
    pid = provider.get("id")
    fallback = bool(primary and pid != primary)
    degraded = snap.get("state") == "DEGRADED" or provider.get("status") == "DEPRECATE"
    return {
        "capability": capability,
        "provider": pid,
        "provider_status": provider.get("status"),
        "health_state": snap.get("state", "UNKNOWN"),
        "state": "DEGRADED" if degraded else "READY",
        "fallback_used": fallback,
        "reason": "fallback-selected" if fallback else "primary-selected",
    }


def resource_class(task: dict[str, Any]) -> str:
    caps = set(task.get("capabilities") or [])
    if caps & {"3d-pipeline"}:
        return "very-heavy"
    if caps & {"e2e-test-web", "browser-automation", "performance-test-web"}:
        return "heavy"
    if task.get("permission") in {"preview-deploy", "production-deploy"}:
        return "medium"
    return "light"


def is_serial(permission: str, policy: dict[str, Any]) -> bool:
    return permission in set(((policy.get("concurrency") or {}).get("serialize_permissions") or []))


def prepare_tasks(graph: dict[str, Any], registry: dict[str, Any], health: dict[str, Any], policy: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, list[str]]]:
    prepared: dict[str, dict[str, Any]] = {}
    blocked: dict[str, list[str]] = {}
    failover_approval = set(((policy.get("failover") or {}).get("approval_required_for_permissions") or []))
    resource_policy = policy.get("resource_classes") or {}
    for task in graph.get("tasks") or []:
        tid = task.get("id")
        if not tid:
            continue
        permission = task.get("permission", "read")
        bindings = [bind(c, permission, registry, health, policy) for c in (task.get("capabilities") or [])]
        reasons = [f"CAPABILITY_BLOCKED:{b['capability']}:{b['reason']}" for b in bindings if b.get("state") == "BLOCKED"]
        fallback_count = sum(bool(b.get("fallback_used")) for b in bindings)
        if fallback_count and permission in failover_approval:
            reasons.append("FAILOVER_APPROVAL_REQUIRED")
        rclass = resource_class(task)
        prepared[tid] = {
            "task_id": tid,
            "permission": permission,
            "resource_class": rclass,
            "requires_storage_preflight": bool((resource_policy.get(rclass) or {}).get("storage_preflight", False)),
            "provider_bindings": bindings,
            "depends_on": list(task.get("depends_on") or []),
            "kind": task.get("kind"),
            "owner_role": task.get("owner_role"),
        }
        if reasons:
            blocked[tid] = sorted(set(reasons))

    # Propagate dependency blocking to downstream tasks.
    changed = True
    while changed:
        changed = False
        for tid, task in prepared.items():
            if tid in blocked:
                continue
            bad = [dep for dep in task["depends_on"] if dep in blocked]
            if bad:
                blocked[tid] = ["DEPENDENCY_BLOCKED:" + dep for dep in sorted(bad)]
                changed = True
    return prepared, blocked


def schedule(prepared: dict[str, dict[str, Any]], blocked: dict[str, list[str]], policy: dict[str, Any]) -> list[dict[str, Any]]:
    remaining = {tid for tid in prepared if tid not in blocked}
    completed: set[str] = set()
    waves: list[dict[str, Any]] = []
    max_reads = int(((policy.get("concurrency") or {}).get("max_parallel_read_tasks") or 8))
    allow_reads_with_write = bool(((policy.get("concurrency") or {}).get("allow_read_tasks_during_write", False)))

    while remaining:
        ready = sorted(tid for tid in remaining if set(prepared[tid]["depends_on"]) <= completed)
        if not ready:
            for tid in sorted(remaining):
                blocked[tid] = ["UNRESOLVED_DEPENDENCY_OR_CYCLE"]
            break
        serial = [tid for tid in ready if is_serial(prepared[tid]["permission"], policy)]
        reads = [tid for tid in ready if tid not in serial]
        if serial:
            selected = [serial[0]]
            if allow_reads_with_write:
                selected += reads[:max_reads]
        else:
            selected = reads[:max_reads]
        wave_tasks = []
        for tid in selected:
            item = dict(prepared[tid])
            item.pop("depends_on", None)
            wave_tasks.append(item)
            remaining.remove(tid)
            completed.add(tid)
        waves.append({"index": len(waves) + 1, "tasks": wave_tasks})
    return waves


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--graph", required=True, type=Path)
    parser.add_argument("--registry", required=True, type=Path)
    parser.add_argument("--health", required=True, type=Path)
    parser.add_argument("--policy", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    graph, registry, health, policy = map(load, [args.graph, args.registry, args.health, args.policy])
    require(graph, TASK_GRAPH_SCHEMA, "task-graph")
    require(registry, REGISTRY_SCHEMA, "registry")
    require(health, HEALTH_SCHEMA, "health")
    require(policy, POLICY_SCHEMA, "scheduler-policy")

    prepared, blocked = prepare_tasks(graph, registry, health, policy)
    waves = schedule(prepared, blocked, policy)
    scheduled = sum(len(w["tasks"]) for w in waves)
    fallbacks = sum(bool(b.get("fallback_used")) for w in waves for t in w["tasks"] for b in t.get("provider_bindings", []))
    plan = {
        "schema": PLAN_SCHEMA,
        "project": graph.get("project"),
        "transition": graph.get("transition"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "waves": waves,
        "blocked_tasks": [{"task_id": tid, "reasons": reasons} for tid, reasons in sorted(blocked.items())],
        "summary": {
            "task_count": len(prepared),
            "scheduled_count": scheduled,
            "blocked_count": len(blocked),
            "wave_count": len(waves),
            "failover_bindings": fallbacks,
        },
    }
    rendered = json.dumps(plan, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
        print(f"EXECUTION_PLAN_WRITTEN={args.output}")
        print(f"SCHEDULED={scheduled}")
        print(f"BLOCKED={len(blocked)}")
        print(f"WAVES={len(waves)}")
        print(f"FAILOVERS={fallbacks}")
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
