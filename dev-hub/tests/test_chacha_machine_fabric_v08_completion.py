#!/usr/bin/env python3

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

CONFIG = ROOT / "config/chacha-machine-fabric.v1.json"
CONTRACT = ROOT / "config/machine-fabric/completion-contract.v1.json"
MANIFESTS = ROOT / "config/machine-fabric/manifests"


class MachineFabricV08CompletionContract(unittest.TestCase):

    def setUp(self):
        self.fabric = json.loads(CONFIG.read_text())
        self.contract = json.loads(CONTRACT.read_text())

        self.nodes = (
            "chachavps",
            "chachatel",
            "chachanas",
            "chachamac",
        )

    def test_completion_phase_is_explicit(self):
        self.assertEqual(
            str(self.fabric["version"]),
            "0.8",
        )

        self.assertEqual(
            self.fabric["node_materialization"]["phase"],
            "V0.8_MATERIALIZED_PENDING_ACTIVATION",
        )

        self.assertEqual(
            self.contract["state"],
            "V0.8_MATERIALIZED_PENDING_ACTIVATION",
        )

        self.assertEqual(
            self.contract["previous_state"],
            "V0.8_PARTIAL",
        )

    def test_exact_four_nodes_are_locally_materialized(self):
        materialization = self.fabric["node_materialization"]

        actual = {
            key
            for key in materialization
            if key != "phase"
        }

        self.assertEqual(
            actual,
            set(self.nodes),
        )

        for node in self.nodes:
            entry = materialization[node]

            self.assertEqual(entry["identity"], "READY")
            self.assertEqual(entry["agent"], "MATERIALIZED")
            self.assertEqual(entry["signed_local_job"], "PASS")
            self.assertIs(entry["service_active"], False)

    def test_node_manifests_require_gate_and_forbid_activation(self):
        for node in self.nodes:
            p = MANIFESTS / f"{node}-node.json"
            manifest = json.loads(p.read_text())

            self.assertTrue(
                manifest["materialization_gate_required"]
            )

            self.assertIs(
                manifest["production_activation_authorized"],
                False,
            )

    def test_contract_preserves_pending_activation_boundary(self):
        requirements = self.contract["requirements"]
        governance = self.contract["governance"]

        self.assertEqual(
            requirements["umg_status"],
            "REGISTERED_PENDING_ACTIVATION",
        )

        self.assertIs(
            requirements["production_activation_authorized"],
            False,
        )

        self.assertIs(
            governance["activation_is_separate_transition"],
            True,
        )

        self.assertIs(
            governance["automatic_activation_authorized"],
            False,
        )

        self.assertIs(
            governance["production_change_authorized"],
            False,
        )

        self.assertIs(
            governance["service_start_authorized"],
            False,
        )

        self.assertEqual(
            governance["automatic_external_spend_eur"],
            0,
        )

    def test_contract_exact_node_set(self):
        self.assertEqual(
            self.contract["required_nodes"],
            list(self.nodes),
        )


if __name__ == "__main__":
    unittest.main()
