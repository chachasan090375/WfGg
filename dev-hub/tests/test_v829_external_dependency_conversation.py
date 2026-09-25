#!/usr/bin/env python3
from __future__ import annotations
import importlib.util,sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"dev-hub/bin"))

def loadmod(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    mod=importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod

central=loadmod("v829_central",ROOT/"dev-hub/bin/central-interface-controller.py")
conversation=loadmod("v829_conversation",ROOT/"dev-hub/bin/conversation-interface-agent.py")
direct=loadmod("v829_direct",ROOT/"dev-hub/bin/direct-operator-service.py")

stderr="""Traceback (most recent call last):
RuntimeError: GUARDIAN_STAGE_UNAVAILABLE:specification-compiler.py:UNAVAILABLE
"""
status,next_action,decision=central.classify_orchestrator_failure("",stderr)
assert status=="AWAITING_EXTERNAL_CONDITION",(status,next_action,decision)
assert next_action=="RETRY_WHEN_GUARDIAN_AVAILABLE",(status,next_action,decision)
assert decision["external_dependency"]=="GUARDIAN",decision
assert decision["reason"]=="GUARDIAN_UNAVAILABLE_FAIL_CLOSED",decision
assert decision["authority_bypass"] is False,decision
assert decision["retryable"] is True,decision

receipt=central.make_receipt(
    "INSTRUCTION","chacha-dev-platform",status,next_action,[],decision
)
reply=conversation.compose(receipt,{"request_id":"v829-test"})
assert reply["kind"]=="WARNING",reply
assert "cerveau central a bien reçu" in reply["message"].casefold(),reply
assert "guardian" in reply["message"].casefold(),reply
assert "sans contourner" in reply["message"].casefold(),reply
assert "de nouveau disponible" in reply["message"].casefold(),reply
assert "n’arrive pas à joindre correctement le cerveau central" not in reply["message"],reply
assert reply["requires_user_response"] is False,reply
assert direct.should_auto_continue(receipt) is False,receipt

status2,next2,decision2=central.classify_orchestrator_failure("","network timeout")
assert status2=="BRAIN_UNAVAILABLE",(status2,next2,decision2)
assert next2=="RETRY_WHEN_BRAIN_AVAILABLE",(status2,next2,decision2)

print("CHACHA_DEV_V829_GUARDIAN_UNAVAILABLE_CLASSIFICATION=PASS")
print("CHACHA_DEV_V829_EXTERNAL_CONDITION_TERMINAL=PASS")
print("CHACHA_DEV_V829_CONVERSATION_EXPLAINS_GUARDIAN=PASS")
print("CHACHA_DEV_V829_NO_GUARDIAN_BYPASS=PASS")
print("CHACHA_DEV_V829_GENERIC_BRAIN_UNAVAILABLE_PRESERVED=PASS")
print("CHACHA_DEV_V829_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
