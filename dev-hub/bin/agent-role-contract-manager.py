#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,subprocess,tempfile
from pathlib import Path
from typing import Any

REPO_ROOT=Path(__file__).resolve().parents[2]
DEFAULT_POLICY=REPO_ROOT/"dev-hub/config/guardian-runtime-policy.v1.json"
DEFAULT_CLIENT=REPO_ROOT/"dev-hub/bin/guardian-client.py"
DEFAULT_MATERIALIZATION_POLICY=REPO_ROOT/"dev-hub/config/canonical-component-registry.v1.json"
DEFAULT_MATERIALIZATION_GATE=REPO_ROOT/"dev-hub/bin/universal-materialization-gate.py"
DEFAULT_DYNAMIC_REGISTRY=Path("/opt/chacha-dev/runtime/canonical-registry/dynamic-components.json")

def load(path:Path)->dict[str,Any]:
    x=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise SystemExit("JSON_ROOT_NOT_OBJECT")
    return x

def save(path:Path,x:dict[str,Any]):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")

def collect(topology:dict[str,Any])->list[dict[str,Any]]:
    rows=[]
    for d in topology.get("decisions") or []:
        if not isinstance(d,dict):continue
        manifest=d.get("manifest")
        if not isinstance(manifest,dict):continue
        contract=manifest.get("guardian_role_contract")
        if not isinstance(contract,dict):continue
        rows.append({"manifest":manifest,"contract":contract})
    return rows

def materialization_gate(manifest:dict[str,Any],mode:str,gate:Path,policy:Path,dynamic:Path,component_id:str|None=None)->dict[str,Any]:
    with tempfile.TemporaryDirectory(prefix="chacha-agent-materialization-") as td:
        td=Path(td);mp=td/"manifest.json";out=td/"receipt.json"
        cmd=["/usr/bin/python3",str(gate),"--mode",mode,"--policy",str(policy),
             "--dynamic-registry",str(dynamic),"--output",str(out)]
        if mode in {"check","register"}:
            mp.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
            cmd.extend(["--manifest",str(mp)])
        elif component_id:
            cmd.extend(["--component-id",component_id])
        q=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=30)
        if q.returncode!=0 or not out.is_file():
            raise RuntimeError("UNIVERSAL_MATERIALIZATION_GATE_FAILED:"+(q.stderr or q.stdout)[-500:])
        x=json.loads(out.read_text(encoding="utf-8"))
        if x.get("status")!="PASS":raise RuntimeError("UNIVERSAL_MATERIALIZATION_GATE_NOT_PASS:"+str(x))
        return x

def register(contract:dict[str,Any],client:Path,policy:Path)->dict[str,Any]:
    with tempfile.TemporaryDirectory(prefix="chacha-agent-contract-") as td:
        p=Path(td)/"contract.json"
        p.write_text(json.dumps(contract,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        q=subprocess.run(
          ["/usr/bin/python3",str(client),"--policy",str(policy),"register-contract","--contract",str(p)],
          stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=30
        )
    try:result=json.loads(q.stdout.strip())
    except Exception:
        result={"status":"UNAVAILABLE","stdout":q.stdout[-500:],"stderr":q.stderr[-500:]}
    if q.returncode!=0 or result.get("status")!="PASS":
        raise RuntimeError("GUARDIAN_DYNAMIC_CONTRACT_REGISTRATION_FAILED:"+str(result))
    return result

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--agent-topology",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    ap.add_argument("--client",type=Path,default=DEFAULT_CLIENT)
    ap.add_argument("--policy",type=Path,default=DEFAULT_POLICY)
    ap.add_argument("--materialization-policy",type=Path,default=DEFAULT_MATERIALIZATION_POLICY)
    ap.add_argument("--materialization-gate",type=Path,default=DEFAULT_MATERIALIZATION_GATE)
    ap.add_argument("--dynamic-registry",type=Path,default=DEFAULT_DYNAMIC_REGISTRY)
    ap.add_argument("--register",action="store_true")
    a=ap.parse_args()
    topo=load(a.agent_topology)
    rows=collect(topo)
    registrations=[];materialization=[]
    for row in rows:
        manifest=row["manifest"];contract=row["contract"]
        if not a.register:
            materialization.append(materialization_gate(manifest,"check",a.materialization_gate,a.materialization_policy,a.dynamic_registry))
            continue
        gate=materialization_gate(manifest,"register",a.materialization_gate,a.materialization_policy,a.dynamic_registry)
        cid=str(gate.get("component_id") or "")
        try:
            guardian=register(contract,a.client,a.policy)
        except Exception:
            if cid:materialization_gate({},"retire",a.materialization_gate,a.materialization_policy,a.dynamic_registry,cid)
            raise
        active=materialization_gate({},"activate",a.materialization_gate,a.materialization_policy,a.dynamic_registry,cid)
        registrations.append(guardian);materialization.append({"register":gate,"activate":active})
    out={
      "schema":"chacha.dev/dynamic-agent-role-contract-batch/v1",
      "project_id":topo.get("project_id"),
      "contract_count":len(rows),
      "contracts":[x["contract"] for x in rows],
      "registrations":registrations,
      "materialization":materialization,
      "registered":bool(a.register),
      "all_registered":bool((not a.register) or len(registrations)==len(rows)),
      "automatic_external_spend_eur":0
    }
    save(a.output,out)
    print("CHACHA_DEV_DYNAMIC_AGENT_ROLE_CONTRACTS=PASS")
    print("CONTRACT_COUNT="+str(len(rows)))
    print("REGISTERED="+("YES" if a.register else "NO"))

if __name__=="__main__":
    main()
