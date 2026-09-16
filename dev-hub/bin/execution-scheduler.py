#!/usr/bin/env python3
"""ChaCha DEV HUB Execution Scheduler V1.1.

Transforms a Task Graph into execution waves. Provider ranking is delegated to
Provider Selection Engine. The scheduler only consumes and revalidates that
plan against the live capability registry, adapter registry and health snapshot,
then applies dependencies, concurrency, retry/failover policy and safety gates.
It plans execution only and never dispatches.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TASK_GRAPH_SCHEMA = "chacha.dev/task-graph/v1"
REGISTRY_SCHEMA = "chacha.dev/capability-registry/v1"
ADAPTERS_SCHEMA = "chacha.dev/provider-adapters/v1"
HEALTH_SCHEMA = "chacha.dev/provider-health-snapshot/v1"
POLICY_SCHEMA = "chacha.dev/execution-scheduler/v1"
SELECTION_SCHEMA = "chacha.dev/provider-selection-plan/v1"
PLAN_SCHEMA = "chacha.dev/execution-plan/v1"


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


def selection_index(selection: dict[str, Any]) -> tuple[dict[tuple[str, str], dict[str, Any]], list[str]]:
    index: dict[tuple[str, str], dict[str, Any]] = {}
    errors: list[str] = []
    for item in selection.get("task_plans") or []:
        if not isinstance(item, dict):
            continue
        task_id = str(item.get("task_id") or "")
        capability = str(item.get("capability") or "")
        if not task_id or not capability:
            errors.append("SELECTION_ENTRY_IDENTITY_MISSING")
            continue
        key = (task_id, capability)
        if key in index:
            errors.append(f"SELECTION_ENTRY_DUPLICATE:{task_id}:{capability}")
            continue
        index[key] = item
    return index, errors


def selected_binding(
    task_id: str,
    capability: str,
    permission: str,
    registry: dict[str, Any],
    adapters: dict[str, Any],
    health: dict[str, Any],
    policy: dict[str, Any],
    selections: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, Any]:
    sel = selections.get((task_id, capability))
    if not isinstance(sel, dict):
        return {
            "capability": capability, "provider": None, "provider_status": None,
            "adapter_status": None, "health_state": None, "state": "BLOCKED",
            "fallback_used": False, "reason": "selection-plan-entry-missing",
        }
    if sel.get("dispatch_authorized") is not False:
        return {
            "capability": capability, "provider": None, "provider_status": None,
            "adapter_status": None, "health_state": None, "state": "BLOCKED",
            "fallback_used": False, "reason": "selection-entry-dispatch-flag-invalid",
        }
    selected = sel.get("selected_provider")
    if not selected:
        return {
            "capability": capability, "provider": None, "provider_status": None,
            "adapter_status": None, "health_state": None, "state": "BLOCKED",
            "fallback_used": False, "reason": "selector-no-execution-eligible-provider",
        }
    pid = str(selected)

    cap = (registry.get("capabilities") or {}).get(capability)
    if not isinstance(cap, dict):
        return {
            "capability": capability, "provider": pid, "provider_status": None,
            "adapter_status": None, "health_state": None, "state": "BLOCKED",
            "fallback_used": False, "reason": "capability-not-registered",
        }
    cap_providers = [p for p in (cap.get("providers") or []) if isinstance(p, dict)]
    by_id = {str(p.get("id")): p for p in cap_providers if p.get("id")}
    provider = by_id.get(pid)
    if not isinstance(provider, dict) or provider.get("status") == "RETIRE":
        return {
            "capability": capability, "provider": pid, "provider_status": None,
            "adapter_status": None, "health_state": None, "state": "BLOCKED",
            "fallback_used": False, "reason": "selector-provider-not-in-capability-registry",
        }

    provider_binding = (adapters.get("providers") or {}).get(pid)
    if not isinstance(provider_binding, dict):
        return {
            "capability": capability, "provider": pid, "provider_status": provider.get("status"),
            "adapter_status": None, "health_state": None, "state": "BLOCKED",
            "fallback_used": False, "reason": "selected-provider-binding-missing",
        }
    adapter_id = provider_binding.get("adapter")
    adapter = (adapters.get("adapters") or {}).get(adapter_id)
    if not isinstance(adapter, dict):
        return {
            "capability": capability, "provider": pid, "provider_status": provider.get("status"),
            "adapter_status": None, "health_state": None, "state": "BLOCKED",
            "fallback_used": False, "reason": "selected-adapter-missing",
        }

    selection_policy = policy.get("provider_selection") or {}
    runtime_statuses = set(selection_policy.get("adapter_runtime_statuses") or [])
    adapter_status = str(adapter.get("status") or "UNKNOWN")
    if adapter_status not in runtime_statuses:
        return {
            "capability": capability, "provider": pid, "provider_status": provider.get("status"),
            "adapter": adapter_id, "adapter_status": adapter_status, "health_state": None,
            "state": "BLOCKED", "fallback_used": False,
            "reason": f"selected-adapter-not-runtime-admitted:{adapter_status}",
        }
    supports = {str(x) for x in (adapter.get("supports") or [])}
    if permission not in supports:
        return {
            "capability": capability, "provider": pid, "provider_status": provider.get("status"),
            "adapter": adapter_id, "adapter_status": adapter_status, "health_state": None,
            "state": "BLOCKED", "fallback_used": False,
            "reason": f"selected-adapter-permission-denied:{permission}",
        }

    snap = (health.get("providers") or {}).get(pid) or {}
    hstate = str(snap.get("state") or "UNKNOWN")
    prod = permission in {
        "production-deploy", "production-data-write", "secret-change",
        "destructive-operation", "technology-replacement",
    }
    if hstate == "UNAVAILABLE":
        reason = "selected-provider-unavailable"
    elif hstate == "UNKNOWN" and not bool(selection_policy.get("allow_unknown", False)):
        reason = "selected-provider-health-unknown"
    elif hstate == "DEGRADED" and not bool(selection_policy.get(
        "allow_degraded_for_production" if prod else "allow_degraded_for_non_production", False
    )):
        reason = "selected-provider-degraded-not-allowed"
    elif hstate not in {"HEALTHY", "DEGRADED"}:
        reason = f"selected-provider-health-invalid:{hstate}"
    else:
        reason = None
    if reason:
        return {
            "capability": capability, "provider": pid, "provider_status": provider.get("status"),
            "adapter": adapter_id, "adapter_status": adapter_status, "health_state": hstate,
            "state": "BLOCKED", "fallback_used": False, "reason": reason,
        }

    primary = str(cap_providers[0].get("id") or "") if cap_providers else ""
    fallback = bool(primary and pid != primary)
    degraded = hstate == "DEGRADED" or provider.get("status") == "DEPRECATE"
    return {
        "capability": capability,
        "provider": pid,
        "provider_status": provider.get("status"),
        "adapter": adapter_id,
        "adapter_status": adapter_status,
        "health_state": hstate,
        "selection_score": next((x.get("score") for x in sel.get("ranked_candidates") or [] if x.get("provider") == pid), None),
        "selection_confidence": sel.get("confidence"),
        "state": "DEGRADED" if degraded else "READY",
        "fallback_used": fallback,
        "reason": "selector-fallback-selected" if fallback else "selector-selected",
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


def prepare_tasks(
    graph: dict[str, Any], registry: dict[str, Any], adapters: dict[str, Any],
    health: dict[str, Any], policy: dict[str, Any], selections: dict[tuple[str, str], dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], dict[str, list[str]]]:
    prepared: dict[str, dict[str, Any]] = {}
    blocked: dict[str, list[str]] = {}
    failover_approval = set(((policy.get("failover") or {}).get("approval_required_for_permissions") or []))
    resource_policy = policy.get("resource_classes") or {}
    for task in graph.get("tasks") or []:
        if not isinstance(task, dict):
            continue
        tid = task.get("id")
        if not tid:
            continue
        permission = str(task.get("permission") or "read")
        bindings = [
            selected_binding(str(tid), str(c), permission, registry, adapters, health, policy, selections)
            for c in (task.get("capabilities") or [])
        ]
        reasons = [f"CAPABILITY_BLOCKED:{b['capability']}:{b['reason']}" for b in bindings if b.get("state") == "BLOCKED"]
        fallback_count = sum(bool(b.get("fallback_used")) for b in bindings)
        if fallback_count and permission in failover_approval:
            reasons.append("FAILOVER_APPROVAL_REQUIRED")
        rclass = resource_class(task)
        prepared[str(tid)] = {
            "task_id": str(tid),
            "permission": permission,
            "resource_class": rclass,
            "requires_storage_preflight": bool((resource_policy.get(rclass) or {}).get("storage_preflight", False)),
            "provider_bindings": bindings,
            "depends_on": list(task.get("depends_on") or []),
            "kind": task.get("kind"),
            "owner_role": task.get("owner_role"),
        }
        if reasons:
            blocked[str(tid)] = sorted(set(reasons))

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
    parser.add_argument("--adapters", required=True, type=Path)
    parser.add_argument("--health", required=True, type=Path)
    parser.add_argument("--selection-plan", required=True, type=Path)
    parser.add_argument("--policy", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    graph, registry, adapters, health, selection, policy = map(
        load, [args.graph, args.registry, args.adapters, args.health, args.selection_plan, args.policy]
    )
    require(graph, TASK_GRAPH_SCHEMA, "task-graph")
    require(registry, REGISTRY_SCHEMA, "registry")
    require(adapters, ADAPTERS_SCHEMA, "adapters")
    require(health, HEALTH_SCHEMA, "health")
    require(selection, SELECTION_SCHEMA, "selection-plan")
    require(policy, POLICY_SCHEMA, "scheduler-policy")

    selection_policy = policy.get("provider_selection") or {}
    if selection_policy.get("selection_plan_must_match_graph") is True:
        if selection.get("project") != graph.get("project") or selection.get("transition") != graph.get("transition"):
            raise SystemExit("SELECTION_PLAN_GRAPH_MISMATCH")
    if selection_policy.get("selection_plan_dispatch_authorized_must_be_false") is True and selection.get("dispatch_authorized") is not False:
        raise SystemExit("SELECTION_PLAN_DISPATCH_FLAG_INVALID")

    selections, selection_errors = selection_index(selection)
    if selection_errors:
        raise SystemExit("SELECTION_PLAN_INVALID=" + ",".join(sorted(set(selection_errors))))

    prepared, blocked = prepare_tasks(graph, registry, adapters, health, policy, selections)
    waves = schedule(prepared, blocked, policy)
    scheduled = sum(len(w["tasks"]) for w in waves)
    fallbacks = sum(bool(b.get("fallback_used")) for w in waves for t in w["tasks"] for b in t.get("provider_bindings", []))
    plan = {
        "schema": PLAN_SCHEMA,
        "project": graph.get("project"),
        "transition": graph.get("transition"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "provider_selection_plan": str(args.selection_plan),
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
