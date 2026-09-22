#!/usr/bin/env python3
from __future__ import annotations
import importlib.util,json,tempfile,sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BIN=ROOT/"dev-hub/bin"
CFG=ROOT/"dev-hub/config"
sys.path.insert(0,str(BIN))

spec=importlib.util.spec_from_file_location("grr",BIN/"guardian_remediation_runtime.py")
grr=importlib.util.module_from_spec(spec);spec.loader.exec_module(grr)

with tempfile.TemporaryDirectory(prefix="v620-remediation-") as td:
    idx=Path(td)/"index.json"
    idx.write_text(json.dumps({
      "schema":"chacha.dev/guardian-remediation-index/v1",
      "items":[
        {"directive_id":"remed-warning","target_actor":"run-controller","target_role":"run-controller",
         "project_id":"p1","severity":"WARNING","required_action":"RELOAD_CONTRACT_AND_REPLAN",
         "rule_codes":["X"],"status":"OPEN","created_at":"2026-09-22T20:00:00Z"},
        {"directive_id":"remed-critical","target_actor":"agent:p1:x","target_role":"agent:p1:x",
         "project_id":"p1","severity":"CRITICAL","required_action":"REPLAN_WITHIN_AUTHORIZED_SCOPE",
         "rule_codes":["CAPABILITY_OUTSIDE_AGENT_MISSION"],"status":"DELIVERED","created_at":"2026-09-22T20:01:00Z"}
      ]
    }),encoding="utf-8")
    d=grr.current_directive(actor="run-controller",subject_role="agent:p1:x",project_id="p1",index_path=idx)
    assert d and d["directive_id"]=="remed-critical",d
    ctx=grr.inject_context({"resource_class":"light"},actor="run-controller",subject_role="agent:p1:x",project_id="p1",index_path=idx)
    assert ctx["remediation_directive_id"]=="remed-critical",ctx
    assert ctx["guardian_required_action"]=="REPLAN_WITHIN_AUTHORIZED_SCOPE",ctx

worker=(ROOT/"dev-hub/guardian/worker.js").read_text(encoding="utf-8")
for marker in [
  "remediation_directives","remediation_holds","REMEDIATION_REQUIRED:",
  "REMEDIATION_MAX_ATTEMPTS_EXCEEDED","RESTORE_AUTHORITATIVE_TASK_BINDING",
  "REPLAN_WITHIN_AUTHORIZED_SCOPE","/v1/remediations",
  "/v1/remediations/delivered","corrective_enforcement:true",
  "remediation_retry_limit:3"
]:
    assert marker in worker,marker

policy=json.load(open(CFG/"guardian-runtime-policy.v1.json",encoding="utf-8"))
ce=policy["corrective_enforcement"]
assert ce["enabled"] is True
assert ce["guardian_may_issue_directives"] is True
assert ce["guardian_may_enforce_holds"] is True
assert ce["guardian_may_rewrite_architecture"] is False
assert ce["guardian_may_expand_permissions"] is False
assert ce["responsible_component_must_reapply_rules"] is True
assert ce["corrected_action_must_be_resubmitted"] is True
assert ce["max_failed_correction_attempts"]==3
assert ce["escalation_after_max_attempts"]=="CRITICAL_STOP_REQUIRED"

controller=(BIN/"guardian-remediation-controller.py").read_text(encoding="utf-8")
assert "mark-remediations-delivered" in controller
assert "GUARDIAN_CORRECTIVE_DIRECTIVE_CRITICAL" in controller
assert '"auto_stop_executed":False' in controller
assert "remediation-index.json" in controller

for path in [
  BIN/"run-controller.py",
  BIN/"autonomous-project-orchestrator.py",
  BIN/"technology_watch_runtime.py"
]:
    src=path.read_text(encoding="utf-8")
    assert "guardian_remediation_runtime as grr" in src,path
    assert "grr.inject_context" in src,path

coverage=json.load(open(CFG/"guardian-coverage-manifest.v1.json",encoding="utf-8"))
assert any(x["component_id"]=="guardian-remediation-controller" for x in coverage["expected_components"])

print("CHACHA_DEV_V620_GUARDIAN_CORRECTIVE_DIRECTIVES=PASS")
print("CHACHA_DEV_V620_ENFORCEMENT_HOLDS=PASS")
print("CHACHA_DEV_V620_RESPONSIBLE_COMPONENT_REMINDER_INJECTION=PASS")
print("CHACHA_DEV_V620_CORRECTED_ACTION_RESUBMISSION=PASS")
print("CHACHA_DEV_V620_MAX_REMEDIATION_ATTEMPTS=3")
print("CHACHA_DEV_V620_GUARDIAN_NO_ARCHITECTURE_REWRITE=PASS")
print("CHACHA_DEV_V620_GUARDIAN_NO_PERMISSION_EXPANSION=PASS")
print("CHACHA_DEV_V620_CRITICAL_ESCALATION_STOP_REQUIRED=PASS")
