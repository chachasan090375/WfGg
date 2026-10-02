from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from chacha_remote_operator.audit import V02_AUDIT_SCHEMA, append_audit
from chacha_remote_operator.lease import LeaseBusy, command_lease
from chacha_remote_operator.operations import _operation_argv, run_governed_operation
from chacha_remote_operator.policy import OperatorPolicy, PolicyError, V02_OPERATION_IDS, load_policy


PROJECT_ROOT = Path(__file__).resolve().parents[1]


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
        "version": "0.2.0",
        "mode": "TEST",
        "fail_closed": True,
        "bind_host": "127.0.0.1",
        "runtime_root": str(tmp_path / "runtime"),
        "canonical_stop_state": str(stop),
        "audit_log": str(tmp_path / "runtime" / "audit.jsonl"),
        "allowed_roots": [str(root)],
        "blocked_path_fragments": ["/.ssh/", "/secrets/", "/.env"],
        "service_status_allowlist": ["safe.service"],
        "command_execution_enabled": False,
        "command_allowlist": [],
        "governed_operations_enabled": True,
        "governed_operation_allowlist": list(V02_OPERATION_IDS),
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
        "external_network_access_enabled": False,
        "automatic_external_spend_eur": 0,
    }
    return OperatorPolicy(raw, tmp_path / "policy.json")


def _guardian_phases(policy: OperatorPolicy) -> set[str]:
    events = sorted((policy.runtime_root / "guardian-events").glob("*.json"))
    return {json.loads(x.read_text(encoding="utf-8"))["phase"] for x in events}


def test_published_v02_policy_is_exact_and_localhost_only() -> None:
    policy = load_policy(PROJECT_ROOT / "config" / "policy.v2.json")
    assert policy.raw["version"] == "0.2.0"
    assert policy.raw["bind_host"] == "127.0.0.1"
    assert policy.raw["fail_closed"] is True
    assert policy.raw["external_network_access_enabled"] is False
    assert policy.raw["command_execution_enabled"] is False
    assert policy.raw["single_writer_command_lease"] is True
    assert policy.raw["guardian_required_for_governed_operations"] is True
    assert policy.raw["automatic_external_spend_eur"] == 0
    assert tuple(policy.raw["governed_operation_allowlist"]) == V02_OPERATION_IDS


def test_raw_command_surface_stays_disabled(tmp_path: Path) -> None:
    p = make_policy(tmp_path)
    assert p.command_allowed(["bash", "-c", "id"]) is False
    assert p.command_allowed(["git", "push"]) is False
    assert p.raw["command_execution_enabled"] is False


def test_server_side_argv_is_exact_and_has_no_shell_or_user_argv(tmp_path: Path) -> None:
    p = make_policy(tmp_path)
    root = p.allowed_roots[0]
    expected = {
        "git_status": (["git", "status", "--short", "--branch"], root),
        "git_head": (["git", "rev-parse", "HEAD"], root),
        "git_tree": (["git", "rev-parse", "HEAD^{tree}"], root),
        "service_is_active": (["systemctl", "is-active", "safe.service"], None),
        "service_is_enabled": (["systemctl", "is-enabled", "safe.service"], None),
        "uptime": (["uptime"], None),
        "free_bytes": (["free", "-b"], None),
        "uname": (["uname", "-a"], None),
    }
    for operation_id, wanted in expected.items():
        cwd = str(root) if operation_id.startswith("git_") else None
        service = "safe.service" if operation_id.startswith("service_") else None
        argv, workdir = _operation_argv(p, operation_id, cwd, service)
        assert (argv, workdir) == wanted

    with pytest.raises(PolicyError, match="UNEXPECTED_CWD_PARAMETER"):
        _operation_argv(p, "uptime", str(root), None)
    with pytest.raises(PolicyError, match="UNEXPECTED_SERVICE_PARAMETER"):
        _operation_argv(p, "uname", None, "safe.service")


def test_named_operation_requires_exact_allowlist(tmp_path: Path) -> None:
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


