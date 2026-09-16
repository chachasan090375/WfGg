#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "config" / "mcp-provider-catalog.v1.json"
REGISTRY = ROOT / "config" / "provider-adapters.v1.json"
CONTRACT = ROOT / "config" / "mcp-context7-contract.v1.json"
PROMOTION_EVIDENCE = ROOT / "evidence" / "context7-contract-ok-to-pilot-2026-09-16.json"
RECEIPT = ROOT / "evidence" / "context7-pilot-promotion-35072331061-receipt.json"
REPORT = ROOT / "evidence" / "context7-pilot-promotion-35072331061-report.json"
PROVENANCE = ROOT / "evidence" / "context7-pilot-promotion-35072331061-provenance.json"


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def fail(msg):
    raise SystemExit(f"CONTEXT7_PILOT_INVALID: {msg}")


def main():
    catalog = load(CATALOG)
    registry = load(REGISTRY)
    contract = load(CONTRACT)
    promotion = load(PROMOTION_EVIDENCE)
    receipt = load(RECEIPT)
    report = load(REPORT)
    provenance = load(PROVENANCE)

    c7 = catalog.get("providers", {}).get("context7-mcp", {})
    adapter = registry.get("adapters", {}).get("context7-mcp-adapter", {})
    provider = registry.get("providers", {}).get("context7-mcp", {})

    if c7.get("runtime_status") != "PILOT":
        fail(f"catalog status={c7.get('runtime_status')}")
    if adapter.get("status") != "PILOT":
        fail(f"adapter status={adapter.get('status')}")
    if provider.get("adapter") != "context7-mcp-adapter" or provider.get("execution") != "external":
        fail("provider binding")
    if adapter.get("executable") not in {None, ""}:
        fail("external adapter executable")
    if adapter.get("supports") != ["read"] or c7.get("write_scope") != []:
        fail("read-only boundary")

    if contract.get("provider_id") != "context7-mcp" or contract.get("adapter_id") != "context7-mcp-adapter":
        fail("contract identity")
    if set(contract.get("tool_policy", {}).get("allow", [])) != {"resolve-library-id", "query-docs"}:
        fail("tool allowlist")
    if contract.get("tool_policy", {}).get("default") != "DENY":
        fail("default deny")
    runtime = contract.get("runtime_policy", {})
    if runtime.get("shell") is not False or runtime.get("production_mutation") is not False:
        fail("runtime mutation/shell")
    if runtime.get("provider_result_trust") != "UNVERIFIED":
        fail("provider result trust")

    if promotion.get("schema") != "chacha.dev/adapter-promotion-evidence/v1":
        fail("promotion evidence schema")
    if promotion.get("adapter") != "context7-mcp-adapter" or promotion.get("provider") != "context7-mcp":
        fail("promotion evidence identity")
    expected = {"runtime-contract-pass", "sandbox-only", "provisioning-pass"}
    evidence = promotion.get("evidence", {})
    if set(evidence) != expected:
        fail("promotion evidence set")
    for key in expected:
        item = evidence[key]
        if item.get("status") != "PASS":
            fail(f"{key} status")
        if item.get("source") != "github-actions:35071943334":
            fail(f"{key} source")

    for obj, name in ((report, "report"), (receipt, "receipt")):
        if obj.get("adapter") != "context7-mcp-adapter":
            fail(f"{name} adapter")
        if obj.get("transition") != "CONTRACT_OK->PILOT":
            fail(f"{name} transition")
        if obj.get("eligible") is not True or obj.get("applied") is not True:
            fail(f"{name} apply state")
        if obj.get("blockers") != []:
            fail(f"{name} blockers")
        if obj.get("production_capable") is not False:
            fail(f"{name} production boundary")
        if obj.get("requires_local_executable") is not False:
            fail(f"{name} executable boundary")
        if obj.get("actor") != "github-actions:35072331061":
            fail(f"{name} actor")

    if receipt.get("receipt_schema") != "chacha.dev/adapter-promotion-receipt/v1":
        fail("receipt schema")
    if receipt.get("previous_entry", {}).get("status") != "CONTRACT_OK":
        fail("receipt previous status")
    if receipt.get("new_entry", {}).get("status") != "PILOT":
        fail("receipt new status")
    if receipt.get("new_entry", {}).get("executable") is not None:
        fail("receipt executable")

    run = provenance.get("qualification_run", {})
    artifact = provenance.get("promotion_artifact", {})
    if run.get("workflow_run_id") != 35072331061 or run.get("workflow_conclusion") != "success":
        fail("provenance workflow")
    if run.get("head_sha") != "62e4538da4da1f0e63c91cd5af78acb5da41b309":
        fail("provenance head sha")
    if artifact.get("artifact_id") != 10437180280:
        fail("provenance artifact id")
    if artifact.get("digest") != "sha256:28938164f03e4f8515b3c73fcb8a53af17e184a8c940ad2be14aff3464bd162b":
        fail("provenance artifact digest")
    if provenance.get("production_capable") is not False or provenance.get("automatic_enable") is not False:
        fail("provenance safety boundary")

    print(
        "CONTEXT7_PILOT_VALID: status=PILOT read_only=true production=false "
        "promotion_run=35072331061 blockers=0"
    )


if __name__ == "__main__":
    main()
