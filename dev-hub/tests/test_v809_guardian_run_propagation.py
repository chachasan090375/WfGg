#!/usr/bin/env python3
from __future__ import annotations
import importlib.util,os,tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]

def loadmod(name,path):
    s=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

orch=loadmod("v809_orch",ROOT/"dev-hub/bin/autonomous-project-orchestrator.py")

with tempfile.TemporaryDirectory(prefix="v809-runid-") as td:
    td=Path(td)
    child=td/"child.py"
    out=td/"run.txt"
    child.write_text(
      "import os,sys\nfrom pathlib import Path\n"
      "Path(sys.argv[1]).write_text(os.environ.get('CHACHA_GUARDIAN_RUN_ID',''),encoding='utf-8')\n",
      encoding="utf-8"
    )
    orch._GUARDIAN_CONTEXT.clear()
    orch._GUARDIAN_CONTEXT.update({"enabled":False,"run_id":"bootstrap-test-run-123"})
    orch.run(child,[out])
    assert out.read_text(encoding="utf-8")=="bootstrap-test-run-123"

src=(ROOT/"dev-hub/bin/autonomous-project-orchestrator.py").read_text(encoding="utf-8")
assert 'child_env["CHACHA_GUARDIAN_RUN_ID"]' in src
assert 'env=child_env' in src

council=(ROOT/"dev-hub/bin/architecture-decision-council.py").read_text(encoding="utf-8")
assert 'os.environ.get("CHACHA_GUARDIAN_RUN_ID") or None' in council
assert '"run_id":None' not in council

print("CHACHA_DEV_V809_PARENT_RUN_ID_PROPAGATED=PASS")
print("CHACHA_DEV_V809_CHILD_STAGE_ENVIRONMENT=PASS")
print("CHACHA_DEV_V809_COUNCIL_SUBCOMPONENT_RUN_ID=PASS")
print("CHACHA_DEV_V809_NO_RUNLESS_COUNCIL_GUARDIAN_EVENT=PASS")
print("CHACHA_DEV_V809_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
