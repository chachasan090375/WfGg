import importlib.util
import os
import pathlib
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
ADAPTER = ROOT / "adapters" / "radar-runtime-adapter.py"

spec = importlib.util.spec_from_file_location("radar_runtime_adapter_v624", ADAPTER)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(mod)


def envelope(action, permission, approval=False):
    return {
        "schema": "chacha.dev/dispatch-envelope/v1",
        "project": "wfgg-radar",
        "transition": "OPERATE->OPERATE",
        "run_id": "v624-test",
        "wave": 1,
        "task": {
            "id": "radar-runtime:" + action,
            "kind": "runtime",
            "description": "V6.24 Messenger pilot contract test",
            "owner_role": "sre-observability",
            "permission": permission,
            "outputs": [],
            "verification": {"mode": "machine"},
        },
        "bindings": [{
            "capability": "radar-pilot-control" if permission == "production-deploy" else "radar-runtime-inspect",
            "provider": "radar-vps-runtime",
            "adapter": "radar-runtime-adapter",
            "fallback_used": False,
            "health_state": "HEALTHY",
        }],
        "policy_context": {
            "resource_class": "light",
            "requires_storage_preflight": False,
            "human_approval_required": approval,
            "approval_id": "production-release" if approval else None,
            "timeout_seconds": 60,
        },
        "workspace": None,
        "metadata": {"radar_runtime": {"action": action}},
    }


