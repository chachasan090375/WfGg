#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import importlib.util
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "bin" / "provider-economics-antigravity-bridge.py"
spec = importlib.util.spec_from_file_location("provider_economics_antigravity_bridge", MODULE_PATH)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class BridgeTests(unittest.TestCase):
    def base(self) -> dict:
        return {
            "schema": mod.SOURCE_SCHEMA,
            "provider_id": "antigravity",
            "status": "BLOCK",
            "cost_class": "quota",
            "observed_at": "2026-09-29T19:00:00Z",
            "automatic_external_spend_eur": 0,
            "quota_available": False,
            "valid_until": "2026-09-29T20:00:00Z",
            "quota_reset_time": "2026-10-04T17:53:18Z",
            "resume_at": "2026-10-04T17:53:18Z",
            "reason_codes": ["ACCOUNT_BASELINE_QUOTA_INSUFFICIENT"],
        }

    def test_stale_source_never_produces_target_attestation(self) -> None:
        source = self.base()
        source["observed_at"] = "2026-09-27T21:10:13Z"
        source["valid_until"] = "2026-09-27T21:30:13Z"
        result = mod.derive(source, now=dt.datetime(2026, 9, 29, 20, 19, tzinfo=dt.timezone.utc))
        self.assertEqual(result["status"], "STALE")
        self.assertEqual(result["reason"], "SOURCE_ATTESTATION_STALE")
        self.assertIsNone(result["target_attestation"])
        self.assertEqual(result["last_known_reset_at"], "2026-10-04T17:53:18Z")

    def test_fresh_exhausted_source_produces_valid_unavailable_attestation(self) -> None:
        source = self.base()
        result = mod.derive(source, now=dt.datetime(2026, 9, 29, 19, 30, tzinfo=dt.timezone.utc))
        self.assertEqual(result["status"], "PASS")
        target = result["target_attestation"]
        self.assertEqual(target["schema"], mod.TARGET_SCHEMA)
        self.assertEqual(target["provider_id"], "agy-gemini-conversation")
        self.assertEqual(target["status"], "PASS")
        self.assertFalse(target["quota_available"])
        self.assertEqual(target["reset_at"], "2026-10-04T17:53:18Z")
        self.assertEqual(target["source_status"], "BLOCK")
        self.assertFalse(result["provider_available"])

    def test_fresh_available_source_preserves_zero_cost(self) -> None:
        source = self.base()
        source["status"] = "PASS"
        source["quota_available"] = True
        source["reason_codes"] = []
        result = mod.derive(source, now=dt.datetime(2026, 9, 29, 19, 30, tzinfo=dt.timezone.utc))
        self.assertEqual(result["status"], "PASS")
        target = result["target_attestation"]
        self.assertTrue(target["quota_available"])
        self.assertEqual(target["automatic_external_spend_eur"], 0)
        self.assertTrue(result["provider_available"])

    def test_nonzero_spend_fails_closed(self) -> None:
        source = self.base()
        source["automatic_external_spend_eur"] = 0.01
        result = mod.derive(source, now=dt.datetime(2026, 9, 29, 19, 30, tzinfo=dt.timezone.utc))
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["reason"], "SOURCE_ATTESTATION_NONZERO_SPEND")
        self.assertIsNone(result["target_attestation"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
