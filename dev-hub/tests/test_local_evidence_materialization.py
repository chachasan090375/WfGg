#!/usr/bin/env python3
from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import tempfile
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load(name: str, rel: str):
    path = ROOT / rel
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def capture(callable_):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = callable_()
    return rc, json.loads(buf.getvalue())


def assert_local_evidence(result: dict) -> None:
    assert result["evidence"]
    for evidence in result["evidence"]:
        source = Path(evidence["source"])
        assert source.is_absolute()
        assert source.is_file()
        actual = "sha256:" + hashlib.sha256(source.read_bytes()).hexdigest()
        assert actual == evidence["digest"]


def assert_declared_outputs(result: dict, declared: list[dict]) -> None:
    expected = [(x["type"], x["id"]) for x in declared]
    actual = [(x["type"], x["id"]) for x in result.get("outputs") or []]
    assert actual == expected
    assert all(x.get("status") == "UNVERIFIED" for x in result.get("outputs") or [])


def test_context7_materialization() -> None:
    mod = load("ctx7", "dev-hub/adapters/context7-mcp-adapter.py")
    with tempfile.TemporaryDirectory() as td:
        mod.EVIDENCE_ROOT = Path(td)
        req = {"project": "p", "run_id": "r", "task": {"id": "t"}}
        payload = b"context7-response\n"
        source, digest = mod.materialize(req, "tools", payload)
        p = Path(source)
        assert p.is_absolute()
        assert p.read_bytes() == payload
        assert digest == "sha256:" + hashlib.sha256(payload).hexdigest()


def test_platform_materialization() -> None:
    mod = load("platform", "dev-hub/adapters/platform-command-adapter.py")
    with tempfile.TemporaryDirectory() as td:
        mod.EVIDENCE_ROOT = Path(td)
        req = {"project": "p", "run_id": "r", "task": {"id": "t"}}
        payload = b'{"snapshot_freshness":"FRESH"}\n'
        source, digest = mod.materialize(req, "technology-watch", payload)
        p = Path(source)
        assert p.is_absolute()
        assert p.read_bytes() == payload
        assert digest == "sha256:" + hashlib.sha256(payload).hexdigest()


def collector_request(action: str, output_type: str, output_id: str) -> dict:
    return {
        "project": "p",
        "run_id": "r",
        "task": {
            "id": "capability:domain-knowledge-research:collector-knowledge-inspect",
            "outputs": [{"type": output_type, "id": output_id}],
        },
        "metadata": {"collector_knowledge": {"action": action}},
    }


def test_collector_status_honors_declared_outputs_and_local_evidence() -> None:
    mod = load("collector_status", "dev-hub/adapters/collector-knowledge-adapter.py")
    with tempfile.TemporaryDirectory() as td:
        mod.EVIDENCE_ROOT = Path(td)
        mod.knowledge_snapshot = lambda: {
            "worker_state": "active",
            "worker_enabled": "enabled",
            "api_state": "active",
            "api_enabled": "enabled",
            "app_exists": True,
            "refresh_exists": True,
            "database_exists": True,
        }
        mod.get_json = lambda path, timeout=10: {"status": "PASS", "stats": {}}
        req = collector_request("status", "report", "declared-status")
        rc, result = capture(lambda: mod.do_status(req, {}))
        assert rc == 0
        assert_declared_outputs(result, req["task"]["outputs"])
        assert_local_evidence(result)
        assert result["evidence"][0]["details"]["origin"] == "vps://localhost/collector-knowledge/status"


def test_collector_query_honors_declared_outputs_and_local_evidence() -> None:
    mod = load("collector_query", "dev-hub/adapters/collector-knowledge-adapter.py")
    with tempfile.TemporaryDirectory() as td:
        mod.EVIDENCE_ROOT = Path(td)
        mod.get_json = lambda path, timeout=10: {"results": [{"id": "x"}]}
        req = collector_request("query", "report", "declared-query")
        rc, result = capture(lambda: mod.do_query(req, {"q": "test", "limit": 5}))
        assert rc == 0
        assert_declared_outputs(result, req["task"]["outputs"])
        assert_local_evidence(result)
        assert result["evidence"][0]["details"]["origin"] == "vps://localhost/collector-knowledge/query"


