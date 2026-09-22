#!/usr/bin/env python3
from __future__ import annotations
import argparse,json
from pathlib import Path
import technology_watch_runtime as tw

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--repo-root",type=Path,default=Path("."))
    sub=ap.add_subparsers(dest="cmd",required=True)
    sub.add_parser("refresh")
    c=sub.add_parser("consult")
    c.add_argument("--consumer",required=True,choices=["branch-foundry","agent-foundry","capability-foundry","architecture-optimizer","architecture-decision-council","reuse-memory"])
    c.add_argument("--domain",default="")
    c.add_argument("--capability",action="append",default=[])
    sub.add_parser("status")
    a=ap.parse_args()
    root=a.repo_root.resolve()
    if a.cmd=="refresh":
        out=tw.write_full_snapshot(root)
        print(json.dumps(out,indent=2,ensure_ascii=False))
        print("CHACHA_TECHNOLOGY_WATCH_REFRESH=PASS")
        print("AUTOMATIC_EXTERNAL_SPEND_EUR=0")
    elif a.cmd=="consult":
        out=tw.consult(root,consumer=a.consumer,domain=a.domain,capabilities=a.capability)
        print(json.dumps(out,indent=2,ensure_ascii=False))
        print("CHACHA_TECHNOLOGY_WATCH_CONSULT=PASS")
    else:
        out=tw.snapshot_status(root)
        print(json.dumps(out,indent=2,ensure_ascii=False))
        print("CHACHA_TECHNOLOGY_WATCH_STATUS="+str(out.get("state")))
if __name__=="__main__":
    main()
