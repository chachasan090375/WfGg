#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "config"
EVID = ROOT / "evidence"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def fail(message: str):
    raise SystemExit(f"PLAYWRIGHT_COMPAT_PILOT_INVALID: {message}")


def main():
    contract = load(CFG / "mcp-playwright-contract.v1.json")
    adapters = load(CFG / "provider-adapters.v1.json")
    catalog = load(CFG / "mcp-provider-catalog.v1.json")
    qualification = load(EVID / "playwright-mcp-adapter-runtime-pilot-qualification-2026-09-16.json")
    receipt = load(EVID / "playwright-mcp-adapter-runtime-pilot-materialization-2026-09-16.json")

    if contract.get("runtime_status") != "PILOT":
        fail("contract status")
    if contract.get("runtime_status") == "ENABLED":
        fail("PILOT must not be ENABLED")

    adapter = adapters.get("adapters", {}).get("playwright-mcp-adapter", {})
    if adapter.get("status") != "PILOT":
        fail("adapter status")
    if adapter.get("executable") is not None:
        fail("external adapter must not claim local executable")
    if adapter.get("supports") != ["read"]:
        fail("adapter permissions expanded")

    provider = adapters.get("providers", {}).get("playwright-mcp", {})
    if provider.get("adapter") != "playwright-mcp-adapter" or provider.get("execution") != "external":
        fail("provider binding")

    cat = catalog.get("providers", {}).get("playwright-mcp", {})
    if cat.get("runtime_status") != "PILOT":
        fail("catalog status")
    if cat.get("provider_binding") != "playwright-mcp":
        fail("catalog binding")

    proto = contract.get("protocol", {})
    if proto.get("dev_hub_preferred_protocol_version") != "2026-07-28":
        fail("DEV HUB protocol baseline")
    if proto.get("upstream_compatibility_protocol_version") != "2025-11-25":
        fail("upstream compatibility protocol")
    if proto.get("compatibility_mode") != "EXPLICIT_PROVIDER_COMPATIBILITY":
        fail("compatibility mode")
    if proto.get("generic_legacy_fallback") is not False:
        fail("generic legacy fallback")
    if proto.get("provider_result_trust") != "UNVERIFIED" or proto.get("verification_broker_required") is not True:
        fail("producer/verifier boundary")

    expected_tools = [
        "browser_navigate",
        "browser_snapshot",
        "browser_console_messages",
        "browser_network_requests",
        "browser_close",
    ]
    policy = contract.get("tool_policy", {})
    if policy.get("default") != "DENY":
        fail("default tool policy")
    if policy.get("pilot_allow") != expected_tools:
        fail("PILOT allowlist drift")
    denied = set(policy.get("explicit_deny", []))
    for name in ("browser_run_code_unsafe", "browser_evaluate", "browser_click", "browser_type", "browser_fill_form", "browser_file_upload"):
        if name not in denied:
            fail(f"missing deny {name}")
    for key in ("arbitrary_javascript", "file_upload", "form_submission", "workspace_write", "repository_write", "production_mutation"):
        if policy.get(key) is not False:
            fail(f"write/unsafe boundary {key}")

    pilot = contract.get("pilot_qualification", {})
    if pilot.get("transition") != "CONTRACT_OK->PILOT":
        fail("pilot transition")
    if pilot.get("runtime_workflow_run_id") != 35091837777 or pilot.get("runtime_workflow_conclusion") != "success":
        fail("runtime workflow evidence")
    if pilot.get("runtime_artifact_id") != 10443819103:
        fail("runtime artifact")
    if pilot.get("runtime_artifact_digest") != "sha256:c7889bd802e28f490537d4c6828dca81a8160c947c14a4edb0f8e2e152d707dd":
        fail("runtime artifact digest")
    if pilot.get("fixed_safe_sequence") != expected_tools:
        fail("fixed safe sequence")
    if pilot.get("producer_result_verification") != "UNVERIFIED":
        fail("result trust")
    if pilot.get("write_permission_probe_status") != "BLOCKED" or pilot.get("write_permission_probe_reason") != "READ_PERMISSION_REQUIRED":
        fail("write permission probe")
    if pilot.get("repository_workspace_write") is not False or pilot.get("production_mutation") is not False:
        fail("write/production mutation")
    if pilot.get("automatic_promotion") is not False or pilot.get("blockers") != []:
        fail("promotion boundary")

    if qualification.get("schema") != "chacha.dev/playwright-mcp-adapter-runtime-pilot-qualification/v1":
        fail("qualification schema")
    qpromo = qualification.get("promotion", {})
    if qpromo.get("eligible_for_pilot") is not True or qpromo.get("status_change_applied") is not False or qpromo.get("blockers") != []:
        fail("qualification evidence boundary")

    if receipt.get("schema") != "chacha.dev/playwright-mcp-adapter-pilot-materialization/v1":
        fail("receipt schema")
    if receipt.get("transition") != "CONTRACT_OK->PILOT":
        fail("receipt transition")
    change = receipt.get("status_change", {})
    if change != {"previous": "CONTRACT_OK", "new": "PILOT", "applied": True, "automatic": False}:
        fail("receipt state change")
    bounds = receipt.get("boundaries", {})
    if bounds.get("supports") != ["read"] or bounds.get("local_executable") is not None:
        fail("receipt permission boundary")
    if bounds.get("production_capable") is not False or bounds.get("provider_result_verification") != "UNVERIFIED":
        fail("receipt production/trust boundary")
    if bounds.get("verification_broker_required") is not True or bounds.get("generic_legacy_fallback") is not False or bounds.get("enabled") is not False:
        fail("receipt enablement boundary")
    if receipt.get("blockers") != []:
        fail("receipt blockers")

    admission = contract.get("admission", {})
    if admission.get("automatic_promotion") is not False or admission.get("next_transition") != "PILOT->ENABLED":
        fail("next transition boundary")

    print("PLAYWRIGHT_COMPAT_PILOT_VALID state=PILOT enabled=false read_only=true compatibility=explicit-provider-only verification=UNVERIFIED production=false")


if __name__ == "__main__":
    main()
