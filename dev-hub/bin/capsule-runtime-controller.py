#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,os,subprocess,time
from pathlib import Path
from typing import Any

DEFAULT_ROOT=Path("/opt/chacha-dev/runtime/capsules")
DEFAULT_STOP=Path("/opt/chacha-dev/runtime/control/emergency-stop.json")
DEFAULT_WORKER=Path("/opt/chacha-dev/platform/current/dev-hub/bin/capsule-worker.py")
DEFAULT_MATERIALIZATION_POLICY=Path("/opt/chacha-dev/platform/current/dev-hub/config/canonical-component-registry.v1.json")
DEFAULT_MATERIALIZATION_GATE=Path("/opt/chacha-dev/platform/current/dev-hub/bin/universal-materialization-gate.py")
DEFAULT_DYNAMIC_REGISTRY=Path("/opt/chacha-dev/runtime/canonical-registry/dynamic-components.json")

def load(p:Path)->dict[str,Any]:
    x=json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(x,dict): raise SystemExit("JSON_ROOT_NOT_OBJECT")
    return x

def save(p:Path,x:dict[str,Any]):
    p.parent.mkdir(parents=True,exist_ok=True)
    t=p.with_suffix(p.suffix+".tmp")
    t.write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    os.replace(t,p)

def stop_active(path:Path)->bool:
    try:return bool(load(path).get("active"))
    except Exception:return False

def unit_for(branch_id:str)->str:
    token=hashlib.sha256(branch_id.encode()).hexdigest()[:16]
    return f"chacha-dev-branch@{token}.service"

def run(argv:list[str],timeout:int=30)->subprocess.CompletedProcess[str]:
    return subprocess.run(argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=timeout)

def active(unit:str)->bool:
    p=run(["/usr/bin/systemctl","is-active",unit],10)
    return p.returncode==0 and p.stdout.strip()=="active"

def gate_call(args,mode:str,output:Path,manifest:Path|None=None,component_id:str|None=None)->dict[str,Any]:
    cmd=["/usr/bin/python3",str(args.materialization_gate),"--mode",mode,
         "--policy",str(args.materialization_policy),"--dynamic-registry",str(args.dynamic_registry),
         "--output",str(output)]
    if manifest is not None:cmd.extend(["--manifest",str(manifest)])
    if component_id:cmd.extend(["--component-id",component_id])
    p=run(cmd,30)
    if p.returncode!=0:raise SystemExit("CAPSULE_MATERIALIZATION_GATE_FAILED:"+(p.stderr or p.stdout)[-500:])
    try:x=load(output)
    except Exception:raise SystemExit("CAPSULE_MATERIALIZATION_GATE_RECEIPT_INVALID")
    if x.get("status")!="PASS":raise SystemExit("CAPSULE_MATERIALIZATION_GATE_NOT_PASS")
    return x

def materialize(args)->dict[str,Any]:
    if stop_active(args.emergency_state):
        raise SystemExit("CHACHA_DEV_EMERGENCY_STOP_ACTIVE")
    topo=load(args.topology); waves=load(args.wave_plan)
    by={str(x.get("branch_id")):x for x in topo.get("decisions") or [] if isinstance(x,dict)}
    wave=next((x for x in waves.get("waves") or [] if int(x.get("wave") or 0)==args.wave),None)
    if not wave: raise SystemExit("CAPSULE_WAVE_NOT_FOUND")
    root=args.runtime_root.resolve(); root.mkdir(parents=True,exist_ok=True)
    launched=[]
    for branch_id in wave.get("branches") or []:
        item=by.get(str(branch_id))
        if not item or not item.get("runtime_required"):
            raise SystemExit("CAPSULE_BRANCH_TOPOLOGY_INVALID:"+str(branch_id))
        rb=item.get("resource_budget") or {}
        mem=max(64,int(rb.get("memory_hard_limit_mb") or 64))
        cpu=max(1,min(10000,int(rb.get("cpu_weight") or 10)))
        tasks=max(1,int(rb.get("processes_max") or 1))
        unit=unit_for(str(branch_id))
        workspace=root/hashlib.sha256(str(branch_id).encode()).hexdigest()[:16]
        workspace.mkdir(parents=True,exist_ok=True)
        birth_input=workspace/"materialization-input.json";save(birth_input,item)
        gate_receipt=gate_call(args,"check" if args.dry_run else "register",
                               workspace/"materialization-gate.json",birth_input)
        gate_component_id=str(gate_receipt.get("component_id") or "")
        if not gate_component_id:raise SystemExit("CAPSULE_MATERIALIZATION_COMPONENT_ID_MISSING")
        manifest={
          "schema":"chacha.dev/runtime-capsule-manifest/v1","branch_id":str(branch_id),
          "unit":unit,"wave":args.wave,"ttl_seconds":args.ttl,
          "resource_budget":{"memory_hard_limit_mb":mem,"cpu_weight":cpu,"processes_max":tasks},
          "materialization_component_id":gate_component_id,
          "materialization_gate_status":"CHECK_ONLY" if args.dry_run else "REGISTERED_PENDING_ACTIVATION",
          "created_at":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())
        }
        mp=workspace/"manifest.json"; save(mp,manifest)
        cmd=[
          "/usr/bin/systemd-run","--unit="+unit,"--collect",
          "--property=MemoryMax="+str(mem)+"M",
          "--property=CPUWeight="+str(cpu),
          "--property=TasksMax="+str(tasks),
          "--property=RuntimeMaxSec="+str(max(30,args.ttl)),
          "--property=KillMode=mixed",
          "--working-directory="+str(workspace),
          "/usr/bin/python3",str(args.worker),"--manifest",str(mp)
        ]
        if args.dry_run:
            launched.append({**manifest,"workspace":str(workspace),"state":"DRY_RUN","command":cmd})
            continue
        p=run(cmd,30)
        if p.returncode!=0:
            raise SystemExit("CAPSULE_SYSTEMD_RUN_FAILED:"+p.stderr.strip()[-400:])
        ok=False
        for _ in range(20):
            if active(unit): ok=True; break
            time.sleep(0.25)
        if not ok: raise SystemExit("CAPSULE_NOT_ACTIVE:"+unit)
        active_receipt=gate_call(args,"activate",workspace/"materialization-activate.json",component_id=gate_component_id)
        launched.append({**manifest,"workspace":str(workspace),"state":"ACTIVE",
                         "materialization_gate_status":active_receipt.get("component_state")})
    registry={"schema":"chacha.dev/runtime-capsule-registry/v1","wave":args.wave,"capsules":launched,
              "emergency_stop_checked":True,"dry_run":bool(args.dry_run)}
    save(root/"registry.json",registry)
    return registry

