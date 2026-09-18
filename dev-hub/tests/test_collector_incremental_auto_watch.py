#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
WATCH=ROOT/"dev-hub/bin/collector-incremental-auto-watch.py"


def executable(path: Path, text: str) -> None:
    path.write_text(text,encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


class CollectorIncrementalAutoWatchTests(unittest.TestCase):
    def test_candidate_verify_commit_then_noop(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            bin_dir=root/"bin"
            bin_dir.mkdir()
            state=root/"state.txt"
            evidence=root/"evidence.json"
            lock=root/"watch.lock"
            portable=root/"portable"
            portable.write_bytes(b"portable-verifier")
            nas_adapter=root/"nas-adapter"
            executable(nas_adapter,"#!/bin/sh\nexit 0\n")
            collector=root/"collector.db"
            collector.write_bytes(b"sqlite-placeholder")

            governor=root/"governor.py"
            executable(governor,'''#!/usr/bin/env python3
import json,os,sys
p=json.load(sys.stdin)
action=p["metadata"]["storage_governor"]["action"]
state=os.environ["MOCK_STATE"]
current=""
try:
    current=open(state).read().strip()
except FileNotFoundError:
    pass
if action=="collector-incremental-package":
    if current=="committed":
        out={"schema":"chacha.dev/task-result/v1","status":"OK","summary":"COLLECTOR_INCREMENTAL_NOOP","outputs":[]}
    else:
        open(state,"w").write("candidate")
        out={
          "schema":"chacha.dev/task-result/v1","status":"OK",
          "summary":"COLLECTOR_INCREMENTAL_CANDIDATE_CREATED",
          "outputs":[{"type":"artifact","id":"projects/wfgg/backups/collector-chain/collector-chain-candidate-000001.json"}]
        }
elif action=="collector-incremental-commit":
    assert current=="candidate",current
    open(state,"w").write("committed")
    out={"schema":"chacha.dev/task-result/v1","status":"OK","summary":"COLLECTOR_INCREMENTAL_COMMITTED","outputs":[]}
else:
    out={"schema":"chacha.dev/task-result/v1","status":"BLOCKED","summary":"unexpected","outputs":[]}
print(json.dumps(out))
''')

            verifier=root/"verifier.py"
            executable(verifier,'''#!/usr/bin/env python3
import json,sys
p=json.load(sys.stdin)
cfg=p["metadata"]["storage_restore_verifier"]
assert cfg["action"]=="verify-incremental-candidate",cfg
assert cfg["candidate_path"].endswith("collector-chain-candidate-000001.json"),cfg
out={
  "schema":"chacha.dev/task-result/v1","status":"OK",
  "summary":"COLLECTOR_INCREMENTAL_RESTORE_VERIFIED",
  "outputs":[{"type":"artifact","id":"collector-chain-verification-000001.json","status":"VERIFIED"}]
}
print(json.dumps(out))
''')

            systemctl=bin_dir/"systemctl"
            executable(systemctl,'''#!/bin/sh
if [ "$1" = "is-active" ]; then
  echo active
  exit 0
fi
if [ "$1" = "show" ]; then
  echo 4242
  exit 0
fi
exit 0
''')

            env=os.environ.copy()
            env.update({
                "PATH":str(bin_dir)+os.pathsep+env.get("PATH",""),
                "CHACHA_STORAGE_GOVERNOR":str(governor),
                "CHACHA_STORAGE_RESTORE_VERIFIER":str(verifier),
                "CHACHA_PORTABLE_RESTORE_VERIFIER":str(portable),
                "CHACHA_NAS_ADAPTER":str(nas_adapter),
                "WFGG_COLLECTOR_DB":str(collector),
                "CHACHA_INCREMENTAL_WATCH_EVIDENCE":str(evidence),
                "CHACHA_INCREMENTAL_WATCH_LOCK":str(lock),
                "WFGG_INCREMENTAL_MAX_ADVANCE":"4",
                "MOCK_STATE":str(state),
            })
            proc=subprocess.run(
                [sys.executable,str(WATCH)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=30,
                env=env,
                check=False,
            )
            self.assertEqual(proc.returncode,0,proc.stdout+"\n"+proc.stderr)
            self.assertIn("INCREMENTAL_PACKAGE_RESULT=COLLECTOR_INCREMENTAL_CANDIDATE_CREATED",proc.stdout)
            self.assertIn("INCREMENTAL_VERIFY_RESULT=COLLECTOR_INCREMENTAL_RESTORE_VERIFIED",proc.stdout)
            self.assertIn("INCREMENTAL_COMMIT_RESULT=COLLECTOR_INCREMENTAL_COMMITTED",proc.stdout)
            self.assertIn("INCREMENTAL_PACKAGE_RESULT=COLLECTOR_INCREMENTAL_NOOP",proc.stdout)
            self.assertIn("COLLECTOR_INCREMENTAL_ADVANCED=1",proc.stdout)
            self.assertIn("COLLECTOR_INCREMENTAL_AUTO_WATCH=PASS",proc.stdout)

            result=json.loads(evidence.read_text(encoding="utf-8"))
            self.assertEqual(result["status"],"PASS")
            self.assertEqual(result["advanced"],1)
            self.assertFalse(result["production_data_mutation"])
            self.assertFalse(result["service_interruption"])
            self.assertEqual(result["collector_pid_before"],"4242")
            self.assertEqual(result["collector_pid_after"],"4242")
            self.assertEqual(state.read_text(),"committed")

    def test_source_orders_verification_before_commit(self):
        text=WATCH.read_text(encoding="utf-8")
        verify=text.index("verified=verify_candidate")
        commit=text.index("committed=commit_candidate")
        self.assertLess(verify,commit)
        self.assertIn("fcntl.LOCK_EX|fcntl.LOCK_NB",text)
        self.assertIn("COLLECTOR_INCREMENTAL_NOOP",text)
        self.assertNotIn("systemctl stop",text)


if __name__=="__main__":
    unittest.main()
