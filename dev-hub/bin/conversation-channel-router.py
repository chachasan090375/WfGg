#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,os,re,time,uuid
from pathlib import Path
from typing import Any

SCHEMA="chacha.dev/channel-route/v1"

def now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())

def save(path:Path,x:dict[str,Any]):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+".tmp")
    tmp.write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    os.replace(tmp,path)

BUILD_PATTERNS=[
 r"\bcr[ée]e(?:r|s|z)?\b",r"\bfabrique(?:r|s|z)?\b",r"\bd[ée]ploie(?:r|s|z)?\b",
 r"\binstalle(?:r|s|z)?\b",r"\bmodifie(?:r|s|z)?\b",r"\bpatch(?:e|er)?\b",
 r"\bprogramme(?:r|s|z)?\b",r"\bcode(?:r|s|z)?\b",r"\bconstruis\b",
 r"\bfais[- ]moi\b.*\b(?:appli|application|site|agent|script|module|apk|image|photo|vid[ée]o)\b"
]
RESEARCH_PATTERNS=[
 r"\brecherche\b",r"\bcherche\b",r"\btrouve[- ]moi\b",r"\bderni[èe]res?\b",
 r"\bactualit[ée]s?\b",r"\bcompare\b",r"\bquelles? solutions?\b",r"\bsource\b"
]
ADVISORY_PATTERNS=[
 r"\btu te souviens\b",r"\brappelle[- ]moi\b",r"\bm[ée]moire\b",
 r"\barchitecture\b",r"\bcentre humain\b",r"\bpersona\b",r"\bavis technique\b"
]

def any_match(text:str,patterns:list[str])->bool:
    t=text.casefold()
    return any(re.search(p,t,re.I) for p in patterns)

def route(channel:str,text:str,project_id:str)->dict[str,Any]:
    ch=str(channel or "BUILD").upper()
    if ch not in {"CONVERSATION","BUILD"}:raise ValueError("CHANNEL_INVALID")
    text=str(text or "").strip()
    if not text:raise ValueError("TEXT_REQUIRED")
    if ch=="BUILD":
        sub="BUILD_PIPELINE";reason="MANUAL_BUILD_CHANNEL"
    elif any_match(text,BUILD_PATTERNS):
        sub="BUILD_HANDOFF_REQUIRED";reason="CONVERSATION_MUTATION_GUARD"
    elif any_match(text,RESEARCH_PATTERNS):
        sub="RESEARCH";reason="INFORMATION_RESEARCH_REQUEST"
    elif any_match(text,ADVISORY_PATTERNS):
        sub="ADVISORY";reason="READ_ONLY_ADVISORY_REQUEST"
    else:
        sub="CHAT";reason="GENERAL_CONVERSATION"
    out={
      "schema":SCHEMA,"route_id":"route-"+uuid.uuid4().hex,
      "observed_at":now_iso(),"channel":ch,"subroute":sub,"reason":reason,
      "project_id":project_id,"user_text":text,
      "manual_channel_authoritative":True,
      "heavy_build_pipeline_allowed":ch=="BUILD",
      "scheduler_allowed":ch=="BUILD",
      "run_controller_allowed":ch=="BUILD",
      "foundry_allowed":ch=="BUILD",
      "mutation_allowed":ch=="BUILD",
      "automatic_channel_switch":False,
      "automatic_external_spend_eur":0
    }
    if sub=="BUILD_HANDOFF_REQUIRED":
        out["creation_brief"]={
          "schema":"chacha.dev/conversation-creation-brief/v1",
          "project_id":project_id,"source_channel":"CONVERSATION",
          "user_request":text,"requires_explicit_build_switch":True,
          "technical_plan_generated":False,"execution_started":False
        }
    return out

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--channel",required=True)
    ap.add_argument("--text",required=True)
    ap.add_argument("--project",default="chacha-dev-platform")
    ap.add_argument("--output",type=Path,required=True)
    a=ap.parse_args()
    out=route(a.channel,a.text,a.project);save(a.output,out)
    print(json.dumps(out,ensure_ascii=False))
    return 0

if __name__=="__main__":raise SystemExit(main())
