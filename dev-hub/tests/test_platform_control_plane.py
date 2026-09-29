#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "bin" / "direct-operator-control-plane-gateway.py"
spec = importlib.util.spec_from_file_location("control_plane_gateway", MODULE_PATH)
assert spec and spec.loader
cpmod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cpmod)


class ControlPlaneTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.repo = root / "repo"
        self.runtime = root / "runtime"
        (self.repo / "config").mkdir(parents=True)
        (self.runtime / "direct-operator" / "responses").mkdir(parents=True)
        (self.runtime / "control").mkdir(parents=True)
        (self.runtime / "provider-economics").mkdir(parents=True)
        backend = root / "agy-dev"
        backend.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        os.chmod(backend, 0o755)
        self.dialogue_policy = {
            "schema": "chacha.dev/dialogue-orchestrator-policy/v1",
            "provider": {
                "id": "agy-gemini-conversation",
                "backend": str(backend),
                "zero_cost_attestation_required": True,
                "allowed_zero_cost_classes": ["free", "owned", "included", "local", "quota"],
            },
        }
        (self.repo / "config" / "dialogue.json").write_text(json.dumps(self.dialogue_policy), encoding="utf-8")
        self.attestation = self.runtime / "provider-economics" / "agy-conversation-zero-cost.json"
        self.direct_policy = {
            "dialogue_orchestrator": {
                "policy": "config/dialogue.json",
                "zero_cost_attestation": str(self.attestation),
            }
        }
        self.policy = {
            "schema": cpmod.POLICY_SCHEMA,
            "jobs_root": str(self.runtime / "direct-operator" / "control-plane-jobs"),
            "session_path": str(self.runtime / "direct-operator" / "session.json"),
            "allowed_response_root": str(self.runtime / "direct-operator"),
            "emergency_stop_path": str(self.runtime / "control" / "emergency-stop.json"),
            "zero_cost_refresh": {"local_evidence_path": None},
        }
        (self.runtime / "control" / "emergency-stop.json").write_text(json.dumps({"active": False}), encoding="utf-8")
        self.control = cpmod.ControlPlane(self.repo, self.runtime, self.direct_policy, self.policy)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def write_last_response(self, next_action: str) -> None:
        response = self.runtime / "direct-operator" / "responses" / "last.json"
        response.write_text(json.dumps({
            "status": "BLOCKED",
            "next_action": next_action,
            "execution_project_id": "chacha-dev-platform",
            "brain_receipt": {"status": "BLOCKED", "decision": {"source": "test"}},
        }), encoding="utf-8")
        (self.runtime / "direct-operator" / "session.json").write_text(json.dumps({"last_response_path": str(response)}), encoding="utf-8")

    def test_control_prefix_is_explicit(self) -> None:
        self.assertTrue(cpmod.control_request("CONTROL_PLANE_ONLY\nstatus"))
        self.assertTrue(cpmod.control_request("  control_plane_only diagnostics"))
        self.assertFalse(cpmod.control_request("diagnose the platform"))

    def test_missing_attestation_does_not_crash(self) -> None:
        report = self.control.report()
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["zero_cost"]["status"], "MISSING")
        self.assertEqual(report["zero_cost"]["reason"], "ZERO_COST_ATTESTATION_MISSING")
        self.assertFalse(report["provider_invoked"])
        self.assertFalse(report["central_orchestrator_invoked"])
        self.assertEqual(report["automatic_external_spend_eur"], 0)

    def test_domain_block_and_zero_cost_missing_are_reported_independently(self) -> None:
        self.write_last_response("DOMAIN_EXECUTION_VERIFICATION_REQUIRED")
        report = self.control.report()
        self.assertEqual(report["domain_execution"]["status"], "BLOCKED")
        self.assertEqual(report["domain_execution"]["reason"], "DOMAIN_EXECUTION_VERIFICATION_REQUIRED")
        self.assertEqual(report["zero_cost"]["reason"], "ZERO_COST_ATTESTATION_MISSING")
        self.assertIn("DOMAIN_EXECUTION_VERIFICATION_REQUIRED", report["root_causes"])
        self.assertIn("ZERO_COST_ATTESTATION_MISSING", report["root_causes"])

    def test_adapter_block_is_observed_without_invoking_adapter(self) -> None:
        self.write_last_response("ADAPTER_ENABLEMENT_REQUIRED")
        report = self.control.report()
        self.assertEqual(report["adapters"]["status"], "BLOCKED")
        self.assertEqual(report["adapters"]["reason"], "ADAPTER_ENABLEMENT_REQUIRED")
        self.assertFalse(report["technology_watch_invoked"])

    def test_valid_quota_attestation_is_eligible(self) -> None:
        valid_until = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat().replace("+00:00", "Z")
        self.attestation.write_text(json.dumps({
            "schema": cpmod.ATTEST_SCHEMA,
            "provider_id": "agy-gemini-conversation",
            "status": "PASS",
            "cost_class": "quota",
            "quota_available": True,
            "valid_until": valid_until,
            "automatic_external_spend_eur": 0,
        }), encoding="utf-8")
        zero = self.control.zero_cost()
        self.assertEqual(zero["status"], "PASS")
        self.assertTrue(zero["eligible"])
        self.assertEqual(zero["reason"], "ZERO_COST_ATTESTED")

    def test_exhausted_quota_is_not_eligible(self) -> None:
        valid_until = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat().replace("+00:00", "Z")
        self.attestation.write_text(json.dumps({
            "schema": cpmod.ATTEST_SCHEMA,
            "provider_id": "agy-gemini-conversation",
            "status": "PASS",
            "cost_class": "quota",
            "quota_available": False,
            "valid_until": valid_until,
            "reset_at": "2026-10-04T17:53:18Z",
            "automatic_external_spend_eur": 0,
        }), encoding="utf-8")
        zero = self.control.zero_cost()
        self.assertEqual(zero["status"], "EXHAUSTED")
        self.assertFalse(zero["eligible"])
        self.assertEqual(zero["reset_at"], "2026-10-04T17:53:18Z")

    def test_refresh_fails_closed_without_verified_local_evidence(self) -> None:
        result = self.control.refresh_zero_cost()
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["reason"], "LOCAL_ZERO_COST_EVIDENCE_NOT_CONFIGURED")
        self.assertFalse(result["attestation_mutated"])
        self.assertFalse(self.attestation.exists())

    def test_submit_produces_local_completed_job(self) -> None:
        jid, job = self.control.submit("CONTROL_PLANE_ONLY status", "user@example.test", "chacha-dev-platform")
        self.assertTrue(jid.startswith("cpj-"))
        self.assertEqual(job["state"], "COMPLETE")
        response = job["response"]
        self.assertEqual(response["route"], "LOCAL_CONTROL_PLANE")
        self.assertFalse(response["brain_decision_obtained"])
        self.assertEqual(response["automatic_external_spend_eur"], 0)
        self.assertTrue((self.control.jobs / (jid + ".json")).is_file())

    def test_session_cannot_escape_direct_operator_runtime(self) -> None:
        outside = Path(self.tmp.name) / "outside.json"
        outside.write_text(json.dumps({"next_action": "ADAPTER_ENABLEMENT_REQUIRED"}), encoding="utf-8")
        (self.runtime / "direct-operator" / "session.json").write_text(json.dumps({"last_response_path": str(outside)}), encoding="utf-8")
        self.assertIsNone(self.control.last_response())


if __name__ == "__main__":
    unittest.main(verbosity=2)
