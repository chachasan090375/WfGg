#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config" / "mcp-context7-contract.v1.json"
REGISTRY = ROOT / "config" / "provider-adapters.v1.json"
CATALOG = ROOT / "config" / "mcp-provider-catalog.v1.json"
ALLOWED_STATUSES = {"DESIGNED", "CONTRACT_OK", "PILOT", "ENABLED", "DEGRADED", "DISABLED", "RETIRED"}


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def fail(msg: str):
    raise SystemExit(f"CONTEXT7_CONTRACT_INVALID: {msg}")


def main():
    contract = load(CONTRACT)
    registry = load(REGISTRY)
    catalog = load(CATALOG)

    if contract.get("schema") != "chacha.dev/mcp-context7-contract/v1":
        fail("schema")
    if contract.get("provider_id") != "context7-mcp":
        fail("provider_id")
    if contract.get("adapter_id") != "context7-mcp-adapter":
        fail("adapter_id")

    endpoint = contract.get("endpoint", {})
    if endpoint.get("remote_url") != "https://mcp.context7.com/mcp":
        fail("remote_url")
    if endpoint.get("transport") != "streamable-http":
        fail("transport")
    if endpoint.get("protocol_baseline") != "2026-07-28":
        fail("protocol_baseline")
    if endpoint.get("discovery_method") != "server/discover":
        fail("discovery_method")

    auth = contract.get("auth", {})
    if auth.get("secret_policy") != "REFERENCE_ONLY" or auth.get("secret_values_in_git") is not False:
        fail("secret_policy")
    if auth.get("authorization_header_in_evidence") != "REDACT":
        fail("redaction")

    policy = contract.get("tool_policy", {})
    allowed = set(policy.get("allow", []))
    if allowed != {"resolve-library-id", "query-docs"}:
        fail(f"tool allowlist={sorted(allowed)}")
    if policy.get("default") != "DENY" or policy.get("unknown_tools") != "DENY":
        fail("default deny")
    if policy.get("mutation_tools") != "DENY" or policy.get("destructive_tools") != "DENY":
        fail("mutation deny")
    if policy.get("read_only_annotation_required") is not True:
        fail("read_only_annotation_required")
    if policy.get("max_query_docs_calls_per_question") != 3:
        fail("query-docs call limit")

    tools = contract.get("tools", {})
    if set(tools) != allowed:
        fail("tools mismatch allowlist")
    if set(tools["resolve-library-id"].get("required_inputs", [])) != {"libraryName", "query"}:
        fail("resolve-library-id inputs")
    if set(tools["query-docs"].get("required_inputs", [])) != {"libraryId", "query"}:
        fail("query-docs inputs")
    if any(v.get("permission") != "read" for v in tools.values()):
        fail("non-read permission")

    runtime = contract.get("runtime_policy", {})
    if runtime.get("shell") is not False or runtime.get("production_mutation") is not False:
        fail("runtime mutation/shell")
    if runtime.get("provider_result_trust") != "UNVERIFIED" or runtime.get("verification_broker_required") is not True:
        fail("verification boundary")

    provider = registry.get("providers", {}).get("context7-mcp")
    adapter = registry.get("adapters", {}).get("context7-mcp-adapter")
    if not provider or provider.get("adapter") != "context7-mcp-adapter" or provider.get("execution") != "external":
        fail("registry provider binding")
    if not adapter:
        fail("adapter missing")
    status = adapter.get("status")
    if status not in ALLOWED_STATUSES:
        fail(f"adapter status={status}")
    if adapter.get("executable") not in {None, ""}:
        fail("external adapter must have no local executable")
    if adapter.get("supports") != ["read"]:
        fail("adapter supports must be read-only")

    c7 = catalog.get("providers", {}).get("context7-mcp")
    if not c7:
        fail("catalog Context7 missing")
    if c7.get("runtime_status") != status:
        fail(f"catalog/adapter status mismatch: catalog={c7.get('runtime_status')} adapter={status}")
    if c7.get("write_scope") != []:
        fail("catalog Context7 write scope")

    if contract.get("source_notes", {}).get("breaking_change_guard") != "get-library-docs is not allowed; query-docs is the expected documentation tool":
        fail("breaking change guard")

    print(f"CONTEXT7_CONTRACT_VALID: provider=context7-mcp adapter=context7-mcp-adapter status={status} tools=2")


if __name__ == "__main__":
    main()
