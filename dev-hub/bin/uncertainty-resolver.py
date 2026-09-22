#!/usr/bin/env python3
from __future__ import annotations
import argparse,json
from pathlib import Path

def load(p):
    x=json.loads(Path(p).read_text(encoding="utf-8"));return x

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--case",required=True);ap.add_argument("--policy",required=True);ap.add_argument("--output",required=True)
    a=ap.parse_args();case=load(a.case);policy=load(a.policy)
    confidence=float(case.get("confidence",0))
    sensitive=bool(case.get("sensitive_approval_boundary"))
    functional=bool(case.get("functional_preference_underdetermined"))
    methods=[x for x in policy.get("self_resolution_order") or [] if x not in set(case.get("exhausted_methods") or [])]
    if sensitive or functional or not methods:
        decision="ASK_HUMAN"
        next_action=None
    else:
        decision="RESOLVE_AUTONOMOUSLY"
        next_action=methods[0]
    result={"schema":"chacha.dev/uncertainty-resolution/v1","decision":decision,"confidence":confidence,
            "next_action":next_action,"assumptions":case.get("assumptions") or [],"unknowns":case.get("unknowns") or []}
    Path(a.output).write_text(json.dumps(result,indent=2)+"\n")
    print("CHACHA_UNCERTAINTY_RESOLVER=PASS")
    print("DECISION="+decision)
if __name__=="__main__":main()
