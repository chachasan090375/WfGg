#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "bin" / "direct-operator-control-plane-gateway.py"
spec = importlib.util.spec_from_file_location("control_plane_gateway", MODULE_PATH)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class ControlPlaneDiagnosticsTests(unittest.TestCase):
    def make_plane(self, root: Path, *, refresh: dict | None = None):
        repo = root / "repo"
        runtime = root / "runtime"
        (repo / "dev-hub/config").mkdir(parents=True, exist_ok=True)
        runtime.mkdir(parents=True, exist_ok=True)
        dialogue_policy = {
            "schema": "chacha.dev/dialogue-orchestrator-policy/v1",
            "provider": {
                "id": "agy-gemini-conversation",
                "backend": str(root / "missing-backend"),
                "zero_cost_attestation_required": True,
                "allowed_zero_cost_classes": ["free", "owned", "included", "local", "quota"],
            },
        }
        (repo / "dev-hub/config/dialogue-orchestrator.v1.json").write_text(
            json.dumps(dialogue_policy), encoding="utf-8"
        )
        direct_policy = {
            "authentication": {"authorized_users_file": str(root / "authorized.json")},
            "dialogue_orchestrator": {
                "policy": "dev-hub/config/dialogue-orchestrator.v1.json",
                "zero_cost_attestation": str(runtime / "provider-economics/agy-conversation-zero-cost.json"),
            },
        }
        policy = {
            "schema": mod.POLICY_SCHEMA,
            "jobs_root": str(runtime / "direct-operator/control-plane-jobs"),
            "session_path": str(runtime / "direct-operator/session.json"),
            "emergency_stop_path": str(runtime / "control/emergency-stop.json"),
            "allowed_response_root": str(runtime / "direct-operator"),
        }
        if refresh is not None:
            policy["zero_cost_refresh"] = refresh
        return mod.ControlPlane(repo, runtime, direct_policy, policy), repo, runtime

    def test_missing_attestation_is_reported_without_crash(self):
        with tempfile.TemporaryDirectory() as td:
            plane, _, _ = self.make_plane(Path(td))
            report = plane.report()
            self.assertEqual(report["status"], "PASS")
            self.assertEqual(report["mode"], "LOCAL_DETERMINISTIC_NO_PROVIDER")
            self.assertFalse(report["provider_invoked"])
            self.assertFalse(report["technology_watch_invoked"])
            self.assertFalse(report["central_orchestrator_invoked"])
            self.assertEqual(report["zero_cost"]["status"], "MISSING")
            self.assertEqual(report["zero_cost"]["reason"], "ZERO_COST_ATTESTATION_MISSING")
            self.assertIn("ZERO_COST_ATTESTATION_MISSING", report["root_causes"])

    def test_domain_block_and_missing_attestation_are_independent_observations(self):
        with tempfile.TemporaryDirectory() as td:
            plane, _, runtime = self.make_plane(Path(td))
            responses = runtime / "direct-operator/responses"
            responses.mkdir(parents=True, exist_ok=True)
            response_path = responses / "prior.json"
            response_path.write_text(json.dumps({
                "schema": "chacha.dev/human-interface-response/v1",
                "status": "BLOCKED",
                "next_action": "DOMAIN_EXECUTION_VERIFICATION_REQUIRED",
                "execution_project_id": "chacha-dev-platform",
                "brain_receipt": {"status": "BLOCKED", "decision": {"source": "test"}},
            }), encoding="utf-8")
            plane.session_path.parent.mkdir(parents=True, exist_ok=True)
            plane.session_path.write_text(json.dumps({"last_response_path": str(response_path)}), encoding="utf-8")
            report = plane.report()
            self.assertEqual(report["domain_execution"]["status"], "BLOCKED")
            self.assertEqual(report["domain_execution"]["reason"], "DOMAIN_EXECUTION_VERIFICATION_REQUIRED")
            self.assertEqual(report["zero_cost"]["reason"], "ZERO_COST_ATTESTATION_MISSING")
            self.assertIn("DOMAIN_EXECUTION_VERIFICATION_REQUIRED", report["root_causes"])
            self.assertIn("ZERO_COST_ATTESTATION_MISSING", report["root_causes"])

    def test_refresh_without_local_evidence_is_fail_closed(self):
        with tempfile.TemporaryDirectory() as td:
            plane, _, _ = self.make_plane(Path(td))
            result = plane.refresh_zero_cost()
            self.assertEqual(result["status"], "BLOCKED")
            self.assertEqual(result["reason"], "LOCAL_ZERO_COST_EVIDENCE_NOT_CONFIGURED")
            self.assertFalse(result["attestation_mutated"])
            self.assertFalse(plane.attestation_path.exists())

    def test_refresh_rejects_unverified_local_evidence_without_mutation(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            evidence = root / "evidence.json"
            evidence.write_text(json.dumps({
                "schema": mod.ATTEST_SCHEMA,
                "provider_id": "agy-gemini-conversation",
                "status": "PASS",
                "cost_class": "quota",
                "quota_available": True,
                "automatic_external_spend_eur": 0,
                "verified": False,
            }), encoding="utf-8")
            plane, _, _ = self.make_plane(root, refresh={"local_evidence_path": str(evidence)})
            result = plane.refresh_zero_cost()
            self.assertEqual(result["status"], "BLOCKED")
            self.assertEqual(result["reason"], "LOCAL_ZERO_COST_EVIDENCE_INVALID")
            self.assertFalse(result["attestation_mutated"])
            self.assertFalse(plane.attestation_path.exists())

    def test_control_plane_prefix_is_explicit(self):
        self.assertTrue(mod.control_request("CONTROL_PLANE_ONLY\nstatus"))
        self.assertTrue(mod.control_request("  control_plane_only inspect"))
        self.assertFalse(mod.control_request("Technology Watch Antigravity vs OpenCode"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
