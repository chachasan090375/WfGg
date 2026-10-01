#!/usr/bin/env python3
import json,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
PROFILE=json.loads((ROOT/"dev-hub/config/ha-standby-chachanas.v1.json").read_text())
POLICY=json.loads((ROOT/"dev-hub/config/ha-readiness.v1.json").read_text())

class HAStandbyProfileTest(unittest.TestCase):
    def test_profile_is_active_passive_and_distinct(self):
        self.assertEqual(PROFILE["mode"],"ACTIVE_PASSIVE")
        self.assertEqual(PROFILE["primary"]["role"],"ACTIVE")
        self.assertEqual(PROFILE["standby"]["role"],"PASSIVE")
        self.assertNotEqual(PROFILE["primary"]["node_id"],PROFILE["standby"]["node_id"])
        self.assertNotEqual(PROFILE["primary"]["failure_domain"],PROFILE["standby"]["failure_domain"])

    def test_service_parity_matches_ha_policy(self):
        self.assertEqual(set(PROFILE["requirements"]["required_services"]),set(POLICY["required_services"]))
        self.assertEqual(PROFILE["requirements"]["state_replication"],"SIGNED_CHECKPOINT_PULL")

    def test_failover_is_not_authorized_by_profile(self):
        s=PROFILE["safety"]
        self.assertFalse(s["active_writer"])
        self.assertFalse(s["production_activation_authorized"])
        self.assertFalse(s["failover_authorized"])
        self.assertEqual(s["bastion_failover_state"],"RESERVED_INACTIVE")
        self.assertEqual(s["automatic_external_spend_eur"],0)

    def test_profile_contains_no_secret_material(self):
        raw=json.dumps(PROFILE).lower()
        for token in ("private_key","api_key","password","authorization","bearer "):
            self.assertNotIn(token,raw)
        self.assertEqual(PROFILE["standby"]["node_id"],"chachanas")
        self.assertTrue(PROFILE["standby"]["runtime_root"].endswith("ChaCha-DEV-Standby"))

if __name__=="__main__":
    unittest.main()
