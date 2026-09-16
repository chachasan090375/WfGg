#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "claude-agent-adapter.v1.json"
REGISTRY = ROOT / "config" / "provider-adapters.v1.json"
CAPABILITIES = ROOT / "config" / "capability-registry.v1.json"


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def fail(msg):
    raise SystemExit(f"CLAUDE_AGENT_DESIGN_INVALID: {msg}")


def provider_entries(capabilities, provider_id):
    found = []
    for capability, item in capabilities.get("capabilities", {}).items():
        for provider in item.get("providers", []):
            if provider.get("id") == provider_id:
                found.append((capability, provider))
    return found


def main():
    config = load(CONFIG)
    registry = load(REGISTRY)
    capabilities = load(CAPABILITIES)

    if config.get("schema") != "chacha.dev/claude-agent-adapter/v1":
        fail("schema")
    if config.get("provider_id") != "anthropic-claude" or config.get("adapter_id") != "claude-agent-adapter":
        fail("identity")
    if config.get("decision") != "ASSESS" or config.get("runtime_status") != "DESIGNED":
        fail("design status")

    integration = config.get("integration", {})
    if integration.get("primary_surface") != "claude-agent-sdk":
        fail("primary surface")
    if integration.get("execution") != "external":
        fail("execution")
    if integration.get("mcp_server_mode") != "SECONDARY_OPTIONAL":
        fail("MCP must remain secondary")
    if integration.get("github_action_mode") != "NOT_PRIMARY":
        fail("GitHub Action must not bypass DEV HUB")

    boundary = config.get("boundary", {})
    if boundary.get("input_schema") != "chacha.dev/dispatch-envelope/v1" or boundary.get("output_schema") != "chacha.dev/task-result/v1":
        fail("DEV HUB boundary")
    if boundary.get("provider_result_trust") != "UNVERIFIED":
        fail("result trust")
    if boundary.get("verification_broker_required") is not True or boundary.get("producer_must_not_self_verify") is not True:
        fail("verification separation")

    auth = config.get("auth", {})
    if auth.get("secret_policy") != "REFERENCE_ONLY":
        fail("secret policy")
    if auth.get("secret_values_in_git") is not False or auth.get("secret_values_in_evidence") is not False:
        fail("secret material")
    if auth.get("environment_reference") != "ANTHROPIC_API_KEY":
        fail("credential reference")
    if auth.get("authorization_and_api_key_headers_in_evidence") != "REDACT":
        fail("credential redaction")

    model = config.get("model_policy", {})
    if model.get("selection") != "RUNTIME_CONFIGURED_APPROVED_ACTIVE_MODEL" or model.get("hardcoded_model_id") is not False:
        fail("model selection")
    for key in ("technology_radar_tracks_models", "technology_radar_tracks_sdk", "technology_radar_tracks_deprecations"):
        if model.get(key) is not True:
            fail(key)

    tools = config.get("tool_policy", {})
    if tools.get("default") != "DENY":
        fail("default deny")
    if set(tools.get("design_stage_allow", [])) != {"Read", "Glob", "Grep"}:
        fail("design allowlist")
    denied = set(tools.get("design_stage_deny", []))
    if not {"Bash", "Edit", "Write"}.issubset(denied):
        fail("dangerous tools not denied")
    for key in ("arbitrary_shell", "workspace_write", "repository_write", "production_mutation", "destructive_operations"):
        if tools.get(key) is not False:
            fail(f"{key} must be false")
    if tools.get("network_tools") != "DENY_UNLESS_SEPARATELY_CONTRACTED" or tools.get("mcp_tools") != "DENY_UNLESS_SEPARATELY_ALLOWLISTED":
        fail("external tool boundary")

    stage = config.get("capability_stage", {})
    if "code-edit" in set(stage.get("admitted_now", [])) or "workspace-write" in set(stage.get("admitted_now", [])):
        fail("write capability admitted too early")
    if not {"code-edit", "workspace-write"}.issubset(set(stage.get("future_after_separate_contract", []))):
        fail("future write contract missing")

    review = config.get("cross_provider_review", {})
    if review.get("enabled") is not True or review.get("same_provider_self_verification") is not False:
        fail("cross-provider review")
    if review.get("verification_authority") != "verification-broker":
        fail("verification authority")

    admission = config.get("admission", {})
    if admission.get("automatic_promotion") is not False:
        fail("automatic promotion")
    if admission.get("runtime_call_allowed_at_design_stage") is not False:
        fail("runtime call at design stage")
    if admission.get("credential_required_at_design_stage") is not False:
        fail("credential required at design stage")
    if admission.get("production_change_allowed") is not False:
        fail("production change")

    provider = registry.get("providers", {}).get("anthropic-claude", {})
    adapter = registry.get("adapters", {}).get("claude-agent-adapter", {})
    if provider != {"adapter": "claude-agent-adapter", "kind": "ai-agent", "execution": "external"}:
        fail("provider registry")
    if adapter.get("status") != "DESIGNED" or adapter.get("executable") not in {None, ""} or adapter.get("supports") != ["read", "plan"]:
        fail("adapter registry")

    entries = provider_entries(capabilities, "anthropic-claude")
    names = {name for name, _ in entries}
    if names != {"code-review", "documentation"}:
        fail(f"capability exposure={sorted(names)}")
    for name, entry in entries:
        if entry.get("status") != "ASSESS" or entry.get("health") != "contract-not-qualified":
            fail(f"capability {name} admission")
        if entry.get("scope") != "read-only-workspace":
            fail(f"capability {name} scope")
    code_edit_ids = {p.get("id") for p in capabilities.get("capabilities", {}).get("code-edit", {}).get("providers", [])}
    if "anthropic-claude" in code_edit_ids:
        fail("Claude must not be in code-edit before write contract")

    print("CLAUDE_AGENT_DESIGN_VALID: provider=anthropic-claude status=DESIGNED assess_only=true read_plan_only=true runtime=false")


if __name__ == "__main__":
    main()
