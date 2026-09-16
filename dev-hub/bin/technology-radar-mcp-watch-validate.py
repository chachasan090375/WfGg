#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "config" / "mcp-provider-catalog.v1.json"
WATCH = ROOT / "config" / "technology-radar-mcp-watch.v1.json"
ROUTING = ROOT / "config" / "agent-routing.v1.json"


def fail(message: str) -> None:
    raise SystemExit(f"MCP_RADAR_WATCH_INVALID: {message}")


def main() -> int:
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    watch = json.loads(WATCH.read_text(encoding="utf-8"))
    routing = json.loads(ROUTING.read_text(encoding="utf-8"))

    if watch.get("schema") != "chacha.dev/technology-radar-mcp-watch/v1":
        fail("unexpected schema")
    if watch.get("owner_role") != "technology-radar-agent":
        fail("owner must be technology-radar-agent")

    inventory = watch.get("inventory", {})
    if inventory.get("catalog_path") != "dev-hub/config/mcp-provider-catalog.v1.json":
        fail("catalog path mismatch")
    if inventory.get("mode") != "DYNAMIC_ALL_PROVIDERS":
        fail("inventory must dynamically include all catalog providers")
    if inventory.get("exclude_provider_ids") != []:
        fail("provider exclusions are forbidden")

    catalog_decisions = {v.get("decision") for v in catalog.get("providers", {}).values()}
    watched_decisions = set(inventory.get("include_catalog_decisions", []))
    if not catalog_decisions.issubset(watched_decisions):
        fail(f"unwatched catalog decisions: {sorted(catalog_decisions - watched_decisions)}")

    catalog_runtime = {v.get("runtime_status") for v in catalog.get("providers", {}).values()}
    watched_runtime = set(inventory.get("include_runtime_statuses", []))
    if not catalog_runtime.issubset(watched_runtime):
        fail(f"unwatched runtime statuses: {sorted(catalog_runtime - watched_runtime)}")

    protocol = watch.get("protocol_watch", {})
    required_protocol_flags = [
        "enabled",
        "track_spec_revisions",
        "track_sdk_migration_guides",
        "track_extensions",
        "track_deprecations",
        "track_security_changes",
    ]
    for key in required_protocol_flags:
        if protocol.get(key) is not True:
            fail(f"protocol_watch.{key} must be true")
    if protocol.get("current_baseline") != "2026-07-28":
        fail("MCP baseline must be 2026-07-28 until an evidenced migration updates it")

    provider_watch = watch.get("provider_watch", {})
    if provider_watch.get("enabled") is not True:
        fail("provider watch must be enabled")
    if provider_watch.get("official_sources_first") is not True:
        fail("official sources must be preferred")
    if provider_watch.get("discover_uncatalogued_candidates") is not True:
        fail("candidate discovery must remain enabled")
    if provider_watch.get("candidate_discovery_is_recommendation_only") is not True:
        fail("new candidate discovery must be recommendation-only")

    gov = watch.get("governance", {})
    required_true = [
        "evidence_required",
        "source_urls_required",
        "recommendations_only",
        "human_approval_for_catalog_decision_change",
        "security_review_on_security_change",
        "platform_review_on_protocol_or_transport_change",
    ]
    for key in required_true:
        if gov.get(key) is not True:
            fail(f"governance.{key} must be true")
    required_false = [
        "catalog_mutation_allowed",
        "provider_status_mutation_allowed",
        "adapter_promotion_allowed",
        "production_change_allowed",
    ]
    for key in required_false:
        if gov.get(key) is not False:
            fail(f"governance.{key} must be false")

    role = routing.get("roles", {}).get("technology-radar-agent", {})
    required_caps = {"technology-radar", "web-research", "comparative-evaluation", "mcp-ecosystem-watch", "connector-watch", "protocol-watch"}
    caps = set(role.get("capabilities", []))
    if not required_caps.issubset(caps):
        fail(f"technology-radar-agent missing capabilities: {sorted(required_caps - caps)}")

    radar_rules = [r for r in routing.get("routing_rules", []) if r.get("primary_role") == "technology-radar-agent"]
    keywords = set()
    for rule in radar_rules:
        keywords.update(rule.get("match", []))
    required_keywords = {"mcp", "connector", "provider-catalog", "protocol-version", "deprecation"}
    if not required_keywords.issubset(keywords):
        fail(f"technology radar routing missing keywords: {sorted(required_keywords - keywords)}")

    count = len(catalog.get("providers", {}))
    print(f"MCP_RADAR_WATCH_VALID: providers_dynamic={count} protocol=MCP baseline=2026-07-28 exclusions=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
