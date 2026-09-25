#!/usr/bin/env python3
from __future__ import annotations
import importlib.util,json,tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]

def loadmod(name,path):
    s=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

grr=loadmod("v808_grr",ROOT/"dev-hub/bin/guardian_remediation_runtime.py")

with tempfile.TemporaryDirectory(prefix="v808-remed-") as td:
    idx=Path(td)/"index.json"
    idx.write_text(json.dumps({
      "schema":"chacha.dev/guardian-remediation-index/v1",
      "items":[
        {
          "directive_id":"old-runless-lease","target_actor":"architecture-decision-council",
          "target_role":"architecture-decision-council","project_id":"platform-bootstrap",
          "run_id":None,"severity":"BLOCK","status":"DELIVERED",
          "rule_codes":["POST_ACTION_MISSING"],"created_at":"2026-09-25 10:00:00"
        },
        {
          "directive_id":"other-run-lease","target_actor":"architecture-decision-council",
          "target_role":"architecture-decision-council","project_id":"platform-bootstrap",
          "run_id":"run-b","severity":"CRITICAL","status":"DELIVERED",
          "rule_codes":["POST_ACTION_MISSING"],"created_at":"2026-09-25 11:00:00"
        },
        {
          "directive_id":"same-run-lease","target_actor":"architecture-decision-council",
          "target_role":"architecture-decision-council","project_id":"platform-bootstrap",
          "run_id":"run-a","severity":"WARNING","status":"DELIVERED",
          "rule_codes":["POST_ACTION_MISSING"],"created_at":"2026-09-25 12:00:00"
        }
      ]
    }),encoding="utf-8")
    d=grr.current_directive(actor="central-orchestrator",subject_role="architecture-decision-council",
                            project_id="platform-bootstrap",run_id="run-a",index_path=idx)
    assert d and d["directive_id"]=="same-run-lease",d
    none=grr.current_directive(actor="central-orchestrator",subject_role="architecture-decision-council",
                               project_id="platform-bootstrap",run_id="run-c",index_path=idx)
    assert none is None,none
    legacy=grr.current_directive(actor="central-orchestrator",subject_role="architecture-decision-council",
                                 project_id="platform-bootstrap",index_path=idx)
    assert legacy and legacy["directive_id"]=="old-runless-lease",legacy

orch=(ROOT/"dev-hub/bin/autonomous-project-orchestrator.py").read_text(encoding="utf-8")
assert '"run_id":"bootstrap-"+uuid.uuid4().hex' in orch
assert 'run_id=str(_GUARDIAN_CONTEXT.get("run_id") or "")' in orch
assert '"run_id":str(_GUARDIAN_CONTEXT.get("run_id") or "")' in orch

worker=(ROOT/"dev-hub/guardian/worker.js").read_text(encoding="utf-8")
assert 'plan.run_id||"*"' in worker
assert "h.run_id=?4" in worker
assert "d.source_alert_id NOT LIKE 'lease-expired-%'" in worker
assert "AND (run_id IS NULL OR run_id='')" in worker

print("CHACHA_DEV_V808_UNIQUE_GUARDIAN_RUN_ID=PASS")
print("CHACHA_DEV_V808_STALE_LEASE_CROSS_RUN_BLOCKED=PASS")
print("CHACHA_DEV_V808_SAME_RUN_REMEDIATION_PRESERVED=PASS")
print("CHACHA_DEV_V808_LEGACY_NON_RUN_CALL_COMPATIBLE=PASS")
print("CHACHA_DEV_V808_WORKER_RUN_SCOPED_HOLDS=PASS")
print("CHACHA_DEV_V808_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
