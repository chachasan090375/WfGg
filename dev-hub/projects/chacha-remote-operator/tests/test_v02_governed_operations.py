from __future__ import annotations

import json
from pathlib import Path

import pytest

from chacha_remote_operator.lease import LeaseBusy, command_lease
from chacha_remote_operator.operations import run_governed_operation
from chacha_remote_operator.policy import OperatorPolicy, PolicyError


def make_policy(tmp_path: Path) -> OperatorPolicy:
    root = tmp_path / "allowed"
    root.mkdir()
    stop = tmp_path / "stop.json"
    stop.write_text('{"active": false}\n', encoding="utf-8")
    guardian_policy = tmp_path / "guardian-policy.json"
    guardian_policy.write_text('{}\n', encoding="utf-8")
    guardian_client = tmp_path / "guardian-client.py"
    guardian_client.write_text(
        "import json,sys\n"
        "p=sys.argv[sys.argv.index('--event')+1]\n"
        "e=json.load(open(p,encoding='utf-8'))\n"
        "print(json.dumps({'schema':'test','action_id':e['action_id'],'verdict':'PASS','remediation_required':False,'stop_recommended':False}))\n",
        encoding="utf-8",
    )
    raw = {
        "schema": "chacha.dev/chacha-remote-operator-policy/v2",
        "mode": "TEST",
        "runtime_root": str(tmp_path / "runtime"),
        "canonical_stop_state": str(stop),
        "audit_log": str(tmp_path / "runtime" / "audit.jsonl"),
        "allowed_roots": [str(root)],
        "blocked_path_fragments": ["/.ssh/", "/secrets/", "/.env"],
        "service_status_allowlist": ["safe.service"],
        "command_execution_enabled": False,
        "command_allowlist": [],
        "governed_operations_enabled": True,
        "governed_operation_allowlist": ["uptime", "free_bytes", "uname", "service_is_active"],
        "single_writer_command_lease": True,
        "guardian_required_for_governed_operations": True,
        "guardian_client_path": str(guardian_client),
        "guardian_policy_path": str(guardian_policy),
        "guardian_timeout_seconds": 5,
        "max_command_seconds": 5,
        "max_command_output_bytes": 4096,
        "file_write_enabled": False,
        "service_mutation_enabled": False,
        "git_mutation_enabled": False,
        "destructive_operations_enabled": False,
        "automatic_external_spend_eur": 0,
    }
    return OperatorPolicy(raw, tmp_path / "policy.json")


def test_raw_command_surface_stays_disabled(tmp_path: Path) -> None:
    p = make_policy(tmp_path)
    assert p.command_allowed(["bash", "-c", "id"]) is False
    assert p.command_allowed(["git", "push"]) is False
    assert p.raw["command_execution_enabled"] is False


def test_named_operation_requires_allowlist(tmp_path: Path) -> None:
    p = make_policy(tmp_path)
    with pytest.raises(PolicyError, match="GOVERNED_OPERATION_NOT_ALLOWLISTED"):
        run_governed_operation(p, "not-a-real-operation")


def test_service_parameter_is_allowlisted(tmp_path: Path) -> None:
    p = make_policy(tmp_path)
    with pytest.raises(PolicyError, match="SERVICE_NOT_ALLOWLISTED"):
        run_governed_operation(p, "service_is_active", service="ssh.service")


def test_single_writer_command_lease(tmp_path: Path) -> None:
    root = tmp_path / "lease"
    with command_lease(root, "first") as first:
        assert first["single_writer"] is True
        with pytest.raises(LeaseBusy, match="REMOTE_OPERATOR_COMMAND_LEASE_BUSY"):
            with command_lease(root, "second"):
                pass
    assert not (root / "command-lease.json").exists()


def test_guardian_pre_post_and_audit_on_real_read_operation(tmp_path: Path) -> None:
    p = make_policy(tmp_path)
    result = run_governed_operation(p, "uptime")
    assert result["operation_id"] == "uptime"
    assert result["returncode"] == 0
    assert str(result["action_id"]).startswith("cro-uptime-")
    assert str(result["lease_id"]).startswith("cro-")
    events = sorted((p.runtime_root / "guardian-events").glob("*.json"))
    assert len(events) == 2
    phases = {json.loads(x.read_text(encoding="utf-8"))["phase"] for x in events}
    assert phases == {"PRE_ACTION", "POST_ACTION"}
    audit = p.audit_log.read_text(encoding="utf-8")
    assert '"tool": "governed_operation"' in audit
    assert '"status": "PASS"' in audit


def test_stop_blocks_before_guardian_or_execution(tmp_path: Path) -> None:
    p = make_policy(tmp_path)
    p.stop_state.write_text('{"active": true}\n', encoding="utf-8")
    with pytest.raises(PolicyError, match="CANONICAL_STOP_ACTIVE"):
        run_governed_operation(p, "uptime")
    assert not (p.runtime_root / "guardian-events").exists()
