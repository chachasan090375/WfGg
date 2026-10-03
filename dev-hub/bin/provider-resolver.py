#!/usr/bin/env python3
"""ChaCha DEV HUB Provider Resolver V1.

Resolves one or more abstract capabilities to concrete providers using the
Capability Registry plus an explicit health snapshot. It never executes a
provider. UNKNOWN health is deliberately not treated as healthy.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

REGISTRY_SCHEMA = "chacha.dev/capability-registry/v1"
HEALTH_SCHEMA = "chacha.dev/provider-health-snapshot/v1"
POLICY_SCHEMA = "chacha.dev/execution-scheduler/v1"

STATUS_SCORE = {
    "ADOPT": 60,
    "PILOT": 50,
    "WATCH": 40,
    "ASSESS": 30,
    "DISCOVER": 20,
    "DEPRECATE": 10,
    "RETIRE": 0,
}
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


def require_schema(value: dict[str, Any], expected: str, label: str) -> None:
    if value.get("schema") != expected:
        raise SystemExit(f"SCHEMA_MISMATCH={label}:expected={expected}:actual={value.get('schema')}")


def fallback_provider_ids(providers: list[dict[str, Any]], primary_id: str) -> set[str]:
    by_id={str(p.get("id")):p for p in providers if isinstance(p,dict) and p.get("id")}
    allowed:set[str]=set(); queue=list((by_id.get(primary_id) or {}).get("fallback") or [])
    while queue:
        pid=str(queue.pop(0))
        if not pid or pid in allowed or pid==primary_id: continue
        if pid not in by_id: continue
        allowed.add(pid); queue.extend((by_id[pid].get("fallback") or []))
    return allowed

def resolve(
    capability: str,
    registry: dict[str, Any],
    health: dict[str, Any],
    policy: dict[str, Any],
    permission: str,
    preferred: str | None = None,
) -> dict[str, Any]:
    cap = (registry.get("capabilities") or {}).get(capability)
    if not isinstance(cap, dict):
        return {"capability": capability, "provider": None, "provider_status": None, "health_state": None,
                "state": "BLOCKED", "fallback_used": False, "reason": "capability-not-registered"}

    selection = policy.get("provider_selection") or {}
    allow_unknown = bool(selection.get("allow_unknown", False))
    production_like = permission in {
        "production-deploy", "production-data-write", "secret-change",
        "destructive-operation", "technology-replacement"
    }
    allow_degraded = bool(
        selection.get("allow_degraded_for_production" if production_like else "allow_degraded_for_non_production", False)
    )

    providers=[p for p in (cap.get("providers") or []) if isinstance(p,dict) and p.get("status")!="RETIRE"]
    if not providers:
        return {"capability": capability, "provider": None, "provider_status": None, "health_state": None,
                "state": "BLOCKED", "fallback_used": False, "reason": "no-provider"}
    primary=str(providers[0].get("id") or "")
    primary_snap=(health.get("providers") or {}).get(primary) or {}
    if primary_snap.get("policy_allowed") is False:
        return {"capability": capability, "provider": None, "provider_status": providers[0].get("status"), "health_state": primary_snap.get("state","UNKNOWN"),
                "state": "BLOCKED", "fallback_used": False, "reason": "primary-policy-denied"}
    if primary_snap.get("security_gates_available") is False:
        return {"capability": capability, "provider": None, "provider_status": providers[0].get("status"), "health_state": primary_snap.get("state","UNKNOWN"),
                "state": "BLOCKED", "fallback_used": False, "reason": "primary-security-gate-unavailable"}
    allowed_fallbacks=fallback_provider_ids(providers,primary)
    candidates: list[dict[str, Any]] = []
    for provider in providers:
        if not isinstance(provider, dict):
            continue
        status = provider.get("status", "DISCOVER")
        if status == "RETIRE":
            continue
        pid = str(provider.get("id") or "")
        if pid != primary and pid not in allowed_fallbacks:
            continue
        snap = (health.get("providers") or {}).get(pid) or {}
        if snap.get("policy_allowed") is False or snap.get("security_gates_available") is False:
            continue
        hstate = snap.get("state", "UNKNOWN")
        if hstate == "UNAVAILABLE":
            continue
        if hstate == "UNKNOWN" and not allow_unknown:
            continue
        if hstate == "DEGRADED" and not allow_degraded:
            continue
        score = STATUS_SCORE.get(status, -100) + HEALTH_SCORE.get(hstate, -100)
        if preferred and pid == preferred:
            score += 1000
        candidates.append({"provider": provider, "health": snap, "score": score})

    if not candidates:
        return {"capability": capability, "provider": None, "provider_status": None, "health_state": None,
                "state": "BLOCKED", "fallback_used": False, "reason": "no-healthy-eligible-provider"}

    candidates.sort(key=lambda x: (x["score"], x["provider"].get("id", "")), reverse=True)
    chosen = candidates[0]
    provider = chosen["provider"]
    snap = chosen["health"]
    hstate = snap.get("state", "UNKNOWN")
    pid = provider.get("id")
    degraded = hstate == "DEGRADED" or provider.get("status") == "DEPRECATE"
    state = "DEGRADED" if degraded else "READY"
    return {
        "capability": capability,
        "provider": pid,
        "provider_status": provider.get("status"),
        "health_state": hstate,
        "state": state,
        "fallback_used": bool(preferred and pid != preferred),
        "reason": "health-and-policy-selection",
        "health_source": snap.get("source"),
        "checked_at": snap.get("checked_at"),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", required=True, type=Path)
    parser.add_argument("--health", required=True, type=Path)
    parser.add_argument("--policy", required=True, type=Path)
    parser.add_argument("--permission", default="read")
    parser.add_argument("--preferred")
    parser.add_argument("capabilities", nargs="+")
    args = parser.parse_args()

    registry = load(args.registry)
    health = load(args.health)
    policy = load(args.policy)
    require_schema(registry, REGISTRY_SCHEMA, "registry")
    require_schema(health, HEALTH_SCHEMA, "health")
    require_schema(policy, POLICY_SCHEMA, "policy")

    results = [resolve(c, registry, health, policy, args.permission, args.preferred) for c in args.capabilities]
    print(json.dumps({
        "resolutions": results,
        "ready": all(x["state"] != "BLOCKED" for x in results),
        "fallback_count": sum(bool(x.get("fallback_used")) for x in results),
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