class RadarV624MessengerPilotContract(unittest.TestCase):
    def test_install_action_permission(self):
        req = envelope("messenger-pilot-install", "production-deploy", approval=True)
        radar, err = mod.validate_request(req)
        self.assertIsNone(err)
        self.assertEqual(radar["action"], "messenger-pilot-install")

        req["task"]["permission"] = "read"
        _radar, err = mod.validate_request(req)
        self.assertEqual(err, "RADAR_RUNTIME_PERMISSION_REQUIRED:production-deploy")

    def test_probe_action_is_nonproduction_permission(self):
        req = envelope("messenger-pilot-probe", "read")
        radar, err = mod.validate_request(req)
        self.assertIsNone(err)
        self.assertEqual(radar["action"], "messenger-pilot-probe")

    def test_exact_v624_paths_and_sha_are_required(self):
        radar = {
            "revision": "a" * 40,
            "installer": "radar-vps/install-v624-messenger-pilot.sh",
            "probe": "radar-vps/probe-v624-messenger-pilot-runtime.sh",
            "expected_messenger_sha256": "b" * 64,
        }
        got = mod.validate_messenger_pilot_metadata(radar, True)
        self.assertEqual(got, (
            "a" * 40,
            "radar-vps/install-v624-messenger-pilot.sh",
            "radar-vps/probe-v624-messenger-pilot-runtime.sh",
            "b" * 64,
        ))

        bad = dict(radar)
        bad["installer"] = "radar-vps/install-v61910-pilot.sh"
        with self.assertRaisesRegex(ValueError, "RADAR_MESSENGER_INSTALLER_PATH_INVALID"):
            mod.validate_messenger_pilot_metadata(bad, True)

        bad = dict(radar)
        bad["probe"] = "../../probe.sh"
        with self.assertRaisesRegex(ValueError, "RADAR_MESSENGER_PROBE_PATH_INVALID"):
            mod.validate_messenger_pilot_metadata(bad, True)

    def test_production_runtime_unchanged_guard(self):
        before = {
            "connector_sha256": "1" * 64,
            "native_sha256": "2" * 64,
            "radar_service": "active",
            "radar_sentinel_timer": "active",
            "radar_sentinel_enabled": "enabled",
            "collector_sentinel_timer": "active",
        }
        self.assertTrue(mod.production_runtime_unchanged(before, dict(before)))
        after = dict(before)
        after["connector_sha256"] = "3" * 64
        self.assertFalse(mod.production_runtime_unchanged(before, after))
        after = dict(before)
        after["radar_sentinel_timer"] = "inactive"
        self.assertFalse(mod.production_runtime_unchanged(before, after))

    def test_install_requires_human_approval(self):
        req = envelope("messenger-pilot-install", "production-deploy", approval=False)
        self.assertEqual(
            mod.approval_required(req),
            "RADAR_PRODUCTION_APPROVAL_POLICY_MISSING",
        )

    def test_adapter_has_no_arbitrary_messenger_paths(self):
        source = ADAPTER.read_text(encoding="utf-8")
        self.assertIn('MESSENGER_INSTALLER_V624 = "radar-vps/install-v624-messenger-pilot.sh"', source)
        self.assertIn('MESSENGER_PROBE_V624 = "radar-vps/probe-v624-messenger-pilot-runtime.sh"', source)
        self.assertIn('"/opt/wfgg-messenger-pilot"', source)
        self.assertIn('"messenger-pilot-install": "production-deploy"', source)
        self.assertIn('"messenger-pilot-probe": "read"', source)

    @mock.patch.object(mod, "download_asset")
    @mock.patch.object(mod, "run")
    @mock.patch.object(mod, "messenger_pilot_snapshot")
    def test_install_fails_closed_if_production_runtime_changes(self, snap, run, download):
        before = {
            "radar_service": "active",
            "radar_sentinel_timer": "active",
            "radar_sentinel_enabled": "enabled",
            "radar_sentinel_service": "inactive",
            "collector_sentinel_timer": "active",
            "connector_sha256": "1" * 64,
            "native_sha256": "2" * 64,
            "messenger_pilot_sha256": None,
            "messenger_pilot_root": "/opt/wfgg-messenger-pilot",
            "messenger_pilot_binary": "/opt/wfgg-messenger-pilot/bin/wfgg-messenger-outbox",
        }
        after = dict(before)
        after["connector_sha256"] = "9" * 64
        after["messenger_pilot_sha256"] = "a" * 64
        snap.side_effect = [before, after]
        run.return_value = mock.Mock(
            returncode=0,
            stdout=b"RADAR_V624_MESSENGER_PILOT_INSTALL=PASS\n",
            stderr=b"",
        )
        req = envelope("messenger-pilot-install", "production-deploy", approval=True)
        req["metadata"]["radar_runtime"].update({
            "revision": "b" * 40,
            "installer": "radar-vps/install-v624-messenger-pilot.sh",
            "expected_messenger_sha256": "a" * 64,
        })
        with mock.patch.object(mod, "emit", side_effect=lambda payload, code=0: payload):
            out = mod.do_messenger_pilot_install(req, req["metadata"]["radar_runtime"])
        self.assertEqual(out["status"], "FAILED")
        self.assertEqual(out["summary"], "RADAR_PRODUCTION_RUNTIME_CHANGED_BY_MESSENGER_PILOT")

    @mock.patch.object(mod, "download_asset")
    @mock.patch.object(mod, "run")
    @mock.patch.object(mod, "messenger_pilot_snapshot")
    def test_probe_requires_pass_marker_and_preserves_runtime(self, snap, run, download):
        stable = {
            "radar_service": "active",
            "radar_sentinel_timer": "active",
            "radar_sentinel_enabled": "enabled",
            "radar_sentinel_service": "inactive",
            "collector_sentinel_timer": "active",
            "connector_sha256": "1" * 64,
            "native_sha256": "2" * 64,
            "messenger_pilot_sha256": "a" * 64,
            "messenger_pilot_root": "/opt/wfgg-messenger-pilot",
            "messenger_pilot_binary": "/opt/wfgg-messenger-pilot/bin/wfgg-messenger-outbox",
        }
        snap.side_effect = [stable, dict(stable)]
        run.return_value = mock.Mock(
            returncode=0,
            stdout=b"RADAR_V624_MESSENGER_RUNTIME_PROBE=PASS\n",
            stderr=b"",
        )
        req = envelope("messenger-pilot-probe", "read")
        req["metadata"]["radar_runtime"].update({
            "revision": "b" * 40,
            "installer": "radar-vps/install-v624-messenger-pilot.sh",
            "probe": "radar-vps/probe-v624-messenger-pilot-runtime.sh",
            "expected_messenger_sha256": "a" * 64,
        })
        with mock.patch.object(mod, "emit", side_effect=lambda payload, code=0: payload):
            out = mod.do_messenger_pilot_probe(req, req["metadata"]["radar_runtime"])
        self.assertEqual(out["status"], "OK")
        self.assertEqual(out["summary"], "RADAR_MESSENGER_PILOT_PROBE_OK")
        self.assertFalse(out["evidence"][0]["details"]["lastwar_mutation"])
        self.assertFalse(out["evidence"][0]["details"]["network_send"])


if __name__ == "__main__":
    unittest.main()
