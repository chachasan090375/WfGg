#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
ADAPTER_PATH=ROOT/"dev-hub/adapters/storage-restore-verifier-adapter.py"

spec=importlib.util.spec_from_file_location("storage_restore_verifier",ADAPTER_PATH)
mod=importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)


class RestoreVerifierContractTests(unittest.TestCase):
    def base_request(self):
        return {
            "schema":"chacha.dev/dispatch-envelope/v1",
            "project":"wfgg-radar",
            "transition":"collector-restore-verification",
            "run_id":"restore-test-001",
            "wave":1,
            "task":{
                "id":"collector-restore-verification",
                "kind":"verification",
                "description":"Verify Collector MASTER restore.",
                "owner_role":"storage-restore-verifier",
                "permission":"workspace-write",
                "outputs":[{"type":"gate","id":"collector-restore-proof"}],
                "verification":{"required":True,"mode":"machine"}
            },
            "bindings":[{
                "capability":"storage-governance",
                "provider":"storage-restore-verifier",
                "adapter":"storage-restore-verifier-adapter",
                "fallback_used":False,
                "health_state":"contract-test"
            }],
            "policy_context":{
                "resource_class":"heavy",
                "requires_storage_preflight":False,
                "human_approval_required":False,
                "approval_id":None,
                "timeout_seconds":1800
            },
            "workspace":"/opt/chacha-dev",
            "metadata":{"storage_restore_verifier":{"action":"verify-master-anchor"}}
        }

    def test_contract_accepts_workspace_write(self):
        cfg,error=mod.validate_request(self.base_request())
        self.assertIsNone(error)
        self.assertEqual(cfg["action"],"verify-master-anchor")

    def test_contract_rejects_read_only(self):
        req=self.base_request()
        req["task"]["permission"]="read"
        _,error=mod.validate_request(req)
        self.assertEqual(error,"RESTORE_VERIFIER_REQUIRES_WORKSPACE_WRITE")

    def test_probe_evaluation_passes_expected_baseline(self):
        rows={
            "cycle_baseline":1171660,
            "cycle_changes":96024,
            "cycle_seen":470620,
            "cycles":35,
            "identity_coverage":0,
            "master_players":27753,
            "masters":1,
            "observations":126611,
            "player_aliases":56695,
            "player_identity":56645,
            "players":56645,
        }
        probe={
            "integrity":"ok",
            "tables":mod.EXPECTED_TABLES,
            "row_counts":rows,
            "max_cycle":35,
            "observations":{"observed_at":"2026-09-18T05:18:47.18986397Z","id":126611},
            "masters":{"created_at":"2026-09-11T22:23:30.164682Z","id":1},
        }
        expected={
            "baseline_cycle":35,
            "observations":{"observed_at":"2026-09-18T05:18:47.18986397Z","id":126611},
            "masters":{"created_at":"2026-09-11T22:23:30.164682Z","id":1},
        }
        self.assertEqual(mod.verify_probe(probe,rows,expected),[])

    def test_probe_evaluation_detects_mismatch(self):
        rows={t:0 for t in mod.EXPECTED_TABLES}
        probe={
            "integrity":"ok",
            "tables":mod.EXPECTED_TABLES,
            "row_counts":dict(rows),
            "max_cycle":35,
            "observations":{"observed_at":"x","id":1},
            "masters":{"created_at":"y","id":1},
        }
        expected={
            "baseline_cycle":35,
            "observations":{"observed_at":"x","id":1},
            "masters":{"created_at":"y","id":1},
        }
        altered=dict(rows); altered["players"]=1
        errors=mod.verify_probe(probe,altered,expected)
        self.assertIn("ROW_COUNTS_MISMATCH",errors)

    def test_source_safety_invariants(self):
        text=ADAPTER_PATH.read_text(encoding="utf-8")
        self.assertIn("independent-restore",text)
        self.assertIn("PRAGMA integrity_check",text)
        self.assertIn("sandbox_deleted_after_verification",text)
        self.assertIn("production_data_mutation",text)
        self.assertIn("rm -f",text)
        self.assertNotIn("rm -rf",text)
        self.assertNotIn("systemctl stop",text)
        self.assertNotIn("storage-governor-adapter.py",text)


if __name__=="__main__":
    unittest.main()
