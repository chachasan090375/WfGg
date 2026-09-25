#!/usr/bin/env python3
from __future__ import annotations
import importlib.util,json,sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"dev-hub/bin"))

def loadmod(name,path):
    s=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

direct=loadmod("v802_direct",ROOT/"dev-hub/bin/direct-operator-service.py")
gateway=loadmod("v802_gateway",ROOT/"dev-hub/bin/human-interface-gateway.py")
conv=loadmod("v802_conv",ROOT/"dev-hub/bin/conversation-interface-agent.py")

assert direct.stable_project("human-interface-request-dor-abc")=="chacha-dev-platform"
assert direct.stable_project("dor-abc")=="chacha-dev-platform"
assert direct.stable_project("chacha-dev-platform")=="chacha-dev-platform"
assert direct.stable_project("real-project")=="real-project"
assert gateway.stable_project("human-interface-request-dor-abc")=="chacha-dev-platform"

assert direct.should_auto_continue({"status":"PLAN_READY","next_action":"DOMAIN_FACTORIES"}) is True
assert direct.should_auto_continue({"status":"CONTINUED","next_action":"ASSEMBLY"}) is True
assert direct.should_auto_continue({"status":"CONTINUED_PLAN_READY","next_action":"DOMAIN_FACTORIES"}) is True
assert direct.should_auto_continue({"status":"READY","next_action":"DELIVERY"}) is True
assert direct.should_auto_continue({"status":"BLOCKED","next_action":"REPLAN_REQUIRED"}) is False
assert direct.should_auto_continue({"status":"AWAITING_APPROVAL","next_action":"AWAIT_HUMAN_APPROVAL"}) is False
assert direct.should_auto_continue({"status":"PLAN_READY","next_action":"AWAIT_USER_DIRECTIVE"}) is False

intent={"request_id":"dor-test","command":"INSTRUCTION","project_id":"chacha-dev-platform"}
receipt={"status":"PLAN_READY","project_id":"human-interface-request-dor-test","next_action":"DOMAIN_FACTORIES",
         "brain_decision_obtained":True,"evidence_refs":[]}
wrapped=direct.wrap(intent,receipt)
assert wrapped["project_id"]=="chacha-dev-platform"
assert wrapped["execution_project_id"]=="human-interface-request-dor-test"

for status,kind,needle in [
  ("BLOCKED","WARNING","bloquée"),
  ("FAILED","ERROR","pas pu terminer"),
  ("PARTIAL","WARNING","partie du travail"),
  ("SUCCESS","RESULT","succès")
]:
    r=conv.compose({"schema":"chacha.dev/central-interface-receipt/v1","status":status,
                    "project_id":"x","next_action":"AWAIT_USER_DIRECTIVE","decision":{}})
    assert r["kind"]==kind,(status,r)
    assert needle in r["message"],(status,r["message"])

src=(ROOT/"dev-hub/bin/direct-operator-service.py").read_text(encoding="utf-8")
assert '"active_project":project' in src
assert '"active_project":response.get("project_id") or project' not in src
assert 'for step in range(max_steps)' in src
assert 'continuation_steps.append' in src
assert 'submitted_user_message' in src

gw=(ROOT/"dev-hub/bin/human-interface-gateway.py").read_text(encoding="utf-8")
assert '"active_project":project' in gw
assert '"active_project":response.get("project_id") or project' not in gw

ui=(ROOT/"dev-hub/direct-operator-ui/index.html").read_text(encoding="utf-8")
assert "👤 Ta demande" in ui
assert "💨 ChaCha répond" in ui
assert "Détails techniques" in ui
assert "if(fromEditor)q.value=''" in ui
assert "if(fromEditor&&!accepted&&!q.value.trim())q.value=original" in ui
assert "execution_project:z.execution_project_id" in ui

policy=json.loads((ROOT/"dev-hub/config/direct-operator.v1.json").read_text(encoding="utf-8"))
assert policy["auto_continue"]["enabled"] is True
assert policy["auto_continue"]["max_steps"]>=12
assert policy["invariants"]["transient_execution_project_never_becomes_session_project"] is True
assert policy["invariants"]["plan_ready_is_not_terminal"] is True

print("CHACHA_DEV_V802_SESSION_PROJECT_STABILITY=PASS")
print("CHACHA_DEV_V802_PLAN_READY_AUTO_CONTINUE=PASS")
print("CHACHA_DEV_V802_ACCEPTED_PROMPT_CLEARED=PASS")
print("CHACHA_DEV_V802_CONVERSATIONAL_FINAL_RESULT=PASS")
print("CHACHA_DEV_V802_TECHNICAL_DETAILS_SECONDARY=PASS")
print("CHACHA_DEV_V802_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