def test_guardian_pre_post_and_enriched_audit_on_real_read_operation(tmp_path: Path) -> None:
    p = make_policy(tmp_path)
    result = run_governed_operation(p, "uptime")
    assert result["operation_id"] == "uptime"
    assert result["returncode"] == 0
    assert str(result["action_id"]).startswith("cro-uptime-")
    assert str(result["lease_id"]).startswith("cro-")
    assert _guardian_phases(p) == {"PRE_ACTION", "POST_ACTION"}

    lines = p.audit_log.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["schema"] == V02_AUDIT_SCHEMA
    assert record["status"] == "PASS"
    assert record["tool"] == "uptime"
    assert record["event_id"].startswith("cro-audit-")
    assert record["timestamp_utc"].endswith("+00:00")
    assert record["details"]["argv"] == ["uptime"]
    assert record["details"]["argv_user_supplied"] is False
    assert record["details"]["shell"] is False
    assert record["details"]["guardian_pre_verdict"] == "PASS"
    assert record["details"]["guardian_post_verdict"] == "PASS"
    assert record["automatic_external_spend_eur"] == 0


def test_audit_is_append_only(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    append_audit(path, "one", "PASS", {"seq": 1}, schema=V02_AUDIT_SCHEMA)
    first = path.read_bytes()
    append_audit(path, "two", "BLOCKED", {"seq": 2}, schema=V02_AUDIT_SCHEMA)
    second = path.read_bytes()
    assert second.startswith(first)
    rows = [json.loads(line) for line in second.decode("utf-8").splitlines()]
    assert [row["details"]["seq"] for row in rows] == [1, 2]


def test_stop_active_blocks_before_guardian_or_execution(tmp_path: Path) -> None:
    p = make_policy(tmp_path)
    p.stop_state.write_text('{"active": true}\n', encoding="utf-8")
    with pytest.raises(PolicyError, match="CANONICAL_STOP_ACTIVE"):
        run_governed_operation(p, "uptime")
    assert not (p.runtime_root / "guardian-events").exists()
    record = json.loads(p.audit_log.read_text(encoding="utf-8").splitlines()[-1])
    assert record["status"] == "BLOCKED"
    assert record["details"]["reason"] == "CANONICAL_STOP_ACTIVE"


def test_missing_stop_state_is_fail_closed(tmp_path: Path) -> None:
    p = make_policy(tmp_path)
    p.stop_state.unlink()
    with pytest.raises(PolicyError, match="STOP_STATE_MISSING"):
        run_governed_operation(p, "uptime")
    assert not (p.runtime_root / "guardian-events").exists()
    record = json.loads(p.audit_log.read_text(encoding="utf-8").splitlines()[-1])
    assert record["status"] == "BLOCKED"
    assert record["details"]["reason"] == "STOP_STATE_MISSING"


def test_guardian_post_runs_when_execution_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import chacha_remote_operator.operations as operations

    p = make_policy(tmp_path)
    monkeypatch.setattr(
        operations,
        "_operation_argv",
        lambda policy, operation_id, cwd, service: (["/definitely/not/a/real/executable"], None),
    )
    with pytest.raises(PolicyError, match="GOVERNED_OPERATION_EXECUTION_FAILED"):
        operations.run_governed_operation(p, "uptime")
    assert _guardian_phases(p) == {"PRE_ACTION", "POST_ACTION"}
    record = json.loads(p.audit_log.read_text(encoding="utf-8").splitlines()[-1])
    assert record["status"] == "BLOCKED"
    assert record["details"]["guardian_pre_verdict"] == "PASS"
    assert record["details"]["guardian_post_verdict"] == "PASS"


def test_v02_mcp_surface_preserves_exactly_eight_named_operations() -> None:
    source = (PROJECT_ROOT / "src" / "chacha_remote_operator" / "server_v02.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    decorated: list[ast.FunctionDef] = []
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        if any(
            isinstance(dec, ast.Call)
            and isinstance(dec.func, ast.Attribute)
            and dec.func.attr == "tool"
            for dec in node.decorator_list
        ):
            decorated.append(node)

    by_name = {node.name: node for node in decorated}
    # V0.2's compatibility contract is the exact eight governed operations.
    # Later protocol extensions may add separately governed tools without
    # changing or weakening that historical operation surface.
    assert tuple(name for name in V02_OPERATION_IDS if name in by_name) == V02_OPERATION_IDS
    signatures = {name: [arg.arg for arg in by_name[name].args.args] for name in V02_OPERATION_IDS}
    assert signatures == {
        "git_status": ["repository"],
        "git_head": ["repository"],
        "git_tree": ["repository"],
        "service_is_active": ["service"],
        "service_is_enabled": ["service"],
        "uptime": [],
        "free_bytes": [],
        "uname": [],
    }
    assert "governed_operation" not in by_name
    assert all("argv" not in params for params in signatures.values())
