#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "bin" / "verification-broker.py"
spec = importlib.util.spec_from_file_location("verification_broker", MODULE_PATH)
assert spec and spec.loader
vb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vb)


def verified_report() -> dict:
    return {
        "status": "VERIFIED",
        "method": "independent-agent",
        "verifier": "verification-broker",
        "observed_at": "2026-09-29T20:00:00Z",
    }


def test_verified_report_promotes_only_unverified_outputs() -> None:
    source = {
        "schema": "chacha.dev/task-result/v1",
        "status": "OK",
        "verification": {"status": "UNVERIFIED"},
        "outputs": [
            {
                "type": "domain-capability-result",
                "id": "domain:product:requirements-analysis",
                "status": "UNVERIFIED",
                "reason": "Planning artifact produced; independent verification required.",
            },
            {
                "type": "other",
                "id": "already-blocked",
                "status": "BLOCKED",
                "reason": "keep blocked",
            },
        ],
    }

    out = vb.build_verified_result(source, verified_report())

    assert out is not None
    assert source["outputs"][0]["status"] == "UNVERIFIED"  # no mutation of source
    assert out["verification"]["status"] == "VERIFIED"
    assert out["outputs"][0]["status"] == "VERIFIED"
    assert out["outputs"][0]["reason"] == "Independent verification completed."
    assert out["outputs"][1]["status"] == "BLOCKED"
    assert out["outputs"][1]["reason"] == "keep blocked"


def test_non_verified_report_never_promotes_outputs() -> None:
    source = {
        "schema": "chacha.dev/task-result/v1",
        "status": "OK",
        "outputs": [{"type": "x", "id": "y", "status": "UNVERIFIED"}],
    }
    report = verified_report()
    report["status"] = "NEEDS_INDEPENDENT_CHECK"

    assert vb.build_verified_result(source, report) is None


if __name__ == "__main__":
    test_verified_report_promotes_only_unverified_outputs()
    test_non_verified_report_never_promotes_outputs()
    print("PASS")
