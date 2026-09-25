#!/usr/bin/env python3
from __future__ import annotations
import importlib.util,json,tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]

def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

def loadmod(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    return mod

dark_policy=load(ROOT/"dev-hub/config/dark-intelligence-agent.v1.json")
conv_policy=load(ROOT/"dev-hub/config/conversation-interface-agent.v1.json")
loc_policy=load(ROOT/"dev-hub/config/professional-localization.v1.json")
routing=load(ROOT/"dev-hub/config/agent-routing.v1.json")
domains=load(ROOT/"dev-hub/config/domain-orchestration.v1.json")
direct=load(ROOT/"dev-hub/config/direct-operator.v1.json")
progress=load(ROOT/"dev-hub/config/progress-reporting.v1.json")

assert dark_policy["collection"]["network_isolation_required"] is True
assert dark_policy["collection"]["central_vps_direct_tor_access_forbidden"] is True
assert dark_policy["collection"]["read_only"] is True
assert dark_policy["collection"]["purchases_forbidden"] is True
assert dark_policy["collection"]["contact_or_posting_forbidden"] is True
assert dark_policy["collection"]["payload_execution_forbidden"] is True
assert dark_policy["verification_pipeline"]["technology_watch_evaluation_required"] is True
assert dark_policy["verification_pipeline"]["source_reputation"]=="dev-hub/bin/technology_source_reputation.py"
assert dark_policy["verification_pipeline"]["logician_falsification"]=="dev-hub/bin/technology_watch_logician.py"
assert dark_policy["verification_pipeline"]["unverified_source_never_becomes_fact"] is True

dark=loadmod("v800_dark",ROOT/"dev-hub/bin/dark-intelligence-agent.py")
obs={
  "schema":"chacha.dev/dark-intelligence-observation/v1",
  "source_class":"tor_onion","source_ref":"http://examplehiddenservice.onion/post/1",
  "source_id":"pilot-onion-source","network_isolated":True,"network_route":"TOR_ISOLATED_CAPSULE",
  "used_platform_credentials":False,"purchase_performed":False,"contact_or_post_performed":False,
  "payload_executed":False,"claims":["A claimed data leak exists"],"publisher":"unknown-onion-source",
  "observed_at":"2026-09-25T09:00:00Z","release_date":"2026-09-25T09:00:00Z"
}
dossier=dark.normalize(obs,dark_policy)
assert dossier["direct_fact_promotion_allowed"] is False
assert dossier["direct_decision_authority"] is False
assert dossier["raw_source_authority"]=="ADVISORY_ONLY"
assert dossier["verification_handoff"]["technology_watch_evaluation_required"] is True
assert dossier["technology_dossier"]["evidence"][0]["verified"] is False

# Prove that the same Technology Watch truth engine receives the normalized source.
import sys
sys.path.insert(0,str(ROOT/"dev-hub/bin"))
import technology_truth_scoring as tts
import technology_watch_logician as twl
truth_policy=load(ROOT/"dev-hub/config/technology-truth-scoring.v1.json")
rep=load(ROOT/"dev-hub/config/technology-source-reputation.v1.json")
logic_policy=load(ROOT/"dev-hub/config/technology-watch-logician.v1.json")
challenge=twl.build_challenge(dossier["technology_dossier"],logic_policy)
score=tts.evaluate(dossier["technology_dossier"],truth_policy,rep,challenge)
assert score["technology_watch_owns_final_evidence_score"] is True
assert score["logician_challenge_summary"]["available"] is True
assert score["automatic_selection_allowed"] is False
assert score["recommendation_class"]!="ADOPT"
assert score["evidence_graph"]["nodes"]

conv=loadmod("v800_conv",ROOT/"dev-hub/bin/conversation-interface-agent.py")
receipt={
  "schema":"chacha.dev/central-interface-receipt/v1","status":"PASS","project_id":"chacha-dev-platform",
  "next_action":"AWAIT_USER_DIRECTIVE","brain_decision_obtained":True,
  "decision":{"summary":"La préparation V8.0 est terminée."}
}
reply=conv.compose(receipt,{"request_id":"req-v800"})
assert reply["message"].startswith("La préparation V8.0")
assert reply["status"]=="PASS"
assert reply["next_action"]=="AWAIT_USER_DIRECTIVE"
assert reply["central_authority_preserved"] is True
assert reply["decision_modified"] is False
assert reply["requires_user_response"] is True

direct_src=(ROOT/"dev-hub/bin/direct-operator-service.py").read_text(encoding="utf-8")
ui=(ROOT/"dev-hub/direct-operator-ui/index.html").read_text(encoding="utf-8")
assert "conversation-interface-agent.py" in direct_src
assert 'response["conversation"]=conversation' in direct_src
assert "cv.message||z.message" in ui
assert direct["conversation"]["decision_authority"] is False
assert any(x["id"]=="conversation-interface-agent" for x in progress["modules"])

dark_role=routing["roles"]["dark-intelligence-agent"]
assert dark_role["default_risk"]=="high"
assert "technology-watch-validation-handoff" in dark_role["capabilities"]
dark_rules=[x for x in routing["routing_rules"] if x.get("primary_role")=="dark-intelligence-agent"]
assert dark_rules and "technology-watch-agent" in dark_rules[-1]["review_roles"] and "bastion" in dark_rules[-1]["review_roles"]
assert domains["threat-intelligence"]["roles"]==["dark-intelligence-agent","technology-watch-agent"]

trans=routing["roles"]["translation-specialist"]["capabilities"]
for cap in ("register-adaptation","locale-localization","ui-length-aware-translation","structured-content-preservation","project-translation-memory"):
    assert cap in trans
assert loc_policy["owner_role"]=="translation-specialist"
assert loc_policy["context"]["source_meaning_has_priority_over_literal_wording"] is True
assert loc_policy["quality"]["variables_and_markup_must_be_preserved"] is True
assert loc_policy["collaboration"]["conversation_interface_agent_for_dialogue_register"] is True

print("CHACHA_DEV_V800_DARK_SOURCE_VERIFICATION_CHAIN=PASS")
print("CHACHA_DEV_V800_DARK_RAW_SOURCE_FACT_PROMOTION=NO")
print("CHACHA_DEV_V800_TOR_ISOLATION_REQUIRED=PASS")
print("CHACHA_DEV_V800_CONVERSATION_BRAIN_TO_HUMAN_PATH=PASS")
print("CHACHA_DEV_V800_CONVERSATION_DECISION_MODIFICATION=NO")
print("CHACHA_DEV_V800_PROFESSIONAL_LOCALIZATION=PASS")
print("CHACHA_DEV_V800_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