def test_collector_install_honors_declared_outputs_and_local_evidence() -> None:
    mod = load("collector_install", "dev-hub/adapters/collector-knowledge-adapter.py")
    with tempfile.TemporaryDirectory() as td:
        mod.EVIDENCE_ROOT = Path(td)
        snapshot = {
            "radar_connector_state": "active",
            "radar_sentinel_state": "active",
            "collector_sentinel_state": "active",
            "connector_sha256": "a",
            "native_sha256": "b",
            "messenger_sha256": "c",
        }
        mod.production_snapshot = lambda: dict(snapshot)
        mod.knowledge_snapshot = lambda: {
            "worker_state": "active",
            "worker_enabled": "enabled",
            "api_state": "active",
            "api_enabled": "enabled",
            "app_exists": True,
            "refresh_exists": True,
            "database_exists": True,
        }
        mod.download = lambda revision, path, destination, timeout: destination.write_bytes(b"#!/bin/sh\n")
        mod.run = lambda argv, timeout=30, env=None: types.SimpleNamespace(returncode=0, stdout=b"OK\n", stderr=b"")
        req = collector_request("pilot-install", "artifact", "declared-install")
        rc, result = capture(lambda: mod.do_install(req, {"revision": "a" * 40}))
        assert rc == 0
        assert_declared_outputs(result, req["task"]["outputs"])
        assert_local_evidence(result)
        assert result["evidence"][0]["details"]["origin"] == "vps://localhost/collector-knowledge/install"


def test_collector_probe_honors_declared_outputs_and_local_evidence() -> None:
    mod = load("collector_probe", "dev-hub/adapters/collector-knowledge-adapter.py")
    with tempfile.TemporaryDirectory() as td:
        mod.EVIDENCE_ROOT = Path(td)
        snapshot = {
            "radar_connector_state": "active",
            "radar_sentinel_state": "active",
            "collector_sentinel_state": "active",
            "connector_sha256": "a",
            "native_sha256": "b",
            "messenger_sha256": "c",
        }
        mod.production_snapshot = lambda: dict(snapshot)
        mod.download = lambda revision, path, destination, timeout: destination.write_bytes(b"#!/bin/sh\n")
        mod.run = lambda argv, timeout=30, env=None: types.SimpleNamespace(
            returncode=0,
            stdout=b"COLLECTOR_KNOWLEDGE_RUNTIME_PROBE=PASS\n",
            stderr=b"",
        )
        mod.get_json = lambda path, timeout=10: {"stats": {"documents": 1}}
        req = collector_request("pilot-probe", "gate", "declared-probe")
        rc, result = capture(lambda: mod.do_probe(req, {"revision": "b" * 40}))
        assert rc == 0
        assert_declared_outputs(result, req["task"]["outputs"])
        assert_local_evidence(result)
        assert result["evidence"][0]["details"]["origin"] == "local://collector-knowledge-probe"


def test_verification_broker_stays_fail_closed_for_external_sources() -> None:
    policy = json.loads((ROOT / "dev-hub/config/verification-broker.v1.json").read_text())
    assert policy["evidence"]["unreadable_external_source"] == "NEEDS_INDEPENDENT_CHECK"
    broker = (ROOT / "dev-hub/bin/verification-broker.py").read_text()
    assert 'if report.get("status") != "VERIFIED"' in broker
    assert 'item.get("status") == "UNVERIFIED"' in broker
    assert 'item["status"] = "VERIFIED"' in broker


def test_success_paths_use_materialized_sources() -> None:
    context7 = (ROOT / "dev-hub/adapters/context7-mcp-adapter.py").read_text()
    platform = (ROOT / "dev-hub/adapters/platform-command-adapter.py").read_text()
    collector = (ROOT / "dev-hub/adapters/collector-knowledge-adapter.py").read_text()

    assert "source_path,source_digest=materialize(req,'context7-tools-list',raw)" in context7
    assert "'source':source_path" in context7
    assert 'source_path,source_digest=materialize(req,"technology-watch-consult",payload)' in platform
    assert '"source":source_path' in platform

    for label in (
        "collector-knowledge-status",
        "collector-knowledge-query",
        "collector-knowledge-install",
        "collector-knowledge-probe",
    ):
        assert f'materialize_evidence(request,"{label}"' in collector

    assert '"source":"vps://localhost/collector-knowledge/query"' not in collector
    assert '"source":"vps://localhost/collector-knowledge/install"' not in collector
    assert '"source":"local://collector-knowledge-probe"' not in collector
    assert '"id":"collector-knowledge-status"' not in collector
    assert '"id":"collector-knowledge-query-result"' not in collector
    assert '"id":"collector-knowledge-engine-v1-pilot"' not in collector
    assert '"id":"collector-knowledge-v1-runtime-pilot"' not in collector


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"PASS total={len(tests)}")
