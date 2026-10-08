import json
import subprocess
from pathlib import Path
import unittest


ROOT=Path(__file__).resolve().parents[1]

CFG=ROOT/"config"/"chacha-machine-fabric.v1.json"

POLICY=(
    ROOT
    /"config"
    /"machine-fabric"
    /"security"
    /"security-policy.v1.json"
)

CHECK=(
    ROOT
    /"bin"
    /"chacha-machine-fabric-security-check.py"
)


class MachineFabricSecurityTests(unittest.TestCase):

    def test_candidate_not_active(self):

        d=json.loads(
            CFG.read_text(encoding="utf-8")
        )

        self.assertEqual(
            d["state"],
            "CANDIDATE_NOT_ACTIVE",
        )

        self.assertFalse(
            d["materialization"]["activation_authorized"]
        )

    def test_project_capsule_ttl(self):

        for p in (
            ROOT
            /"config"
            /"machine-fabric"
            /"manifests"
        ).glob("*.json"):

            d=json.loads(
                p.read_text(encoding="utf-8")
            )

            self.assertEqual(
                d["ttl_seconds"],
                3600,
            )

    def test_security_policy(self):

        d=json.loads(
            POLICY.read_text(encoding="utf-8")
        )

        self.assertEqual(
            d["node_identity"]["algorithm"],
            "Ed25519",
        )

        self.assertEqual(
            d["payload_security"][
                "application_encryption_algorithm"
            ],
            "age-X25519",
        )

        self.assertEqual(
            d["transfer_integrity"]["digest_algorithm"],
            "SHA-256",
        )

        self.assertTrue(
            d["secret_handling"][
                "raw_secret_in_mcp_forbidden"
            ]
        )

        self.assertTrue(
            d["local_authorization"][
                "node_agent_may_refuse_control_plane_order"
            ]
        )

    def test_security_gate_script(self):

        p=subprocess.run(
            ["python3",str(CHECK)],
            text=True,
            capture_output=True,
        )

        self.assertEqual(
            p.returncode,
            0,
            p.stdout+p.stderr,
        )

        self.assertIn(
            "MACHINE_FABRIC_SECURITY_POLICY=PASS",
            p.stdout,
        )


if __name__ == "__main__":
    unittest.main()
