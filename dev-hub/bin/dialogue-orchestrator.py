#!/usr/bin/env python3
from __future__ import annotations

import argparse,datetime as dt,json,os,re,subprocess,tempfile,time
from pathlib import Path
from typing import Any

POLICY_SCHEMA="chacha.dev/dialogue-orchestrator-policy/v1"
BASE_SCHEMA="chacha.dev/conversation-response/v1"
MODEL_SCHEMA="chacha.dev/dialogue-model-output/v1"
ATTEST_SCHEMA="chacha.dev/conversation-provider-zero-cost-attestation/v1"

def now_iso()->str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())

def load(path:Path,default=None):
    try:x=json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        if default is not None:return default
        raise
    if not isinstance(x,dict):raise ValueError("JSON_ROOT_NOT_OBJECT:"+str(path))
    return x

def save(path:Path,x:dict[str,Any])->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+".tmp")
    tmp.write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    os.replace(tmp,path)

def parse_iso(v:str)->dt.datetime|None:
    try:
        return dt.datetime.fromisoformat(v.replace("Z","+00:00"))
    except Exception:
        return None

def provider_eligibility(policy:dict[str,Any],attestation:dict[str,Any]|None,now:dt.datetime|None=None)->dict[str,Any]:
    p=policy.get("provider") if isinstance(policy.get("provider"),dict) else {}
    pid=str(p.get("id") or "")
    if not p.get("zero_cost_attestation_required"):
        return {"eligible":False,"reason":"ZERO_COST_ATTESTATION_POLICY_REQUIRED","provider_id":pid}
    if not isinstance(attestation,dict):
        return {"eligible":False,"reason":"ZERO_COST_ATTESTATION_MISSING","provider_id":pid}
    if attestation.get("schema")!=ATTEST_SCHEMA or attestation.get("provider_id")!=pid or attestation.get("status")!="PASS":
        return {"eligible":False,"reason":"ZERO_COST_ATTESTATION_INVALID","provider_id":pid}
    try:spend=float(attestation.get("automatic_external_spend_eur"))
    except Exception:spend=-1
    if spend!=0:
        return {"eligible":False,"reason":"ZERO_COST_ATTESTATION_NONZERO_SPEND","provider_id":pid}
    cost=str(attestation.get("cost_class") or "").lower()
    allowed={str(x).lower() for x in p.get("allowed_zero_cost_classes") or []}
    if cost not in allowed:
        return {"eligible":False,"reason":"COST_CLASS_NOT_AUTOMATIC_ZERO","provider_id":pid,"cost_class":cost}
    if cost=="quota":
        if attestation.get("quota_available") is not True:
            return {"eligible":False,"reason":"FREE_QUOTA_NOT_CONFIRMED","provider_id":pid,"cost_class":cost}
        valid_until=parse_iso(str(attestation.get("valid_until") or ""))
        current=now or dt.datetime.now(dt.timezone.utc)
        if valid_until is None or valid_until<=current:
            return {"eligible":False,"reason":"ZERO_COST_ATTESTATION_EXPIRED","provider_id":pid,"cost_class":cost}
    return {"eligible":True,"reason":"ZERO_COST_ATTESTED","provider_id":pid,"cost_class":cost}

def model_schema()->dict[str,Any]:
    return {
      "$schema":"https://json-schema.org/draft/2020-12/schema",
      "type":"object","additionalProperties":False,
      "required":["schema","message"],
      "properties":{
        "schema":{"const":MODEL_SCHEMA},
        "message":{"type":"string","minLength":1,"maxLength":12000}
      }
    }

def agent_markdown()->str:
    return """---
name: chacha-human-dialogue
description: Human dialogue surface for ChaCha DEV. No tools. Rephrasing only.
tools: []
mainAgent: true
subagent: false
---
You are the human dialogue surface of ChaCha DEV.

You receive a LOCKED_RESPONSE produced by ChaCha DEV's central decision path.
Your only job is to make its human-facing message natural and conversational.

Hard rules:
- Never change, reverse, weaken or strengthen the locked technical decision.
- Never invent work performed, approvals, status, versions, prices, dates, identities, causes, guarantees or next actions.
- Never claim an external dependency is available when the locked response says otherwise.
- Do not execute, browse, call tools, authenticate, purchase, post or mutate anything.
- Use recent conversation only for continuity and references already present there.
- Human profile fields are voluntary style preferences, not factual evidence about the world.
- Never infer age, gender, ethnicity, religion, culture, region or personality from name, voice, accent or location.
- Interaction signals are temporary communication cues, not diagnoses.
- Adapt register, directness, verbosity and light humor only when explicitly requested.
- If SPEAKER_PERSONA is present, embody that fictional persona's language, social style, humor and emotional expression.
- SPEAKER_PERSONA is a creative performance contract, not evidence about any real person or population.
- Persona performance must never change the locked operational meaning, status, next action, approvals or uncertainty.
- Preserve uncertainty from the locked response.
- Return only JSON matching the supplied schema.
"""

