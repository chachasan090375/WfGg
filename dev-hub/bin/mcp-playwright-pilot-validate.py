#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "config" / "provider-adapters.v1.json"
CATALOG = ROOT / "config" / "mcp-provider-catalog.v1.json"
CONTRACT = ROOT / "config" / "mcp-playwright-contract.v1.json"
CAPABILITIES = ROOT / "config" / "capability-registry.v1.json"
RECEIPT = ROOT / "evidence" / "playwright-mcp-pilot-promotion-receipt-2026-09-16.json"
PROMOTION_EVIDENCE = ROOT / "evidence" / "playwright-mcp-contract-ok-to-pilot-2026-09-16.json"
ADAPTER_EVIDENCE = ROOT / "evidence" / "playwright-mcp-adapter-contract-2026-09-16.json"
SAFE = [
    "browser_navigate",
    "browser_snapshot",
    "browser_console_messages",
    "browser_network_requests",
    "browser_close",
]
DENIED = {
    "browser_run_code_unsafe",
    "browser_evaluate",
    "browser_click",
    "browser_type",
    "browser_fill_form",
    "browser_file_upload",
    "browser_drop",
    "browser_drag",
    "browser_handle_dialog",
    "browser_hover",
    "browser_press_key",
    "browser_select_option",
    "browser_webmcp_call",
    "browser_webmcp_list",
}


def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit(f"PLAYWRIGHT_PILOT_INVALID:object:{path}")
    return value


def fail(message: str) -> None:
    raise SystemExit("PLAYWRIGHT_PILOT_INVALID:" + message)


def main() -> None:
    registry, catalog, contract, caps, receipt, promo, adapter_evidence = map(
        load, [REGISTRY, CATALOG, CONTRACT, CAPABILITIES, RECEIPT, PROMOTION_EVIDENCE, ADAPTER_EVIDENCE]
    )

    provider = (registry.get("providers") or {}).get("playwright-mcp") or {}
    adapter = (registry.get("adapters") or {}).get("playwright-mcp-adapter") or {}
    cat = (catalog.get("providers") or {}).get("playwright-mcp") or {}

    if provider != {"adapter": "playwright-mcp-adapter", "kind": "mcp", "execution": "external"}:
        fail("provider-binding")
    if adapter.get("status") != "PILOT":
        fail("adapter-status")
    if adapter.get("executable") is not None:
        fail("external-executable-must-be-null")
    if adapter.get("supports") != ["read"]:
        fail("adapter-permissions")

    if cat.get("runtime_status") != "PILOT":
        fail("catalog-status")
    if cat.get("provider_binding") != "playwright-mcp":
        fail("catalog-binding")
    if cat.get("health_probe") != "provider-specific-legacy-initialize-tools-list-and-safe-inspection":
        fail("catalog-health-probe")
    if contract.get("runtime_status") != "PILOT":
        fail("contract-status")
    protocol = contract.get("protocol") or {}
    if protocol.get("dev_hub_baseline") != "2026-07-28":
        fail("dev-hub-baseline")
    if protocol.get("upstream_compatibility_protocol") != "2025-11-25":
        fail("upstream-protocol")
    if protocol.get("compatibility_mode") != "EXPLICIT_PROVIDER_COMPATIBILITY":
        fail("compatibility-mode")
    if protocol.get("generic_legacy_fallback") is not False:
        fail("generic-legacy-fallback")

    tools = contract.get("tool_policy") or {}
    if tools.get("default") != "DENY":
        fail("tool-default")
    if tools.get("pilot_allow") != SAFE:
        fail("pilot-tool-surface")
    if set(tools.get("explicit_deny") or []) != DENIED:
        fail("deny-surface")
    if tools.get("caller_selects_tool") is not False:
        fail("caller-tool-choice")
    for key in ("arbitrary_javascript", "file_upload", "form_submission", "webmcp_page_tools",
                "workspace_write", "repository_write", "production_mutation"):
        if tools.get(key) is not False:
            fail("tool-policy:" + key)

    network = contract.get("network_policy") or {}
    required_network_true = [
        "test_or_preview_origins_only",
        "allowed_origins_required_at_runtime",
        "allowed_origins_supplied_by_adapter_environment_only",
        "redirect_target_must_be_revalidated_by_adapter",
        "query_string_removed_from_evidence_source",
        "service_workers_blocked_in_pilot",
    ]
    if any(network.get(k) is not True for k in required_network_true):
        fail("network-policy")
    if network.get("file_url_navigation") is not False or network.get("unrestricted_file_access") is not False:
        fail("filesystem-navigation")

    qual = contract.get("pilot_qualification") or {}
    if qual.get("promotion_evaluation_run_id") != 35091045623:
        fail("promotion-run")
    if qual.get("promotion_eligible") is not True or qual.get("promotion_blockers") != []:
        fail("promotion-eligibility")
    if qual.get("requires_local_executable") is not False:
        fail("local-executable")
    if qual.get("production_capable") is not False or qual.get("approval_required") is not False:
        fail("production-boundary")

    if receipt.get("receipt_schema") != "chacha.dev/adapter-promotion-receipt/v1":
        fail("receipt-schema")
    if receipt.get("transition") != "CONTRACT_OK->PILOT":
        fail("receipt-transition")
    if receipt.get("eligible") is not True or receipt.get("applied") is not True or receipt.get("blockers") != []:
        fail("receipt-result")
    if receipt.get("execution_kinds") != ["external"] or receipt.get("requires_local_executable") is not False:
        fail("receipt-execution")
    if receipt.get("previous_entry", {}).get("status") != "CONTRACT_OK":
        fail("receipt-old-status")
    if receipt.get("new_entry") != {"status": "PILOT", "executable": None, "supports": ["read"]}:
        fail("receipt-new-entry")
    if receipt.get("workflow", {}).get("artifact_digest") != "sha256:7aa7f402435ca1df9dfad47ef739e3eb653f65f813eb0f4cc2156a87d12dff9c":
        fail("receipt-artifact")

    if promo.get("schema") != "chacha.dev/adapter-promotion-evidence/v1":
        fail("promotion-evidence-schema")
    if set((promo.get("evidence") or {}).keys()) != {"runtime-contract-pass", "sandbox-only", "provisioning-pass"}:
        fail("promotion-evidence-set")
    if any(v.get("status") != "PASS" for v in (promo.get("evidence") or {}).values()):
        fail("promotion-evidence-pass")
    if adapter_evidence.get("runtime_result", {}).get("verification_status") != "UNVERIFIED":
        fail("verification-boundary")

    # PILOT lifecycle admission is separate from capability admission. The provider
    # must not become schedulable until provider health + capability wiring have
    # their own evidence and CI gate.
    for capability, item in (caps.get("capabilities") or {}).items():
        ids = [x.get("id") for x in (item.get("providers") or []) if isinstance(x, dict)]
        if "playwright-mcp" in ids:
            fail("premature-capability-admission:" + capability)

    print("PLAYWRIGHT_MCP_PILOT_VALID: status=PILOT external=true read_only=true selectable=false blockers=0")


if __name__ == "__main__":
    main()
