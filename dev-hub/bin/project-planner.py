#!/usr/bin/env python3
"""ChaCha DEV HUB Project Planner V1.

Transforms a Project Intent into a deterministic architecture Project Plan
and a draft Manifest V3. It never executes providers or changes production.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

INTENT_ID = "chacha.dev/project-intent/v1"
PLAN_ID = "chacha.dev/project-plan/v1"
MANIFEST_ID = "chacha.dev/project-manifest/v3"
REGISTRY_ID = "chacha.dev/capability-registry/v1"
PATHS_ID = "chacha.dev/golden-path-registry/v1"

STATUS_RANK = {"ADOPT": 60, "PILOT": 50, "WATCH": 40, "ASSESS": 30, "DISCOVER": 20, "DEPRECATE": 10, "RETIRE": 0}
CONDITIONAL = {"PILOT", "WATCH", "ASSESS", "DISCOVER"}
GATES = [
    "product-domain", "ux-frontend", "api-backend", "data", "integrations",
    "identity-security", "testing", "build-dependencies", "ci-cd-release",
    "environments-infra", "observability", "performance", "reliability-resilience",
    "backup-recovery", "documentation", "operations-sre", "finops-capacity",
    "governance-compliance",
]


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


def score(intent: dict[str, Any], path: dict[str, Any]) -> tuple[float, list[str]]:
    total = 0.0
    reasons: list[str] = []
    channels = set(intent.get("channels") or [])
    fit = path.get("fit") or {}
    overlap = channels & set(fit.get("channels") or [])
    if overlap:
        total += min(0.45, 0.15 * len(overlap))
        reasons.append("channel match: " + ", ".join(sorted(overlap)))
    data = intent.get("data") or {}
    if data.get("stores_data"):
        if fit.get("data_store"):
            total += 0.18
            reasons.append("persistent-data fit")
        else:
            total -= 0.18
    all_components = set(path.get("components", [])) | set(path.get("optional_components", []))
    if data.get("object_storage_required") and "object-storage" in all_components:
        total += 0.10
        reasons.append("object-storage fit")
    if data.get("relational_required") and "database" in all_components:
        total += 0.10
        reasons.append("relational-data fit")
    nf = intent.get("non_functional") or {}
    if nf.get("real_time_required") and fit.get("real_time"):
        total += 0.08
        reasons.append("real-time fit")
    if nf.get("offline_required") and "pwa" in set(fit.get("channels") or []):
        total += 0.08
        reasons.append("offline/PWA fit")
    prefs = intent.get("preferences") or {}
    if prefs.get("simplicity_over_flexibility") and fit.get("simplicity") == "high":
        total += 0.06
        reasons.append("simplicity preference")
    if prefs.get("managed_services_preferred") and fit.get("managed_first"):
        total += 0.06
        reasons.append("managed-services preference")
    if intent.get("criticality") in {"high", "critical"} and fit.get("managed_first"):
        total += 0.05
        reasons.append("managed-service bias for critical workload")
    return max(0.0, min(1.0, total)), reasons


def select_paths(intent: dict[str, Any], paths: dict[str, Any]) -> list[dict[str, Any]]:
    ranked = []
    for path in paths.get("paths", []):
        value, reasons = score(intent, path)
        ranked.append((value, path, reasons))
    ranked.sort(key=lambda item: (item[0], item[1].get("id", "")), reverse=True)
    if not ranked:
        raise SystemExit("NO_GOLDEN_PATHS")
    primary = ranked[0]
    selected = [{"path": primary[1], "score": primary[0], "reasons": primary[2]}]
    channels = set(intent.get("channels") or [])
    for addon_id, trigger in (("GP-05", {"scheduled", "event-driven"}), ("GP-06", {"ai-agent"}), ("GP-07", {"3d-pipeline"})):
        if channels & trigger and primary[1].get("id") != addon_id:
            addon = next((item for item in ranked if item[1].get("id") == addon_id), None)
            if addon:
                selected.append({"path": addon[1], "score": max(addon[0], 0.65), "reasons": addon[2] + ["composite-path trigger"]})
    return selected


def component(kind: str) -> dict[str, Any]:
    ids = {
        "frontend-web": "frontend", "frontend-mobile": "mobile", "backend-api": "api",
        "worker-edge": "api", "service": "service", "database": "database",
        "object-storage": "object-storage", "cache": "cache", "queue-event-bus": "events",
        "scheduled-job": "job", "data-pipeline": "pipeline", "ai-agent": "ai-agent",
        "3d-pipeline": "3d-pipeline", "static-assets": "assets",
    }
    return {"id": ids.get(kind, kind.replace("_", "-")), "type": kind, "required": True, "reason": "selected-golden-path", "depends_on": []}


def infer_components(intent: dict[str, Any], selected: list[dict[str, Any]]) -> list[dict[str, Any]]:
    kinds: list[str] = []
    optional: set[str] = set()
    for item in selected:
        p = item["path"]
        for kind in p.get("components", []):
            if kind not in kinds:
                kinds.append(kind)
        optional.update(p.get("optional_components", []))
    data = intent.get("data") or {}
    if data.get("stores_data") and "database" in optional and "database" not in kinds:
        kinds.append("database")
    if data.get("object_storage_required") and "object-storage" not in kinds:
        kinds.append("object-storage")
    channels = set(intent.get("channels") or [])
    if "scheduled" in channels and not ({"scheduled-job", "data-pipeline"} & set(kinds)):
        kinds.append("scheduled-job")
    if "ai-agent" in channels and "ai-agent" not in kinds:
        kinds.append("ai-agent")
    result = [component(kind) for kind in kinds]
    by_id = {item["id"]: item for item in result}
    if "frontend" in by_id and "api" in by_id:
        by_id["frontend"]["depends_on"].append("api")
    for app in ("api", "service"):
        if app in by_id and "database" in by_id:
            by_id[app]["depends_on"].append("database")
        if app in by_id and "object-storage" in by_id:
            by_id[app]["depends_on"].append("object-storage")
    if "ai-agent" in by_id and "api" in by_id:
        by_id["ai-agent"]["depends_on"].append("api")
    return result


def resolve(cap_id: str, registry: dict[str, Any]) -> dict[str, Any]:
    cap = (registry.get("capabilities") or {}).get(cap_id)
    if not cap:
        return {"id": cap_id, "required": True, "provider": None, "provider_status": None, "resolution_state": "UNAVAILABLE", "reason": "capability-not-registered"}
    providers = [p for p in cap.get("providers", []) if p.get("status") != "RETIRE"]
    if not providers:
        return {"id": cap_id, "required": True, "provider": None, "provider_status": None, "resolution_state": "UNAVAILABLE", "reason": "no-eligible-provider"}
    chosen = max(providers, key=lambda p: STATUS_RANK.get(p.get("status", ""), -1))
    status = chosen.get("status", "UNKNOWN")
    state = "READY" if status == "ADOPT" else "CONDITIONAL" if status in CONDITIONAL else "DEGRADED" if status == "DEPRECATE" else "UNAVAILABLE"
    return {"id": cap_id, "required": True, "provider": chosen.get("id"), "provider_status": status, "resolution_state": state, "reason": "best-fit-registry-selection"}


def capabilities(intent: dict[str, Any], selected: list[dict[str, Any]], registry: dict[str, Any]) -> list[dict[str, Any]]:
    ids = ["source-control", "code-edit", "code-review", "technology-radar", "architecture-audit", "storage-governance"]
    for item in selected:
        for cap in item["path"].get("capabilities", []):
            if cap not in ids:
                ids.append(cap)
    if set(intent.get("channels") or []) & {"web", "pwa"}:
        for cap in ("web-docs", "library-docs", "e2e-test-web", "performance-test-web", "smoke-test-web"):
            if cap not in ids:
                ids.append(cap)
    return [resolve(cap, registry) for cap in ids]


def gate_map(intent: dict[str, Any]) -> dict[str, Any]:
    blocking = {"identity-security", "testing", "build-dependencies", "ci-cd-release", "backup-recovery"}
    if intent.get("criticality") in {"high", "critical"}:
        blocking |= {"observability", "reliability-resilience"}
    return {gate: {"required": True, "blocking": gate in blocking, "evidence_expected": ["machine-verifiable evidence before OK"]} for gate in GATES}


def decision_list(intent: dict[str, Any], resolved: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    channels = set(intent.get("channels") or [])
    data = intent.get("data") or {}
    nf = intent.get("non_functional") or {}
    if channels & {"web", "pwa", "mobile", "api"}:
        out.append({"id": "AUTH_MODEL", "status": "NEEDS_INPUT", "question": "What authentication/authorization model is required?", "recommendation": "Choose the least-complex model that satisfies user and data sensitivity requirements.", "options": ["anonymous/public", "email-link", "OIDC/OAuth", "enterprise-SSO"], "rationale": ["identity boundaries affect frontend, API, secrets and audit requirements"]})
    if data.get("stores_data") and nf.get("rpo_hours") is None:
        out.append({"id": "RPO", "status": "NEEDS_INPUT", "question": "What is the maximum acceptable data-loss window (RPO)?", "recommendation": "Set an explicit RPO before release.", "options": ["24h", "4h", "1h", "<1h"], "rationale": ["backup cadence cannot be validated without an RPO"]})
    if data.get("stores_data") and nf.get("rto_hours") is None:
        out.append({"id": "RTO", "status": "NEEDS_INPUT", "question": "What is the maximum acceptable restoration time (RTO)?", "recommendation": "Set an explicit RTO before release.", "options": ["24h", "4h", "2h", "<1h"], "rationale": ["recovery architecture depends on target restoration time"]})
    for item in resolved:
        if item["resolution_state"] == "CONDITIONAL":
            out.append({"id": "PROVIDER_" + item["id"].upper().replace("-", "_"), "status": "NEEDS_EVIDENCE", "question": f"Promote provider {item['provider']} for capability {item['id']}?", "recommendation": "Keep conditional until execution and comparative evidence exists.", "options": ["retain-conditional", "pilot", "adopt-after-evidence", "replace-provider"], "rationale": [f"registry status is {item['provider_status']}"]})
    return out


def draft_manifest(intent: dict[str, Any], comps: list[dict[str, Any]], resolved: list[dict[str, Any]], gates: dict[str, Any]) -> dict[str, Any]:
    ident = intent["identity"]
    nf = intent.get("non_functional") or {}
    data = intent.get("data") or {}
    mcomps = []
    for item in comps:
        interfaces = ["https"] if item["type"] == "frontend-web" else ["https-api"] if item["type"] in {"worker-edge", "backend-api", "service"} else []
        mcomps.append({"id": item["id"], "type": item["type"], "path": item["id"], "interfaces": interfaces, "depends_on": item.get("depends_on", []), "commands": {}, "artifacts": [], "env_refs": [], "secret_refs": [], "observability_hooks": [], "owner": item["id"] + "-role"})
    return {
        "schema": MANIFEST_ID,
        "identity": {"name": ident["name"], "slug": ident["slug"], "description": ident.get("description", intent.get("goal", "")), "lifecycle_stage": "DESIGN", "criticality": intent.get("criticality", "medium"), "tags": sorted(set(intent.get("channels") or []))},
        "repository": {"url": "UNRESOLVED", "default_branch": "main", "monorepo": True, "source_of_truth": "git"},
        "ownership": {"technical_owner": "project-owner"},
        "components": mcomps,
        "dependencies": [{"from": c["id"], "to": dep, "kind": "runtime", "required": True} for c in comps for dep in c.get("depends_on", [])],
        "environments": [{"name": "development", "class": "dev", "approval_required": False}, {"name": "preview", "class": "preview", "promotion_from": "development", "approval_required": False}, {"name": "production", "class": "production", "promotion_from": "preview", "approval_required": True}],
        "capabilities": [{"id": r["id"], "required": True, **({"preferred_provider": r["provider"]} if r.get("provider") else {}), "fallback_allowed": True} for r in resolved],
        "quality_gates": {k: {"required": v["required"], "blocking": v["blocking"], "minimum_status": "OK" if v["blocking"] else "PARTIAL", "evidence_required": True} for k, v in gates.items()},
        "non_functional_requirements": {"availability_target": nf.get("availability_target", ""), "latency_target": nf.get("latency_target", ""), "accessibility_target": (intent.get("users") or {}).get("accessibility_target", ""), "supported_locales": (intent.get("users") or {}).get("locales", [])},
        "security": {"production_change_requires_approval": True},
        "data": {"classification": data.get("sensitivity", "internal"), "retention_policy": data.get("retention", "UNRESOLVED")},
        "observability": {"structured_logs": True, "health_checks": True, "alerts_required": True},
        "recovery": {"rpo_hours": nf.get("rpo_hours"), "rto_hours": nf.get("rto_hours"), "backup_policy": "UNRESOLVED", "restore_procedure": "UNRESOLVED", "production_restore_test_required": True},
        "delivery": {"ci_provider": "github-actions", "release_strategy": "preview-then-production", "rollback_strategy": "required", "artifact_versioning": "git-sha"},
        "storage": {"governor_required": True, "tiers": [{"name": "git", "purpose": ["source", "configuration", "docs", "tests"], "provider": "github", "retention": "versioned"}, {"name": "execution", "purpose": ["workspace", "temporary-builds", "bounded-caches"], "provider": "vps", "retention": "ephemeral"}, {"name": "archive", "purpose": ["artifacts", "backups", "history"], "provider": "nas", "retention": "policy-driven"}]},
        "technology_policy": {"radar_enabled": True, "auto_replace_production": False, "pilot_requires_approval": True, "recommend_requires_comparative_evidence": True, "allowed_stages": ["DISCOVER", "WATCH", "ASSESS", "PILOT", "RECOMMEND", "ADOPT", "DEPRECATE", "RETIRE"]},
        "operations": {"rollback_required": True, "quota_monitoring_required": True}
    }


def make_plan(intent: dict[str, Any], registry: dict[str, Any], paths: dict[str, Any]) -> dict[str, Any]:
    if intent.get("schema") != INTENT_ID:
        raise SystemExit(f"INTENT_SCHEMA_INVALID={intent.get('schema')}")
    if registry.get("schema") != REGISTRY_ID:
        raise SystemExit(f"REGISTRY_SCHEMA_INVALID={registry.get('schema')}")
    if paths.get("schema") != PATHS_ID:
        raise SystemExit(f"GOLDEN_PATH_SCHEMA_INVALID={paths.get('schema')}")
    selected = select_paths(intent, paths)
    comps = infer_components(intent, selected)
    resolved = capabilities(intent, selected, registry)
    gates = gate_map(intent)
    decisions = decision_list(intent, resolved)
    bad = [r["id"] for r in resolved if r["resolution_state"] in {"UNAVAILABLE", "DEGRADED"}]
    unresolved = [d["id"] for d in decisions if d["status"] in {"NEEDS_INPUT", "NEEDS_APPROVAL"}]
    ready = not bad and not unresolved
    ranked_alternatives = sorted(((score(intent, p)[0], p["id"]) for p in paths.get("paths", [])), reverse=True)
    primary = selected[0]
    return {
        "schema": PLAN_ID,
        "project": intent["identity"]["slug"],
        "golden_path": {"id": "+".join(x["path"]["id"] for x in selected), "confidence": round(primary["score"], 2), "reasons": primary["reasons"], "alternatives": [pid for _, pid in ranked_alternatives if pid != primary["path"]["id"]][:3]},
        "components": comps,
        "capabilities": resolved,
        "quality_gates": gates,
        "decisions": decisions,
        "risks": ([{"id": "ARCH_UNRESOLVED", "severity": "high", "description": "Architecture contains unresolved mandatory decisions.", "mitigation": "Resolve all NEEDS_INPUT/NEEDS_APPROVAL decisions before implementation."}] if unresolved else []),
        "readiness": {"architecture_contract_ready": ready, "code_generation_allowed": ready, "production_change_allowed": False, "blocking_reasons": [f"capability:{x}" for x in bad] + [f"decision:{x}" for x in unresolved]},
        "draft_manifest": draft_manifest(intent, comps, resolved, gates),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("intent", type=Path)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--golden-paths", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--manifest-output", type=Path)
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()
    result = make_plan(load(args.intent), load(args.registry), load(args.golden_paths))
    text = json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None) + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    if args.manifest_output:
        args.manifest_output.write_text(json.dumps(result["draft_manifest"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
