#!/usr/bin/env python3
from __future__ import annotations
import importlib.util,json,stat,sys,tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BIN=ROOT/"dev-hub/bin"
sys.path.insert(0,str(BIN))

def loadmod(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    mod=importlib.util.module_from_spec(spec);assert spec and spec.loader
    spec.loader.exec_module(mod);return mod

router=loadmod("v813_router",BIN/"conversation-channel-router.py")
research=loadmod("v813_research",BIN/"research-broker.py")
advisory=loadmod("v813_advisory",BIN/"conversation-advisory-bus.py")
reasoner=loadmod("v813_reasoner",BIN/"conversation-reasoner.py")
direct=loadmod("v813_direct",BIN/"direct-operator-service.py")

policy=json.load(open(ROOT/"dev-hub/config/dual-channel.v1.json"))
assert policy["routing"]["manual_switch_authoritative"] is True
assert policy["routing"]["conversation_never_auto_switches_to_build"] is True
assert policy["channels"]["CONVERSATION"]["heavy_build_pipeline"] is False
assert policy["channels"]["CONVERSATION"]["mutation_authority"] is False
assert policy["advisory_bus"]["may_not_call_scheduler"] is True
assert policy["advisory_bus"]["may_not_call_run_controller"] is True
assert policy["advisory_bus"]["may_not_trigger_foundries"] is True

chat=router.route("CONVERSATION","On discute un peu ?","chacha-dev-platform")
assert chat["subroute"]=="CHAT",chat
assert chat["heavy_build_pipeline_allowed"] is False
research_route=router.route("CONVERSATION","Recherche les solutions Android voice récentes","chacha-dev-platform")
assert research_route["subroute"]=="RESEARCH",research_route
advice=router.route("CONVERSATION","Tu te souviens de notre architecture ?","chacha-dev-platform")
assert advice["subroute"]=="ADVISORY",advice
handoff=router.route("CONVERSATION","Crée-moi une application météo","chacha-dev-platform")
assert handoff["subroute"]=="BUILD_HANDOFF_REQUIRED",handoff
assert handoff["creation_brief"]["requires_explicit_build_switch"] is True
assert handoff["creation_brief"]["execution_started"] is False
build=router.route("BUILD","Crée-moi une application météo","chacha-dev-platform")
assert build["subroute"]=="BUILD_PIPELINE",build
assert build["heavy_build_pipeline_allowed"] is True

with tempfile.TemporaryDirectory(prefix="v813-dual-") as td:
    td=Path(td)
    snapshot=td/"technology.json"
    snapshot.write_text(json.dumps({
      "schema":"fixture","generated_at":"2026-09-25T22:00:00Z","snapshot_digest":"sha256:fixture",
      "source_mode":"FIXTURE","zero_spend_candidate_available":True,
      "eligible_provider_candidates":[
        {"provider_id":"android-speech-local","domain":"android voice","capabilities":["speech","tts"],"cost_class":"free","eligible":True},
        {"provider_id":"unrelated-db","domain":"database","capabilities":["sql"],"cost_class":"free","eligible":True}
      ],
      "provider_candidates":[]
    }))
    rb=research.research("android voice speech",snapshot,8)
    assert rb["status"]=="PASS",rb
    assert rb["results"][0]["data"]["domain"]=="android voice",rb
    assert "speech" in rb["results"][0]["data"]["capabilities"],rb
    assert rb["fresh_refresh_triggered"] is False
    assert rb["general_web_provider"]=="UNBOUND"

    memory=td/"memory.json"
    memory.write_text(json.dumps({
      "schema":"fixture","generated_at":"2026-09-25T20:00:00Z","snapshot_digest":"sha256:memory",
      "items":[
        {"project_id":"chacha-dev-platform","kind":"architecture","summary":"Dual channel conversation architecture keeps build execution separate."},
        {"project_id":"other","kind":"note","summary":"Unrelated observation."}
      ]
    }))
    brief=advisory.build("architecture conversation",memory,td/"missing.db",rb)
    assert brief["read_only"] is True
    assert brief["memory"]["items"],brief
    assert brief["authorities"]["scheduler_called"] is False
    assert brief["authorities"]["run_controller_called"] is False
    assert brief["authorities"]["foundry_called"] is False
    assert brief["authorities"]["mutation_authority"] is False

    rp=json.load(open(ROOT/"dev-hub/config/conversation-reasoner.v1.json"))
    fallback=reasoner.reason("Allo",chat,{"items":[]},{},{},brief,rp,None,None)
    assert fallback["message"]=="Je suis là. Le canal Conversation est prêt.",fallback
    assert fallback["conversation_reasoner"]["provider_eligible"] is False
    assert fallback["conversation_reasoner"]["provider_invoked"] is False
    assert fallback["conversation_reasoner"]["scheduler_called"] is False

    fake=td/"fake-provider"
    fake.write_text("""#!/usr/bin/env python3
import json,sys
prompt=''
for i,x in enumerate(sys.argv):
    if x=='-p' and i+1<len(sys.argv):prompt=sys.argv[i+1]
if '"CHANNEL":"CONVERSATION"' not in prompt:
    raise SystemExit(7)
print(json.dumps({"status":"SUCCESS","structured_output":{"schema":"chacha.dev/conversation-reasoner-model-output/v1","message":"Oui, on peut en discuter tranquillement."}},ensure_ascii=False))
""")
    fake.chmod(fake.stat().st_mode|stat.S_IXUSR)
    att={
      "schema":"chacha.dev/conversation-provider-zero-cost-attestation/v1",
      "provider_id":"agy-gemini-conversation","status":"PASS","cost_class":"local",
      "automatic_external_spend_eur":0
    }
    rp2=json.loads(json.dumps(rp));rp2["provider"]["backend"]=str(fake);rp2["provider"]["models"]=["fixture"]
    user_human={"profile":{"preferred_name":"Test","gender_identity":"woman","age_band":"30-39","conversation_register":"direct"},"interaction_signals":{}}
    persona={"schema":"chacha.dev/fictional-persona-card/v1","persona_id":"persona-test","display_name":"Persona Test","stereotype_intensity":2,"identity_frame":{"presentation_gender":"woman","age_band":"30-39"},"behavior_dimensions":{},"creative_assumptions":[]}
    safe_h=reasoner.safe_human_context(user_human)
    assert "gender_identity" not in safe_h["profile"]
    assert "age_band" not in safe_h["profile"]
    model=reasoner.reason("On discute un peu ?",chat,{"items":[]},user_human,persona,brief,rp2,att,fake)
    assert model["message"]=="Oui, on peut en discuter tranquillement.",model
    assert model["conversation_reasoner"]["mode"]=="MODEL_CHAT"
    assert model["conversation_reasoner"]["provider_invoked"] is True
    assert model["conversation_reasoner"]["speaker_persona_id"]=="persona-test"
    assert model["conversation_reasoner"]["speaker_persona_applied"] is True

    op=json.load(open(ROOT/"dev-hub/config/direct-operator.v1.json"))
    op["runtime_root"]=str(td/"direct-operator")
    state=direct.State(ROOT,td,op)
    k1=state.idempotency_key("user","project","same-request","CONVERSATION")
    k2=state.idempotency_key("user","project","same-request","BUILD")
    assert k1!=k2
    j1,c1=state.accept_intent("Allo","project","user","same-request","CONVERSATION")
    j2,c2=state.accept_intent("Allo","project","user","same-request","BUILD")
    assert c1 and c2 and j1!=j2

ui=(ROOT/"dev-hub/direct-operator-ui/index.html").read_text()
assert "💬 ChaCha" in ui and "🛠️ Créer" in ui
assert "channelOverride||selectedChannel" in ui
assert "localStorage.getItem('chacha-channel')" in ui
assert "submit('Stop',false,'BUILD')" in ui
assert "Rien ne sera lancé avant ton envoi." in ui
assert "Conversation + création, un même cerveau" in ui

contracts=json.load(open(ROOT/"dev-hub/config/guardian-role-contracts.v1.json"))["contracts"]
contract_ids={x.get("contract_id") for x in contracts}
for cid in (
  "role:conversation-channel-router",
  "role:conversation-advisory-bus",
  "role:conversation-reasoner",
  "role:research-broker"
):
    assert cid in contract_ids,cid
for c in contracts:
    if c.get("contract_id") in {
      "role:conversation-channel-router","role:conversation-advisory-bus",
      "role:conversation-reasoner","role:research-broker"
    }:
        assert "AUTOMATIC_PAID_UPGRADE" in c.get("forbidden_actions",[]),c
        assert "PRODUCTION_DEPLOY" in c.get("forbidden_actions",[]),c

targets=json.load(open(ROOT/"dev-hub/config/assurance-agent-instrumentation.v1.json"))["priority_targets"]
target_ids={x.get("agent_id") for x in targets}
for aid in ("conversation-channel-router","conversation-advisory-bus","conversation-reasoner","research-broker"):
    assert aid in target_ids,aid

service=(ROOT/"dev-hub/bin/direct-operator-service.py").read_text()
conversation_block=service.split("def process_conversation",1)[1].split("def process(",1)[0]
for forbidden in ("self.translator","self.controller","execution-scheduler.py","run-controller.py","self.central("):
    assert forbidden not in conversation_block,forbidden
assert '"foundry_called":False' in conversation_block
assert '"scheduler_called":False' in conversation_block
assert '"run_controller_called":False' in conversation_block
assert "self.advisory_bus" in conversation_block
assert "self.research_broker" in conversation_block
assert "self.conversation_reasoner" in conversation_block

print("CHACHA_DEV_V813_MANUAL_CHANNEL_AUTHORITY=PASS")
print("CHACHA_DEV_V813_CONVERSATION_NO_BUILD_PIPELINE=PASS")
print("CHACHA_DEV_V813_BUILD_HANDOFF_EXPLICIT=PASS")
print("CHACHA_DEV_V813_RESEARCH_READ_ONLY_SNAPSHOT=PASS")
print("CHACHA_DEV_V813_ADVISORY_BUS_READ_ONLY=PASS")
print("CHACHA_DEV_V813_CONVERSATION_REASONER_ZERO_COST_GATE=PASS")
print("CHACHA_DEV_V813_CHANNEL_IDEMPOTENCY_ISOLATION=PASS")
print("CHACHA_DEV_V813_UI_SWITCH=PASS")
print("CHACHA_DEV_V813_USER_DEMOGRAPHICS_NOT_SPEAKER_STYLE=PASS")
print("CHACHA_DEV_V813_CONVERSATION_PERSONA=PASS")
print("CHACHA_DEV_V813_GLOBAL_STOP_PRESERVED=PASS")
print("CHACHA_DEV_V813_GUARDIAN_ROLE_CONTRACTS=PASS")
print("CHACHA_DEV_V813_ASSURANCE_INSTRUMENTATION=PASS")
print("CHACHA_DEV_V813_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
