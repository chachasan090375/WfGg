#!/usr/bin/env python3
from __future__ import annotations
import datetime as dt,importlib.util,json,os,stat,sys,tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"dev-hub/bin"))

def loadmod(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    mod=importlib.util.module_from_spec(spec);assert spec and spec.loader
    spec.loader.exec_module(mod);return mod

dlg=loadmod("v811_dialogue",ROOT/"dev-hub/bin/dialogue-orchestrator.py")
policy=json.load(open(ROOT/"dev-hub/config/dialogue-orchestrator.v1.json"))

base={
 "schema":"chacha.dev/conversation-response/v1",
 "agent_id":"conversation-interface-agent",
 "kind":"WARNING",
 "message":"Le contrôle Guardian est temporairement indisponible. L’exécution pourra reprendre dès qu’il sera disponible.",
 "requires_user_response":False,
 "status":"AWAITING_EXTERNAL_CONDITION",
 "next_action":"RETRY_WHEN_GUARDIAN_AVAILABLE",
 "central_authority_preserved":True,
 "decision_modified":False,
 "automatic_external_spend_eur":0
}
human={
 "schema":"chacha.dev/human-context-brief/v1",
 "profile":{
   "preferred_name":"Cédric","preferred_form_of_address":"tu",
   "gender_identity":"homme","age_band":"50-59",
   "regional_contexts":["Provence"],"cultural_contexts":["France"],
   "conversation_register":"familier-direct","humor_level":"léger"
 },
 "interaction_signals":{"explicit_frustration":True},
 "rules":{"technical_decision_authority":False}
}
timeline={
 "schema":"chacha.dev/conversation-timeline/v1",
 "items":[
   {"user":{"text":"Pourquoi ça bloque ?"},"assistant":{"text":"Guardian ne répond pas."}},
   {"user":{"text":"OK, tiens-moi au courant."},"assistant":{"text":"Je continue dès que possible."}}
 ]
}

# No attestation => provider is never invoked.
out=dlg.orchestrate(base,human,timeline,policy,None,Path("/definitely/missing/provider"))
assert out["message"]==base["message"],out
assert out["status"]==base["status"] and out["next_action"]==base["next_action"],out
m=out["dialogue_orchestrator"]
assert m["provider_eligible"] is False
assert m["provider_invoked"] is False
assert m["provider_reason"]=="ZERO_COST_ATTESTATION_MISSING"
assert m["mode"]=="DETERMINISTIC_BASE_RESPONSE"

now=dt.datetime.now(dt.timezone.utc)
att={
 "schema":"chacha.dev/conversation-provider-zero-cost-attestation/v1",
 "provider_id":"agy-gemini-conversation","status":"PASS","cost_class":"quota",
 "quota_available":True,"valid_until":"2099-01-01T00:00:00Z",
 "automatic_external_spend_eur":0
}
elig=dlg.provider_eligibility(policy,att,now)
assert elig["eligible"] is True,elig
expired=dict(att);expired["valid_until"]="2020-01-01T00:00:00Z"
assert dlg.provider_eligibility(policy,expired,now)["eligible"] is False

with tempfile.TemporaryDirectory(prefix="v811-dialogue-") as td:
    td=Path(td)
    safe=td/"safe-provider"
    safe.write_text("""#!/usr/bin/env python3
import json
print(json.dumps({"status":"SUCCESS","structured_output":{"schema":"chacha.dev/dialogue-model-output/v1","message":"Je l’ai bien reçu. Pour l’instant, Guardian est temporairement indisponible ; je reprendrai l’exécution dès qu’il sera de nouveau disponible."}},ensure_ascii=False))
""")
    safe.chmod(safe.stat().st_mode|stat.S_IXUSR)
    out=dlg.orchestrate(base,human,timeline,policy,att,safe)
    assert out["dialogue_orchestrator"]["provider_invoked"] is True,out
    assert out["dialogue_orchestrator"]["mode"]=="MODEL_REPHRASE",out
    assert out["status"]==base["status"] and out["next_action"]==base["next_action"],out
    assert out["central_authority_preserved"] is True and out["decision_modified"] is False
    assert "Guardian" in out["message"]

    unsafe=td/"unsafe-provider"
    unsafe.write_text("""#!/usr/bin/env python3
import json
print(json.dumps({"status":"SUCCESS","structured_output":{"schema":"chacha.dev/dialogue-model-output/v1","message":"C’est réglé en V9.9.9 et cela coûtera 199 EUR. Guardian reviendra ensuite."}},ensure_ascii=False))
""")
    unsafe.chmod(unsafe.stat().st_mode|stat.S_IXUSR)
    out2=dlg.orchestrate(base,human,timeline,policy,att,unsafe)
    assert out2["message"]==base["message"],out2
    assert out2["dialogue_orchestrator"]["provider_invoked"] is True
    assert out2["dialogue_orchestrator"]["mode"]=="DETERMINISTIC_FALLBACK_AFTER_PROVIDER"
    attempts=(out2["dialogue_orchestrator"].get("runtime") or {}).get("attempts") or []
    assert attempts and any(x.get("status")=="REJECTED" for x in attempts),attempts

style=dlg.style_context(human)
assert style["declared_preferences"]["preferred_name"]=="Cédric"
assert style["declared_preferences"]["regional_contexts"]==["Provence"]
assert "gender_identity" not in style["declared_preferences"]
assert "age_band" not in style["declared_preferences"]
assert style["rules"]["no_stereotype_inference"] is True

prompt=dlg.build_prompt(base,human,timeline,policy)
assert "DIALOGUE_JOB_JSON=" in prompt
assert "gender_identity" not in prompt
assert "age_band" not in prompt
assert "Guardian" in prompt

print("CHACHA_DEV_V811_ZERO_COST_GATE_FAIL_CLOSED=PASS")
print("CHACHA_DEV_V811_PROVIDER_NOT_CALLED_WITHOUT_ATTESTATION=PASS")
print("CHACHA_DEV_V811_ATTESTED_PROVIDER_REPHRASE=PASS")
print("CHACHA_DEV_V811_STATUS_AND_NEXT_ACTION_IMMUTABLE=PASS")
print("CHACHA_DEV_V811_NEW_TECHNICAL_FACT_REJECTION=PASS")
print("CHACHA_DEV_V811_DEMOGRAPHIC_STYLE_STEREOTYPE_GUARD=PASS")
print("CHACHA_DEV_V811_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
