#!/usr/bin/env python3
"""ChaCha DEV HUB Task Graph Engine V1.

Builds a deterministic DAG for one lifecycle transition. It converts lifecycle
requirements into specialist tasks without executing them. The output is a plan,
not proof of success.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TASK_GRAPH_SCHEMA = "chacha.dev/task-graph/v1"
LIFECYCLE_SCHEMA = "chacha.dev/lifecycle/v1"
QUALITY_SCHEMA = "chacha.dev/quality-gates/v1"
CATALOG_SCHEMA = "chacha.dev/evidence-catalog/v1"
ORCH_SCHEMA = "chacha.dev/orchestration-policy/v1"


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit(f"FILE_NOT_FOUND={path}")
    except json.JSONDecodeError as exc:
        raise SystemExit(f"JSON_INVALID={path}:{exc.lineno}:{exc.colno}:{exc.msg}")
    if not isinstance(value, dict):
        raise SystemExit(f"JSON_ROOT_NOT_OBJECT={path}")
    return value


def require_schema(value: dict[str, Any], expected: str, label: str) -> None:
    if value.get("schema") != expected:
        raise SystemExit(f"SCHEMA_MISMATCH={label}:expected={expected}:actual={value.get('schema')}")


def verification(mode: str, required: list[str] | None = None) -> dict[str, Any]:
    allowed = {"machine", "independent-agent", "human", "machine-or-human"}
    if mode not in allowed:
        mode = "machine-or-human"
    return {
        "mode": mode,
        "self_certification_allowed": False,
        "required_evidence": required or ["source", "timestamp", "digest"],
    }


def artifact_task(artifact_id: str, catalog: dict[str, Any]) -> dict[str, Any]:
    defaults = catalog.get("defaults") or {}
    item = (catalog.get("artifacts") or {}).get(artifact_id) or {}
    owner = item.get("owner_role", "orchestrator")
    mode = item.get("verification") or (defaults.get("verification") or {}).get("mode", "machine-or-human")
    return {
        "id": f"artifact:{artifact_id}",
        "kind": "artifact",
        "description": f"Produce and independently verify lifecycle artifact {artifact_id}",
        "owner_role": owner,
        "capabilities": item.get("capabilities") or [],
        "permission": item.get("permission", defaults.get("permission", "read")),
        "depends_on": [],
        "outputs": [{"type": "artifact", "id": artifact_id}],
        "verification": verification(mode),
        "blocking": True,
        "parallel_group": f"artifact-{owner}",
    }


def gate_task(gate_id: str, quality: dict[str, Any], artifact_ids: list[str]) -> dict[str, Any]:
    definition = (quality.get("gates") or {}).get(gate_id) or {}
    role = definition.get("owner_role", "orchestrator")
    evidence = definition.get("evidence") or []
    return {
        "id": f"gate:{gate_id}",
        "kind": "gate",
        "description": f"Evaluate quality gate {gate_id} from collected evidence",
        "owner_role": role,
        "capabilities": ["architecture-audit"],
        "permission": "read",
        "depends_on": [f"artifact:{x}" for x in artifact_ids],
        "outputs": [{"type": "gate", "id": gate_id}],
        "verification": verification("independent-agent", ["gate-report", "evidence-links", *evidence]),
        "blocking": bool(definition.get("default_blocking", False)),
        "parallel_group": "gate-evaluation",
    }


def approval_task(approval_id: str, dependencies: list[str]) -> dict[str, Any]:
    return {
        "id": f"approval:{approval_id}",
        "kind": "approval",
        "description": f"Obtain explicit human approval: {approval_id}",
        "owner_role": "orchestrator",
        "capabilities": [],
        "permission": "plan",
        "depends_on": dependencies,
        "outputs": [{"type": "approval", "id": approval_id}],
        "verification": verification("human", ["actor", "timestamp", "decision"]),
        "blocking": True,
        "parallel_group": "human-approval",
    }


def validate_permissions(tasks: list[dict[str, Any]], current: str, orchestration: dict[str, Any]) -> None:
    stages = orchestration.get("stages") or {}
    stage = stages.get(current) or {}
    allowed = set(stage.get("allowed_permissions") or []) | {"read", "plan"}
    for task in tasks:
        permission = task.get("permission")
        if permission not in allowed:
            raise SystemExit(f"TASK_PERMISSION_NOT_ALLOWED={task.get('id')}:{permission}:current={current}")


def ensure_acyclic(tasks: list[dict[str, Any]]) -> None:
    ids = {t["id"] for t in tasks}
    deps = {t["id"]: set(t.get("depends_on") or []) for t in tasks}
    for tid, items in deps.items():
        unknown = sorted(items - ids)
        if unknown:
            raise SystemExit(f"TASK_DEPENDENCY_UNKNOWN={tid}:{','.join(unknown)}")
    ready = sorted(tid for tid, items in deps.items() if not items)
    visited: list[str] = []
    while ready:
        tid = ready.pop(0)
        if tid in visited:
            continue
        visited.append(tid)
        for other in sorted(ids - set(visited)):
            if tid in deps[other]:
                deps[other].remove(tid)
                if not deps[other] and other not in ready:
                    ready.append(other)
                    ready.sort()
    if len(visited) != len(ids):
        cyclic = sorted(ids - set(visited))
        raise SystemExit(f"TASK_GRAPH_CYCLE={','.join(cyclic)}")


def build_graph(project: str, transition: str, lifecycle: dict[str, Any], quality: dict[str, Any], catalog: dict[str, Any], orchestration: dict[str, Any]) -> dict[str, Any]:
    rule = (lifecycle.get("transitions") or {}).get(transition)
    if not isinstance(rule, dict):
        raise SystemExit(f"TRANSITION_NOT_DEFINED={transition}")
    if "->" not in transition:
        raise SystemExit(f"TRANSITION_INVALID={transition}")
    current, target = transition.split("->", 1)

    artifact_ids = list(rule.get("required_artifacts") or [])
    tasks = [artifact_task(a, catalog) for a in artifact_ids]

    gate_policy = rule.get("gate_policy", "none")
    if gate_policy == "required-gates":
        gate_ids = list(rule.get("required_gates") or [])
    elif gate_policy == "release":
        gate_ids = list((quality.get("gates") or {}).keys())
    else:
        gate_ids = []

    for gate_id in gate_ids:
        if gate_id not in (quality.get("gates") or {}):
            raise SystemExit(f"QUALITY_GATE_UNKNOWN={gate_id}")
        tasks.append(gate_task(gate_id, quality, artifact_ids))

    dependencies = [t["id"] for t in tasks]
    for approval_id in rule.get("required_approvals") or []:
        tasks.append(approval_task(approval_id, dependencies.copy()))

    # Transition work is performed while the project is still in its current
    # stage. A successful transition grants the target-stage permissions only
    # after the Lifecycle Engine promotes the state.
    validate_permissions(tasks, current, orchestration)
    ensure_acyclic(tasks)

    return {
        "schema": TASK_GRAPH_SCHEMA,
        "project": project,
        "transition": transition,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tasks": tasks,
        "summary": {
            "task_count": len(tasks),
            "artifact_tasks": sum(t["kind"] == "artifact" for t in tasks),
            "gate_tasks": sum(t["kind"] == "gate" for t in tasks),
            "approval_tasks": sum(t["kind"] == "approval" for t in tasks),
            "blocking_tasks": sum(bool(t.get("blocking")) for t in tasks),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--transition", required=True)
    parser.add_argument("--lifecycle", required=True, type=Path)
    parser.add_argument("--quality", required=True, type=Path)
    parser.add_argument("--catalog", required=True, type=Path)
    parser.add_argument("--orchestration", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    lifecycle = load_json(args.lifecycle)
    quality = load_json(args.quality)
    catalog = load_json(args.catalog)
    orchestration = load_json(args.orchestration)
    require_schema(lifecycle, LIFECYCLE_SCHEMA, "lifecycle")
    require_schema(quality, QUALITY_SCHEMA, "quality")
    require_schema(catalog, CATALOG_SCHEMA, "catalog")
    require_schema(orchestration, ORCH_SCHEMA, "orchestration")

    graph = build_graph(args.project, args.transition, lifecycle, quality, catalog, orchestration)
    rendered = json.dumps(graph, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
        print(f"TASK_GRAPH_WRITTEN={args.output}")
        print(f"TASK_COUNT={graph['summary']['task_count']}")
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
