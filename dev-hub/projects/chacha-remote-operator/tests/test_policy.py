from __future__ import annotations

import json
from pathlib import Path

import pytest

from chacha_remote_operator.policy import OperatorPolicy, PolicyError


def policy(tmp_path: Path, command_enabled: bool = False) -> OperatorPolicy:
    root = tmp_path / "allowed"
    root.mkdir()
    stop = tmp_path / "stop.json"
    stop.write_text('{"active": false}\n', encoding="utf-8")
    audit = tmp_path / "audit.jsonl"
    data = {
        "schema": "chacha.dev/chacha-remote-operator-policy/v1",
        "canonical_stop_state": str(stop),
        "audit_log": str(audit),
        "allowed_roots": [str(root)],
        "blocked_path_fragments": ["/.ssh/", "/secrets/", "/.env"],
        "command_execution_enabled": command_enabled,
        "command_allowlist": [["git", "status"], ["systemctl", "is-active"]],
        "service_status_allowlist": ["safe.service"],
    }
    return OperatorPolicy(data, tmp_path / "policy.json")


def test_path_allowlist_and_escape(tmp_path: Path) -> None:
    p = policy(tmp_path)
    allowed = tmp_path / "allowed" / "x.txt"
    allowed.write_text("ok", encoding="utf-8")
    assert p.resolve_read_path(str(allowed)) == allowed.resolve()
    with pytest.raises(PolicyError, match="PATH_OUTSIDE_ALLOWLIST"):
        p.resolve_read_path(str(tmp_path / "outside.txt"))


def test_secret_class_blocked(tmp_path: Path) -> None:
    p = policy(tmp_path)
    secret = tmp_path / "allowed" / ".ssh" / "id_ed25519"
    secret.parent.mkdir()
    secret.write_text("never", encoding="utf-8")
    with pytest.raises(PolicyError, match="PATH_SECRET_CLASS_BLOCKED"):
        p.resolve_read_path(str(secret))


def test_stop_blocks_operations(tmp_path: Path) -> None:
    p = policy(tmp_path)
    p.require_operational()
    p.stop_state.write_text(json.dumps({"active": True}), encoding="utf-8")
    with pytest.raises(PolicyError, match="CANONICAL_STOP_ACTIVE"):
        p.require_operational()


def test_commands_disabled_by_default(tmp_path: Path) -> None:
    p = policy(tmp_path, command_enabled=False)
    assert p.command_allowed(["git", "status"]) is False


def test_command_requires_allowlisted_prefix(tmp_path: Path) -> None:
    p = policy(tmp_path, command_enabled=True)
    assert p.command_allowed(["git", "status", "--short"]) is True
    assert p.command_allowed(["git", "push"]) is False
    assert p.command_allowed(["bash", "-c", "id"]) is False


def test_service_allowlist(tmp_path: Path) -> None:
    p = policy(tmp_path)
    assert p.service_allowed("safe.service") is True
    assert p.service_allowed("ssh.service") is False
