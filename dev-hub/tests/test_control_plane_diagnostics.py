#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "dev-hub/bin/direct-operator-control-plane-gateway.py"
SPEC = importlib.util.spec_from_file_location("control_plane_gateway", MODULE_PATH)
assert SPEC and SPEC.loader
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


class ControlPlaneDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)
        self.repo = self.root / "repo"
        self.runtime = self.root / "runtime"
        (self.repo / "dev-hub/config").mkdir(parents=True)
        (self.runtime / "direct-operator/responses").mkdir(parents=True)
        (self.runtime / "control").mkdir(parents=True)
        (self.runtime / "provider-economics").mkdir(parents=True)
        self.attestation = self.runtime / "provider-economics/agy-conversation-zero-cost.json"
        self.dialogue_policy = self.repo / "dev-hub/config/dialogue-orchestrator.v1.json"
        self.dialogue_policy.write_text(json.dumps({
            "schema": "chacha.dev/dialogue-orchestrator-policy/v1",
            "provider": {
                "id": "agy-gemini-conversation",
                "backend": str(self.root / "missing-backend"),
                "zero_cost_attestation_required": True,
                "allowed_zero_cost_classes": ["free", "owned", "included", "local", "quota"]
            }
        }), encoding="utf-8")
        self.direct_policy = {
            "dialogue_orchestrator": {
                "policy": "dev-hub/config/dialogue-orchestrator.v1.json",
                "zero_cost_attestation": str(self.attestation)
            }
        }
        self.policy = {
            "jobs_root": str(self.runtime / "direct-operator/control-plane-jobs"),
            "session_path": str(self.runtime / "direct-operator/session.json"),
            "allowed_response_root": str(self.runtime / "direct-operator"),
            "emergency_stop_path": str(self.runtime / "control/emergency-stop.json"),
            "zero_cost_refresh": {"local_evidence_path": None}
        }
        (self.runtime / "control/emergency-stop.json").write_text(
            json.dumps({"active": False}), encoding="utf-8"
        )
        self.cp = mod.ControlPlane(self.repo, self.runtime, self.direct_policy, self.policy)

    def tearDown(self):
        self.td.cleanup()

    def write_last_response(self, next_action: str):
        response = {
            "schema": "chacha.dev/human-interface-response/v1",
            "status": "BLOCKED",
            "next_action": next_action,
            "execution_project_id": "chacha-dev-platform",
            "brain_receipt": {"status": "BLOCKED", "decision": {}}
        }
        path = self.runtime / "direct-operator/responses/last.json"
        path.write_text(json.dumps(response), encoding="utf-8")
        (self.runtime / "direct-operator/session.json").write_text(
            json.dumps({"last_response_path": str(path)}), encoding="utf-8"
        )

    def test_missing_attestation_is_diagnostic_not_exception(self):
        result = self.cp.zero_cost()
        self.assertFalse(result["eligible"])
        self.assertEqual(result["status"], "MISSING")
        self.assertEqual(result["reason"], "ZERO_COST_ATTESTATION_MISSING")

    def test_domain_and_zero_cost_are_reported_independently(self):
        self.write_last_response("DOMAIN_EXECUTION_VERIFICATION_REQUIRED")
        report = self.cp.report()
        self.assertEqual(report["mode"], "LOCAL_DETERMINISTIC_NO_PROVIDER")
        self.assertFalse(report["provider_invoked"])
        self.assertFalse(report["technology_watch_invoked"])
        self.assertFalse(report["central_orchestrator_invoked"])
        self.assertEqual(report["domain_execution"]["status"], "BLOCKED")
        self.assertEqual(report["zero_cost"]["status"], "MISSING")
        self.assertIn("DOMAIN_EXECUTION_VERIFICATION_REQUIRED", report["root_causes"])
        self.assertIn("ZERO_COST_ATTESTATION_MISSING", report["root_causes"])

    def test_adapter_block_is_observed_without_invocation(self):
        self.write_last_response("ADAPTER_ENABLEMENT_REQUIRED")
        report = self.cp.report()
        self.assertEqual(report["adapters"]["status"], "BLOCKED")
        self.assertFalse(report["provider_invoked"])
        self.assertEqual(report["automatic_external_spend_eur"], 0)

    def test_refresh_fails_closed_without_verified_local_evidence(self):
        before = self.attestation.exists()
        result = self.cp.refresh_zero_cost()
        after = self.attestation.exists()
        self.assertFalse(before)
        self.assertFalse(after)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["reason"], "LOCAL_ZERO_COST_EVIDENCE_NOT_CONFIGURED")
        self.assertFalse(result["attestation_mutated"])

    def test_control_plane_prefix_is_deterministic(self):
        self.assertTrue(mod.control_request("CONTROL_PLANE_ONLY\nstatus"))
        self.assertTrue(mod.control_request("  control_plane_only diagnose"))
        self.assertFalse(mod.control_request("Go"))

    def test_submit_completes_locally_without_brain(self):
        jid, job = self.cp.submit("CONTROL_PLANE_ONLY", "user@example.test", "chacha-dev-platform")
        self.assertTrue(jid.startswith("cpj-"))
        self.assertEqual(job["state"], "COMPLETE")
        response = job["response"]
        self.assertEqual(response["route"], "LOCAL_CONTROL_PLANE")
        self.assertFalse(response["brain_decision_obtained"])
        self.assertEqual(response["automatic_external_spend_eur"], 0)
        self.assertEqual(response["control_plane"]["mode"], "LOCAL_DETERMINISTIC_NO_PROVIDER")


if __name__ == "__main__":
    unittest.main()