def bounded_timeline(timeline:dict[str,Any],limit:int)->list[dict[str,str]]:
    items=timeline.get("items") if isinstance(timeline.get("items"),list) else []
    out=[]
    for t in items[-max(0,limit):]:
        if not isinstance(t,dict):continue
        u=t.get("user") if isinstance(t.get("user"),dict) else {}
        a=t.get("assistant") if isinstance(t.get("assistant"),dict) else {}
        if str(u.get("text") or "").strip():out.append({"role":"user","text":str(u.get("text"))[:4000]})
        if str(a.get("text") or "").strip():out.append({"role":"assistant","text":str(a.get("text"))[:4000]})
    return out[-max(0,limit*2):]

def style_context(human:dict[str,Any])->dict[str,Any]:
    profile=human.get("profile") if isinstance(human.get("profile"),dict) else {}
    signals=human.get("interaction_signals") if isinstance(human.get("interaction_signals"),dict) else {}
    allowed=("preferred_name","preferred_form_of_address","languages","cultural_contexts","regional_contexts",
             "conversation_register","directness","verbosity","humor_level","voice_preferences")
    return {
      "declared_preferences":{k:profile[k] for k in allowed if k in profile},
      "ephemeral_interaction_signals":signals,
      "rules":{"no_stereotype_inference":True,"no_psychological_diagnosis":True}
    }

def persona_context(persona:dict[str,Any]|None)->dict[str,Any]:
    if not isinstance(persona,dict) or persona.get("schema")!="chacha.dev/fictional-persona-card/v1":
        return {}
    dims=persona.get("behavior_dimensions") if isinstance(persona.get("behavior_dimensions"),dict) else {}
    compact={}
    for domain,rows in dims.items():
        if not isinstance(rows,list):continue
        picked=[]
        for row in rows[:6]:
            if not isinstance(row,dict):continue
            strength=float(row.get("strength") or 0)
            if strength<=0:continue
            picked.append({
              "pattern":str(row.get("pattern") or "")[:800],
              "strength":round(strength,3),
              "evidence_scope":row.get("evidence_scope")
            })
        if picked:compact[str(domain)]=picked
    return {
      "persona_id":persona.get("persona_id"),
      "display_name":persona.get("display_name"),
      "mode":"FICTIONAL_ARCHETYPE",
      "stereotype_intensity":persona.get("stereotype_intensity"),
      "identity_frame":persona.get("identity_frame") if isinstance(persona.get("identity_frame"),dict) else {},
      "creative_assumptions":list(persona.get("creative_assumptions") or [])[:20],
      "behavior_dimensions":compact,
      "governance":{
        "fictional_persona":True,
        "not_a_prediction_about_real_people":True,
        "technical_decision_authority":False
      }
    }

def build_prompt(base:dict[str,Any],human:dict[str,Any],timeline:dict[str,Any],policy:dict[str,Any],persona:dict[str,Any]|None=None)->str:
    c=policy.get("context") if isinstance(policy.get("context"),dict) else {}
    payload={
      "LOCKED_RESPONSE":{
        "status":base.get("status"),
        "next_action":base.get("next_action"),
        "kind":base.get("kind"),
        "requires_user_response":base.get("requires_user_response"),
        "message":base.get("message")
      },
      "RECENT_DIALOGUE":bounded_timeline(timeline,int(c.get("recent_turn_limit") or 16)),
      "HUMAN_STYLE_CONTEXT":style_context(human),
      "SPEAKER_PERSONA":persona_context(persona),
      "TASK":"Rewrite only LOCKED_RESPONSE.message as a natural reply. Convey exactly the same operational meaning and uncertainty. When SPEAKER_PERSONA is present, perform that fictional persona without adding technical facts."
    }
    prompt="DIALOGUE_JOB_JSON="+json.dumps(payload,ensure_ascii=False,separators=(",",":"))
    max_chars=max(4000,int(c.get("max_prompt_chars") or 30000))
    if len(prompt)>max_chars:
        payload["RECENT_DIALOGUE"]=payload["RECENT_DIALOGUE"][-6:]
        prompt="DIALOGUE_JOB_JSON="+json.dumps(payload,ensure_ascii=False,separators=(",",":"))
    return prompt[:max_chars]

