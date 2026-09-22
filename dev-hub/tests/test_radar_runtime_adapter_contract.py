import importlib.util
import json
import os
import pathlib
import sqlite3
import tempfile
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

    def test_cluster_quality_diagnostic_contract(self):
        req = envelope("cluster-quality-diagnostic", "read")
        radar, err = mod.validate_request(req)
        self.assertIsNone(err)
        self.assertEqual(radar["action"], "cluster-quality-diagnostic")

    def test_cluster_catalog_probe_contract(self):
        req = envelope("cluster-catalog-probe", "read")
        radar, err = mod.validate_request(req)
        self.assertIsNone(err)
        self.assertEqual(radar["action"], "cluster-catalog-probe")

    def test_history_performance_diagnostic_contract(self):
        req = envelope("history-performance-diagnostic", "read")
        radar, err = mod.validate_request(req)
        self.assertIsNone(err)
        self.assertEqual(radar["action"], "history-performance-diagnostic")

    def test_census_frontier_diagnostic_contract(self):
        req = envelope("census-frontier-diagnostic", "read")
        radar, err = mod.validate_request(req)
        self.assertIsNone(err)
        self.assertEqual(radar["action"], "census-frontier-diagnostic")

    def test_seed_scout_route_diagnostic_contract(self):
        req = envelope("seed-scout-route-diagnostic", "read")
        radar, err = mod.validate_request(req)
        self.assertIsNone(err)
        self.assertEqual(radar["action"], "seed-scout-route-diagnostic")

    def test_email_auth_runtime_diagnostic_contract(self):
        req = envelope("email-auth-runtime-diagnostic", "read")
        radar, err = mod.validate_request(req)
        self.assertIsNone(err)
        self.assertEqual(radar["action"], "email-auth-runtime-diagnostic")

    def test_autopilot_progress_diagnostic_contract(self):
        req = envelope("autopilot-progress-diagnostic", "read")
        radar, err = mod.validate_request(req)
        self.assertIsNone(err)
        self.assertEqual(radar["action"], "autopilot-progress-diagnostic")

    def test_sentinel_release_diagnostic_contract(self):
        req = envelope("sentinel-release-diagnostic", "read")
        req["metadata"]["radar_runtime"].update({
            "production_revision": "a" * 40,
            "expected_connector_sha256": "b" * 64,
            "expected_native_sha256": "c" * 64,
        })
        radar, err = mod.validate_request(req)
        self.assertIsNone(err)
        self.assertEqual(radar["action"], "sentinel-release-diagnostic")

    def test_sentinel_release_diagnostic_is_read_only(self):
        source = ADAPTER.read_text(encoding="utf-8")
        self.assertIn('"sentinel-release-diagnostic": "read"', source)
        self.assertIn('"runtime_mutation": False', source)
        self.assertIn('"game_scan_executed": False', source)
        self.assertIn('"collector_mutation": False', source)

    def test_radar_signature_is_stable(self):
        got = mod.radar_signature("GET", "/x", "1", "n", b"", "s" * 32)
        self.assertEqual(len(got), 64)
        self.assertRegex(got, r"^[0-9a-f]{64}$")

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

    def test_cluster_quality_snapshot_ready(self):
        with tempfile.TemporaryDirectory() as td:
            db = pathlib.Path(td) / "collector.db"
            conn = sqlite3.connect(db)
            try:
                conn.execute("CREATE TABLE cycles (id INTEGER PRIMARY KEY, status TEXT, error TEXT, query TEXT)")
                conn.execute("INSERT INTO cycles(status,error,query) VALUES ('SUCCESS','','@federated:972')")
                conn.commit()
            finally:
                conn.close()
            with mock.patch.dict(os.environ, {"WFGG_COLLECTOR_DB": str(db)}, clear=False):
                snap = mod.cluster_quality_snapshot()
            self.assertTrue(snap["quality_gate_ready"])
            self.assertTrue(snap["cycles_table_present"])
            self.assertEqual(snap["missing_columns"], [])
            self.assertEqual(snap["cycle_count"], 1)
            self.assertEqual(snap["federated_cycles"], 1)

    def test_cluster_quality_snapshot_missing_columns(self):
        with tempfile.TemporaryDirectory() as td:
            db = pathlib.Path(td) / "collector.db"
            conn = sqlite3.connect(db)
            try:
                conn.execute("CREATE TABLE cycles (id INTEGER PRIMARY KEY, status TEXT)")
                conn.commit()
            finally:
                conn.close()
            with mock.patch.dict(os.environ, {"WFGG_COLLECTOR_DB": str(db)}, clear=False):
                snap = mod.cluster_quality_snapshot()
            self.assertFalse(snap["quality_gate_ready"])
            self.assertEqual(snap["failure_class"], "CYCLES_REQUIRED_COLUMNS_MISSING")
            self.assertIn("error", snap["missing_columns"])
            self.assertIn("query", snap["missing_columns"])

    def test_autopilot_progress_snapshot_reads_targeted_cycles(self):
        with tempfile.TemporaryDirectory() as td:
            db = pathlib.Path(td) / "collector.db"
            conn = sqlite3.connect(db)
            try:
                conn.execute("""CREATE TABLE cycles (
                    id INTEGER PRIMARY KEY,
                    status TEXT,
                    error TEXT,
                    query TEXT,
                    started_at TEXT,
                    finished_at TEXT
                )""")
                conn.execute("INSERT INTO cycles VALUES (1,'SUCCESS','','@federated:8122','2026-09-20T11:00:00Z','2026-09-20T11:05:00Z')")
                conn.execute("INSERT INTO cycles VALUES (2,'RUNNING','','@federated:954','2026-09-20T11:06:00Z','')")
                conn.commit()
            finally:
                conn.close()
            connector = pathlib.Path(td) / "radar-connector"
            connector.write_bytes(b"test")
            with mock.patch.dict(os.environ, {"WFGG_COLLECTOR_DB": str(db)}, clear=False), \
                 mock.patch.object(mod, "state", return_value="active"), \
                 mock.patch.object(mod, "sha256_file", return_value="a"*64), \
                 mock.patch.object(mod, "CONNECTOR", connector):
                snap = mod.autopilot_progress_snapshot()
            self.assertEqual(snap["latest_cycle_id"], 2)
            self.assertEqual(snap["latest_query"], "@federated:954")
            self.assertEqual(snap["activity_evidence"], "ACTIVE_TARGETED_CYCLE")
            self.assertEqual(len(snap["active_targeted_cycles"]), 1)


    def test_messenger_pilot_install_contract(self):
        req = envelope("messenger-pilot-install", "workspace-write")
        radar, err = mod.validate_request(req)
        self.assertIsNone(err)
        self.assertEqual(radar["action"], "messenger-pilot-install")

    def test_messenger_pilot_install_rejects_production_permission(self):
        req = envelope("messenger-pilot-install", "production-deploy", approval=True)
        _radar, err = mod.validate_request(req)
        self.assertEqual(err, "RADAR_RUNTIME_PERMISSION_REQUIRED:workspace-write")

    def test_messenger_pilot_probe_contract(self):
        req = envelope("messenger-pilot-probe", "read")
        radar, err = mod.validate_request(req)
        self.assertIsNone(err)
        self.assertEqual(radar["action"], "messenger-pilot-probe")

    def test_messenger_pilot_metadata_is_pinned(self):
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

    def test_messenger_pilot_arbitrary_asset_paths_rejected(self):
        radar = {
            "revision": "a" * 40,
            "installer": "../../evil.sh",
            "probe": "radar-vps/probe-v624-messenger-pilot-runtime.sh",
            "expected_messenger_sha256": "b" * 64,
        }
        with self.assertRaisesRegex(ValueError, "RADAR_MESSENGER_INSTALLER_PATH_INVALID"):
            mod.validate_messenger_pilot_metadata(radar, True)

    def test_messenger_pilot_invalid_sha_rejected(self):
        radar = {
            "revision": "a" * 40,
            "installer": "radar-vps/install-v624-messenger-pilot.sh",
            "probe": "radar-vps/probe-v624-messenger-pilot-runtime.sh",
            "expected_messenger_sha256": "short",
        }
        with self.assertRaisesRegex(ValueError, "RADAR_MESSENGER_EXPECTED_SHA_INVALID"):
            mod.validate_messenger_pilot_metadata(radar, True)

    def test_production_runtime_unchanged_guard(self):
        before = {
            "radar_service": "active",
            "radar_sentinel_timer": "active",
            "radar_sentinel_enabled": "enabled",
            "collector_sentinel_timer": "active",
            "connector_sha256": "1" * 64,
            "native_sha256": "2" * 64,
        }
        self.assertTrue(mod.production_runtime_unchanged(before, dict(before)))
        after = dict(before)
        after["connector_sha256"] = "3" * 64
        self.assertFalse(mod.production_runtime_unchanged(before, after))

    def test_messenger_actions_do_not_require_production_window(self):
        source = ADAPTER.read_text(encoding="utf-8")
        install = source[source.index("def do_messenger_pilot_install"):source.index("def do_messenger_pilot_probe")]
        probe = source[source.index("def do_messenger_pilot_probe"):source.index("def do_status")]
        self.assertNotIn("approval_required(", install)
        self.assertNotIn("pilot-open", install)
        self.assertNotIn("systemctl(", install)
        self.assertNotIn("approval_required(", probe)
        self.assertNotIn("pilot-close", probe)
        self.assertNotIn("systemctl(", probe)

    def test_no_shell_true_in_source(self):
        source = ADAPTER.read_text(encoding="utf-8")
        self.assertIn("shell=False", source)
        self.assertNotIn("shell=True", source)
        self.assertNotIn("os.system(", source)


if __name__ == "__main__":
    unittest.main()
