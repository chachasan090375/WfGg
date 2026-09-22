#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

def load(path:Path)->dict[str,Any]:
    x=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise SystemExit("JSON_ROOT_NOT_OBJECT")
    return x

def fits(wave:dict[str,Any],item:dict[str,Any],limits:dict[str,int])->bool:
    r=item.get("resource_budget") or {}
    return (
        wave["memory_mb"]+int(r.get("memory_hard_limit_mb") or 0) <= limits["memory_mb"]
        and wave["disk_mb"]+int(r.get("disk_soft_limit_mb") or 0) <= limits["disk_mb"]
        and wave["cpu_weight"]+int(r.get("cpu_weight") or 0) <= limits["cpu_weight"]
        and wave["processes"]+int(r.get("processes_max") or 0) <= limits["processes"]
        and len(wave["branches"]) < limits["parallel_capsules"]
    )

def schedule(topology:dict[str,Any],policy:dict[str,Any])->dict[str,Any]:
    budget=(policy.get("runtime_capsules") or {}).get("global_runtime_budget") or {}
    limits={
        "memory_mb":int(budget.get("memory_hard_limit_mb") or 1024),
        "disk_mb":int(budget.get("active_disk_soft_limit_mb") or 2048),
        "cpu_weight":int(budget.get("cpu_weight") or 100),
        "processes":int(budget.get("processes_max") or 3),
        "parallel_capsules":int(budget.get("maximum_parallel_capsules") or 2),
    }
    items=[x for x in topology.get("decisions") or [] if x.get("runtime_required")]
    items.sort(key=lambda x:int((x.get("resource_budget") or {}).get("memory_hard_limit_mb") or 0),reverse=True)
    waves=[]
    unschedulable=[]
    for item in items:
        placed=False
        for wave in waves:
            if fits(wave,item,limits):
                wave["branches"].append(item["branch_id"])
                r=item.get("resource_budget") or {}
                wave["memory_mb"]+=int(r.get("memory_hard_limit_mb") or 0)
                wave["disk_mb"]+=int(r.get("disk_soft_limit_mb") or 0)
                wave["cpu_weight"]+=int(r.get("cpu_weight") or 0)
                wave["processes"]+=int(r.get("processes_max") or 0)
                placed=True;break
        if not placed:
            empty={"wave":len(waves)+1,"branches":[],"memory_mb":0,"disk_mb":0,"cpu_weight":0,"processes":0}
            if fits(empty,item,limits):
                r=item.get("resource_budget") or {}
                empty["branches"]=[item["branch_id"]]
                empty["memory_mb"]=int(r.get("memory_hard_limit_mb") or 0)
                empty["disk_mb"]=int(r.get("disk_soft_limit_mb") or 0)
                empty["cpu_weight"]=int(r.get("cpu_weight") or 0)
                empty["processes"]=int(r.get("processes_max") or 0)
                waves.append(empty)
            else:
                unschedulable.append({
                    "branch_id":item.get("branch_id"),
                    "resource_budget":item.get("resource_budget"),
                    "reason":"BRANCH_EXCEEDS_GLOBAL_RUNTIME_BUDGET"
                })
    return {
        "schema":"chacha.dev/runtime-wave-plan/v1",
        "limits":limits,
        "waves":waves,
        "wave_count":len(waves),
        "unschedulable":unschedulable,
        "schedulable":not unschedulable,
        "memory_only_branches":[x.get("branch_id") for x in topology.get("decisions") or [] if x.get("decision")=="MEMORY_ONLY"]
    }

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--topology",required=True,type=Path)
    ap.add_argument("--policy",required=True,type=Path)
    ap.add_argument("--output",required=True,type=Path)
    a=ap.parse_args()
    out=schedule(load(a.topology),load(a.policy))
    a.output.write_text(json.dumps(out,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print("CHACHA_CAPSULE_SCHEDULER=PASS")
    print("WAVES="+str(out["wave_count"]))
    print("SCHEDULABLE="+("YES" if out["schedulable"] else "NO"))
    if not out["schedulable"]:raise SystemExit(2)

if __name__=="__main__":main()
