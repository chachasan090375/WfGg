#!/usr/bin/env python3
from __future__ import annotations
import argparse,datetime,json,math
from collections import defaultdict
from pathlib import Path
from typing import Any
POLICY_SCHEMA="chacha.dev/model-capability-confidence-policy/v1"
OBS_SCHEMA="chacha.dev/model-capability-observation/v1"
OUT_SCHEMA="chacha.dev/model-capability-confidence/v1"

def load(path:Path)->dict[str,Any]:
    v=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(v,dict):raise ValueError("JSON_ROOT_NOT_OBJECT")
    return v

def parse_time(v:str)->datetime.datetime:
    return datetime.datetime.fromisoformat(v.replace("Z","+00:00")).astimezone(datetime.timezone.utc)

def observations(path:Path)->list[dict[str,Any]]:
    out=[]
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():continue
        x=json.loads(line)
        if x.get("schema")!=OBS_SCHEMA:raise ValueError("OBS_SCHEMA_MISMATCH")
        out.append(x)
    return out
def compute(policy:dict[str,Any],obs:list[dict[str,Any]],now:datetime.datetime)->dict[str,Any]:
    if policy.get("schema")!=POLICY_SCHEMA:raise ValueError("POLICY_SCHEMA_MISMATCH")
    groups=defaultdict(list)
    for o in obs:groups[(str(o.get("model_id") or ""),str(o.get("capability") or ""))].append(o)
    rows=[]
    for (model,cap),items in sorted(groups.items()):
        passed=sum(1 for x in items if str(x.get("result"))=="PASS")
        newest=max(parse_time(str(x.get("observed_at"))) for x in items)
        age_days=max(0.0,(now-newest).total_seconds()/86400)
        raw=passed/len(items);sample_factor=min(1.0,len(items)/max(1,int(policy.get("minimum_samples") or 3)))
        fresh_days=float(policy.get("freshness_days") or 7);stale_days=float(policy.get("stale_days") or 30)
        if age_days<=fresh_days:fresh=1.0
        elif age_days>=stale_days:fresh=0.0
        else:fresh=1.0-(age_days-fresh_days)/(stale_days-fresh_days)
        score=round(raw*sample_factor*fresh,4)
        if age_days>=stale_days:state="STALE"
        elif score>=float(policy.get("verified_threshold") or .8):state="VERIFIED"
        elif score>=float(policy.get("provisional_threshold") or .6):state="PROVISIONAL"
        else:state="UNTRUSTED"
        rows.append({"model_id":model,"capability":cap,"samples":len(items),"pass_rate":round(raw,4),"age_days":round(age_days,2),"confidence":score,"state":state})
    return {"schema":OUT_SCHEMA,"status":"PASS","entries":rows,
            "execution_authority":False,"technology_watch_revalidation_required":True,
            "automatic_external_spend_eur":0}

def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument("--policy",type=Path,required=True)
    ap.add_argument("--observations",type=Path,required=True);ap.add_argument("--output",type=Path,required=True)
    a=ap.parse_args()
    try:
        out=compute(load(a.policy),observations(a.observations),datetime.datetime.now(datetime.timezone.utc))
        a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(out,indent=2,sort_keys=True)+"\n")
        print("CHACHA_DEV_MODEL_CAPABILITY_CONFIDENCE=PASS")
        print("EXECUTION_AUTHORITY=NO")
        print("AUTOMATIC_EXTERNAL_SPEND_EUR=0");return 0
    except Exception as exc:
        print("CHACHA_DEV_MODEL_CAPABILITY_CONFIDENCE=BLOCK reason="+str(exc));return 20

if __name__=="__main__":raise SystemExit(main())
