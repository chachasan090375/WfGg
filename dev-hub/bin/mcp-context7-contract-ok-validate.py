#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "config" / "mcp-provider-catalog.v1.json"
REGISTRY = ROOT / "config" / "provider-adapters.v1.json"
CONTRACT = ROOT / "config" / "mcp-context7-contract.v1.json"
EVIDENCE = ROOT / "evidence" / "context7-contract-ok-2026-09-16.json"


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def fail(msg):
    raise SystemExit(f"CONTEXT7_CONTRACT_OK_INVALID: {msg}")


def main():
    catalog = load(CATALOG)
    registry = load(REGISTRY)
    contract = load(CONTRACT)
    evidence = load(EVIDENCE)

    c7 = catalog.get("providers", {}).get("context7-mcp", {})
    catalog_status = c7.get("runtime_status")
    if catalog_status not in {"CONTRACT_OK", "PILOT"}:
        fail(f"catalog status={catalog_status}")
    if c7.get("write_scope") != [] or c7.get("risk_class") != "LOW":
        fail("catalog boundary")

    provider = registry.get("providers", {}).get("context7-mcp", {})
    adapter = registry.get("adapters", {}).get("context7-mcp-adapter", {})
    if provider.get("adapter") != "context7-mcp-adapter" or provider.get("execution") != "external":
        fail("provider binding")
    adapter_status = adapter.get("status")
    if adapter_status not in {"CONTRACT_OK", "PILOT"}:
        fail(f"adapter status={adapter_status}")
    if adapter_status != catalog_status:
        fail(f"catalog/adapter mismatch: catalog={catalog_status} adapter={adapter_status}")
    if adapter.get("executable") not in {None, ""}:
        fail("external adapter executable")
    if adapter.get("supports") != ["read"]:
        fail("adapter permissions")

    if contract.get("provider_id") != "context7-mcp" or contract.get("adapter_id") != "context7-mcp-adapter":
        fail("contract identity")
    if set(contract.get("tool_policy", {}).get("allow", [])) != {"resolve-library-id", "query-docs"}:
        fail("tool allowlist")
    if contract.get("tool_policy", {}).get("default") != "DENY":
        fail("default deny")

    if evidence.get("schema") != "chacha.dev/mcp-contract-qualification-evidence/v1":
        fail("evidence schema")
    if evidence.get("transition") != "DESIGNED->CONTRACT_OK":
        fail("evidence transition")
    if evidence.get("source", {}).get("workflow_run_id") != 35071309971:
        fail("qualifying workflow id")
    if evidence.get("source", {}).get("workflow_conclusion") != "success":
        fail("qualifying workflow conclusion")
    if evidence.get("decision", {}).get("eligible") is not True or evidence.get("decision", {}).get("blockers") != []:
        fail("eligibility")
    if evidence.get("checks", {}).get("generic_adapter_static_contract") != "PASS":
        fail("static contract evidence")
    if evidence.get("runtime", {}).get("executed") is not False:
        fail("historical CONTRACT_OK evidence must not claim runtime")
    if evidence.get("checks", {}).get("automatic_promotion") is not False:
        fail("automatic promotion must be false")

    advanced_mcp = {
        pid: p.get("runtime_status")
        for pid, p in catalog.get("providers", {}).items()
        if pid != "context7-mcp" and p.get("runtime_status") in {"CONTRACT_OK", "PILOT", "ENABLED"}
    }
    if advanced_mcp:
        fail(f"unexpected advanced MCP providers: {advanced_mcp}")

    print(
        "CONTEXT7_CONTRACT_OK_HISTORY_VALID: "
        f"historical static qualification preserved; current_status={adapter_status}"
    )


if __name__ == "__main__":
    main()
