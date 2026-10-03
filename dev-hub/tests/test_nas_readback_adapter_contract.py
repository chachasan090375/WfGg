from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ADAPTER = ROOT / "dev-hub/adapters/nas-readback-adapter.py"
POLICY = ROOT / "dev-hub/config/nas-readback-adapter.v1.json"

spec = importlib.util.spec_from_file_location("nas_readback_adapter", ADAPTER)
m = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(m)
policy = json.loads(POLICY.read_text(encoding="utf-8"))


def digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def request(workspace: Path, expected: str | None = None) -> dict:
    return {
        "schema": "chacha.dev/dispatch-envelope/v1",
        "project": "chacha-dev",
        "run_id": "nas-readback-contract-test",
        "task": {"id": "readback", "permission": "workspace-write"},
        "bindings": [{"provider": "nas-readback", "adapter": "nas-readback-adapter"}],
        "workspace": str(workspace),
        "metadata": {
            "nas_readback": {
                "action": "read-file",
                "remote_path": "knowledge/cognitive-memory-shadow/test.db",
                "local_path": "restore/test.db",
                "expected_sha256": expected or digest(b"hello"),
            }
        },
    }


def test_policy_is_least_privilege() -> None:
    assert policy["production_activation_authorized"] is False
    assert policy["automatic_external_spend_eur"] == 0
    assert policy["workspace"]["overwrite_allowed"] is False
    assert policy["workspace"]["active_memory_restore_forbidden"] is True
    assert policy["nas"]["host"] == "chachanas"
    assert policy["nas"]["root"] == "/share/CACHEDEV1_DATA/ChaCha-DEV-HUB"
    assert "knowledge/cognitive-memory-shadow/" in policy["nas"]["allowed_prefixes"]


def test_request_requires_workspace_write_and_binding() -> None:
    with tempfile.TemporaryDirectory(prefix="nas-readback-contract-") as td:
        req = request(Path(td))
        cfg, error = m.validate_request(req, policy)
        assert error is None and cfg is not None
        req["task"]["permission"] = "read"
        _, error = m.validate_request(req, policy)
        assert error == "NAS_READBACK_REQUIRES_WORKSPACE_WRITE"
        req = request(Path(td))
        req["bindings"] = []
        _, error = m.validate_request(req, policy)
        assert error == "NAS_READBACK_BINDING_MISSING"

def test_paths_are_allowlisted_and_no_overwrite() -> None:
    with tempfile.TemporaryDirectory(prefix="nas-readback-contract-") as td:
        workspace = Path(td)
        req = request(workspace)
        cfg = req["metadata"]["nas_readback"]
        remote, destination, expected = m.resolve_paths(req, cfg, policy)
        assert remote.startswith("knowledge/cognitive-memory-shadow/")
        assert destination == workspace / "restore/test.db"
        assert expected == digest(b"hello")
        req["metadata"]["nas_readback"]["remote_path"] = "knowledge/other/test.db"
        try:
            m.resolve_paths(req, req["metadata"]["nas_readback"], policy)
            raise AssertionError("non-allowlisted remote path accepted")
        except ValueError as exc:
            assert str(exc) == "NAS_READBACK_REMOTE_PATH_NOT_ALLOWLISTED"
        req = request(workspace)
        target = workspace / "restore/test.db"
        target.parent.mkdir(parents=True)
        target.write_bytes(b"existing")
        try:
            m.resolve_paths(req, req["metadata"]["nas_readback"], policy)
            raise AssertionError("existing destination accepted")
        except ValueError as exc:
            assert str(exc) == "NAS_READBACK_LOCAL_DESTINATION_EXISTS"


def test_active_memory_workspace_is_blocked() -> None:
    req = request(Path("/opt/chacha-dev/runtime/knowledge"))
    try:
        m.resolve_paths(req, req["metadata"]["nas_readback"], policy)
        raise AssertionError("active memory workspace accepted")
    except ValueError as exc:
        assert str(exc) == "NAS_READBACK_WORKSPACE_NOT_ALLOWLISTED"

def test_readback_copies_only_after_double_hash_verification() -> None:
    payload = b"hello"
    expected = digest(payload)
    with tempfile.TemporaryDirectory(prefix="nas-readback-contract-") as td:
        workspace = Path(td)
        req = request(workspace, expected)
        cfg = req["metadata"]["nas_readback"]
        original_size, original_remote_sha, original_run = m.remote_size, m.remote_sha256, m.run
        m.remote_size = lambda _p, _r: len(payload)
        m.remote_sha256 = lambda _p, _r: expected
        def fake_run(argv, timeout=60):
            Path(argv[-1]).write_bytes(payload)
            return subprocess.CompletedProcess(argv, 0, b"", b"")
        m.run = fake_run
        try:
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = m.readback(req, cfg, policy)
            result = json.loads(out.getvalue())
            assert rc == 0
            assert result["status"] == "OK"
            assert result["evidence"][0]["details"]["remote_write_performed"] is False
            assert (workspace / "restore/test.db").read_bytes() == payload
        finally:
            m.remote_size, m.remote_sha256, m.run = original_size, original_remote_sha, original_run


def test_remote_hash_mismatch_blocks_before_copy() -> None:
    with tempfile.TemporaryDirectory(prefix="nas-readback-contract-") as td:
        req = request(Path(td))
        cfg = req["metadata"]["nas_readback"]
        original_size, original_remote_sha = m.remote_size, m.remote_sha256
        m.remote_size = lambda _p, _r: 5
        m.remote_sha256 = lambda _p, _r: digest(b"wrong")
        try:
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = m.readback(req, cfg, policy)
            assert rc == 2
            assert json.loads(out.getvalue())["summary"] == "NAS_READBACK_REMOTE_SHA256_MISMATCH"
        finally:
            m.remote_size, m.remote_sha256 = original_size, original_remote_sha

def test_source_has_no_remote_mutation_primitives() -> None:
    source = ADAPTER.read_text(encoding="utf-8")
    forbidden = [
        "NAS_ACTION_NOT_ALLOWED",
        "mkdir -p",
        "rm -f",
        "cat >",
        "mv ",
        "put-file",
    ]
    for marker in forbidden:
        assert marker not in source, marker
    assert '"sha256sum"' in source
    assert '"stat", "-c", "%s"' in source
    assert '"/usr/bin/scp", "-q", "--"' in source


if __name__ == "__main__":
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_") and callable(value)]
    for test in tests:
        test()
        print(test.__name__ + "=PASS")
    print("CHACHA_DEV_NAS_READBACK_ADAPTER_CONTRACT=PASS")
    print("TEST_COUNT=" + str(len(tests)))
    print("REMOTE_WRITE_AUTHORITY=NO")
    print("AUTOMATIC_EXTERNAL_SPEND_EUR=0")
