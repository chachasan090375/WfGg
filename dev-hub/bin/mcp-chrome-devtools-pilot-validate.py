#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "config"
EVID = ROOT / "evidence"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def fail(message: str):
    raise SystemExit(f"CHROME_DEVTOOLS_MCP_PILOT_INVALID: {message}")


def main():
    contract = load(CFG / "mcp-chrome-devtools-contract.v1.json")
    adapters = load(CFG / "provider-adapters.v1.json")
    catalog = load(CFG / "mcp-provider-catalog.v1.json")
    runtime = load(EVID / "chrome-devtools-mcp-adapter-runtime-qualification-2026-09-16.json")
    navigation = load(EVID / "chrome-devtools-mcp-controlled-navigation-qualification-2026-09-16.json")
    receipt = load(EVID / "chrome-devtools-mcp-pilot-materialization-2026-09-16.json")

    if contract.get("runtime_status") != "PILOT": fail("contract status")
    adapter = adapters.get("adapters", {}).get("chrome-devtools-mcp-adapter", {})
    if adapter != {"status": "PILOT", "executable": None, "supports": ["read"]}: fail("adapter boundary")
    provider = adapters.get("providers", {}).get("chrome-devtools-mcp", {})
    if provider.get("adapter") != "chrome-devtools-mcp-adapter" or provider.get("execution") != "external": fail("provider binding")
    cat = catalog.get("providers", {}).get("chrome-devtools-mcp", {})
    if cat.get("runtime_status") != "PILOT" or cat.get("decision") != "ASSESS": fail("catalog state")

    proto = contract.get("protocol", {})
    if proto.get("dev_hub_preferred_protocol_version") != "2026-07-28": fail("baseline")
    if proto.get("upstream_protocol_version") != "2025-11-25": fail("compat protocol")
    if proto.get("compatibility_mode") != "EXPLICIT_PROVIDER_COMPATIBILITY" or proto.get("generic_legacy_fallback") is not False: fail("compat mode")
    if proto.get("provider_result_trust") != "UNVERIFIED" or proto.get("verification_broker_required") is not True: fail("verification boundary")

    policy = contract.get("tool_policy", {})
    if policy.get("default") != "DENY": fail("default policy")
    if policy.get("pilot_caller_operations") != ["inspect_current_page", "inspect_url"]: fail("caller operations")
    if policy.get("adapter_internal_allow") != ["navigate_page"]: fail("internal navigation")
    if policy.get("caller_direct_tool_selection") is not False or policy.get("caller_direct_page_id_selection") is not False or policy.get("caller_direct_allowlist_selection") is not False: fail("caller direct control")
    denied = set(policy.get("explicit_deny", []))
    for name in ("evaluate_script", "click", "fill", "type_text", "upload_file", "navigate_page"):
        if name not in denied: fail(f"missing caller deny {name}")
    for key in ("javascript_evaluation", "file_upload", "form_submission", "browser_interaction", "workspace_write", "repository_write", "production_mutation"):
        if policy.get(key) is not False: fail(f"unsafe boundary {key}")

    network = contract.get("network_policy", {})
    if network.get("test_or_preview_origins_only") is not True: fail("target scope")
    if network.get("adapter_validates_target_origin_before_runtime") is not True: fail("origin precheck")
    if network.get("redirect_target_must_be_revalidated_by_adapter") is not True or network.get("cross_origin_redirect_must_block") is not True: fail("redirect policy")
    if network.get("allowed_url_pattern_minimum_chrome_major") != 149: fail("Chrome minimum")

    if runtime.get("eligible_for_pilot_qualification") is not True or runtime.get("blockers") != []: fail("runtime qualification")
    if runtime.get("workflow_run_id") != 35117348691 or runtime.get("artifact_id") != 10455774189: fail("runtime evidence ids")
    if runtime.get("boundaries", {}).get("provider_result_verification") != "UNVERIFIED": fail("runtime trust")
    if navigation.get("pilot_promotion_ready") is not True or navigation.get("blockers") != []: fail("navigation qualification")
    if navigation.get("workflow_run_id") != 35120006463 or navigation.get("artifact_id") != 10456458970: fail("navigation evidence ids")
    checks = navigation.get("checks", {})
    for key in ("adapter_controlled_navigation", "same_origin_redirect_revalidated", "cross_origin_redirect_blocked", "javascript_evaluation_disabled", "browser_interaction_disabled", "repository_unchanged"):
        if checks.get(key) != "PASS": fail(f"navigation check {key}")

    pilot = contract.get("pilot_qualification", {})
    if pilot.get("transition") != "CONTRACT_OK->PILOT" or pilot.get("blockers") != []: fail("pilot transition")
    if pilot.get("automatic_promotion") is not False or pilot.get("permissions_expanded") is not False: fail("promotion boundary")
    if pilot.get("local_executable") is not None or pilot.get("execution") != "external": fail("execution boundary")
    if pilot.get("provider_result_verification") != "UNVERIFIED" or pilot.get("verification_broker_required") is not True: fail("pilot trust")

    if receipt.get("schema") != "chacha.dev/chrome-devtools-mcp-pilot-materialization/v1": fail("receipt schema")
    if receipt.get("transition") != "CONTRACT_OK->PILOT": fail("receipt transition")
    if receipt.get("status_change") != {"previous": "CONTRACT_OK", "new": "PILOT", "applied": True, "automatic": False}: fail("receipt state")
    bounds = receipt.get("boundaries", {})
    if bounds.get("supports") != ["read"] or bounds.get("local_executable") is not None or bounds.get("enabled") is not False: fail("receipt adapter boundary")
    if bounds.get("production_capable") is not False or bounds.get("browser_interaction") is not False or bounds.get("javascript_evaluation") is not False: fail("receipt runtime boundary")
    if bounds.get("provider_result_verification") != "UNVERIFIED" or bounds.get("verification_broker_required") is not True: fail("receipt trust")
    if receipt.get("blockers") != []: fail("receipt blockers")

    admission = contract.get("admission", {})
    if admission.get("automatic_promotion") is not False or admission.get("next_transition") != "PILOT->ENABLED": fail("next transition")
    if admission.get("pilot_promotion_materialized") is not True: fail("materialization marker")

    print("CHROME_DEVTOOLS_MCP_PILOT_VALID state=PILOT enabled=false read_only=true controlled_navigation=true verification=UNVERIFIED production=false")


if __name__ == "__main__":
    main()
