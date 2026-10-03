from __future__ import annotations

import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = PROJECT_ROOT / "config" / "chatgpt-exposure.v1.json"


def load_contract() -> dict:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def test_chatgpt_exposure_reuses_private_streamable_http_mcp() -> None:
    contract = load_contract()
    source = contract["source_candidate"]
    transport = contract["exposure_transport"]

    assert contract["schema"] == "chacha.dev/chatgpt-remote-operator-exposure/v1"
    assert source["transport"] == "streamable-http"
    assert source["private_endpoint"] == "http://127.0.0.1:8767/mcp"
    assert transport["kind"] == "OPENAI_SECURE_MCP_TUNNEL"
    assert transport["public_ingress_forbidden"] is True
    assert transport["mcp_must_remain_loopback_bound"] is True
    assert transport["credentials_in_source_forbidden"] is True
    assert float(transport["automatic_external_spend_eur"]) == 0


def test_direct_operator_authentication_cannot_be_spoofed_or_bypassed() -> None:
    contract = load_contract()
    direct = contract["direct_operator_target"]

    assert direct["current_human_authentication_mode"] == "TAILSCALE_SERVE_IDENTITY"
    assert direct["machine_to_machine_authentication"] == "HMAC_SHA256_RUNTIME_SECRET"
    assert direct["service_id"] == "chacha-remote-operator-mcp"
    assert direct["secret_registry"] == "/opt/chacha-dev/runtime/secrets/direct-operator-m2m.json"
    assert direct["tailscale_identity_header_spoofing_forbidden"] is True
    assert direct["direct_central_orchestrator_bypass_forbidden"] is True
    assert direct["forced_channel"] == "BUILD"
    assert direct["direct_mutation_authority"] is False
    assert direct["technical_decision_authority"] is False


def test_source_bridge_exists_but_pilot_remains_fail_closed() -> None:
    contract = load_contract()
    required = contract["pilot_required_surface"]
    direct = contract["direct_operator_target"]
    activation = contract["activation"]

    assert required["direct_operator_intent"] == "SOURCE_IMPLEMENTED_DISABLED"
    assert required["direct_operator_job"] == "SOURCE_IMPLEMENTED_DISABLED"
    assert direct["intent_path"] == "/api/v1/m2m/intent"
    assert direct["job_path_prefix"] == "/api/v1/m2m/jobs/"
    assert direct["bridge_enabled"] is False
    assert activation["production_activation_allowed"] is False
    assert activation["direct_operator_bridge"] == "SOURCE_IMPLEMENTED_DISABLED"
    assert activation["direct_operator_handler"] == "SOURCE_IMPLEMENTED_DISABLED"
    assert activation["runtime_secret_materialized"] is False
    assert activation["pilot_allowed_before_all_gates_pass"] is False


def test_governance_preserves_canonical_route_authority() -> None:
    contract = load_contract()
    governance = contract["governance"]
    direct = contract["direct_operator_target"]

    assert governance["canonical_stop_required"] is True
    assert governance["guardian_required"] is True
    assert governance["sentinelle_required_before_production"] is True
    assert governance["bastion_required_for_network_exposure"] is True
    assert governance["umg_required"] is True
    assert governance["ccr_required"] is True
    assert governance["guardian_role_extension"] == "role:remote-operator-functional-ingress-agent"
    assert governance["canonical_route_authority"] == "dev-hub/config/canonical-route-authority.v1.json"
    assert governance["unknown_route_fails_closed"] is True
    assert governance["fallback_cannot_expand_authority"] is True
    assert governance["chatgpt_is_not_operational_source_of_truth"] is True
    assert direct["canonical_route_id"] == "remote-mcp-functional-build"
    assert "first_pilot" not in contract
    assert "revision" not in contract["source_candidate"]