def status(args)->dict[str,Any]:
    p=args.runtime_root.resolve()/"registry.json"
    r=load(p) if p.is_file() else {"schema":"chacha.dev/runtime-capsule-registry/v1","capsules":[]}
    rows=[]
    for c in r.get("capsules") or []:
        unit=str(c.get("unit") or "")
        rows.append({**c,"runtime_state":"DRY_RUN" if r.get("dry_run") else ("ACTIVE" if active(unit) else "INACTIVE")})
    return {"schema":"chacha.dev/runtime-capsule-status/v1","capsules":rows,"emergency_stop_active":stop_active(args.emergency_state)}

def teardown(args)->dict[str,Any]:
    p=args.runtime_root.resolve()/"registry.json"
    r=load(p) if p.is_file() else {"capsules":[]}
    out=[]
    for c in r.get("capsules") or []:
        unit=str(c.get("unit") or "")
        if unit:
            q=run(["/usr/bin/systemctl","stop",unit],30)
            stopped=q.returncode==0 or not active(unit)
            cid=str(c.get("materialization_component_id") or "")
            if stopped and cid:
                gate_call(args,"retire",args.runtime_root.resolve()/(hashlib.sha256(str(c.get("branch_id") or "").encode()).hexdigest()[:16])/"materialization-retire.json",component_id=cid)
            out.append({"unit":unit,"stopped":stopped,"materialization_component_id":cid or None,
                        "canonical_state":"RETIRED" if stopped and cid else None})
    return {"schema":"chacha.dev/runtime-capsule-teardown/v1","results":out}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--runtime-root",type=Path,default=DEFAULT_ROOT)
    ap.add_argument("--emergency-state",type=Path,default=DEFAULT_STOP)
    ap.add_argument("--materialization-policy",type=Path,default=DEFAULT_MATERIALIZATION_POLICY)
    ap.add_argument("--materialization-gate",type=Path,default=DEFAULT_MATERIALIZATION_GATE)
    ap.add_argument("--dynamic-registry",type=Path,default=DEFAULT_DYNAMIC_REGISTRY)
    sub=ap.add_subparsers(dest="cmd",required=True)
    m=sub.add_parser("materialize");m.add_argument("--topology",required=True,type=Path);m.add_argument("--wave-plan",required=True,type=Path)
    m.add_argument("--wave",type=int,default=1);m.add_argument("--ttl",type=int,default=120);m.add_argument("--worker",type=Path,default=DEFAULT_WORKER);m.add_argument("--dry-run",action="store_true")
    sub.add_parser("status");sub.add_parser("teardown")
    a=ap.parse_args()
    out=materialize(a) if a.cmd=="materialize" else (status(a) if a.cmd=="status" else teardown(a))
    print(json.dumps(out,indent=2,ensure_ascii=False))
    print("CHACHA_CAPSULE_RUNTIME_"+a.cmd.upper()+"=PASS")
if __name__=="__main__":
    main()
