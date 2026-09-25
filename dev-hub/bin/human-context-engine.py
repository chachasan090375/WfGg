#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,re,time
from pathlib import Path
from typing import Any

PROFILE_SCHEMA="chacha.dev/human-conversation-profile/v1"
CONTEXT_SCHEMA="chacha.dev/human-context-brief/v1"

def now_iso()->str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())

def load(path:Path,default=None):
    try:x=json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        if default is not None:return default
        raise
    if not isinstance(x,dict):raise ValueError("JSON_ROOT_NOT_OBJECT")
    return x

def normalize_profile(raw:dict[str,Any])->dict[str,Any]:
    allowed={
      "preferred_name","preferred_form_of_address","gender_identity","age_band",
      "languages","cultural_contexts","regional_contexts","conversation_register",
      "directness","verbosity","humor_level","voice_preferences"
    }
    out={"schema":PROFILE_SCHEMA,"explicit_opt_in":True}
    for k in allowed:
        if k not in raw:continue
        v=raw[k]
        if isinstance(v,str):
            v=v.strip()
            if v:out[k]=v[:300]
        elif isinstance(v,list):
            vals=[str(x).strip()[:120] for x in v if str(x).strip()]
            if vals:out[k]=vals[:20]
        elif isinstance(v,dict) and k=="voice_preferences":
            safe={}
            for kk,vv in v.items():
                if str(kk) in {"enabled","language","voice_style","speech_rate","pitch","auto_speak"}:
                    safe[str(kk)]=vv
            if safe:out[k]=safe
    return out

def explicit_signals(text:str)->dict[str,bool]:
    t=text.casefold()
    def anyp(patterns):
        return any(re.search(p,t) for p in patterns)
    return {
      "explicit_urgency":anyp([r"\burgent\b",r"\btout de suite\b",r"\brapidement\b",r"\bje suis press[ée]\b"]),
      "explicit_frustration":anyp([r"\bça m['’]énerve\b",r"\bje suis énerv[ée]\b",r"\bça me saoule\b",r"\bfrustr[ée]\b",r"\btu tournes en boucle\b"]),
      "explicit_enthusiasm":anyp([r"\bsuper\b",r"\bgénial\b",r"\bexcellent\b",r"\bparfait\b",r"\bj['’]adore\b"]),
      "explicit_uncertainty":anyp([r"\bje ne sais pas\b",r"\bje sais pas\b",r"\bje ne comprends pas\b",r"\bje comprends pas\b",r"\bpas sûr\b"]),
      "explicit_need_for_reassurance":anyp([r"\brassure[- ]moi\b",r"\bconfirme[- ]moi\b",r"\bje veux être sûr\b",r"\bj['’]ai besoin d['’]être sûr\b"])
    }

def build(profile:dict[str,Any],text:str)->dict[str,Any]:
    p=normalize_profile(profile)
    signals=explicit_signals(text)
    return {
      "schema":CONTEXT_SCHEMA,
      "created_at":now_iso(),
      "profile":p,
      "interaction_signals":{k:v for k,v in signals.items() if v},
      "rules":{
        "profile_is_user_declared":True,
        "no_protected_trait_inference":True,
        "no_voice_or_accent_demographic_inference":True,
        "no_psychological_diagnosis":True,
        "signals_are_ephemeral":True,
        "technical_decision_authority":False
      },
      "automatic_external_spend_eur":0
    }

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--profile",type=Path)
    ap.add_argument("--text",default="")
    ap.add_argument("--output",type=Path,required=True)
    a=ap.parse_args()
    profile=load(a.profile,{}) if a.profile else {}
    out=build(profile,a.text)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(out,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print("CHACHA_DEV_V810_HUMAN_CONTEXT=PASS")
    print("CHACHA_DEV_V810_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
    return 0

if __name__=="__main__":raise SystemExit(main())
