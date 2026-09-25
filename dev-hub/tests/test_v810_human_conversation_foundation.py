#!/usr/bin/env python3
from __future__ import annotations
import importlib.util,json,sys,tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"dev-hub/bin"))

def loadmod(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    mod=importlib.util.module_from_spec(spec);assert spec and spec.loader
    spec.loader.exec_module(mod);return mod

direct=loadmod("v810_direct",ROOT/"dev-hub/bin/direct-operator-service.py")
human=loadmod("v810_human",ROOT/"dev-hub/bin/human-context-engine.py")
conv=loadmod("v810_conv",ROOT/"dev-hub/bin/conversation-interface-agent.py")

policy=json.load(open(ROOT/"dev-hub/config/human-conversation.v1.json"))
assert policy["profile"]["explicit_opt_in_only"] is True
assert policy["profile"]["never_infer_from_voice"] is True
assert policy["profile"]["never_infer_from_accent"] is True
assert policy["profile"]["never_infer_from_location"] is True
assert policy["profile"]["never_infer_protected_traits"] is True
assert policy["emotion_and_interaction"]["diagnosis_forbidden"] is True
assert policy["emotion_and_interaction"]["persistent_psychological_label_forbidden"] is True
assert policy["authority"]["decision_authority"] is False
assert policy["authority"]["execution_authority"] is False

signals=human.explicit_signals("Ça m'énerve, je ne comprends pas et j'ai besoin d'être sûr.")
assert signals["explicit_frustration"] is True
assert signals["explicit_uncertainty"] is True
assert signals["explicit_need_for_reassurance"] is True

profile={
 "preferred_name":"Cédric","preferred_form_of_address":"tu","age_band":"50-59",
 "gender_identity":"homme","cultural_contexts":["France"],"regional_contexts":["Provence"],
 "conversation_register":"familier-direct","humor_level":"léger",
 "unknown_secret_field":"must-not-survive"
}
ctx=human.build(profile,"Super, mais je suis pressé.")
assert ctx["profile"]["preferred_name"]=="Cédric"
assert ctx["profile"]["regional_contexts"]==["Provence"]
assert "unknown_secret_field" not in ctx["profile"]
assert ctx["interaction_signals"]["explicit_urgency"] is True
assert ctx["interaction_signals"]["explicit_enthusiasm"] is True
assert ctx["rules"]["technical_decision_authority"] is False

receipt={
 "schema":"chacha.dev/central-interface-receipt/v1","status":"PASS",
 "project_id":"chacha-dev-platform","next_action":"AWAIT_USER_DIRECTIVE",
 "decision":{"summary":"La préparation est terminée."}
}
reply=conv.compose(receipt,{"request_id":"req-v810"},ctx)
assert reply["central_authority_preserved"] is True
assert reply["decision_modified"] is False
assert reply["human_context_applied"] is True
assert reply["style_directives"]["preferred_name"]=="Cédric"
assert reply["style_directives"]["regional_contexts"]==["Provence"]
assert reply["style_directives"]["no_stereotype_inference"] is True
assert reply["style_directives"]["technical_decision_authority"] is False

base_policy=json.load(open(ROOT/"dev-hub/config/direct-operator.v1.json"))
with tempfile.TemporaryDirectory(prefix="v810-conversation-") as td:
    rt=Path(td)
    p=dict(base_policy);p["runtime_root"]=str(rt/"direct-operator")
    st=direct.State(ROOT,rt,p)
    alice="alice@example.test";bob="bob@example.test"
    saved=st.save_profile(alice,{**profile,"unknown_field":"discard"})
    assert saved["preferred_name"]=="Cédric"
    assert "unknown_field" not in saved
    assert st.profile_view(bob)["schema"]=="chacha.dev/human-conversation-profile/v1"
    assert "preferred_name" not in st.profile_view(bob)

    def response(i,user,assistant):
        return {
          "schema":"chacha.dev/human-interface-response/v1",
          "request_id":f"dor-{i}","project_id":"chacha-dev-platform",
          "session_project_id":"chacha-dev-platform","status":"PASS",
          "next_action":"AWAIT_USER_DIRECTIVE","submitted_user_message":user,
          "submitted_at":f"2026-09-25T22:0{i}:00Z","responded_at":f"2026-09-25T22:0{i}:05Z",
          "conversation":{"message":assistant,"kind":"RESULT","responded_at":f"2026-09-25T22:0{i}:05Z"}
        }
    st.append_turn(alice,response(1,"Salut ChaCha","Salut Cédric."))
    st.append_turn(alice,response(2,"On continue ?","Oui."))
    tl=st.conversation_view(alice,100)
    assert tl["schema"]=="chacha.dev/conversation-timeline/v1"
    assert tl["count"]==2,tl
    assert tl["items"][0]["user"]["text"]=="Salut ChaCha"
    assert tl["items"][1]["assistant"]["text"]=="Oui."
    assert st.conversation_view(bob,100)["count"]==0

ui=(ROOT/"dev-hub/direct-operator-ui/index.html").read_text()
assert 'id="timeline"' in ui
assert "function renderTimeline(payload)" in ui
assert "/api/v1/conversation?limit=100" in ui
assert "/api/v1/human-profile" in ui
assert "ChaCha ne déduit pas ton âge" in ui
assert "👤 Ta demande" in ui and "💨 ChaCha répond" in ui
assert "async function hydrateConversation()" in ui
assert "if(s.last_response)renderConversation(s.last_response)" in ui

android=(ROOT/"android/chacha-direct-operator-widget/app/src/main/java/com/wfgg/chachadev/operator/OperatorActivity.java").read_text()
assert "RecognizerIntent.ACTION_RECOGNIZE_SPEECH" in android
assert policy["voice"]["text_to_speech_provider"]=="UNBOUND"
assert policy["voice"]["barge_in"]=="UNBOUND"

print("CHACHA_DEV_V810_MULTI_TURN_TIMELINE=PASS")
print("CHACHA_DEV_V810_PROFILE_PER_OPERATOR_ISOLATION=PASS")
print("CHACHA_DEV_V810_EXPLICIT_HUMAN_PROFILE=PASS")
print("CHACHA_DEV_V810_EXPLICIT_INTERACTION_SIGNALS=PASS")
print("CHACHA_DEV_V810_NO_DEMOGRAPHIC_INFERENCE=PASS")
print("CHACHA_DEV_V810_CENTRAL_AUTHORITY_PRESERVED=PASS")
print("CHACHA_DEV_V810_CONVERSATIONAL_UI=PASS")
print("CHACHA_DEV_V810_VOICE_INPUT_EXISTING=PASS")
print("CHACHA_DEV_V810_VOICE_OUTPUT_PHASE=FOUNDATION_ONLY")
print("CHACHA_DEV_V810_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
