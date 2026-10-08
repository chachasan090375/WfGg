import importlib.util
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "config" / "chacha-machine-fabric.v1.json"
ROUTER_PATH = ROOT / "bin" / "chacha-machine-fabric-router.py"


def load_router():
    spec = importlib.util.spec_from_file_location(
        "chacha_machine_fabric_router",
        ROUTER_PATH,
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class MachineFabricV04Tests(unittest.TestCase):
    def setUp(self):
        self.registry = json.loads(
            REGISTRY_PATH.read_text(encoding="utf-8")
        )
        self.router = load_router()

    def test_candidate_is_not_active(self):
        self.assertEqual(
            self.registry["state"],
            "CANDIDATE_NOT_ACTIVE",
        )

    def test_remote_mcp_remains_first_route(self):
        self.assertTrue(
            self.registry["governance"]["remote_mcp_first_route"]
        )

    def test_no_arbitrary_shell(self):
        self.assertFalse(
            self.registry["governance"]["arbitrary_shell"]
        )

    def test_required_nodes_exist(self):
        self.assertEqual(
            set(self.registry["nodes"]),
            {
                "chachavps",
                "chachamac",
                "chachanas",
                "chachatel",
            },
        )

    def test_mac_resolution(self):
        result = self.router.resolve(
            self.registry,
            "chachamac",
            "system.identity",
        )

        self.assertEqual(
            result["state"],
            "RESOLVED_NOT_EXECUTED",
        )

        self.assertEqual(
            result["transport"],
            "tailscale",
        )

        self.assertFalse(
            result["arbitrary_shell"]
        )

    def test_unsupported_capability_fails_closed(self):
        with self.assertRaises(self.router.FabricError):
            self.router.resolve(
                self.registry,
                "chachatel",
                "git.tree",
            )


if __name__ == "__main__":
    unittest.main()