TECH_PATTERNS=[
  re.compile(r"\b[0-9a-f]{12,64}\b",re.I),
  re.compile(r"\bV?\d+\.\d+(?:\.\d+){0,2}\b",re.I),
  re.compile(r"https?://[^\s]+",re.I),
  re.compile(r"(?<!\w)/(?:[A-Za-z0-9._-]+/){1,}[A-Za-z0-9._-]+"),
  re.compile(r"\b[A-Z][A-Z0-9]+(?:_[A-Z0-9]+)+\b"),
  re.compile(r"\b\d+(?:[.,]\d+)?\s*(?:€|EUR|USD|\$)\b",re.I)
]

def technical_tokens(text:str)->set[str]:
    out=set()
    for rx in TECH_PATTERNS:
        out.update(m.group(0) for m in rx.finditer(text or ""))
    return out

def validate_rephrase(message:str,base:dict[str,Any],timeline:dict[str,Any])->tuple[bool,str]:
    msg=str(message or "").strip()
    if not msg:return False,"EMPTY_MODEL_MESSAGE"
    source=str(base.get("message") or "")
    for row in bounded_timeline(timeline,16):
        source+="\n"+row["text"]
    new={x for x in technical_tokens(msg) if x not in source}
    if new:return False,"NEW_TECHNICAL_IDENTIFIER:"+sorted(new)[0]
    return True,"PASS"

def parse_backend(raw:bytes)->dict[str,Any]:
    if len(raw)>512*1024:raise ValueError("DIALOGUE_BACKEND_OUTPUT_TOO_LARGE")
    env=json.loads(raw.decode("utf-8","strict").strip(),strict=False)
    if not isinstance(env,dict):raise ValueError("DIALOGUE_BACKEND_ENVELOPE_INVALID")
    structured=env.get("structured_output")
    if isinstance(structured,str):structured=json.loads(structured)
    if not isinstance(structured,dict):
        response=env.get("response")
        if isinstance(response,str):structured=json.loads(response)
        elif isinstance(response,dict):structured=response
    if env.get("status")!="SUCCESS" or not isinstance(structured,dict):
        raise ValueError("DIALOGUE_BACKEND_NOT_SUCCESS")
    if structured.get("schema")!=MODEL_SCHEMA:
        raise ValueError("DIALOGUE_MODEL_SCHEMA_INVALID")
    return structured

def invoke_model(base:dict[str,Any],human:dict[str,Any],timeline:dict[str,Any],policy:dict[str,Any],backend_override:Path|None=None,persona:dict[str,Any]|None=None)->tuple[str|None,dict[str,Any]]:
    p=policy.get("provider") if isinstance(policy.get("provider"),dict) else {}
    backend=backend_override or Path(str(p.get("backend") or "/usr/local/bin/agy-dev"))
    if not backend.is_file() or not os.access(backend,os.X_OK):
        return None,{"status":"UNAVAILABLE","reason":"BACKEND_MISSING","attempts":[]}
    models=[str(x) for x in p.get("models") or [] if str(x)]
    timeout=max(15,min(120,int(p.get("timeout_seconds") or 75)))
    attempts=[]
    with tempfile.TemporaryDirectory(prefix="chacha-dialogue-") as td:
        wd=Path(td)
        agent=wd/".agents/agents/chacha-human-dialogue";agent.mkdir(parents=True)
        (agent/"agent.md").write_text(agent_markdown(),encoding="utf-8")
        schema=wd/"output.schema.json";schema.write_text(json.dumps(model_schema(),indent=2)+"\n",encoding="utf-8")
        env=os.environ.copy();env["CI"]="1";env["NO_COLOR"]="1"
        for model in models:
            try:
                proc=subprocess.run([
                  str(backend),"-p",build_prompt(base,human,timeline,policy,persona),
                  "--model",model,"--agent","chacha-human-dialogue",
                  "--output-format","json","--json-schema",str(schema),
                  "--print-timeout",f"{timeout}s","--sandbox"
                ],stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                  cwd=str(wd),env=env,check=False,timeout=timeout+15)
            except subprocess.TimeoutExpired:
                attempts.append({"model":model,"status":"FAILED","reason":"TIMEOUT"});continue
            if proc.returncode!=0:
                attempts.append({"model":model,"status":"FAILED","reason":"BACKEND_ERROR"});continue
            try:out=parse_backend(proc.stdout)
            except Exception as exc:
                attempts.append({"model":model,"status":"FAILED","reason":type(exc).__name__});continue
            msg=str(out.get("message") or "").strip()
            ok,reason=validate_rephrase(msg,base,timeline)
            if not ok:
                attempts.append({"model":model,"status":"REJECTED","reason":reason});continue
            return msg,{"status":"PASS","backend":"agy-dev","model":model,"attempts":attempts+[{"model":model,"status":"PASS"}],"sandbox":True,"tool_access":"NONE"}
    return None,{"status":"UNAVAILABLE","reason":"ALL_MODELS_FAILED_OR_REJECTED","attempts":attempts}

