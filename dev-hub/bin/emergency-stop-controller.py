#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from pathlib import Path

DEFAULT_STATE=Path("/opt/chacha-dev/runtime/control/emergency-stop.json")
TRANSIENT_PREFIXES=("chacha-dev-branch@","chacha-dev-agent@","chacha-dev-preview@")

def now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())

def read_state(path:Path):
    try:
        x=json.loads(path.read_text(encoding="utf-8"))
        if isinstance(x,dict):return x
    except Exception:
        pass
    return {"active":False,"schema":"chacha.dev/emergency-stop-state/v1"}

def atomic_write(path:Path,value:dict):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(".tmp")
    tmp.write_text(json.dumps(value,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    os.replace(tmp,path)

def transient_units():
    p=subprocess.run(
        ["/usr/bin/systemctl","list-units","--type=service","--all","--no-legend","--no-pager"],
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=20
    )
    if p.returncode!=0:return []
    units=[]
    for line in p.stdout.splitlines():
        unit=line.split(None,1)[0] if line.split() else ""
        if any(unit.startswith(prefix) for prefix in TRANSIENT_PREFIXES):
            units.append(unit)
    return sorted(set(units))

def stop_units(units):
    stopped=[];failed=[]
    for unit in units:
        p=subprocess.run(["/usr/bin/systemctl","stop",unit],
                         stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=30)
        (stopped if p.returncode==0 else failed).append(unit)
    return stopped,failed

def activate(path:Path,reason:str,actor:str):
    units=transient_units()
    stopped,failed=stop_units(units)
    state={
        "schema":"chacha.dev/emergency-stop-state/v1",
        "active":True,
        "activated_at":now_iso(),
        "actor":actor,
        "reason":reason,
        "new_dispatch_blocked":True,
        "new_materialization_blocked":True,
        "core_frozen":True,
        "foundries_frozen":True,
        "persistent_collectors_preserved":True,
        "persistent_memory_preserved":True,
        "transient_units_seen":units,
        "transient_units_stopped":stopped,
        "transient_units_failed":failed
    }
    atomic_write(path,state)
    return state

def reset(path:Path,actor:str,reason:str):
    previous=read_state(path)
    state={
        "schema":"chacha.dev/emergency-stop-state/v1",
        "active":False,
        "reset_at":now_iso(),
        "actor":actor,
        "reason":reason,
        "previous_activation":previous.get("activated_at"),
        "health_check_required_before_resume":True,
        "resume_authorized":False
    }
    atomic_write(path,state)
    return state

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--state",type=Path,default=DEFAULT_STATE)
    sub=ap.add_subparsers(dest="cmd",required=True)
    a=sub.add_parser("activate");a.add_argument("--reason",required=True);a.add_argument("--actor",default="human-emergency-stop")
    r=sub.add_parser("reset");r.add_argument("--reason",required=True);r.add_argument("--actor",default="human-emergency-reset")
    sub.add_parser("status")
    args=ap.parse_args()
    if args.cmd=="activate":
        out=activate(args.state,args.reason,args.actor)
    elif args.cmd=="reset":
        out=reset(args.state,args.actor,args.reason)
    else:
        out=read_state(args.state)
    print(json.dumps(out,indent=2,ensure_ascii=False))
    if out.get("active"):print("CHACHA_DEV_EMERGENCY_STOP=ACTIVE")
    else:print("CHACHA_DEV_EMERGENCY_STOP=INACTIVE")

if __name__=="__main__":main()
