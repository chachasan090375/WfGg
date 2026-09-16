#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "config" / "provider-adapters.v1.json"
CATALOG = ROOT / "config" / "mcp-provider-catalog.v1.json"
CONTRACT = ROOT / "config" / "mcp-playwright-contract.v1.json"
ROLLBACKS = ROOT / "config" / "adapter-rollbacks.v1.json"
RECEIPT = ROOT / "evidence" / "playwright-mcp-enabled-promotion-35093990825-receipt.json"
REPORT = ROOT / "evidence" / "playwright-mcp-enabled-promotion-35093990825-report.json"
PROVENANCE = ROOT / "evidence" / "playwright-mcp-enabled-promotion-35093990825-provenance.json"
READINESS = ROOT / "evidence" / "playwright-mcp-compat-enable-readiness-2026-09-16.json"
SANDBOX = ROOT / "evidence" / "playwright-mcp-compat-enable-sandbox-2026-09-16.json"

SAFE_TOOLS = [
    "browser_navigate",
    "browser_snapshot",
    "browser_console_messages",
    "browser_network_requests",
    "browser_close",
]
DENIED_TOOLS = {
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


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def fail(msg):
    raise SystemExit(f"PLAYWRIGHT_ENABLED_INVALID: {msg}")


def main():
    registry = load(REGISTRY)
    catalog = load(CATALOG)
    contract = load(CONTRACT)
    rollbacks = load(ROLLBACKS)
    receipt = load(RECEIPT)
    report = load(REPORT)
    provenance = load(PROVENANCE)
    readiness = load(READINESS)
    sandbox = load(SANDBOX)

    provider = registry.get("providers", {}).get("playwright-mcp", {})
    adapter = registry.get("adapters", {}).get("playwright-mcp-adapter", {})
    if provider.get("adapter") != "playwright-mcp-adapter" or provider.get("execution") != "external":
        fail("provider binding")
    if adapter.get("status") != "ENABLED":
        fail(f"adapter status={adapter.get('status')}")
    if adapter.get("executable") not in {None, ""}:
        fail("external adapter must not bind local executable")
    if adapter.get("supports") != ["read"]:
        fail("adapter must remain read-only")

    p = catalog.get("providers", {}).get("playwright-mcp", {})
    if p.get("runtime_status") != "ENABLED":
        fail(f"catalog status={p.get('runtime_status')}")
    if p.get("provider_binding") != "playwright-mcp":
        fail("catalog provider binding")
    if p.get("risk_class") != "MEDIUM":
        fail("catalog risk class")
    if p.get("write_scope") != ["test-artifacts"]:
        fail("catalog write scope changed")

    if contract.get("runtime_status") != "ENABLED":
        fail(f"contract status={contract.get('runtime_status')}")
    proto = contract.get("protocol", {})
    if proto.get("dev_hub_preferred_protocol_version") != "2026-07-28":
        fail("DEV HUB protocol baseline")
    if proto.get("upstream_compatibility_protocol_version") != "2025-11-25":
        fail("upstream compatibility protocol")
    if proto.get("compatibility_mode") != "EXPLICIT_PROVIDER_COMPATIBILITY":
        fail("compatibility mode")
    if proto.get("generic_legacy_fallback") is not False:
        fail("generic legacy fallback must remain false")
    if proto.get("provider_result_trust") != "UNVERIFIED":
        fail("provider result trust")
    if proto.get("verification_broker_required") is not True or proto.get("producer_must_not_self_verify") is not True:
        fail("verification boundary")

    tools = contract.get("tool_policy", {})
    if tools.get("default") != "DENY":
        fail("tool default policy")
    if tools.get("pilot_allow") != SAFE_TOOLS:
        fail("qualified safe tool sequence changed")
    if not DENIED_TOOLS.issubset(set(tools.get("explicit_deny") or [])):
        fail("interactive/write deny surface")
    for key in ("workspace_write", "repository_write", "production_mutation", "arbitrary_javascript", "file_upload", "form_submission", "webmcp_page_tools"):
        if tools.get(key) is not False:
            fail(f"tool boundary {key}")

    execution = contract.get("execution", {})
    if execution.get("production_target_allowed") is not False:
        fail("production target")
    if execution.get("authenticated_user_profile_allowed") is not False:
        fail("authenticated profile")
    if execution.get("persistent_profile") is not False:
        fail("persistent profile")

    eq = contract.get("enablement_qualification", {})
    if eq.get("transition") != "PILOT->ENABLED" or eq.get("blockers") != []:
        fail("enablement qualification")
    if not all(eq.get(k) is True for k in ("repeatable_pass", "provider_health_pass", "rollback_defined", "sandbox_promotion_applied")):
        fail("enablement gates")
    if eq.get("authoritative_registry_mutated_during_sandbox") is not False:
        fail("sandbox authoritative mutation")
    if eq.get("production_capable") is not False or eq.get("approval_required") is not False:
        fail("production capability")
    if eq.get("permissions") != ["read"] or eq.get("local_executable") is not None:
        fail("enablement permissions/executable")
    if eq.get("provider_result_verification") != "UNVERIFIED":
        fail("enablement verification state")

    rb = rollbacks.get("adapters", {}).get("playwright-mcp-adapter", {})
    if rb.get("enabled") is not True or rb.get("from_status") != "ENABLED" or rb.get("target_status") != "DISABLED":
        fail("rollback")
    if len(rb.get("steps") or []) < 2 or not (rb.get("verification") or []):
        fail("rollback detail")

    if readiness.get("readiness_status") != "READY_FOR_ENABLEMENT" or readiness.get("blockers") != []:
        fail("readiness summary")
    if readiness.get("repeatability", {}).get("successful_runs") != 3:
        fail("repeatability")
    if readiness.get("health", {}).get("state") != "HEALTHY" or readiness.get("health", {}).get("fresh") is not True:
        fail("provider health")
    if readiness.get("promotion_plan", {}).get("eligible") is not True or readiness.get("promotion_plan", {}).get("applied") is not False:
        fail("readiness promotion plan")

    if sandbox.get("scope") != "TEMPORARY_REGISTRY_COPY_ONLY" or sandbox.get("blockers") != []:
        fail("sandbox scope")
    sp = sandbox.get("sandbox_promotion", {})
    if sp.get("eligible") is not True or sp.get("applied_to_sandbox_copy") is not True:
        fail("sandbox promotion")
    if sp.get("sandbox_status_before") != "PILOT" or sp.get("sandbox_status_after") != "ENABLED":
        fail("sandbox status transition")
    if sp.get("authoritative_status_after") != "PILOT":
        fail("sandbox authoritative status")
    if sp.get("supports_after") != ["read"] or sp.get("production_capable") is not False:
        fail("sandbox boundary")

    if receipt.get("receipt_schema") != "chacha.dev/adapter-promotion-receipt/v1":
        fail("receipt schema")
    if receipt.get("transition") != "PILOT->ENABLED" or receipt.get("eligible") is not True or receipt.get("applied") is not True:
        fail("receipt transition")
    if receipt.get("blockers") != []:
        fail("receipt blockers")
    if receipt.get("production_capable") is not False or receipt.get("approval_required") is not False:
        fail("receipt production boundary")
    if receipt.get("requires_local_executable") is not False:
        fail("receipt executable requirement")
    if receipt.get("previous_entry", {}).get("status") != "PILOT" or receipt.get("new_entry", {}).get("status") != "ENABLED":
        fail("receipt status transition")
    if receipt.get("new_entry", {}).get("supports") != ["read"] or receipt.get("new_entry", {}).get("executable") is not None:
        fail("receipt new entry boundary")

    if report.get("eligible") is not True or report.get("applied") is not True or report.get("blockers") != []:
        fail("promotion report")
    if report.get("registry_digest_before") != "sha256:8259fceca0cfb5e22fc78b0fe1052fe596f47dc538649b5c71f1b7caad646dcb":
        fail("registry digest before")
    if report.get("registry_digest_after") != "sha256:154d3c69a0cea358e36c8313421274e45273cb5778ee1fb4779c455d8cdc10bd":
        fail("registry digest after")

    if provenance.get("transition") != "PILOT->ENABLED":
        fail("provenance transition")
    ready = provenance.get("readiness", {})
    if ready.get("workflow_run_id") != 35093635617 or ready.get("workflow_conclusion") != "success" or ready.get("artifact_id") != 10445391711:
        fail("readiness provenance")
    if ready.get("artifact_digest") != "sha256:ee046b2d953a5f6765f4fd71f7cb5a9a47c81daf4eb0ef6118b0a64405879047":
        fail("readiness artifact digest")
    sand = provenance.get("sandbox_promotion", {})
    if sand.get("workflow_run_id") != 35093990825 or sand.get("workflow_conclusion") != "success" or sand.get("artifact_id") != 10445322680:
        fail("sandbox provenance")
    if sand.get("artifact_digest") != "sha256:5b31b7835fe02c9df47cd65b131920e767539c60517425e3e32cac51ed4f33a7":
        fail("sandbox artifact digest")
    state = provenance.get("materialized_branch_state", {})
    if state.get("adapter_status") != "ENABLED" or state.get("provider_runtime_status") != "ENABLED" or state.get("contract_runtime_status") != "ENABLED":
        fail("materialized branch state")
    if state.get("permissions") != ["read"] or state.get("local_executable") is not None:
        fail("materialized branch permissions")
    if state.get("production_capable") is not False or state.get("production_modified") is not False or state.get("vps_modified") is not False:
        fail("materialized branch production/VPS boundary")
    if state.get("provider_result_verification") != "UNVERIFIED" or state.get("verification_broker_required") is not True:
        fail("materialized branch verification boundary")

    print("PLAYWRIGHT_ENABLED_VALID: status=ENABLED read_only=true external=true production_capable=false verification=UNVERIFIED rollback=DISABLED blockers=0")


if __name__ == "__main__":
    main()
