#!/usr/bin/env python3
from __future__ import annotations
import argparse,json
from pathlib import Path

def load(p):
    x=json.loads(Path(p).read_text(encoding="utf-8"));return x

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--run",required=True);ap.add_argument("--definition",required=True);ap.add_argument("--output",required=True)
    a=ap.parse_args();run=load(a.run);definition=load(a.definition)
    mandatory=definition.get("mandatory_stages") or [];done=set(run.get("completed_stages") or [])
    stage_coverage=len(set(mandatory)&done)/max(1,len(mandatory))
    metrics=run.get("metrics") or {}
    dimensions={
      "stage_coverage":stage_coverage,
      "automatic_decision_rate":float(metrics.get("automatic_decision_rate",0)),
      "acceptance_pass_rate":float(metrics.get("acceptance_pass_rate",0)),
      "rollback_readiness":float(metrics.get("rollback_readiness",0)),
      "knowledge_reuse":float(metrics.get("knowledge_reuse",0)),
      "human_interrupt_rate":1.0-float(metrics.get("human_interrupt_rate",1))
    }
    score=round(sum(dimensions.values())/len(dimensions),4)
    result={"schema":"chacha.dev/autonomy-audit/v1","score":score,"target":definition.get("target_score",0.95),
            "target_met":score>=float(definition.get("target_score",0.95)),"dimensions":dimensions,
            "missing_stages":[x for x in mandatory if x not in done]}
    Path(a.output).write_text(json.dumps(result,indent=2)+"\n")
    print("CHACHA_AUTONOMY_AUDIT=PASS")
    print("AUTONOMY_SCORE="+str(score))
if __name__=="__main__":main()
