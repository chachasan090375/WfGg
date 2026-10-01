#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,math
from collections import defaultdict
from pathlib import Path
from typing import Any

POLICY_SCHEMA="chacha.dev/cognitive-route-outcome-learning-policy/v1"
EVENT_SCHEMA="chacha.dev/cognitive-route-outcome/v1"
OUTPUT_SCHEMA="chacha.dev/cognitive-route-learning-summary/v1"

def load(path:Path)->dict[str,Any]:
    v=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(v,dict): raise ValueError("JSON_ROOT_NOT_OBJECT")
    return v

def load_events(path:Path)->list[dict[str,Any]]:
    out=[]
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip(): continue
        x=json.loads(line)
        if x.get("schema")!=EVENT_SCHEMA: raise ValueError("EVENT_SCHEMA_MISMATCH")
        out.append(x)
    return out
def percentile(values:list[float],q:float)->float:
    if not values:return 0.0
    xs=sorted(values);pos=(len(xs)-1)*q;lo=math.floor(pos);hi=math.ceil(pos)
    if lo==hi:return float(xs[lo])
    return float(xs[lo]+(xs[hi]-xs[lo])*(pos-lo))

def summarize(policy:dict[str,Any],events:list[dict[str,Any]])->dict[str,Any]:
    if policy.get("schema")!=POLICY_SCHEMA: raise ValueError("POLICY_SCHEMA_MISMATCH")
    if int(policy.get("automatic_external_spend_eur",-1))!=0: raise ValueError("NONZERO_SPEND_POLICY")
    groups=defaultdict(list)
    for e in events:
        groups[(str(e.get("model_id") or ""),str(e.get("task_class") or ""))].append(e)
    rows=[]
    for (model,task),items in sorted(groups.items()):
        passed=sum(1 for x in items if str(x.get("status"))=="PASS")
        rate=passed/len(items);p95=percentile([float(x.get("latency_seconds") or 0) for x in items],0.95)
        min_samples=int(policy.get("minimum_samples") or 3)
        if len(items)<min_samples:rec="HOLD_INSUFFICIENT_EVIDENCE"
        elif rate<float(policy.get("degradation_pass_rate") or .75):rec="DEGRADE_CANDIDATE"
        elif rate>=float(policy.get("promotion_pass_rate") or .95) and p95<=float(policy.get("latency_target_seconds") or 15):rec="PROMOTION_CANDIDATE"
        else:rec="HOLD"
        rows.append({"model_id":model,"task_class":task,"samples":len(items),"pass_rate":round(rate,4),"p95_latency_seconds":round(p95,3),"recommendation":rec})
    return {"schema":OUTPUT_SCHEMA,"status":"PASS","groups":rows,
            "router_mutation_authorized":False,"registry_mutation_authorized":False,
            "technology_watch_revalidation_required":True,"automatic_external_spend_eur":0}

def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument("--policy",type=Path,required=True)
    ap.add_argument("--events",type=Path,required=True);ap.add_argument("--output",type=Path,required=True)
    a=ap.parse_args()
    try:
        out=summarize(load(a.policy),load_events(a.events));a.output.parent.mkdir(parents=True,exist_ok=True)
        a.output.write_text(json.dumps(out,indent=2,sort_keys=True)+"\n",encoding="utf-8")
        print("CHACHA_DEV_COGNITIVE_ROUTE_OUTCOME_LEARNING=PASS")
        print("ROUTER_MUTATION_AUTHORIZED=NO")
        print("AUTOMATIC_EXTERNAL_SPEND_EUR=0")
        return 0
    except Exception as exc:
        print("CHACHA_DEV_COGNITIVE_ROUTE_OUTCOME_LEARNING=BLOCK reason="+str(exc));return 20

if __name__=="__main__": raise SystemExit(main())
