#!/usr/bin/env python3
from __future__ import annotations
import argparse,json
from pathlib import Path

WEIGHTS={"functional_quality":25,"correctness":20,"reliability":15,"security":12,"latency":6,"resource_use":6,"cost":6,"maintainability":5,"evidence_quality":5}

def load(p):
    x=json.loads(Path(p).read_text(encoding="utf-8"));return x

def score(m):
    return round(sum(float(m.get(k,0))*w for k,w in WEIGHTS.items())/sum(WEIGHTS.values()),4)

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--input",required=True);ap.add_argument("--output",required=True)
    a=ap.parse_args();data=load(a.input)
    rows=[]
    for c in data.get("candidates") or []:
        r=dict(c);r["score"]=score(c.get("metrics") or {});r["eligible"]=all((c.get("hard_constraints") or {}).values()) if c.get("hard_constraints") else True;rows.append(r)
    eligible=sorted([r for r in rows if r["eligible"]],key=lambda r:(r["score"],str(r.get("id"))),reverse=True)
    winner=eligible[0] if eligible else None
    result={"schema":"chacha.dev/competition-arena-result/v1","arena":data.get("arena"),
            "winner":winner.get("id") if winner else None,"winner_score":winner.get("score") if winner else None,
            "candidates":rows,"canary_required":bool(winner)}
    Path(a.output).write_text(json.dumps(result,indent=2)+"\n")
    print("CHACHA_COMPETITION_ARENA=PASS")
    print("WINNER="+str(result["winner"]))
if __name__=="__main__":main()
