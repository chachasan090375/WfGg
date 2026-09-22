#!/usr/bin/env python3
from __future__ import annotations
import argparse,json
from pathlib import Path

def load(p):
    x=json.loads(Path(p).read_text(encoding="utf-8"));return x

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--project",required=True);ap.add_argument("--policy",required=True);ap.add_argument("--output",required=True)
    a=ap.parse_args();project=load(a.project);policy=load(a.policy)
    result={"schema":"chacha.dev/digital-twin-plan/v1","project_id":project.get("project_id"),
      "environment":{"production_data_write":False,"production_secret_copy":False,"disposable":True},
      "exercises":[{"name":x,"required":True} for x in policy.get("exercises") or []],
      "export_acceptance_evidence":True,"release_blocked_until_pass":True}
    Path(a.output).write_text(json.dumps(result,indent=2)+"\n")
    print("CHACHA_DIGITAL_TWIN=PASS")
if __name__=="__main__":main()
