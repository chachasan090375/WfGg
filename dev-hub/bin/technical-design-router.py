#!/usr/bin/env python3
"""ChaCha DEV HUB Product Requirement -> Technical Design Router V1.

This engine is the formal boundary between product intent ("what") and technical
resolution work ("how"). It never implements code, changes production, selects
new production technology, or approves its own architecture.

It:
- preserves the human product requirement as the authoritative input;
- detects affected project components/domains;
- routes design work to logical specialist roles;
- emits required architecture decisions and cross-reviews;
- emits a design-only Task Graph owned by ChaCha Dev Architect + specialists;
- keeps implementation blocked until specialist outputs and reviews exist.
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REQ_SCHEMA = "chacha.dev/product-requirement/v1"
MANIFEST_SCHEMA = "chacha.dev/project-manifest/v3"
ROUTING_SCHEMA = "chacha.dev/agent-routing/v1"
POLICY_SCHEMA = "chacha.dev/technical-design-policy/v1"
PLAN_SCHEMA = "chacha.dev/technical-design-plan/v1"
GRAPH_SCHEMA = "chacha.dev/task-graph/v1"

DOMAIN_ORDER = [
    "product-domain", "frontend", "backend-api", "data", "integration",
    "security", "testing", "platform", "sre-observability", "performance",
    "recovery", "release", "documentation",
]

KEYWORDS: dict[str, set[str]] = {
    "frontend": {
        "ui", "frontend", "display", "afficher", "clic", "click", "cliquable",
        "popup", "carte", "map", "responsive", "accessibility", "avatar",
    },
    "backend-api": {
        "api", "backend", "worker", "service", "endpoint", "search", "recherche",
        "player", "joueur", "profile", "profil", "gameuid", "collector", "lookup",
        "query", "enrichment", "enrichissement",
    },
    "data": {
        "database", "d1", "schema", "table", "index", "migration", "persist",
        "persistence", "historique", "history", "alias", "gameuid", "provenance",
        "observation", "deduplicate", "deduplication", "canonical",
    },
    "integration": {
        "connector", "protocol", "protocole", "last war", "get.user.info.multi",
        "worldpointinfo", "shieldinfo", "external api", "integration",
    },
    "security": {
        "readonly", "read-only", "secret", "token", "session", "hmac", "auth",
        "authorization", "permission", "sensitive", "redaction",
    },
    "testing": {
        "test", "acceptance", "regression", "e2e", "unit", "integration test",
        "verify", "verification", "preuve", "proof",
    },
    "platform": {
        "vps", "cloudflare", "runtime", "environment", "deploy", "infrastructure",
        "systemd", "worker",
    },
    "sre-observability": {
        "health", "log", "metric", "alert", "observability", "diagnostic",
        "monitor", "sentinel",
    },
    "performance": {
        "performance", "latency", "fast", "rapid", "rapide", "load", "capacity",
        "3 caractères", "3 characters",
    },
    "recovery": {
        "backup", "restore", "rollback", "recovery", "rpo", "rto", "migration",
    },
    "release": {
        "preview", "release", "production", "promotion", "deploy", "rollback",
    },
    "documentation": {
        "adr", "architecture", "documentation", "runbook", "traceability",
    },
}

DOMAIN_CAPABILITY = {
    "product-domain": "architecture-audit",
    "frontend": "architecture-audit",
    "backend-api": "architecture-audit",
    "data": "architecture-audit",
    "integration": "architecture-audit",
    "security": "architecture-audit",
    "testing": "architecture-audit",
    "platform": "architecture-audit",
    "sre-observability": "architecture-audit",
    "performance": "architecture-audit",
    "recovery": "architecture-audit",
    "release": "architecture-audit",
    "documentation": "architecture-audit",
}


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


def require_schema(value: dict[str, Any], expected: str, label: str) -> None:
    if value.get("schema") != expected:
        raise SystemExit(
            f"SCHEMA_MISMATCH={label}:expected={expected}:actual={value.get('schema')}"
        )


def slug(value: str) -> str:
    x = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return x or "item"


def requirement_text(req: dict[str, Any]) -> str:
    fields: list[str] = [
        str(req.get("title") or ""),
        str(req.get("objective") or ""),
        *[str(x) for x in req.get("functional_requirements") or []],
        *[str(x) for x in req.get("acceptance_criteria") or []],
        *[str(x) for x in req.get("constraints") or []],
        *[str(x) for x in req.get("must_preserve") or []],
        *[str(x) for x in req.get("unknowns") or []],
    ]
    return " ".join(fields).lower()


def infer_domains(req: dict[str, Any], manifest: dict[str, Any], policy: dict[str, Any]) -> tuple[list[str], dict[str, list[str]]]:
    explicit = [str(x) for x in req.get("domains") or []]
    reasons: dict[str, list[str]] = {d: ["explicit product requirement domain"] for d in explicit}
    text = requirement_text(req)

    for domain, words in KEYWORDS.items():
        hits = sorted({w for w in words if w in text})
        if hits:
            reasons.setdefault(domain, []).append("keyword evidence: " + ", ".join(hits[:8]))

    # A functional product change always needs domain normalization, tests and ADR traceability.
    reasons.setdefault("product-domain", []).append("mandatory product/domain normalization")
    reasons.setdefault("testing", []).append("acceptance criteria require independent test design")
    reasons.setdefault("documentation", []).append("consequential design decisions require ADR traceability")

    # Component-aware reinforcement: if the requirement explicitly names a component id/path,
    # include the domains associated with that component type.
    component_domains = policy.get("component_domains") or {}
    for comp in manifest.get("components") or []:
        if not isinstance(comp, dict):
            continue
        cid = str(comp.get("id") or "")
        path = str(comp.get("path") or "")
        ctype = str(comp.get("type") or "")
        named = bool(cid and cid.lower() in text) or bool(path and path.lower() in text)
        if named:
            for domain in component_domains.get(ctype) or []:
                reasons.setdefault(str(domain), []).append(f"affected component named: {cid}")

    domains = [d for d in DOMAIN_ORDER if d in reasons]
    return domains, reasons


def affected_components(req: dict[str, Any], manifest: dict[str, Any], domains: list[str], policy: dict[str, Any]) -> list[str]:
    text = requirement_text(req)
    component_domains = policy.get("component_domains") or {}
    out: list[str] = []
    domain_set = set(domains)

    for comp in manifest.get("components") or []:
        if not isinstance(comp, dict):
            continue
        cid = str(comp.get("id") or "")
        ctype = str(comp.get("type") or "")
        path = str(comp.get("path") or "")
        comp_domains = set(str(x) for x in component_domains.get(ctype) or [])
        named = bool(cid and cid.lower() in text) or bool(path and path.lower() in text)
        if named or (comp_domains & domain_set):
            if cid and cid not in out:
                out.append(cid)
    return out


def role_capabilities(role: str, routing: dict[str, Any]) -> list[str]:
    r = (routing.get("roles") or {}).get(role) or {}
    return [str(x) for x in r.get("capabilities") or []]


def specialist_assignments(
    domains: list[str],
    reasons: dict[str, list[str]],
    policy: dict[str, Any],
    routing: dict[str, Any],
) -> list[dict[str, Any]]:
    domain_roles = policy.get("domain_roles") or {}
    contracts = policy.get("design_contracts") or {}
    mandatory_reviews = policy.get("mandatory_cross_reviews") or {}

    ordered_roles: list[str] = []
    role_domains: dict[str, list[str]] = {}
    role_reasons: dict[str, list[str]] = {}

    for domain in domains:
        role = str(domain_roles.get(domain) or "")
        if not role:
            continue
        if role not in ordered_roles:
            ordered_roles.append(role)
        role_domains.setdefault(role, []).append(domain)
        role_reasons.setdefault(role, []).extend(reasons.get(domain) or [])

    # Product-domain and ADR roles are non-optional boundaries.
    for role, why in (
        ("product-domain-architect", "mandatory product/domain contract"),
        ("documentation-adr-agent", "mandatory requirement-to-design traceability"),
    ):
        if role not in ordered_roles:
            ordered_roles.append(role)
        role_reasons.setdefault(role, []).append(why)

    assignments: list[dict[str, Any]] = []
    for role in ordered_roles:
        contract = contracts.get(role) or {}
        reviews = [str(x) for x in mandatory_reviews.get(role) or []]
        assignments.append({
            "role": role,
            "primary": role not in {"documentation-adr-agent"},
            "reason": sorted(set(role_reasons.get(role) or ["policy-required design role"])),
            "capabilities": role_capabilities(role, routing),
            "responsibilities": [str(x) for x in contract.get("responsibilities") or []],
            "outputs": [str(x) for x in contract.get("outputs") or []],
            "review_roles": reviews,
        })
    return assignments


def architecture_decisions(
    domains: list[str],
    req: dict[str, Any],
    policy: dict[str, Any],
) -> list[dict[str, Any]]:
    catalog = policy.get("decision_catalog") or {}
    domain_roles = policy.get("domain_roles") or {}
    constraints = [str(x) for x in req.get("constraints") or []]
    preserve = [str(x) for x in req.get("must_preserve") or []]
    technical = req.get("technical_constraints") or {}
    technical_lines = []
    if technical.get("readonly_external_system"):
        technical_lines.append("external system must remain READONLY")
    if technical.get("production_change_requires_approval"):
        technical_lines.append("production changes require explicit human approval")
    for x in technical.get("must_use") or []:
        technical_lines.append("must use: " + str(x))
    for x in technical.get("must_not_use") or []:
        technical_lines.append("must not use: " + str(x))
    inherited = constraints + ["must preserve: " + x for x in preserve] + technical_lines

    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for domain in domains:
        role = str(domain_roles.get(domain) or "chacha-dev-architect")
        for item in catalog.get(domain) or []:
            did = str(item.get("id") or "")
            if not did or did in seen:
                continue
            seen.add(did)
            out.append({
                "id": did,
                "owner_role": role,
                "status": "REQUIRED",
                "question": str(item.get("question") or ""),
                "required_output": str(item.get("required_output") or ""),
                "constraints": inherited,
            })
    return out


def cross_reviews(assignments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    present = {str(a["role"]) for a in assignments}
    review_map: dict[str, set[str]] = {}
    for a in assignments:
        subject = str(a["role"])
        for reviewer in a.get("review_roles") or []:
            reviewer = str(reviewer)
            if reviewer in present and reviewer != subject:
                review_map.setdefault(reviewer, set()).add(subject)
    return [
        {"reviewer_role": role, "subjects": sorted(subjects)}
        for role, subjects in sorted(review_map.items())
    ]


def build_task_graph(
    project: str,
    requirement_id: str,
    assignments: list[dict[str, Any]],
    reviews: list[dict[str, Any]],
) -> dict[str, Any]:
    tasks: list[dict[str, Any]] = []
    role_task: dict[str, str] = {}

    product_task = "design:product-domain-architect"
    for assignment in assignments:
        role = str(assignment["role"])
        tid = "design:" + slug(role)
        role_task[role] = tid
        deps: list[str] = []
        if role != "product-domain-architect":
            deps = [product_task]
        tasks.append({
            "id": tid,
            "kind": "artifact",
            "description": f"Produce technical-design fragment for {role} from requirement {requirement_id}",
            "owner_role": role,
            "capabilities": [DOMAIN_CAPABILITY.get("product-domain", "architecture-audit")],
            "permission": "plan",
            "depends_on": deps,
            "outputs": [{"type": "artifact", "id": f"technical-design-fragment:{role}"}],
            "verification": {
                "mode": "independent-agent",
                "self_certification_allowed": False,
                "required_evidence": ["requirement-ref", "manifest-ref", "decision-record", "review"],
            },
            "blocking": True,
            "parallel_group": "technical-design-specialists",
            "metadata": {
                "specialist_role": role,
                "specialist_capabilities": assignment.get("capabilities") or [],
                "design_outputs": assignment.get("outputs") or [],
            },
        })

    review_tasks: list[str] = []
    for review in reviews:
        reviewer = str(review["reviewer_role"])
        subjects = [str(x) for x in review.get("subjects") or []]
        tid = "design-review:" + slug(reviewer)
        deps = sorted({role_task[x] for x in subjects if x in role_task})
        if reviewer in role_task:
            deps.append(role_task[reviewer])
        deps = sorted(set(deps))
        tasks.append({
            "id": tid,
            "kind": "gate",
            "description": f"Cross-review technical design by {reviewer}",
            "owner_role": reviewer,
            "capabilities": ["architecture-audit"],
            "permission": "plan",
            "depends_on": deps,
            "outputs": [{"type": "gate", "id": f"technical-design-review:{reviewer}"}],
            "verification": {
                "mode": "independent-agent",
                "self_certification_allowed": False,
                "required_evidence": ["reviewed-fragments", "findings", "decision-links"],
            },
            "blocking": True,
            "parallel_group": "technical-design-cross-review",
            "metadata": {"review_subject_roles": subjects},
        })
        review_tasks.append(tid)

    adr_role = "documentation-adr-agent"
    adr_task = role_task.get(adr_role)
    if adr_task:
        # ADR synthesis must wait for every primary specialist and cross-review.
        all_other = [t["id"] for t in tasks if t["id"] != adr_task]
        for task in tasks:
            if task["id"] == adr_task:
                task["depends_on"] = sorted(set(all_other))
                task["parallel_group"] = "technical-design-finalization"
                task["description"] = (
                    f"Synthesize ADRs and requirement-design traceability for {requirement_id}"
                )
                break

    ids = {t["id"] for t in tasks}
    for task in tasks:
        unknown = set(task.get("depends_on") or []) - ids
        if unknown:
            raise SystemExit(f"TECHNICAL_DESIGN_DEPENDENCY_UNKNOWN={task['id']}:{','.join(sorted(unknown))}")

    return {
        "schema": GRAPH_SCHEMA,
        "project": project,
        "transition": "PRODUCT_REQUIREMENT->TECHNICAL_DESIGN",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tasks": tasks,
        "summary": {
            "task_count": len(tasks),
            "artifact_tasks": sum(t["kind"] == "artifact" for t in tasks),
            "gate_tasks": sum(t["kind"] == "gate" for t in tasks),
            "approval_tasks": 0,
            "blocking_tasks": sum(bool(t.get("blocking")) for t in tasks),
        },
    }


def plan(
    req: dict[str, Any],
    manifest: dict[str, Any],
    routing: dict[str, Any],
    policy: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    require_schema(req, REQ_SCHEMA, "requirement")
    require_schema(manifest, MANIFEST_SCHEMA, "manifest")
    require_schema(routing, ROUTING_SCHEMA, "agent-routing")
    require_schema(policy, POLICY_SCHEMA, "technical-design-policy")

    project = str(req["project"])
    manifest_project = str((manifest.get("identity") or {}).get("slug") or "")
    if project != manifest_project:
        raise SystemExit(
            f"PROJECT_MISMATCH=requirement:{project}:manifest:{manifest_project}"
        )

    domains, reasons = infer_domains(req, manifest, policy)
    components = affected_components(req, manifest, domains, policy)
    assignments = specialist_assignments(domains, reasons, policy, routing)
    decisions = architecture_decisions(domains, req, policy)
    reviews = cross_reviews(assignments)

    required_roles = {a["role"] for a in assignments if a["primary"]}
    backend_needed = "backend-api" in domains or "integration" in domains
    data_needed = "data" in domains
    if backend_needed and "backend-api-architect" not in required_roles:
        raise SystemExit("BACKEND_ARCHITECT_ROUTING_MISSING")
    if data_needed and "data-architect" not in required_roles:
        raise SystemExit("DATA_ARCHITECT_ROUTING_MISSING")

    required_before = [
        str(x)
        for x in ((policy.get("implementation_gate") or {}).get("required_before_implementation") or [])
    ]
    blockers = [
        "specialist-design-fragments-not-yet-produced",
        "mandatory-cross-reviews-not-yet-executed",
        "architecture-decisions-not-yet-resolved",
        "adr-set-not-yet-recorded",
    ]

    design_plan = {
        "schema": PLAN_SCHEMA,
        "project": project,
        "requirement_id": str(req["id"]),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "orchestrator": "chacha-dev-architect",
        "affected_components": components,
        "specialist_assignments": assignments,
        "architecture_decisions": decisions,
        "cross_reviews": reviews,
        "implementation_gate": {
            "code_generation_allowed": False,
            "blocking_reasons": blockers,
            "required_before_implementation": required_before,
        },
        "provenance": {
            "requirement_source": req.get("source"),
            "manifest": "project-manifest-v3",
            "routing_policy": "agent-routing-v1",
            "technical_design_policy": "technical-design-policy-v1",
            "product_owner_owns_what": True,
            "technical_specialists_own_how": True,
        },
    }
    graph = build_task_graph(project, str(req["id"]), assignments, reviews)
    return design_plan, graph


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--requirement", required=True, type=Path)
    ap.add_argument("--manifest", required=True, type=Path)
    ap.add_argument("--routing", type=Path, default=Path("dev-hub/config/agent-routing.v1.json"))
    ap.add_argument("--policy", type=Path, default=Path("dev-hub/config/technical-design.v1.json"))
    ap.add_argument("--output", required=True, type=Path)
    ap.add_argument("--task-graph-output", required=True, type=Path)
    args = ap.parse_args()

    result, graph = plan(
        load(args.requirement),
        load(args.manifest),
        load(args.routing),
        load(args.policy),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.task_graph_output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.task_graph_output.write_text(json.dumps(graph, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    roles = [x["role"] for x in result["specialist_assignments"]]
    print("TECHNICAL_DESIGN_PLAN=PASS")
    print("PROJECT=" + result["project"])
    print("REQUIREMENT_ID=" + result["requirement_id"])
    print("AFFECTED_COMPONENTS=" + ",".join(result["affected_components"]))
    print("SPECIALIST_ROLES=" + ",".join(roles))
    print("BACKEND_ARCHITECT=" + ("YES" if "backend-api-architect" in roles else "NO"))
    print("DATA_ARCHITECT=" + ("YES" if "data-architect" in roles else "NO"))
    print("CODE_GENERATION_ALLOWED=NO")
    print("IMPLEMENTATION_BLOCKED_UNTIL_TECHNICAL_DESIGN=PASS")
    print("TECHNICAL_DESIGN_OUTPUT=" + str(args.output))
    print("TECHNICAL_DESIGN_TASK_GRAPH=" + str(args.task_graph_output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
