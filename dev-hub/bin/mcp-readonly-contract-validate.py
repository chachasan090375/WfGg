#!/usr/bin/env python3
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config" / "mcp-readonly-contract.v1.json"

EXPECTED = {
    ("schema",): "chacha.dev/mcp-readonly-contract/v1",
    ("protocol", "version"): "2026-07-28",
    ("protocol", "discovery"): "server/discover",
    ("protocol", "tools_list"): "tools/list",
    ("protocol", "tools_call"): "tools/call",
    ("protocol", "remote_transport"): "streamable-http",
    ("protocol", "local_transport"): "stdio",
    ("boundary", "input"): "chacha.dev/dispatch-envelope/v1",
    ("boundary", "output"): "chacha.dev/task-result/v1",
    ("boundary", "shell"): False,
    ("boundary", "provider_result_trust"): "UNVERIFIED",
    ("policy", "default_tool_policy"): "DENY",
    ("policy", "explicit_allowlist_required"): True,
    ("policy", "unknown_tools"): "DENY",
    ("policy", "mutation_tools"): "DENY",
    ("policy", "destructive_tools"): "DENY",
    ("policy", "missing_or_ambiguous_annotations"): "DENY",
    ("policy", "production_mutation"): "DENY",
    ("auth", "secret_values_in_git"): False,
    ("auth", "authorization_headers_in_evidence"): "REDACT",
    ("auth", "credential_echo"): "DENY",
    ("health", "discovery_required"): True,
    ("health", "tools_list_required"): True,
    ("health", "failure_state"): "UNAVAILABLE",
    ("evidence", "producer_cannot_self_verify"): True,
    ("evidence", "independent_verifier"): "verification-broker",
    ("evidence", "redact_secrets"): True,
    ("rollback", "target_state"): "DISABLED",
    ("rollback", "must_not_require_provider"): True,
    ("rollback", "reversible_without_secret_rotation"): True,
}

FORBIDDEN_SECRET_FIELDS = {
    "token", "access_token", "refresh_token", "api_key", "apikey",
    "client_secret", "password", "private_key", "secret_value"
}


def fail(message: str) -> None:
    print(f"MCP_READONLY_CONTRACT_INVALID: {message}", file=sys.stderr)
    raise SystemExit(1)


def get_path(data, path):
    current = data
    for part in path:
        if not isinstance(current, dict) or part not in current:
            fail(f"missing {'.'.join(path)}")
        current = current[part]
    return current


def walk(value, path="$"):
    if isinstance(value, dict):
        for key, child in value.items():
            if key.lower() in FORBIDDEN_SECRET_FIELDS:
                fail(f"forbidden secret field {path}.{key}")
            walk(child, f"{path}.{key}")
    elif isinstance(value, list):
        for i, child in enumerate(value):
            walk(child, f"{path}[{i}]")


def main() -> int:
    try:
        data = json.loads(CONTRACT.read_text(encoding="utf-8"))
    except Exception as exc:
        fail(f"cannot parse contract: {exc}")

    for path, expected in EXPECTED.items():
        actual = get_path(data, path)
        if actual != expected:
            fail(f"{'.'.join(path)} must be {expected!r}, got {actual!r}")

    walk(data)

    max_exec = get_path(data, ("policy", "max_execution_seconds"))
    if not isinstance(max_exec, int) or not 1 <= max_exec <= 60:
        fail("policy.max_execution_seconds must be 1..60")

    max_result = get_path(data, ("policy", "max_result_bytes"))
    if not isinstance(max_result, int) or not 1024 <= max_result <= 4194304:
        fail("policy.max_result_bytes outside safe range")

    freshness = get_path(data, ("health", "freshness_seconds"))
    if not isinstance(freshness, int) or freshness > 300:
        fail("health.freshness_seconds must be <= 300")

    health_timeout = get_path(data, ("health", "timeout_seconds"))
    if not isinstance(health_timeout, int) or not 1 <= health_timeout <= 30:
        fail("health.timeout_seconds must be 1..30")

    if get_path(data, ("auth", "secret_transport")) not in {
        "EXTERNAL_OAUTH", "EXTERNAL_SECRET_STORE", "REFERENCE_ONLY", "NONE"
    }:
        fail("unsupported auth.secret_transport")

    print(
        "MCP_READONLY_CONTRACT_VALID: "
        "default=DENY mutations=DENY destructive=DENY production=DENY "
        "verification=independent rollback=DISABLED"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
