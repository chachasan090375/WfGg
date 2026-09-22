#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ADAPTER = ROOT / "dev-hub/adapters/nas-ssh-adapter.py"
FIXTURE = ROOT / "dev-hub/fixtures/nas-ssh-adapter.preflight.v1.json"


class NasSshAdapterContractTests(unittest.TestCase):
    def run_adapter(self, payload: dict, ssh_body: str = "") -> dict:
        with tempfile.TemporaryDirectory() as td:
            mock = Path(td) / "mock-ssh"
            mock.write_text(
                "#!/usr/bin/env python3\n"
                "import sys\n"
                + (ssh_body or "print('Filesystem 1024-blocks Used Available Capacity Mounted on')\nprint('/dev/mock 4000000000 100000000 3900000000 3% /share/CACHEDEV1_DATA')\n"),
                encoding="utf-8",
            )
            mock.chmod(0o755)
            env = os.environ.copy()
            env.update({
                "CHACHA_NAS_SSH_BIN": str(mock),
                "CHACHA_NAS_SCP_BIN": str(mock),
                "CHACHA_NAS_HOST": "chachanas",
                "CHACHA_NAS_ROOT": "/share/CACHEDEV1_DATA/ChaCha-DEV-HUB",
            })
            proc = subprocess.run(
                ["python3", str(ADAPTER)],
                input=json.dumps(payload).encode(),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                check=False,
                timeout=10,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr.decode())
            return json.loads(proc.stdout.decode())

    def fixture(self) -> dict:
        return json.loads(FIXTURE.read_text(encoding="utf-8"))

    def test_preflight_is_ok_with_capacity(self):
        out = self.run_adapter(self.fixture())
        self.assertEqual(out["schema"], "chacha.dev/task-result/v1")
        self.assertEqual(out["status"], "OK")
        self.assertEqual(out["summary"], "NAS_PREFLIGHT_OK")
        self.assertEqual(out["verification"]["status"], "UNVERIFIED")
        self.assertEqual(out["outputs"][0]["id"], "storage-preflight")

    def test_preflight_blocks_when_reserve_not_met(self):
        payload = self.fixture()
        payload["metadata"]["nas_storage"]["need_mb"] = 3_899_999
        out = self.run_adapter(payload)
        self.assertEqual(out["status"], "BLOCKED")
        self.assertEqual(out["summary"], "NAS_PREFLIGHT_INSUFFICIENT_SPACE")

    def test_unknown_action_is_blocked_before_runtime(self):
        payload = self.fixture()
        payload["metadata"]["nas_storage"]["action"] = "delete"
        out = self.run_adapter(payload)
        self.assertEqual(out["status"], "BLOCKED")
        self.assertEqual(out["summary"], "NAS_ACTION_NOT_ALLOWED")

    def test_write_requires_workspace_write_permission(self):
        payload = self.fixture()
        payload["metadata"]["nas_storage"] = {
            "action": "put-file",
            "local_path": "artifact.bin",
            "remote_path": "projects/wfgg/artifacts/artifact.bin",
        }
        out = self.run_adapter(payload)
        self.assertEqual(out["status"], "BLOCKED")
        self.assertEqual(out["summary"], "NAS_PUT_FILE_REQUIRES_WORKSPACE_WRITE")

    def test_write_with_required_approval_blocks_without_approval_id(self):
        payload = self.fixture()
        payload["task"]["permission"] = "workspace-write"
        payload["metadata"]["nas_storage"] = {
            "action": "put-file",
            "local_path": "artifact.bin",
            "remote_path": "projects/wfgg/artifacts/artifact.bin",
        }
        payload["policy_context"]["human_approval_required"] = True
        payload["policy_context"]["approval_id"] = None
        out = self.run_adapter(payload)
        self.assertEqual(out["status"], "BLOCKED")
        self.assertEqual(out["summary"], "NAS_WRITE_APPROVAL_MISSING")

    def test_source_contract_has_no_local_shell(self):
        text = ADAPTER.read_text(encoding="utf-8")
        self.assertIn("shell=False", text)
        self.assertNotIn("shell=True", text)
        self.assertIn("NAS_DESTINATION_ALREADY_EXISTS", text)
        self.assertIn("NAS_PARENT_PREPARE_FAILED", text)
        self.assertIn('["mkdir", "-p", parent]', text)
        self.assertIn("create-only atomic file publication", text)
        self.assertNotIn("rmtree(", text)


if __name__ == "__main__":
    unittest.main()
