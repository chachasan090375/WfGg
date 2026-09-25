#!/usr/bin/env python3
from __future__ import annotations
import importlib.util,json,sqlite3,sys,tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BIN=ROOT/"dev-hub/bin"
sys.path.insert(0,str(BIN))

def loadmod(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    mod=importlib.util.module_from_spec(spec);assert spec and spec.loader
    spec.loader.exec_module(mod);return mod

hbc=loadmod("v812_hbc",BIN/"human-behavior-center.py")
dlg=loadmod("v812_dialogue",BIN/"dialogue-orchestrator.py")
direct=loadmod("v812_direct",BIN/"direct-operator-service.py")

policy=json.load(open(ROOT/"dev-hub/config/human-behavior-center.v1.json"))
hbc.validate_policy(policy)
assert policy["authority"]["decision_authority"] is False
assert policy["authority"]["execution_authority"] is False
assert policy["persona"]["creative_stereotype_mode_allowed"] is True
assert policy["persona"]["real_person_prediction_from_persona_forbidden"] is True
assert policy["evidence"]["fiction_never_promoted_to_empirical_truth"] is True
assert policy["storage"]["raw_film_storage"] is False
assert policy["media_analysis_future_contract"]["store_full_dialogue_transcripts"] is False

with tempfile.TemporaryDirectory(prefix="v812-hbc-") as td:
    td=Path(td);db=td/"evidence.db";con=hbc.connect(db)

    observations=[
      {
        "schema":"chacha.dev/human-behavior-observation/v1",
        "observation_id":"fixture-research-001",
        "source":{"type":"PEER_REVIEWED_RESEARCH","ref":"fixture://research/001","title":"Synthetic qualification fixture"},
        "evidence_scope":"EMPIRICAL_HINT",
        "domain":"politeness",
        "facets":{"culture":"France","age_band":"30-39"},
        "pattern":"Synthetic empirical fixture: formal disagreement may be expressed with controlled politeness.",
        "confidence":0.82,"derived_not_raw":True
      },
      {
        "schema":"chacha.dev/human-behavior-observation/v1",
        "observation_id":"fixture-film-001",
        "source":{"type":"FICTIONAL_FILM","ref":"fixture://film/001","title":"Synthetic fictional representation A"},
        "evidence_scope":"REPRESENTATION_ONLY",
        "domain":"humor",
        "facets":{"region":"Paris 16e","social_milieu":"BCBG","presentation_gender":"woman","age_band":"30-39"},
        "pattern":"Synthetic fictional representation: restrained irony and socially coded understatement.",
        "confidence":0.76,"derived_not_raw":True
      },
      {
        "schema":"chacha.dev/human-behavior-observation/v1",
        "observation_id":"fixture-tv-contradiction-001",
        "source":{"type":"FICTIONAL_TV","ref":"fixture://tv/contradiction/001","title":"Synthetic fictional representation B"},
        "evidence_scope":"REPRESENTATION_ONLY",
        "domain":"conflict_response",
        "facets":{"region":"Paris 16e","social_milieu":"BCBG","presentation_gender":"woman","age_band":"30-39"},
        "pattern":"Synthetic contradictory representation: direct verbal confrontation when social status is challenged.",
        "confidence":0.66,"derived_not_raw":True
      },
      {
        "schema":"chacha.dev/human-behavior-observation/v1",
        "observation_id":"fixture-normandy-001",
        "source":{"type":"PUBLIC_VIDEO_OBSERVATION","ref":"fixture://video/normandy/001","title":"Synthetic contextual fixture"},
        "evidence_scope":"CONTEXTUAL_OBSERVATION",
        "domain":"regional_expression",
        "facets":{"region":"Normandie","age_band":"30-39"},
        "pattern":"Synthetic contextual fixture for a different region; it must not match the Paris persona.",
        "confidence":0.9,"derived_not_raw":True
      }
    ]
    for row in observations:
        result=hbc.ingest(con,row,policy)
        assert result["status"]=="INGESTED",result

    # Same evidence is idempotent.
    same=hbc.ingest(con,observations[0],policy)
    assert same["status"]=="UNCHANGED",same

    # Fiction cannot masquerade as empirical evidence.
    bad=dict(observations[1]);bad["observation_id"]="bad-fiction-scope";bad["evidence_scope"]="EMPIRICAL_HINT"
    try:hbc.ingest(con,bad,policy)
    except ValueError as exc:assert "EVIDENCE_SCOPE_NOT_ALLOWED" in str(exc)
    else:raise AssertionError("FICTION_SCOPE_MUST_FAIL")

    spec={
      "schema":"chacha.dev/fictional-persona-spec/v1",
      "persona_id":"camille-xvie",
      "mode":"FICTIONAL_ARCHETYPE",
      "display_name":"Camille",
      "stereotype_intensity":3,
      "presentation_gender":"woman",
      "age_band":"30-39",
      "regions":["Paris 16e"],
      "cultures":["France"],
      "social_milieu":["BCBG"],
      "languages":["français"],
      "temperament":["maîtrisée","observatrice"],
      "speech_style":["phrases soignées","ironie légère"],
      "creative_notes":["persona volontairement typée pour un avatar ludique"]
    }
    card=hbc.synthesize(con,spec,policy,24)
    assert card["schema"]=="chacha.dev/fictional-persona-card/v1",card
    assert card["persona_id"]=="camille-xvie"
    assert card["identity_frame"]["presentation_gender"]=="woman"
    assert card["identity_frame"]["regions"]==["Paris 16e"]
    ids={x["observation_id"] for x in card["evidence_hints"]}
    assert "fixture-film-001" in ids,ids
    assert "fixture-tv-contradiction-001" in ids,ids
    assert "fixture-normandy-001" not in ids,ids
    assert card["governance"]["not_a_prediction_about_real_people"] is True
    assert card["governance"]["fictional_representation_never_empirical_truth"] is True
    assert all(x["creative_application_strength"]>=0 for x in card["evidence_hints"])
    assert any(x["representation_only"] for x in card["evidence_hints"])

    # Zero stereotype intensity preserves evidence but applies no stereotype strength.
    zero=dict(spec);zero["persona_id"]="camille-neutralized";zero["stereotype_intensity"]=0
    zero_card=hbc.synthesize(con,zero,policy,24)
    assert zero_card["evidence_hints"]
    assert all(x["creative_application_strength"]==0 for x in zero_card["evidence_hints"])

    fb={
      "schema":"chacha.dev/persona-feedback/v1",
      "feedback_id":"feedback-001","persona_id":"camille-xvie",
      "interaction_context":"Synthetic avatar conversation fixture",
      "observed_effect":"The fictional persona felt too formal for the intended playful scene.",
      "rating":-1,
      "adjustment_hint":"Reduce formality in playful contexts."
    }
    fr=hbc.record_feedback(con,fb)
    assert fr["status"]=="RECORDED"
    assert fr["policy_mutated"] is False
    assert fr["permissions_changed"] is False

    delta=hbc.learning_delta(con)
    assert delta["schema"]=="chacha.dev/human-behavior-evidence-delta/v1"
    assert delta["policy_change_requested"] is False
    assert delta["permission_change_requested"] is False
    assert len(delta["observations"])==4
    assert len(delta["persona_feedback"])==1

    # Persona can be consumed by the dialogue layer as fictional speaker context.
    pc=dlg.persona_context(card)
    assert pc["persona_id"]=="camille-xvie"
    assert pc["governance"]["fictional_persona"] is True
    assert pc["governance"]["not_a_prediction_about_real_people"] is True
    assert "humor" in pc["behavior_dimensions"]
    base={
      "schema":"chacha.dev/conversation-response/v1","kind":"RESULT",
      "message":"La préparation est terminée.","requires_user_response":False,
      "status":"PASS","next_action":"AWAIT_USER_DIRECTIVE",
      "central_authority_preserved":True,"decision_modified":False
    }
    prompt=dlg.build_prompt(base,{},{"items":[]},json.load(open(ROOT/"dev-hub/config/dialogue-orchestrator.v1.json")),card)
    assert '"SPEAKER_PERSONA"' in prompt
    assert "camille-xvie" in prompt
    assert "La préparation est terminée." in prompt

    # Direct Operator catalog / selection is private and explicit.
    op_policy=json.load(open(ROOT/"dev-hub/config/direct-operator.v1.json"))
    op_policy["runtime_root"]=str(td/"direct-operator")
    op_policy["human_behavior_center"]["persona_dir"]=str(td/"personas")
    persona_dir=Path(op_policy["human_behavior_center"]["persona_dir"]);persona_dir.mkdir(parents=True)
    card_path=persona_dir/"camille-xvie.json";card_path.write_text(json.dumps(card,ensure_ascii=False))
    state=direct.State(ROOT,td,op_policy)
    state.persona_dir=persona_dir
    state.save_profile("operator@example.test",{"assistant_persona_id":"camille-xvie"})
    catalog=state.persona_catalog()
    assert catalog["count"]==1,catalog
    assert catalog["items"][0]["persona_id"]=="camille-xvie"
    assert state.selected_persona_path("operator@example.test")==card_path
    assert state.selected_persona_path("other@example.test") is None

# Governance registration
contracts=json.load(open(ROOT/"dev-hub/config/guardian-role-contracts.v1.json"))["contracts"]
contract=next(x for x in contracts if x.get("contract_id")=="role:human-behavior-center")
assert "SYNTHESIZE_FICTIONAL_PERSONA" in contract["allowed_actions"]
assert "INFER_REAL_PERSON_PROTECTED_TRAITS" in contract["forbidden_actions"]
assert "TREAT_FICTION_AS_EMPIRICAL_POPULATION_TRUTH" in contract["forbidden_actions"]
assert "AUTOMATIC_PAID_UPGRADE" in contract["forbidden_actions"]

targets=json.load(open(ROOT/"dev-hub/config/assurance-agent-instrumentation.v1.json"))["priority_targets"]
assert any(x.get("agent_id")=="human-behavior-center" for x in targets)
learning=json.load(open(ROOT/"dev-hub/config/universal-learning.v1.json"))
assert "human-behavior-center" in learning["source_kinds"]

ui=(ROOT/"dev-hub/direct-operator-ui/index.html").read_text()
assert "Persona de ChaCha" in ui
assert "/api/v1/personas" in ui
assert "assistant_persona_id" in ui

print("CHACHA_DEV_V812_DERIVED_EVIDENCE_STORE=PASS")
print("CHACHA_DEV_V812_FICTION_SCOPE_SEPARATION=PASS")
print("CHACHA_DEV_V812_CONTRADICTORY_REPRESENTATIONS_PRESERVED=PASS")
print("CHACHA_DEV_V812_CONTROLLED_STEREOTYPE_INTENSITY=PASS")
print("CHACHA_DEV_V812_FICTIONAL_PERSONA_SYNTHESIS=PASS")
print("CHACHA_DEV_V812_PERSONA_FEEDBACK_LEARNING=PASS")
print("CHACHA_DEV_V812_DIALOGUE_PERSONA_CONTEXT=PASS")
print("CHACHA_DEV_V812_DIRECT_OPERATOR_PERSONA_SELECTION=PASS")
print("CHACHA_DEV_V812_GUARDIAN_ROLE_CONTRACT=PASS")
print("CHACHA_DEV_V812_UNIVERSAL_LEARNING_UPLINK=PASS")
print("CHACHA_DEV_V812_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
