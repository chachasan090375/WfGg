#!/usr/bin/env python3
from __future__ import annotations
import importlib.util,json,stat,sys,tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BIN=ROOT/"dev-hub/bin"
sys.path.insert(0,str(BIN))

def mod(name,path):
    s=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(s);assert s and s.loader
    s.loader.exec_module(m);return m

router=mod("v813_router",BIN/"conversation-channel-router.py")
advisory=mod("v813_advisory",BIN/"conversation-advisory-bus.py")
research=mod("v813_research",BIN/"research-broker.py")
reasoner=mod("v813_reasoner",BIN/"conversation-reasoner.py")
direct=mod("v813_direct",BIN/"direct-operator-service.py")

dual=json.load(open(ROOT/"dev-hub/config/dual-channel.v1.json"))
rp=json.load(open(ROOT/"dev-hub/config/conversation-reasoner.v1.json"))
assert dual["routing"]["manual_switch_is_authoritative"] is True
assert dual["routing"]["conversation_never_auto_escalates_to_build"] is True

chat=router.route("CONVERSATION","Allo","chacha-dev-platform")
assert chat["subroute"]=="CHAT"
assert chat["scheduler_allowed"] is False
assert chat["run_controller_allowed"] is False
assert chat["mutation_allowed"] is False

handoff=router.route("CONVERSATION","Crée une application de test","chacha-dev-platform")
assert handoff["subroute"]=="BUILD_HANDOFF_REQUIRED"
assert handoff["automatic_channel_switch"] is False
assert handoff["creation_brief"]["requires_explicit_build_switch"] is True
assert handoff["creation_brief"]["execution_started"] is False

build=router.route("BUILD","Crée une application de test","chacha-dev-platform")
assert build["subroute"]=="BUILD_PIPELINE"
assert build["heavy_build_pipeline_allowed"] is True
assert router.route("CONVERSATION","cherche les dernières solutions TTS","p")["subroute"]=="RESEARCH"
assert router.route("CONVERSATION","tu te souviens de notre architecture ?","p")["subroute"]=="ADVISORY"

with tempfile.TemporaryDirectory(prefix="v813-") as td:
    td=Path(td)
    snap=td/"tech.json"
    snap.write_text(json.dumps({
      "snapshot_digest":"fixture-digest","generated_at":"2026-09-25T20:00:00Z",
      "provider_candidates":[
        {"id":"tts-local","capability":"speech synthesis","status":"ENABLED",
         "cost_class":"local","zero_external_spend":True},
        {"id":"image-x","capability":"image generation","status":"ENABLED",
         "cost_class":"quota","zero_external_spend":False}
      ],
      "technology_taxonomy":{"domain_categories":{
        "voice":{"capabilities":["speech synthesis"],"known_provider_ids":["tts-local"]}
      }}
    }),encoding="utf-8")
    rb=research.research("solutions speech synthesis TTS",snap,8)
    assert rb["status"]=="PASS",rb
    assert rb["read_only"] is True
    assert rb["fresh_refresh_triggered"] is False
    assert rb["network_call_performed"] is False
    assert rb["external_provider_invoked"] is False

    memory=td/"memory.json"
    memory.write_text(json.dumps({
      "snapshot_digest":"memory-fixture",
      "generated_at":"2026-09-25T20:00:00Z",
      "items":[{
        "project_id":"chacha-dev-platform",
        "kind":"architecture",
        "summary":"dual channel conversation architecture",
        "confidence":0.9,
        "state":"TRUSTED"
      }]
    }),encoding="utf-8")
    adv=advisory.build("architecture conversation",memory,td/"missing-human.db",rb)
    assert adv["read_only"] is True
    assert adv["authorities"]["execution_authority"] is False
    assert adv["authorities"]["scheduler_called"] is False
    assert adv["authorities"]["run_controller_called"] is False
    assert adv["memory"]["items"],adv

    noatt=reasoner.reason("Allo",chat,{"items":[]},{},{},adv,rp,None,None)
    assert noatt["status"]=="PASS"
    assert noatt["message"]=="Je suis là. Le canal Conversation est prêt."
    meta=noatt["conversation_reasoner"]
    assert meta["provider_eligible"] is False
    assert meta["provider_invoked"] is False
    assert meta["scheduler_called"] is False

contracts=json.load(open(ROOT/"dev-hub/config/guardian-role-contracts.v1.json"))["contracts"]
for cid in (
 "role:conversation-channel-router",
 "role:conversation-advisory-bus",
 "role:conversation-reasoner",
 "role:research-broker"
):
    c=next(x for x in contracts if x.get("contract_id")==cid)
    assert "EXECUTE_PROJECT_MUTATION" in c["forbidden_actions"]
    assert "RUN_SCHEDULER" in c["forbidden_actions"]
    assert "RUN_CONTROLLER_EXECUTE" in c["forbidden_actions"]
    assert "AUTO_SWITCH_TO_BUILD" in c["forbidden_actions"]

targets=json.load(open(ROOT/"dev-hub/config/assurance-agent-instrumentation.v1.json"))["priority_targets"]
for aid in ("conversation-channel-router","conversation-advisory-bus",
            "conversation-reasoner","research-broker"):
    assert any(x.get("agent_id")==aid for x in targets)

ui=(ROOT/"dev-hub/direct-operator-ui/index.html").read_text()
assert "💬 ChaCha" in ui and "🛠️ Créer" in ui
assert "channel:channelOverride||selectedChannel" in ui
assert "pendingBuildText" in ui
assert "submit('Stop',false,'BUILD')" in ui
assert "localStorage.setItem('chacha-channel'" in ui

src=(BIN/"direct-operator-service.py").read_text()
assert 'channel:str="BUILD"' in src
assert 'channel=="CONVERSATION" and normalize(text)!="STOP"' in src
cfg=(ROOT/"dev-hub/config/direct-operator.v1.json").read_text()
assert '"central_orchestrator_required": "BUILD_CHANNEL_ONLY"' in cfg

print("CHACHA_DEV_V813_MANUAL_DUAL_CHANNEL=PASS")
print("CHACHA_DEV_V813_EXPLICIT_BUILD_HANDOFF=PASS")
print("CHACHA_DEV_V813_READ_ONLY_ADVISORY_BUS=PASS")
print("CHACHA_DEV_V813_CACHED_RESEARCH_NO_NETWORK=PASS")
print("CHACHA_DEV_V813_ZERO_COST_CONVERSATION_GATE=PASS")
print("CHACHA_DEV_V813_STATIC_GUARDIAN_CONTRACTS=PASS")
print("CHACHA_DEV_V813_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
