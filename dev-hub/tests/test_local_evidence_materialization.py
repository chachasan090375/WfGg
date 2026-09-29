#!/usr/bin/env python3
from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load(name: str, rel: str):
    path = ROOT / rel
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


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


def test_collector_status_honors_declared_outputs_and_local_evidence() -> None:
    mod = load("collector", "dev-hub/adapters/collector-knowledge-adapter.py")
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
        req = {
            "project": "p",
            "run_id": "r",
            "task": {
                "id": "capability:domain-knowledge-research:collector-knowledge-inspect",
                "outputs": [{"type": "report", "id": "declared-status"}],
            },
        }
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = mod.do_status(req, {})
        assert rc == 0
        result = json.loads(buf.getvalue())
        assert [(x["type"], x["id"]) for x in result["outputs"]] == [("report", "declared-status")]
        assert result["outputs"][0]["status"] == "UNVERIFIED"
        evidence = result["evidence"][0]
        source = Path(evidence["source"])
        assert source.is_absolute() and source.is_file()
        assert evidence["details"]["origin"] == "vps://localhost/collector-knowledge/status"
        actual = "sha256:" + hashlib.sha256(source.read_bytes()).hexdigest()
        assert actual == evidence["digest"]


def test_verification_broker_stays_fail_closed_for_external_sources() -> None:
    policy = json.loads((ROOT / "dev-hub/config/verification-broker.v1.json").read_text())
    assert policy["evidence"]["unreadable_external_source"] == "NEEDS_INDEPENDENT_CHECK"
    broker = (ROOT / "dev-hub/bin/verification-broker.py").read_text()
    assert 'if report.get("status") != "VERIFIED"' in broker
    assert 'if item.get("status") == "UNVERIFIED"' in broker
    assert 'item["status"] = "VERIFIED"' in broker


def test_success_paths_use_materialized_sources() -> None:
    context7 = (ROOT / "dev-hub/adapters/context7-mcp-adapter.py").read_text()
    platform = (ROOT / "dev-hub/adapters/platform-command-adapter.py").read_text()
    collector = (ROOT / "dev-hub/adapters/collector-knowledge-adapter.py").read_text()
    assert "source_path,source_digest=materialize(req,'context7-tools-list',raw)" in context7
    assert "'source':source_path" in context7
    assert 'source_path,source_digest=materialize(req,"technology-watch-consult",payload)' in platform
    assert '"source":source_path' in platform
    assert 'source_path,source_digest=materialize_evidence(request,"collector-knowledge-status",raw)' in collector
    assert 'declared_outputs(request,"Local Knowledge Engine runtime snapshot.")' in collector


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"PASS total={len(tests)}")
