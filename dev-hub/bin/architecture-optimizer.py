#!/usr/bin/env python3
from __future__ import annotations
import argparse,json
from pathlib import Path

SCHEMA="chacha.dev/self-evolution/v1"

def load(p):
    x=json.loads(Path(p).read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise SystemExit("JSON_ROOT_NOT_OBJECT")
    return x

def weighted_score(metrics,weights):
    total=sum(float(weights.get(k,0)) for k in weights) or 1.0
    s=0.0
    for k,w in weights.items():
        v=float(metrics.get(k,0))
        if v<0 or v>100: raise ValueError("METRIC_OUT_OF_RANGE:"+k)
        s+=v*float(w)
    return round(s/total,4)

def hard_ok(candidate):
    hc=candidate.get("hard_constraints") or {}
    return all(bool(v) for v in hc.values()) if hc else True

def sensitive(candidate,policy):
    flags=set(candidate.get("approval_flags") or [])
    boundaries=set(policy.get("approval_boundaries") or [])
    return sorted(flags & boundaries)

def decide(current,candidates,policy):
    weights=policy.get("scoring") or {}
    current_score=weighted_score(current.get("metrics") or {},weights)
    evaluated=[]
    for c in candidates:
        row=dict(c)
        row["score"]=weighted_score(c.get("metrics") or {},weights)
        row["hard_constraints_ok"]=hard_ok(c)
        row["approval_required_for"]=sensitive(c,policy)
        row["eligible"]=row["hard_constraints_ok"] and not row["approval_required_for"]
        evaluated.append(row)
    eligible=[x for x in evaluated if x["eligible"]]
    eligible.sort(key=lambda x:(x["score"],str(x.get("id"))),reverse=True)
    ap=policy.get("auto_promotion") or {}
    min_gain=float(ap.get("minimum_score_gain",0))
    if not eligible:
        return {"decision":"KEEP_CURRENT","current_score":current_score,"reason":"no-policy-eligible-candidate","candidates":evaluated}
    best=eligible[0]
    gain=round(best["score"]-current_score,4)
    risk=str(best.get("risk_class") or "LOW")
    allowed=set(ap.get("allowed_risk_classes") or [])
    gates=best.get("gates") or {}
    fixtures=float(gates.get("fixture_pass_rate",0))
    canary=bool(gates.get("canary_ready"))
    rollback=bool(gates.get("rollback_ready"))
    evidence=bool(gates.get("evidence_ready"))
    promotable=(gain>=min_gain and risk in allowed and fixtures>=float(ap.get("minimum_fixture_pass_rate",1.0))
                and canary and rollback and evidence)
    return {
        "decision":"PROMOTE_CANARY" if promotable else "KEEP_CURRENT",
        "current_score":current_score,
        "candidate":best.get("id"),
        "candidate_score":best["score"],
        "score_gain":gain,
        "reason":"better-policy-qualified-candidate" if promotable else "candidate-did-not-pass-auto-promotion-gates",
        "candidates":evaluated
    }

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--policy",required=True)
    ap.add_argument("--input",required=True)
    ap.add_argument("--output",required=True)
    a=ap.parse_args()
    policy=load(a.policy);data=load(a.input)
    if policy.get("schema")!=SCHEMA:raise SystemExit("SELF_EVOLUTION_SCHEMA_INVALID")
    out=decide(data["current"],data.get("candidates") or [],policy)
    Path(a.output).write_text(json.dumps(out,indent=2)+"\n",encoding="utf-8")
    print("CHACHA_ARCHITECTURE_OPTIMIZER=PASS")
    print("DECISION="+out["decision"])

if __name__=="__main__":main()
