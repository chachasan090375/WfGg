import importlib.util
import json
import pathlib
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
ADAPTER = ROOT / "adapters" / "radar-runtime-adapter.py"

spec = importlib.util.spec_from_file_location("radar_runtime_adapter", ADAPTER)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(mod)


def envelope(action="status", permission="read", approval=False):
    return {
        "schema": "chacha.dev/dispatch-envelope/v1",
        "project": "wfgg-radar",
        "transition": "OPERATE->OPERATE",
        "run_id": "test-run",
        "wave": 1,
        "task": {
            "id": f"radar:{action}",
            "kind": "runtime",
            "description": "test",
            "owner_role": "sre-observability",
            "permission": permission,
            "outputs": [],
            "verification": {"mode": "machine"},
        },
        "bindings": [{
            "capability": "radar-runtime-inspect" if permission == "read" else "radar-pilot-control",
            "provider": "radar-vps-runtime",
            "adapter": "radar-runtime-adapter",
            "fallback_used": False,
            "health_state": "HEALTHY",
        }],
        "policy_context": {
            "resource_class": "light",
            "requires_storage_preflight": False,
            "human_approval_required": approval,
            "approval_id": "approval-1" if approval else None,
            "timeout_seconds": 30,
        },
        "workspace": None,
        "metadata": {"radar_runtime": {"action": action}},
    }


class RadarRuntimeAdapterContract(unittest.TestCase):
    def test_status_contract(self):
        req = envelope()
        radar, err = mod.validate_request(req)
        self.assertIsNone(err)
        self.assertEqual(radar["action"], "status")

    def test_write_action_requires_production_deploy_permission(self):
        req = envelope("pilot-open", "read")
        _radar, err = mod.validate_request(req)
        self.assertEqual(err, "RADAR_RUNTIME_PERMISSION_REQUIRED:production-deploy")

    def test_binding_is_required(self):
        req = envelope()
        req["bindings"] = []
        _radar, err = mod.validate_request(req)
        self.assertEqual(err, "RADAR_RUNTIME_BINDING_MISSING")

    def test_approval_is_explicit(self):
        req = envelope("pilot-open", "production-deploy", approval=False)
        self.assertEqual(mod.approval_required(req), "RADAR_PRODUCTION_APPROVAL_POLICY_MISSING")
        req["policy_context"]["human_approval_required"] = True
        self.assertEqual(mod.approval_required(req), "RADAR_PRODUCTION_APPROVAL_MISSING")
        req["policy_context"]["approval_id"] = "approval-1"
        self.assertIsNone(mod.approval_required(req))

    def test_pinned_revision_and_paths(self):
        radar = {
            "revision": "a" * 40,
            "installer": "radar-vps/install-v6191-pilot.sh",
            "probe": "radar-vps/probe-v6191-pilot-runtime.sh",
            "expected_connector_sha256": "b" * 64,
            "expected_native_sha256": "c" * 64,
        }
        got = mod.validate_pilot_metadata(radar, True)
        self.assertEqual(got[0], "a" * 40)

    def test_arbitrary_asset_paths_rejected(self):
        radar = {
            "revision": "a" * 40,
            "installer": "../../evil.sh",
            "probe": "radar-vps/probe-v6191-pilot-runtime.sh",
            "expected_connector_sha256": "b" * 64,
            "expected_native_sha256": "c" * 64,
        }
        with self.assertRaisesRegex(ValueError, "RADAR_INSTALLER_PATH_INVALID"):
            mod.validate_pilot_metadata(radar, True)

    @mock.patch.object(mod, "status_snapshot")
    def test_status_returns_unverified_result(self, snap):
        snap.return_value = {
            "radar_service": "active",
            "radar_sentinel_timer": "active",
            "radar_sentinel_enabled": "enabled",
            "radar_sentinel_service": "inactive",
            "collector_sentinel_timer": "active",
            "connector_sha256": "1" * 64,
            "native_sha256": "2" * 64,
        }
        req = envelope()
        payload = mod.result(req, "OK", "RADAR_RUNTIME_STATUS_OK")
        self.assertEqual(payload["verification"]["status"], "UNVERIFIED")
        self.assertEqual(payload["producer"], "radar-runtime-adapter")

    def test_no_shell_true_in_source(self):
        source = ADAPTER.read_text(encoding="utf-8")
        self.assertIn("shell=False", source)
        self.assertNotIn("shell=True", source)
        self.assertNotIn("os.system(", source)


if __name__ == "__main__":
    unittest.main()