def orchestrate(base:dict[str,Any],human:dict[str,Any],timeline:dict[str,Any],policy:dict[str,Any],
                attestation:dict[str,Any]|None=None,backend_override:Path|None=None,
                persona:dict[str,Any]|None=None)->dict[str,Any]:
    if policy.get("schema")!=POLICY_SCHEMA:raise ValueError("DIALOGUE_POLICY_INVALID")
    if base.get("schema")!=BASE_SCHEMA:raise ValueError("DIALOGUE_BASE_RESPONSE_INVALID")
    out=dict(base)
    elig=provider_eligibility(policy,attestation)
    meta={
      "schema":"chacha.dev/dialogue-orchestrator-meta/v1",
      "provider_id":elig.get("provider_id"),"provider_eligible":bool(elig.get("eligible")),
      "provider_reason":elig.get("reason"),"provider_invoked":False,
      "mode":"DETERMINISTIC_BASE_RESPONSE","central_status_immutable":True,
      "central_next_action_immutable":True,"central_authority_preserved":True,
      "decision_modified":False,
      "speaker_persona_id":(persona or {}).get("persona_id") if isinstance(persona,dict) else None,
      "speaker_persona_applied":bool(persona_context(persona)),
      "automatic_external_spend_eur":0
    }
    if elig.get("eligible"):
        msg,runtime=invoke_model(base,human,timeline,policy,backend_override,persona)
        meta["provider_invoked"]=True;meta["runtime"]=runtime
        if msg:
            out["message"]=msg;meta["mode"]="MODEL_REPHRASE"
        else:
            meta["mode"]="DETERMINISTIC_FALLBACK_AFTER_PROVIDER"
    out["status"]=base.get("status")
    out["next_action"]=base.get("next_action")
    out["central_authority_preserved"]=True
    out["decision_modified"]=False
    out["dialogue_orchestrator"]=meta
    out["automatic_external_spend_eur"]=0
    return out

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--base",type=Path,required=True)
    ap.add_argument("--human-context",type=Path)
    ap.add_argument("--timeline",type=Path)
    ap.add_argument("--persona-card",type=Path)
    ap.add_argument("--policy",type=Path,required=True)
    ap.add_argument("--attestation",type=Path)
    ap.add_argument("--backend",type=Path)
    ap.add_argument("--output",type=Path,required=True)
    a=ap.parse_args()
    base=load(a.base);human=load(a.human_context,{}) if a.human_context else {};timeline=load(a.timeline,{}) if a.timeline else {}
    persona=load(a.persona_card,{}) if a.persona_card and a.persona_card.is_file() else {}
    policy=load(a.policy);att=load(a.attestation) if a.attestation and a.attestation.is_file() else None
    out=orchestrate(base,human,timeline,policy,att,a.backend,persona)
    save(a.output,out)
    print(json.dumps(out,ensure_ascii=False))
    print("CHACHA_DEV_V811_DIALOGUE_ORCHESTRATOR=PASS",file=os.sys.stderr)
    print("CHACHA_DEV_V811_AUTOMATIC_EXTERNAL_SPEND_EUR=0",file=os.sys.stderr)
    return 0

if __name__=="__main__":raise SystemExit(main())
