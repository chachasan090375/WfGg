#!/usr/bin/env python3
from __future__ import annotations
import importlib.util,json,tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]

def loadmod(name,path):
    s=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

mod=loadmod("v803_direct",ROOT/"dev-hub/bin/direct-operator-service.py")
policy=mod.load(ROOT/"dev-hub/config/direct-operator.v1.json")

with tempfile.TemporaryDirectory(prefix="v803-session-") as raw:
    runtime=Path(raw)
    st=mod.State(ROOT,runtime,policy)
    response={
      "schema":"chacha.dev/human-interface-response/v1",
      "request_id":"dor-persist-test",
      "project_id":"chacha-dev-platform",
      "session_project_id":"chacha-dev-platform",
      "execution_project_id":"human-interface-request-dor-persist-test",
      "status":"BLOCKED",
      "next_action":"CAPABILITY_BUILD_REQUIRED",
      "submitted_user_message":"Termine le collecteur Dark Intelligence.",
      "conversation":{
        "schema":"chacha.dev/conversation-response/v1",
        "kind":"WARNING",
        "message":"⛔ Je n’ai pas pu terminer la demande : une capacité doit encore être construite."
      }
    }
    rp=st.responses/"dor-persist-test.json"
    mod.atomic(rp,response)
    st.save_session({
      "schema":"chacha.dev/direct-operator-session/v1",
      "active_project":"chacha-dev-platform",
      "last_command":"INSTRUCTION",
      "last_request_id":"dor-persist-test",
      "last_response_path":str(rp),
      "last_response_digest":mod.fd(rp)
    })
    view=st.session_view()
    assert view["active_project"]=="chacha-dev-platform",view
    assert view["last_request_id"]=="dor-persist-test",view
    assert view["last_response"]["submitted_user_message"]=="Termine le collecteur Dark Intelligence.",view
    assert view["last_response"]["conversation"]["kind"]=="WARNING",view
    assert "capacité" in view["last_response"]["conversation"]["message"],view
    assert view["last_response_digest"]==mod.fd(rp),view

    # Never expose an arbitrary path supplied through session metadata.
    outside=runtime/"outside.json"
    mod.atomic(outside,{"secret":"must-not-be-returned"})
    s=st.session();s["last_response_path"]=str(outside);s["last_response_digest"]=mod.fd(outside);st.save_session(s)
    escaped=st.session_view()
    assert "last_response" not in escaped,escaped

ui=(ROOT/"dev-hub/direct-operator-ui/index.html").read_text(encoding="utf-8")
assert "async function hydrateConversation()" in ui
assert "if(s.last_response)renderConversation(s.last_response)" in ui
assert "hydrateConversation();refreshProgress()" in ui
assert "function renderConversation(z)" in ui
assert "submitted_user_message" in ui
assert "👤 Ta demande" in ui
assert "💨 ChaCha répond" in ui
assert "Détails techniques" in ui
assert "if(fromEditor)q.value=''" in ui

print("CHACHA_DEV_V803_LAST_RESPONSE_PERSISTED=PASS")
print("CHACHA_DEV_V803_RELOAD_HYDRATES_CONVERSATION=PASS")
print("CHACHA_DEV_V803_SESSION_PATH_ESCAPE_BLOCKED=PASS")
print("CHACHA_DEV_V803_ACCEPTED_PROMPT_STAYS_CLEARED=PASS")
print("CHACHA_DEV_V803_TECHNICAL_DETAILS_RESTORED=PASS")
print("CHACHA_DEV_V803_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
