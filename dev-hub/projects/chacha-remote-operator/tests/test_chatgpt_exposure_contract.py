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

    assert direct["current_authentication_mode"] == "TAILSCALE_SERVE_IDENTITY"
    assert direct["machine_to_machine_authentication"] == "UNRESOLVED"
    assert direct["tailscale_identity_header_spoofing_forbidden"] is True
    assert direct["direct_central_orchestrator_bypass_forbidden"] is True


def test_pilot_stays_blocked_until_real_direct_operator_bridge_exists() -> None:
    contract = load_contract()
    required = contract["pilot_required_surface"]
    activation = contract["activation"]

    assert required["direct_operator_intent"] == "UNRESOLVED"
    assert required["direct_operator_job"] == "UNRESOLVED"
    assert activation["production_activation_allowed"] is False
    assert activation["direct_operator_bridge"] == "UNRESOLVED"
    assert activation["pilot_allowed_before_all_gates_pass"] is False


def test_governance_and_pilot_path_preserve_authorities() -> None:
    contract = load_contract()
    governance = contract["governance"]
    pilot = contract["first_pilot"]

    assert governance["canonical_stop_required"] is True
    assert governance["guardian_required"] is True
    assert governance["sentinelle_required_before_production"] is True
    assert governance["bastion_required_for_network_exposure"] is True
    assert governance["umg_required"] is True
    assert governance["ccr_required"] is True
    assert governance["new_core_capability_required"] is False
    assert governance["chatgpt_is_not_operational_source_of_truth"] is True
    assert governance["capability_resolution_order"] == ["REUSE", "EXTEND", "ADAPT", "CREATE"]
    assert pilot["remote_desktop_commander_forbidden"] is True
    assert pilot["route"] == [
        "CHATGPT",
        "CHACHA_REMOTE_OPERATOR_MCP",
        "DIRECT_OPERATOR",
        "CENTRAL_ORCHESTRATOR",
        "TARGETED_FUNCTIONAL_ACCEPTANCE",
        "GUARDIAN",
    ]
