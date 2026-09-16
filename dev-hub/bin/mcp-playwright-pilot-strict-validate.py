#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config" / "mcp-playwright-contract.v1.json"
CATALOG = ROOT / "config" / "mcp-provider-catalog.v1.json"
REGISTRY = ROOT / "config" / "provider-adapters.v1.json"
RECEIPT = ROOT / "evidence" / "playwright-mcp-pilot-strict-35091189045-receipt.json"
REPORT = ROOT / "evidence" / "playwright-mcp-pilot-strict-35091189045-report.json"
PROVENANCE = ROOT / "evidence" / "playwright-mcp-pilot-strict-35091189045-provenance.json"
PROMOTION = ROOT / "evidence" / "playwright-mcp-contract-ok-to-pilot-2026-09-16.json"
ADAPTER_EVIDENCE = ROOT / "evidence" / "playwright-mcp-adapter-contract-2026-09-16.json"


def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit(f"PLAYWRIGHT_PILOT_INVALID:{path.name}:not-object")
    return value


def require(ok: bool, label: str) -> None:
    if not ok:
        raise SystemExit(f"PLAYWRIGHT_PILOT_INVALID:{label}")


def main() -> None:
    c = load(CONTRACT)
    cat = load(CATALOG)
    reg = load(REGISTRY)
    receipt = load(RECEIPT)
    report = load(REPORT)
    provenance = load(PROVENANCE)
    promotion = load(PROMOTION)
    adapter_ev = load(ADAPTER_EVIDENCE)

    require(c.get("schema") == "chacha.dev/mcp-playwright-contract/v1", "contract-schema")
    require(cat.get("schema") == "chacha.dev/mcp-provider-catalog/v1", "catalog-schema")
    require(reg.get("schema") == "chacha.dev/provider-adapters/v1", "registry-schema")
    require(receipt.get("receipt_schema") == "chacha.dev/adapter-promotion-receipt/v1", "receipt-schema")
    require(report.get("schema") == "chacha.dev/adapter-promotion-report/v1", "report-schema")
    require(provenance.get("schema") == "chacha.dev/playwright-mcp-pilot-provenance/v1", "provenance-schema")
    require(promotion.get("schema") == "chacha.dev/adapter-promotion-evidence/v1", "promotion-evidence-schema")
    require(adapter_ev.get("schema") == "chacha.dev/playwright-mcp-adapter-contract-evidence/v1", "adapter-evidence-schema")

    provider = cat["providers"]["playwright-mcp"]
    binding = reg["providers"]["playwright-mcp"]
    adapter = reg["adapters"]["playwright-mcp-adapter"]

    require(c.get("runtime_status") == "PILOT", "contract-not-pilot")
    require(provider.get("runtime_status") == "PILOT", "catalog-not-pilot")
    require(adapter.get("status") == "PILOT", "adapter-not-pilot")
    require(binding.get("adapter") == "playwright-mcp-adapter", "provider-binding")
    require(binding.get("execution") == "external", "execution-not-external")
    require(adapter.get("executable") is None, "external-executable-must-be-null")
    require(adapter.get("supports") == ["read"], "permissions-not-read-only")
    require(provider.get("decision") == "ASSESS", "decision-changed")
    require(provider.get("provider_binding") == "playwright-mcp", "catalog-binding")
    require(provider.get("health_probe") == "playwright-provider-compat-initialize-tools-list-and-browser-launch", "health-probe-stale")

    protocol = cat.get("protocol") or {}
    cprotocol = c.get("protocol") or {}
    require(protocol.get("preferred_version") == "2026-07-28", "catalog-baseline-changed")
    require(protocol.get("discovery_method") == "server/discover", "catalog-discovery-changed")
    require(protocol.get("compatibility_policy") == "explicit-provider-adapter-only", "catalog-compat-policy")
    require(cprotocol.get("dev_hub_baseline") == "2026-07-28", "contract-baseline")
    require(cprotocol.get("upstream_observed") == "2025-11-25", "upstream-protocol")
    require(cprotocol.get("compatibility_mode") == "EXPLICIT_PROVIDER_COMPATIBILITY", "compat-mode")
    require(cprotocol.get("generic_legacy_fallback") is False, "generic-legacy-fallback")
    require(cprotocol.get("provider_result_trust") == "UNVERIFIED", "provider-trust")
    require(cprotocol.get("verification_broker_required") is True, "verification-broker")
    require(cprotocol.get("producer_must_not_self_verify") is True, "producer-self-verify")

    tools = c.get("tool_policy") or {}
    require(tools.get("default") == "DENY", "tool-default")
    require("browser_run_code_unsafe" in (tools.get("explicit_deny") or []), "unsafe-tool-not-denied")
    require("browser_evaluate" in (tools.get("explicit_deny") or []), "evaluate-not-denied")
    require(tools.get("arbitrary_javascript") is False, "javascript-enabled")
    require(tools.get("workspace_write") is False, "workspace-write")
    require(tools.get("repository_write") is False, "repository-write")
    require(tools.get("production_mutation") is False, "production-mutation")
    require((c.get("execution") or {}).get("production_target_allowed") is False, "production-target")
    require((c.get("execution") or {}).get("vps_install_allowed_at_pilot_stage") is False, "vps-install")

    pq = c.get("pilot_qualification") or {}
    require(pq.get("transition") == "CONTRACT_OK->PILOT", "pilot-transition")
    require(pq.get("modern_probe_workflow_run_id") == 35089773583, "modern-probe-run")
    require(pq.get("modern_probe_result") == "BLOCKED_UPSTREAM_SERVER_DISCOVER_UNSUPPORTED", "modern-probe-history")
    require(pq.get("legacy_compat_workflow_run_id") == 35090224070 and pq.get("legacy_compat_pass") is True, "legacy-compat")
    require(pq.get("adapter_contract_workflow_run_id") == 35090712764 and pq.get("adapter_contract_pass") is True, "adapter-contract")
    require(pq.get("promotion_sandbox_workflow_run_id") == 35091189045, "promotion-run")
    require(pq.get("promotion_sandbox_artifact_id") == 10443899182, "promotion-artifact")
    require(pq.get("promotion_sandbox_artifact_digest") == "sha256:1030b3caf128760d110f5b72495addb975adc97a7543ff075e270589e655da88", "promotion-artifact-digest")
    require(pq.get("promotion_evidence_digest") == "sha256:fbd8a337bb54ffe90309e5ec2ab5215be265960b515e19579aba340b73a14854", "promotion-evidence-digest")
    require(pq.get("eligible") is True and pq.get("sandbox_applied") is True, "pilot-not-qualified")
    require(pq.get("blockers") == [], "pilot-blockers")
    require(pq.get("production_capable") is False, "production-capable")
    require(pq.get("requires_local_executable") is False, "requires-local-executable")
    require(pq.get("permissions_expanded") is False, "permissions-expanded")
    require(pq.get("automatic_promotion") is False, "automatic-promotion")

    require(report.get("transition") == "CONTRACT_OK->PILOT", "report-transition")
    require(report.get("eligible") is True and report.get("applied") is True, "report-not-applied")
    require(report.get("blockers") == [], "report-blockers")
    require(report.get("production_capable") is False, "report-production")
    require(report.get("requires_local_executable") is False, "report-local-exec")
    require(receipt.get("previous_entry", {}).get("status") == "CONTRACT_OK", "receipt-previous")
    require(receipt.get("new_entry", {}).get("status") == "PILOT", "receipt-new")
    require(receipt.get("new_entry", {}).get("executable") is None, "receipt-executable")
    require(receipt.get("new_entry", {}).get("supports") == ["read"], "receipt-permissions")
    require(receipt.get("evidence_digest") == "sha256:fbd8a337bb54ffe90309e5ec2ab5215be265960b515e19579aba340b73a14854", "receipt-evidence-digest")

    required_labels = {"runtime-contract-pass", "sandbox-only", "provisioning-pass"}
    pe = promotion.get("evidence") or {}
    require(set(pe) == required_labels, "promotion-labels")
    for label in required_labels:
        require(pe[label].get("status") == "PASS", f"promotion-label:{label}")
        require(pe[label].get("source") == "github-actions:35090712764", f"promotion-source:{label}")
    require(pe["runtime-contract-pass"].get("details", {}).get("unsafe_tool_invoked") is False, "unsafe-tool-invoked")
    require(pe["sandbox-only"].get("details", {}).get("production_target") is False, "sandbox-production")
    require(pe["provisioning-pass"].get("details", {}).get("execution") == "external", "provisioning-execution")
    require(pe["provisioning-pass"].get("details", {}).get("local_executable") is None, "provisioning-local-exec")

    checks = adapter_ev.get("checks") or {}
    for key in (
        "generic_adapter_registry_contract", "tool_injection_blocked_before_runtime",
        "write_permission_blocked_before_runtime", "bad_binding_blocked_before_runtime",
        "real_dispatch_envelope_to_task_result", "task_result_status_ok",
        "verification_remains_unverified", "final_origin_revalidated",
        "query_string_removed_from_evidence_source", "origin_escalation_blocked",
        "repository_unchanged", "production_target_false", "workspace_write_false",
    ):
        require(checks.get(key) == "PASS", f"adapter-evidence:{key}")

    require(provenance.get("materialized_status") == "PILOT", "provenance-status")
    require(provenance.get("baseline_protocol") == "2026-07-28", "provenance-baseline")
    require(provenance.get("upstream_protocol") == "2025-11-25", "provenance-upstream")
    require(provenance.get("generic_legacy_fallback") is False, "provenance-generic-fallback")
    chain = provenance.get("chain") or []
    require([x.get("workflow_run_id") for x in chain] == [35089773583, 35090224070, 35090712764, 35091189045], "provenance-chain")
    safety = provenance.get("safety") or {}
    require(safety.get("supports") == ["read"], "provenance-supports")
    require(safety.get("local_executable") is None, "provenance-executable")
    require(safety.get("production_capable") is False, "provenance-production")
    require(safety.get("automatic_enable") is False, "provenance-auto-enable")

    require((c.get("admission") or {}).get("next_transition") == "PILOT->ENABLED", "next-transition")
    require((c.get("admission") or {}).get("automatic_promotion") is False, "admission-auto-promotion")

    print("PLAYWRIGHT_MCP_STRICT_PILOT_VALID: status=PILOT read_only=true production=false legacy_provider_specific=true enabled=false")


if __name__ == "__main__":
    main()
