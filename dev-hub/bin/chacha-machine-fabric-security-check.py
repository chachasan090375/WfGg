#!/usr/bin/env python3

import json
from pathlib import Path


ROOT=Path(__file__).resolve().parents[1]

POLICY=(
    ROOT
    /"config"
    /"machine-fabric"
    /"security"
    /"security-policy.v1.json"
)


def main():
    d=json.loads(
        POLICY.read_text(encoding="utf-8")
    )

    assert d["schema"] == \
        "chacha.machine-fabric/security-policy/v1"

    assert d["transport"]["private_mesh_required"] is True
    assert d["transport"]["technology"] == "tailscale-wireguard"
    assert d["transport"]["public_ingress_required"] is False

    assert d["node_identity"]["algorithm"] == "Ed25519"
    assert d["node_identity"]["unique_private_key_per_node"] is True
    assert d["node_identity"]["shared_private_keys_forbidden"] is True

    c=d["command_envelope"]

    assert c["signature_algorithm"] == "Ed25519"
    assert c["signature_required"] is True
    assert c["nonce_required"] is True
    assert c["minimum_nonce_bits"] >= 128
    assert c["expiry_required"] is True
    assert c["replay_cache_required"] is True

    p=d["payload_security"]

    assert p["application_encryption_algorithm"] == "age-X25519"
    assert "CONFIDENTIAL" in p["mandatory_for"]
    assert "RESTRICTED" in p["mandatory_for"]

    t=d["transfer_integrity"]

    assert t["digest_algorithm"] == "SHA-256"
    assert t["source_digest_required"] is True
    assert t["destination_digest_required"] is True
    assert t["digests_must_match_before_success"] is True

    s=d["secret_handling"]

    assert s["raw_secret_in_mcp_forbidden"] is True
    assert s["secret_reference_only_in_control_plane"] is True
    assert s["private_keys_in_repository_forbidden"] is True

    l=d["local_authorization"]

    assert l["node_agent_must_recheck_policy"] is True
    assert l["node_agent_may_refuse_control_plane_order"] is True
    assert l["arbitrary_shell"] is False

    cp=d["control_plane"]

    assert cp["remote_mcp_first_route"] is True
    assert cp["guardian_required"] is True
    assert cp["stop_required"] is True

    print("MACHINE_FABRIC_SECURITY_POLICY=PASS")
    print("RUNTIME_CRYPTO_ACTIVE=NO")
    print("NEXT=NODE_AGENT_CRYPTO_ENFORCEMENT")


if __name__ == "__main__":
    main()
