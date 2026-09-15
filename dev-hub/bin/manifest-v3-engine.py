#!/usr/bin/env python3
"""ChaCha DEV HUB Manifest V3 engine.

Pure-stdlib reference implementation for:
- semantic validation of project manifests;
- component and environment dependency graph checks;
- capability/provider resolution against the registry;
- machine-readable inspection output.

This deliberately does not execute providers or modify production.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

SCHEMA_ID = "chacha.dev/project-manifest/v3"
REGISTRY_ID = "chacha.dev/capability-registry/v1"
CANONICAL_GATES = [
    "product-domain",
    "ux-frontend",
    "api-backend",
    "data",
    "integrations",
    "identity-security",
    "testing",
    "build-dependencies",
    "ci-cd-release",
    "environments-infra",
    "observability",
    "performance",
    "reliability-resilience",
    "backup-recovery",
    "documentation",
    "operations-sre",
    "finops-capacity",
    "governance-compliance",
]

STATUS_RANK = {
    "ADOPT": 60,
    "PILOT": 50,
    "WATCH": 40,
    "ASSESS": 30,
    "DISCOVER": 20,
    "DEPRECATE": 10,
    "RETIRE": 0,
}
CONDITIONAL_STATUSES = {"PILOT", "WATCH", "ASSESS", "DISCOVER"}


def load_json(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        raise SystemExit(f"FILE_NOT_FOUND={path}")
    except json.JSONDecodeError as exc:
        raise SystemExit(f"JSON_INVALID={path}:{exc.lineno}:{exc.colno}:{exc.msg}")
    if not isinstance(data, dict):
        raise SystemExit(f"JSON_ROOT_NOT_OBJECT={path}")
    return data


def add_issue(issues: list[dict[str, str]], level: str, code: str, message: str) -> None:
    issues.append({"level": level, "code": code, "message": message})


def topo(nodes: list[str], edges: list[tuple[str, str]]) -> tuple[list[str], list[str]]:
    adj: dict[str, set[str]] = {n: set() for n in nodes}
    indeg = {n: 0 for n in nodes}
    for src, dst in edges:
        if src not in adj or dst not in adj or src == dst:
            continue
        if dst not in adj[src]:
            adj[src].add(dst)
            indeg[dst] += 1
    q = deque(sorted(n for n, d in indeg.items() if d == 0))
    order: list[str] = []
    while q:
        n = q.popleft()
        order.append(n)
        for dst in sorted(adj[n]):
            indeg[dst] -= 1
            if indeg[dst] == 0:
                q.append(dst)
    cyclic = sorted(n for n, d in indeg.items() if d > 0)
    return order, cyclic


def component_graph(manifest: dict[str, Any]) -> dict[str, Any]:
    components = manifest.get("components") or []
    nodes = [c.get("id") for c in components if isinstance(c, dict) and c.get("id")]
    edges: set[tuple[str, str, str]] = set()
    for comp in components:
        if not isinstance(comp, dict) or not comp.get("id"):
            continue
        for dep in comp.get("depends_on") or []:
            edges.add((comp["id"], dep, "declared"))
    for edge in manifest.get("dependencies") or []:
        if isinstance(edge, dict) and edge.get("from") and edge.get("to"):
            edges.add((edge["from"], edge["to"], edge.get("kind", "unspecified")))
    topo_order, cyclic = topo(nodes, [(a, b) for a, b, _ in edges])
    return {
        "nodes": nodes,
        "edges": [
            {"from": a, "to": b, "kind": k}
            for a, b, k in sorted(edges)
        ],
        "topological_order": topo_order,
        "cycle_nodes": cyclic,
        "acyclic": not cyclic,
    }


def environment_graph(manifest: dict[str, Any]) -> dict[str, Any]:
    envs = manifest.get("environments") or []
    nodes = [e.get("name") for e in envs if isinstance(e, dict) and e.get("name")]
    edges: list[tuple[str, str]] = []
    for env in envs:
        if not isinstance(env, dict):
            continue
        parent, name = env.get("promotion_from"), env.get("name")
        if parent and name:
            edges.append((parent, name))
    order, cyclic = topo(nodes, edges)
    return {
        "nodes": nodes,
        "edges": [{"from": a, "to": b} for a, b in edges],
        "promotion_order": order,
        "cycle_nodes": cyclic,
        "acyclic": not cyclic,
    }


def resolve_capability(req: dict[str, Any], registry: dict[str, Any]) -> dict[str, Any]:
    cap_id = req.get("id", "")
    cap = (registry.get("capabilities") or {}).get(cap_id)
    if not cap:
        return {
            "id": cap_id,
            "required": bool(req.get("required")),
            "state": "UNAVAILABLE",
            "provider": None,
            "provider_status": None,
            "reason": "capability-not-registered",
        }

    providers = cap.get("providers") or []
    preferred = req.get("preferred_provider")
    fallback_allowed = req.get("fallback_allowed", True)

    viable = [p for p in providers if p.get("status") != "RETIRE"]
    if preferred:
        preferred_items = [p for p in viable if p.get("id") == preferred]
    else:
        preferred_items = []

    if preferred_items:
        chosen = preferred_items[0]
    elif fallback_allowed and viable:
        chosen = max(viable, key=lambda p: STATUS_RANK.get(p.get("status", ""), -1))
    else:
        chosen = None

    if not chosen:
        return {
            "id": cap_id,
            "required": bool(req.get("required")),
            "state": "UNAVAILABLE",
            "provider": None,
            "provider_status": None,
            "reason": "no-eligible-provider",
        }

    status = chosen.get("status", "UNKNOWN")
    if status == "ADOPT":
        state = "READY"
    elif status in CONDITIONAL_STATUSES:
        state = "CONDITIONAL"
    elif status == "DEPRECATE":
        state = "DEGRADED"
    else:
        state = "UNAVAILABLE"

    return {
        "id": cap_id,
        "required": bool(req.get("required")),
        "state": state,
        "provider": chosen.get("id"),
        "provider_status": status,
        "health_policy": chosen.get("health"),
        "cost_class": chosen.get("cost_class"),
        "scope": chosen.get("scope"),
        "preferred_provider": preferred,
        "fallback_used": bool(preferred and chosen.get("id") != preferred),
        "reason": "resolved",
    }


def resolve_all(manifest: dict[str, Any], registry: dict[str, Any]) -> dict[str, Any]:
    resolutions = [resolve_capability(r, registry) for r in manifest.get("capabilities") or []]
    required_bad = [r for r in resolutions if r["required"] and r["state"] in {"UNAVAILABLE", "DEGRADED"}]
    required_conditional = [r for r in resolutions if r["required"] and r["state"] == "CONDITIONAL"]
    return {
        "resolutions": resolutions,
        "required_unavailable": len(required_bad),
        "required_conditional": len(required_conditional),
        "execution_ready": not required_bad,
        "production_ready": not required_bad and not required_conditional,
    }


def validate(manifest: dict[str, Any], registry: dict[str, Any]) -> dict[str, Any]:
    issues: list[dict[str, str]] = []

    required_top = [
        "schema", "identity", "repository", "ownership", "components", "environments",
        "capabilities", "quality_gates", "storage", "technology_policy",
    ]
    for key in required_top:
        if key not in manifest:
            add_issue(issues, "ERROR", "TOP_LEVEL_MISSING", key)

    if manifest.get("schema") != SCHEMA_ID:
        add_issue(issues, "ERROR", "SCHEMA_ID", f"expected {SCHEMA_ID}")
    if registry.get("schema") != REGISTRY_ID:
        add_issue(issues, "ERROR", "REGISTRY_ID", f"expected {REGISTRY_ID}")

    identity = manifest.get("identity") or {}
    if not identity.get("name") or not identity.get("slug") or not identity.get("lifecycle_stage"):
        add_issue(issues, "ERROR", "IDENTITY_INCOMPLETE", "name, slug and lifecycle_stage are mandatory")

    components = manifest.get("components") or []
    ids = [c.get("id") for c in components if isinstance(c, dict)]
    valid_ids = {x for x in ids if x}
    if not components:
        add_issue(issues, "ERROR", "COMPONENTS_EMPTY", "at least one component is required")
    if len(ids) != len(set(ids)):
        add_issue(issues, "ERROR", "COMPONENT_ID_DUPLICATE", "component ids must be unique")
    for c in components:
        if not isinstance(c, dict):
            add_issue(issues, "ERROR", "COMPONENT_INVALID", "component must be an object")
            continue
        cid = c.get("id", "?")
        for key in ("id", "type", "path"):
            if not c.get(key) and c.get(key) != "":
                add_issue(issues, "ERROR", "COMPONENT_FIELD_MISSING", f"{cid}.{key}")
        for dep in c.get("depends_on") or []:
            if dep not in valid_ids:
                add_issue(issues, "ERROR", "COMPONENT_DEP_UNKNOWN", f"{cid}->{dep}")
            if dep == cid:
                add_issue(issues, "ERROR", "COMPONENT_SELF_DEP", cid)
        ctype = c.get("type")
        commands = c.get("commands") or {}
        if ctype in {"backend-api", "worker-edge", "service", "cli"} and not commands.get("test"):
            add_issue(issues, "WARN", "TEST_COMMAND_MISSING", cid)

    dep_edges = manifest.get("dependencies") or []
    for edge in dep_edges:
        if not isinstance(edge, dict):
            add_issue(issues, "ERROR", "DEPENDENCY_INVALID", "dependency edge must be an object")
            continue
        a, b = edge.get("from"), edge.get("to")
        if a not in valid_ids or b not in valid_ids:
            add_issue(issues, "ERROR", "DEPENDENCY_ENDPOINT_UNKNOWN", f"{a}->{b}")
        if a == b:
            add_issue(issues, "ERROR", "DEPENDENCY_SELF", str(a))

    cg = component_graph(manifest)
    if not cg["acyclic"]:
        add_issue(issues, "ERROR", "COMPONENT_CYCLE", ",".join(cg["cycle_nodes"]))

    envs = manifest.get("environments") or []
    env_names = [e.get("name") for e in envs if isinstance(e, dict) and e.get("name")]
    env_set = set(env_names)
    if len(env_names) != len(env_set):
        add_issue(issues, "ERROR", "ENVIRONMENT_DUPLICATE", "environment names must be unique")
    for env in envs:
        if not isinstance(env, dict):
            continue
        parent = env.get("promotion_from")
        if parent and parent not in env_set:
            add_issue(issues, "ERROR", "ENV_PROMOTION_UNKNOWN", f"{env.get('name')}<-{parent}")
        if env.get("class") == "production" and not env.get("approval_required", False):
            add_issue(issues, "ERROR", "PRODUCTION_APPROVAL_REQUIRED", env.get("name", "production"))
    eg = environment_graph(manifest)
    if not eg["acyclic"]:
        add_issue(issues, "ERROR", "ENVIRONMENT_CYCLE", ",".join(eg["cycle_nodes"]))

    gates = manifest.get("quality_gates") or {}
    for gate in CANONICAL_GATES:
        if gate not in gates:
            add_issue(issues, "ERROR", "GATE_MISSING", gate)
    for gate in gates:
        if gate not in CANONICAL_GATES:
            add_issue(issues, "WARN", "GATE_NON_STANDARD", gate)

    tech = manifest.get("technology_policy") or {}
    if tech.get("auto_replace_production") is not False:
        add_issue(issues, "ERROR", "AUTO_REPLACE_FORBIDDEN", "auto_replace_production must be false")

    storage = manifest.get("storage") or {}
    if not storage.get("tiers"):
        add_issue(issues, "ERROR", "STORAGE_TIERS_MISSING", "storage tiers are mandatory")
    if not storage.get("governor_required", False):
        add_issue(issues, "WARN", "STORAGE_GOVERNOR_DISABLED", "capacity protection is recommended")

    criticality = identity.get("criticality", "medium")
    recovery = manifest.get("recovery") or {}
    if criticality in {"high", "critical"}:
        if recovery.get("rpo_hours") is None or recovery.get("rto_hours") is None:
            add_issue(issues, "ERROR", "RECOVERY_OBJECTIVES_MISSING", criticality)
        if not recovery.get("production_restore_test_required", False):
            add_issue(issues, "WARN", "PRODUCTION_RESTORE_TEST_NOT_REQUIRED", criticality)

    registry_caps = registry.get("capabilities") or {}
    for cap in manifest.get("capabilities") or []:
        cid = cap.get("id") if isinstance(cap, dict) else None
        if not cid:
            add_issue(issues, "ERROR", "CAPABILITY_ID_MISSING", "capability requirement")
        elif cid not in registry_caps:
            add_issue(issues, "ERROR", "CAPABILITY_UNKNOWN", cid)

    for agent in manifest.get("agents") or []:
        if not isinstance(agent, dict):
            continue
        for cid in agent.get("capabilities") or []:
            if cid not in registry_caps:
                add_issue(issues, "WARN", "AGENT_CAPABILITY_UNREGISTERED", f"{agent.get('role','?')}:{cid}")
        if agent.get("approval_scope") == "production-change":
            add_issue(issues, "WARN", "AGENT_PRODUCTION_SCOPE", agent.get("role", "?"))

    for src in manifest.get("knowledge_sources") or []:
        if isinstance(src, dict) and src.get("capability") not in registry_caps:
            add_issue(issues, "ERROR", "KNOWLEDGE_CAPABILITY_UNKNOWN", str(src.get("capability")))

    resolution = resolve_all(manifest, registry)
    for r in resolution["resolutions"]:
        if r["required"] and r["state"] == "UNAVAILABLE":
            add_issue(issues, "ERROR", "CAPABILITY_UNAVAILABLE", r["id"])
        elif r["required"] and r["state"] == "DEGRADED":
            add_issue(issues, "ERROR", "CAPABILITY_DEGRADED", r["id"])
        elif r["required"] and r["state"] == "CONDITIONAL":
            add_issue(issues, "WARN", "CAPABILITY_CONDITIONAL", f"{r['id']}:{r['provider']}:{r['provider_status']}")

    errors = [i for i in issues if i["level"] == "ERROR"]
    warnings = [i for i in issues if i["level"] == "WARN"]
    return {
        "valid": not errors,
        "errors": len(errors),
        "warnings": len(warnings),
        "issues": issues,
        "component_graph": cg,
        "environment_graph": eg,
        "capability_resolution": resolution,
    }


def print_human(report: dict[str, Any], manifest: dict[str, Any]) -> None:
    print("=== MANIFEST V3 VALIDATION ===")
    print(f"PROJECT={manifest.get('identity', {}).get('slug', '?')}")
    print(f"VALID={'YES' if report['valid'] else 'NO'}")
    print(f"ERRORS={report['errors']}")
    print(f"WARNINGS={report['warnings']}")
    print(f"COMPONENTS={len(report['component_graph']['nodes'])}")
    print(f"COMPONENT_GRAPH={'ACYCLIC' if report['component_graph']['acyclic'] else 'CYCLIC'}")
    print(f"ENV_GRAPH={'ACYCLIC' if report['environment_graph']['acyclic'] else 'CYCLIC'}")
    caps = report["capability_resolution"]
    print(f"CAP_REQUIRED_UNAVAILABLE={caps['required_unavailable']}")
    print(f"CAP_REQUIRED_CONDITIONAL={caps['required_conditional']}")
    print(f"EXECUTION_READY={'YES' if caps['execution_ready'] else 'NO'}")
    print(f"PRODUCTION_PROVIDER_READY={'YES' if caps['production_ready'] else 'NO'}")
    for item in report["issues"]:
        print(f"{item['level']}={item['code']}::{item['message']}")


def print_graph(report: dict[str, Any]) -> None:
    print("=== COMPONENT GRAPH ===")
    for edge in report["component_graph"]["edges"]:
        print(f"{edge['from']} -> {edge['to']} [{edge['kind']}]")
    print("TOPO=" + ",".join(report["component_graph"]["topological_order"]))
    print("=== ENVIRONMENT PROMOTION GRAPH ===")
    for edge in report["environment_graph"]["edges"]:
        print(f"{edge['from']} -> {edge['to']}")
    print("PROMOTION_ORDER=" + ",".join(report["environment_graph"]["promotion_order"]))


def print_resolution(report: dict[str, Any]) -> None:
    print("=== CAPABILITY RESOLUTION ===")
    for r in report["capability_resolution"]["resolutions"]:
        print(
            f"{r['id']} | required={str(r['required']).lower()} | state={r['state']} | "
            f"provider={r.get('provider') or '-'} | status={r.get('provider_status') or '-'} | "
            f"fallback={str(r.get('fallback_used', False)).lower()}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="ChaCha DEV HUB Manifest V3 engine")
    parser.add_argument("command", choices=["validate", "graph", "resolve", "inspect"])
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()

    manifest = load_json(args.manifest)
    registry = load_json(args.registry)
    report = validate(manifest, registry)

    if args.as_json or args.command == "inspect":
        print(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True))
    elif args.command == "validate":
        print_human(report, manifest)
    elif args.command == "graph":
        print_graph(report)
    elif args.command == "resolve":
        print_resolution(report)

    return 0 if report["valid"] else 2


if __name__ == "__main__":
    sys.exit(main())
