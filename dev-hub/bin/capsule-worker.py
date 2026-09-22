#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,signal,time
from pathlib import Path

running=True
def stop(_sig,_frame):
    global running
    running=False

def write(path:Path,payload:dict):
    path.write_text(json.dumps(payload,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--manifest",required=True,type=Path)
    a=ap.parse_args()
    m=json.loads(a.manifest.read_text(encoding="utf-8"))
    workspace=a.manifest.parent
    state=workspace/"worker-state.json"
    signal.signal(signal.SIGTERM,stop)
    signal.signal(signal.SIGINT,stop)
    started=time.time()
    write(state,{"schema":"chacha.dev/capsule-worker-state/v1","branch_id":m["branch_id"],"state":"RUNNING","started_epoch":started})
    while running:
        time.sleep(1)
    write(state,{"schema":"chacha.dev/capsule-worker-state/v1","branch_id":m["branch_id"],"state":"STOPPED","started_epoch":started,"stopped_epoch":time.time()})
if __name__=="__main__":
    main()
