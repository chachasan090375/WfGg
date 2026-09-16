#!/usr/bin/env python3
"""ChaCha DEV HUB Provider Selection Engine V1.

Ranks providers for Task Graph capabilities without dispatching anything.
It deliberately separates comparative ranking from execution eligibility:
non-admitted providers may be visible in shadow ranking, but only providers
whose adapters are PILOT/ENABLED and whose current health/permissions satisfy
policy can become selected_provider.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

POLICY_SCHEMA = "chacha.dev/provider-selection-policy/v1"
GRAPH_SCHEMA = "chacha.dev/task-graph/v1"
REGISTRY_SCHEMA = "chacha.dev/capability-registry/v1"
ADAPTERS_SCHEMA = "chacha.dev/provider-adapters/v1"
HEALTH_SCHEMA = "chacha.dev/provider-health-snapshot/v1"
HISTORY_SCHEMA = "chacha.dev/provider-performance-history/v1"
OUTPUT_SCHEMA = "chacha.dev/provider-selection-plan/v1"

COST_FIT = {
    "free": 1.0,
    "included": 1.0,
    "local": 1.0,
    "owned": 1.0,
    "low": 0.85,
    "quota": 0.65,
    "api": 0.55,
}
HEALTH_FIT = {"HEALTHY": 1.0, "DEGRADED": 0.65, "UNKNOWN": 0.0, "UNAVAILABLE": 0.0}
STATUS_FIT = {"ADOPT": 1.0, "PILOT": 0.9, "WATCH": 0.7, "ASSESS": 0.6, "DISCOVER": 0.4, "DEPRECATE": 0.2, "RETIRE": 0.0}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load(path: Path, required_schema: str | None = None) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit(f"FILE_NOT_FOUND={path}")
    except json.JSONDecodeError as exc:
        raise SystemExit(f"JSON_INVALID={path}:{exc.lineno}:{exc.colno}:{exc.msg}")
    if not isinstance(value, dict):
        raise SystemExit(f"JSON_ROOT_NOT_OBJECT={path}")
    if required_schema and value.get("schema") != required_schema:
        raise SystemExit(f"SCHEMA_MISMATCH={path}:expected={required_schema}:actual={value.get('schema')}")
    return value


def clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def history_metrics(history: dict[str, Any], provider: str, capability: str) -> dict[str, Any]:
    p = ((history.get("providers") or {}).get(provider) or {}) if history else {}
    c = ((p.get("capabilities") or {}).get(capability) or {}) if isinstance(p, dict) else {}
    return c if isinstance(c, dict) else {}


def quality_fit(metrics: dict[str, Any]) -> tuple[float, int]:
    runs = int(metrics.get("verified_runs") or 0)
    if runs <= 0:
        return 0.0, 0
    success = clamp(float(metrics.get("verified_success_rate", 0.0)))
    first = clamp(float(metrics.get("verification_first_pass_rate", 0.0)))
    rollback = clamp(float(metrics.get("rollback_rate", 0.0)))
    regression = clamp(float(metrics.get("regression_rate", 0.0)))
    rework = clamp(float(metrics.get("human_rework_rate", 0.0)))
    score = success * 0.40 + first * 0.20 + (1 - rollback) * 0.15 + (1 - regression) * 0.15 + (1 - rework) * 0.10
    return clamp(score), runs


def latency_fit(metrics: dict[str, Any]) -> float:
    raw = metrics.get("p95_latency_ms")
    if raw is None:
        return 0.5
    try:
        ms = float(raw)
    except (TypeError, ValueError):
        return 0.5
    if ms <= 5_000:
        return 1.0
    if ms <= 30_000:
        return 0.85
    if ms <= 120_000:
        return 0.65
    if ms <= 600_000:
        return 0.40
    return 0.20


def confidence(runs: int, policy: dict[str, Any]) -> str:
    levels = policy.get("confidence") or {}
    ordered = sorted(
        ((int((cfg or {}).get("minimum_verified_runs") or 0), name) for name, cfg in levels.items()),
        reverse=True,
    )
    for minimum, name in ordered:
        if runs >= minimum:
            return name
    return "NONE"


def permission_supported(permission: str, supports: list[str]) -> bool:
    return permission in supports


def rank_capability(
    task: dict[str, Any], capability: str, registry: dict[str, Any], adapters: dict[str, Any],
    health: dict[str, Any], history: dict[str, Any], policy: dict[str, Any],
) -> dict[str, Any]:
    cap = (registry.get("capabilities") or {}).get(capability)
    task_id = str(task.get("id") or "UNKNOWN")
    permission = str(task.get("permission") or "read")
    previous_provider = task.get("previous_provider")
    weights = ((policy.get("score") or {}).get("weights") or {})
    runtime_allowed = set(((policy.get("eligibility") or {}).get("require_adapter_runtime_status") or []))
    health_allowed = set(((policy.get("eligibility") or {}).get("require_health") or []))

    if not isinstance(cap, dict):
        return {
            "task_id": task_id,
            "capability": capability,
            "permission": permission,
            "eligible_providers": [],
            "rejected_providers": [{"provider": None, "reasons": ["CAPABILITY_NOT_REGISTERED"]}],
            "ranked_candidates": [],
            "selected_provider": None,
            "confidence": "NONE",
            "selection_reasons": ["CAPABILITY_NOT_REGISTERED"],
            "evidence_refs": [],
            "dispatch_authorized": False,
        }

    ranked: list[dict[str, Any]] = []
    eligible: list[str] = []
    rejected: list[dict[str, Any]] = []

    for provider in [x for x in (cap.get("providers") or []) if isinstance(x, dict)]:
        pid = str(provider.get("id") or "")
        if not pid:
            continue
        cap_status = str(provider.get("status") or "DISCOVER")
        if cap_status == "RETIRE":
            rejected.append({"provider": pid, "reasons": ["CAPABILITY_PROVIDER_RETIRED"]})
            continue

        binding = (adapters.get("providers") or {}).get(pid)
        reasons: list[str] = []
        adapter_id = None
        adapter_status = None
        adapter_supports: list[str] = []
        if not isinstance(binding, dict):
            reasons.append("PROVIDER_BINDING_MISSING")
        else:
            adapter_id = binding.get("adapter")
            adapter = (adapters.get("adapters") or {}).get(adapter_id)
            if not isinstance(adapter, dict):
                reasons.append("ADAPTER_MISSING")
            else:
                adapter_status = adapter.get("status")
                adapter_supports = [str(x) for x in (adapter.get("supports") or [])]
                if adapter_status not in runtime_allowed:
                    reasons.append(f"ADAPTER_NOT_RUNTIME_ADMITTED:{adapter_status}")
                if not permission_supported(permission, adapter_supports):
                    reasons.append(f"PERMISSION_NOT_SUPPORTED:{permission}")

        snap = (health.get("providers") or {}).get(pid) or {}
        hstate = str(snap.get("state") or "UNKNOWN")
        if hstate not in health_allowed:
            reasons.append(f"HEALTH_NOT_ELIGIBLE:{hstate}")

        metrics = history_metrics(history, pid, capability)
        qfit, verified_runs = quality_fit(metrics)
        lfit = latency_fit(metrics)
        cost = str(provider.get("cost_class") or "unknown")
        cfit = COST_FIT.get(cost, 0.5)
        hfit = HEALTH_FIT.get(hstate, 0.0)
        sfit = STATUS_FIT.get(cap_status, 0.3)
        rfit = 1.0 if permission_supported(permission, adapter_supports) else 0.0
        diversity = 1.0 if previous_provider and previous_provider != pid else (0.0 if previous_provider == pid else 0.5)

        dimensions = {
            "task_capability_fit": sfit,
            "verified_historical_quality": qfit,
            "provider_health": hfit,
            "risk_fit": rfit,
            "latency_fit": lfit,
            "cost_fit": cfit,
            "cross_provider_diversity": diversity,
        }
        score = sum(float(weights.get(name) or 0) * clamp(value) for name, value in dimensions.items())
        executable = not reasons
        if executable:
            eligible.append(pid)
        else:
            rejected.append({"provider": pid, "reasons": sorted(set(reasons))})

        ranked.append({
            "provider": pid,
            "capability_status": cap_status,
            "adapter": adapter_id,
            "adapter_status": adapter_status,
            "health": hstate,
            "cost_class": cost,
            "verified_runs": verified_runs,
            "confidence": confidence(verified_runs, policy),
            "score": round(score, 3),
            "score_dimensions": {k: round(v, 4) for k, v in dimensions.items()},
            "execution_eligible": executable,
            "execution_blockers": sorted(set(reasons)),
        })

    ranked.sort(key=lambda x: (x["score"], x["confidence"], x["provider"]), reverse=True)
    executable_ranked = [x for x in ranked if x["execution_eligible"]]
    selected = executable_ranked[0]["provider"] if executable_ranked else None
    selected_entry = executable_ranked[0] if executable_ranked else None

    reasons = []
    if selected_entry:
        reasons = [
            f"SELECTED_HIGHEST_ELIGIBLE_SCORE:{selected_entry['score']}",
            f"HEALTH:{selected_entry['health']}",
            f"ADAPTER_STATUS:{selected_entry['adapter_status']}",
        ]
    elif ranked:
        reasons = ["NO_EXECUTION_ELIGIBLE_PROVIDER", "SHADOW_RANKING_AVAILABLE"]
    else:
        reasons = ["NO_PROVIDER_CANDIDATE"]

    return {
        "task_id": task_id,
        "capability": capability,
        "permission": permission,
        "eligible_providers": eligible,
        "rejected_providers": rejected,
        "ranked_candidates": ranked,
        "selected_provider": selected,
        "confidence": selected_entry["confidence"] if selected_entry else (ranked[0]["confidence"] if ranked else "NONE"),
        "selection_reasons": reasons,
        "evidence_refs": list((metrics.get("evidence_refs") or []) if selected_entry else []),
        "dispatch_authorized": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="ChaCha DEV HUB plan-only provider selector")
    parser.add_argument("--graph", required=True, type=Path)
    parser.add_argument("--registry", required=True, type=Path)
    parser.add_argument("--adapters", required=True, type=Path)
    parser.add_argument("--health", required=True, type=Path)
    parser.add_argument("--policy", required=True, type=Path)
    parser.add_argument("--history", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    graph = load(args.graph, GRAPH_SCHEMA)
    registry = load(args.registry, REGISTRY_SCHEMA)
    adapters = load(args.adapters, ADAPTERS_SCHEMA)
    health = load(args.health, HEALTH_SCHEMA)
    policy = load(args.policy, POLICY_SCHEMA)
    history: dict[str, Any] = {}
    if args.history:
        history = load(args.history, HISTORY_SCHEMA)

    task_plans: list[dict[str, Any]] = []
    for task in graph.get("tasks") or []:
        if not isinstance(task, dict):
            continue
        for capability in task.get("capabilities") or []:
            task_plans.append(rank_capability(task, str(capability), registry, adapters, health, history, policy))

    selected_count = sum(x.get("selected_provider") is not None for x in task_plans)
    blocked_count = len(task_plans) - selected_count
    output = {
        "schema": OUTPUT_SCHEMA,
        "project": graph.get("project"),
        "transition": graph.get("transition"),
        "generated_at": now_iso(),
        "mode": policy.get("mode"),
        "task_plans": task_plans,
        "summary": {
            "capability_plan_count": len(task_plans),
            "execution_selectable_count": selected_count,
            "execution_blocked_count": blocked_count,
            "shadow_rankings_available": sum(bool(x.get("ranked_candidates")) for x in task_plans),
        },
        "dispatch_authorized": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"PROVIDER_SELECTION_PLAN_WRITTEN={args.output}")
    print(f"CAPABILITY_PLANS={len(task_plans)}")
    print(f"EXECUTION_SELECTABLE={selected_count}")
    print(f"EXECUTION_BLOCKED={blocked_count}")
    print("DISPATCH_AUTHORIZED=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
