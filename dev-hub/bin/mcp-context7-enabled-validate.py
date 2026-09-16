#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "config" / "provider-adapters.v1.json"
CATALOG = ROOT / "config" / "mcp-provider-catalog.v1.json"
CONTRACT = ROOT / "config" / "mcp-context7-contract.v1.json"
ROLLBACKS = ROOT / "config" / "adapter-rollbacks.v1.json"
RECEIPT = ROOT / "evidence" / "context7-enabled-promotion-35076725665-receipt.json"
REPORT = ROOT / "evidence" / "context7-enabled-promotion-35076725665-report.json"
PROVENANCE = ROOT / "evidence" / "context7-enabled-promotion-35076725665-provenance.json"
READINESS = ROOT / "evidence" / "context7-enable-readiness-35076408369-evidence.json"


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def fail(msg):
    raise SystemExit(f"CONTEXT7_ENABLED_INVALID: {msg}")


def main():
    registry = load(REGISTRY)
    catalog = load(CATALOG)
    contract = load(CONTRACT)
    rollbacks = load(ROLLBACKS)
    receipt = load(RECEIPT)
    report = load(REPORT)
    provenance = load(PROVENANCE)
    readiness = load(READINESS)

    provider = registry.get("providers", {}).get("context7-mcp", {})
    adapter = registry.get("adapters", {}).get("context7-mcp-adapter", {})
    if provider.get("adapter") != "context7-mcp-adapter" or provider.get("execution") != "external":
        fail("provider binding")
    if adapter.get("status") != "ENABLED":
        fail(f"adapter status={adapter.get('status')}")
    if adapter.get("executable") not in {None, ""}:
        fail("external adapter must not bind local executable")
    if adapter.get("supports") != ["read"]:
        fail("adapter must remain read-only")

    c7 = catalog.get("providers", {}).get("context7-mcp", {})
    if c7.get("runtime_status") != "ENABLED":
        fail(f"catalog status={c7.get('runtime_status')}")
    if c7.get("write_scope") != [] or c7.get("risk_class") != "LOW":
        fail("catalog boundary")
    if c7.get("provider_binding") != "context7-mcp":
        fail("catalog provider binding")

    tools = contract.get("tool_policy", {})
    if set(tools.get("allow", [])) != {"resolve-library-id", "query-docs"}:
        fail("tool allowlist")
    if tools.get("default") != "DENY" or tools.get("mutation_tools") != "DENY" or tools.get("destructive_tools") != "DENY":
        fail("tool deny policy")
    runtime = contract.get("runtime_policy", {})
    if runtime.get("provider_result_trust") != "UNVERIFIED":
        fail("provider result trust")
    if runtime.get("production_mutation") is not False:
        fail("production mutation boundary")
    if runtime.get("verification_broker_required") is not True:
        fail("verification broker")

    rb = rollbacks.get("adapters", {}).get("context7-mcp-adapter", {})
    if rb.get("enabled") is not True or rb.get("target_status") != "DISABLED":
        fail("rollback")
    if len(rb.get("steps") or []) < 2 or not (rb.get("verification") or []):
        fail("rollback detail")

    for key in ("repeatable-pass", "provider-health-pass", "rollback-defined"):
        if readiness.get("evidence", {}).get(key, {}).get("status") != "PASS":
            fail(f"readiness evidence {key}")

    if receipt.get("receipt_schema") != "chacha.dev/adapter-promotion-receipt/v1":
        fail("receipt schema")
    if receipt.get("transition") != "PILOT->ENABLED" or receipt.get("eligible") is not True or receipt.get("applied") is not True:
        fail("receipt transition")
    if receipt.get("blockers") != []:
        fail(f"receipt blockers={receipt.get('blockers')}")
    if receipt.get("production_capable") is not False or receipt.get("approval_required") is not False:
        fail("unexpected production capability or approval requirement")
    if receipt.get("requires_local_executable") is not False:
        fail("receipt executable requirement")
    if receipt.get("previous_entry", {}).get("status") != "PILOT":
        fail("receipt previous status")
    if receipt.get("new_entry", {}).get("status") != "ENABLED":
        fail("receipt new status")
    if receipt.get("new_entry", {}).get("supports") != ["read"]:
        fail("receipt new permissions")
    if receipt.get("new_entry", {}).get("executable") not in {None, ""}:
        fail("receipt local executable")

    if report.get("eligible") is not True or report.get("applied") is not True or report.get("blockers") != []:
        fail("promotion report")
    if provenance.get("workflow_run_id") != 35076725665 or provenance.get("workflow_conclusion") != "success":
        fail("provenance workflow")
    if provenance.get("artifact_id") != 10437409843:
        fail("provenance artifact")
    if provenance.get("artifact_digest") != "sha256:11bfad6376a18a81d614124fa8c829617d00345540c40d9e8c0b490a6d9d3a5d":
        fail("provenance digest")
    if provenance.get("materialized_branch_state", {}).get("production_modified") is not False:
        fail("production modification claim")

    print("CONTEXT7_ENABLED_VALID: status=ENABLED read_only=true production_capable=false rollback=DISABLED blockers=0")


if __name__ == "__main__":
    main()
