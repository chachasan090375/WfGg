#!/usr/bin/env python3
from __future__ import annotations
import argparse,copy,json
from pathlib import Path
from typing import Any
SCHEMA="chacha.dev/technology-source-reputation/v1"
def load(path:Path)->dict[str,Any]:
    x=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise SystemExit("JSON_ROOT_NOT_OBJECT:"+str(path))
    return x
def save(path:Path,x:dict[str,Any])->None:
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
def confidence(confirmed:float,contradicted:float)->float:
    total=confirmed+contradicted
    return round(100.0*confirmed/total,1) if total>0 else 50.0
def profile_confidence(registry:dict[str,Any],publisher:str,claim_class:str|None=None)->float:
    priors=registry.get("priors") or {"confirmed":1,"contradicted":1}
    p=(registry.get("publishers") or {}).get(publisher) or {}
    if claim_class:
        cls=(p.get("by_claim_class") or {}).get(claim_class) or {}
        if float(cls.get("confirmed",0))+float(cls.get("contradicted",0))>0:
            return confidence(float(priors.get("confirmed",1))+float(cls.get("confirmed",0)),
                              float(priors.get("contradicted",1))+float(cls.get("contradicted",0)))
    return confidence(float(priors.get("confirmed",1))+float(p.get("confirmed",0)),
                      float(priors.get("contradicted",1))+float(p.get("contradicted",0)))
def apply_event(registry:dict[str,Any],event:dict[str,Any])->dict[str,Any]:
    out=copy.deepcopy(registry)
    if out.get("schema")!=SCHEMA:raise ValueError("SOURCE_REPUTATION_SCHEMA_INVALID")
    publisher=str(event.get("publisher") or "").strip();outcome=str(event.get("outcome") or "").upper()
    claim_class=str(event.get("claim_class") or "general");evidence_ref=str(event.get("evidence_ref") or "")
    if not publisher or not evidence_ref:raise ValueError("SOURCE_REPUTATION_PROVENANCE_REQUIRED")
    weights=(out.get("event_weights") or {}).get(outcome)
    if not isinstance(weights,dict):raise ValueError("SOURCE_REPUTATION_OUTCOME_UNKNOWN:"+outcome)
    row=out.setdefault("publishers",{}).setdefault(publisher,{"confirmed":0.0,"contradicted":0.0,"events":0,"by_claim_class":{}})
    row["confirmed"]=float(row.get("confirmed",0))+float(weights.get("confirmed",0))
    row["contradicted"]=float(row.get("contradicted",0))+float(weights.get("contradicted",0))
    row["events"]=int(row.get("events",0))+1
    cls=row.setdefault("by_claim_class",{}).setdefault(claim_class,{"confirmed":0.0,"contradicted":0.0,"events":0})
    cls["confirmed"]=float(cls.get("confirmed",0))+float(weights.get("confirmed",0))
    cls["contradicted"]=float(cls.get("contradicted",0))+float(weights.get("contradicted",0))
    cls["events"]=int(cls.get("events",0))+1
    row["confidence"]=profile_confidence(out,publisher);cls["confidence"]=profile_confidence(out,publisher,claim_class)
    row.setdefault("recent_evidence_refs",[]).append(evidence_ref);row["recent_evidence_refs"]=row["recent_evidence_refs"][-20:]
    return out
def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument("--registry",type=Path,required=True);ap.add_argument("--event",type=Path,required=True);ap.add_argument("--output",type=Path,required=True);a=ap.parse_args()
    out=apply_event(load(a.registry),load(a.event));save(a.output,out);event=load(a.event);publisher=str(event.get("publisher"))
    print(json.dumps({"publisher":publisher,"confidence":profile_confidence(out,publisher),"automatic_external_spend_eur":0},ensure_ascii=False))
    print("CHACHA_DEV_V645_SOURCE_REPUTATION_UPDATE=PASS");print("CHACHA_DEV_V645_AUTOMATIC_EXTERNAL_SPEND_EUR=0");return 0
if __name__=="__main__":raise SystemExit(main())
