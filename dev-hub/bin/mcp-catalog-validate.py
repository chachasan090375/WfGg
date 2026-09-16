#!/usr/bin/env python3
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
CATALOG = ROOT / "config" / "mcp-provider-catalog.v1.json"

ALLOWED_DECISIONS = {"ADOPT", "ASSESS", "WATCH", "DEFER", "REJECT"}
ALLOWED_RUNTIME = {"CATALOG_ONLY", "DESIGNED", "CONTRACT_OK", "PILOT", "ENABLED", "DISABLED"}
FORBIDDEN_SECRET_FIELDS = {
    "token",
    "access_token",
    "refresh_token",
    "api_key",
    "apikey",
    "client_secret",
    "password",
    "private_key",
    "secret_value",
}
EXPECTED_PROTOCOL = {
    "preferred_version": "2026-07-28",
    "discovery_method": "server/discover",
    "tools_list_method": "tools/list",
    "tools_call_method": "tools/call",
    "remote_transport": "streamable-http",
    "local_transport": "stdio",
    "legacy_sse_for_new_deployments": False,
    "compatibility_policy": "explicit-provider-adapter-only",
}


def fail(message: str) -> None:
    print(f"MCP_CATALOG_INVALID: {message}", file=sys.stderr)
    raise SystemExit(1)


def walk_forbidden_fields(value, path="$"):
    if isinstance(value, dict):
        for key, child in value.items():
            if key.lower() in FORBIDDEN_SECRET_FIELDS:
                fail(f"forbidden secret field {path}.{key}")
            walk_forbidden_fields(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            walk_forbidden_fields(child, f"{path}[{index}]")


def validate_explicit_compatibility(provider_id: str, provider: dict, protocol: dict) -> None:
    compat = provider.get("protocol_compatibility")
    if not isinstance(compat, dict):
        fail(f"provider {provider_id} uses initialize health probe without explicit protocol_compatibility")
    if protocol.get("compatibility_policy") != "explicit-provider-adapter-only":
        fail(f"provider {provider_id} compatibility requires explicit-provider-adapter-only global policy")
    if compat.get("mode") != "EXPLICIT_PROVIDER_COMPATIBILITY":
        fail(f"provider {provider_id} compatibility mode must be EXPLICIT_PROVIDER_COMPATIBILITY")
    if compat.get("provider_specific") is not True:
        fail(f"provider {provider_id} compatibility must be provider-specific")
    if compat.get("dev_hub_baseline") != protocol.get("preferred_version"):
        fail(f"provider {provider_id} compatibility baseline must match DEV HUB preferred protocol")
    upstream = compat.get("upstream_version")
    if not isinstance(upstream, str) or not upstream.strip():
        fail(f"provider {provider_id} compatibility upstream version missing")
    if compat.get("generic_legacy_fallback") is not False:
        fail(f"provider {provider_id} cannot enable generic legacy fallback")
    if not provider.get("provider_binding"):
        fail(f"provider {provider_id} compatibility requires an explicit provider binding")
    if provider.get("runtime_status") not in {"PILOT", "ENABLED", "DISABLED"}:
        fail(f"provider {provider_id} initialize compatibility health probe requires admitted runtime status")


def main() -> int:
    try:
        data = json.loads(CATALOG.read_text(encoding="utf-8"))
    except Exception as exc:
        fail(f"cannot parse {CATALOG}: {exc}")

    if data.get("schema") != "chacha.dev/mcp-provider-catalog/v1":
        fail("unexpected schema id")

    protocol = data.get("protocol")
    if not isinstance(protocol, dict):
        fail("protocol must be an object")
    for field, expected in EXPECTED_PROTOCOL.items():
        if protocol.get(field) != expected:
            fail(f"protocol.{field} must be {expected!r}")

    policy = data.get("policy")
    if not isinstance(policy, dict):
        fail("policy must be an object")

    required_true = [
        "no_secret_values_in_catalog",
        "catalog_does_not_enable_runtime",
        "adapter_pipeline_required",
        "production_change_requires_approval",
        "filesystem_root_access_forbidden",
    ]
    for field in required_true:
        if policy.get(field) is not True:
            fail(f"policy.{field} must be true")

    if policy.get("default_admission") != "DENY":
        fail("default admission must be DENY")

    providers = data.get("providers")
    if not isinstance(providers, dict) or not providers:
        fail("providers must be a non-empty object")

    walk_forbidden_fields(data)

    for provider_id, provider in providers.items():
        if not isinstance(provider, dict):
            fail(f"provider {provider_id} must be an object")
        if provider.get("decision") not in ALLOWED_DECISIONS:
            fail(f"provider {provider_id} has invalid decision")
        if provider.get("runtime_status") not in ALLOWED_RUNTIME:
            fail(f"provider {provider_id} has invalid runtime status")
        priority = provider.get("priority")
        if not isinstance(priority, int) or priority not in {1, 2, 3}:
            fail(f"provider {provider_id} priority must be 1..3")
        capabilities = provider.get("target_capabilities")
        if not isinstance(capabilities, list) or not capabilities or len(capabilities) != len(set(capabilities)):
            fail(f"provider {provider_id} target_capabilities must be unique and non-empty")

        if provider.get("integration_mode") in {"remote-mcp", "local-mcp"}:
            probe = provider.get("health_probe")
            if probe and "initialize" in probe.lower():
                validate_explicit_compatibility(provider_id, provider, protocol)
            elif provider.get("protocol_compatibility") is not None:
                compat = provider.get("protocol_compatibility")
                if not isinstance(compat, dict) or compat.get("generic_legacy_fallback") is not False:
                    fail(f"provider {provider_id} has invalid protocol_compatibility")

        if provider_id == "filesystem-mcp":
            allowed = provider.get("allowed_roots", [])
            forbidden = provider.get("forbidden_roots", [])
            expected_allowed = {
                "/opt/chacha-dev/workspaces",
                "/opt/chacha-dev/adapters",
                "/opt/chacha-dev/evidence",
            }
            if set(allowed) != expected_allowed:
                fail("filesystem-mcp approved roots changed without policy update")
            if "/" not in forbidden:
                fail("filesystem-mcp must explicitly forbid filesystem root")
            if provider.get("runtime_status") not in {"CATALOG_ONLY", "DESIGNED"}:
                fail("filesystem-mcp cannot advance beyond DESIGNED through catalog-only changes")

        if provider.get("decision") == "DEFER" and provider.get("runtime_status") != "CATALOG_ONLY":
            fail(f"deferred provider {provider_id} must remain CATALOG_ONLY")

    print(
        "MCP_CATALOG_VALID: "
        f"providers={len(providers)} default_admission=DENY "
        f"protocol={protocol['preferred_version']} discovery={protocol['discovery_method']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
