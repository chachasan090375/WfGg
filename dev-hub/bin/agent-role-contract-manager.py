#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,subprocess,tempfile
from pathlib import Path
from typing import Any

DEFAULT_POLICY=Path("/opt/chacha-dev/platform/current/dev-hub/config/guardian-runtime-policy.v1.json")
DEFAULT_CLIENT=Path("/opt/chacha-dev/platform/current/dev-hub/bin/guardian-client.py")

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
        rows.append(contract)
    return rows

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
    ap.add_argument("--register",action="store_true")
    a=ap.parse_args()
    topo=load(a.agent_topology)
    contracts=collect(topo)
    registrations=[]
    if a.register:
        for contract in contracts:
            registrations.append(register(contract,a.client,a.policy))
    out={
      "schema":"chacha.dev/dynamic-agent-role-contract-batch/v1",
      "project_id":topo.get("project_id"),
      "contract_count":len(contracts),
      "contracts":contracts,
      "registrations":registrations,
      "registered":bool(a.register),
      "all_registered":bool((not a.register) or len(registrations)==len(contracts)),
      "automatic_external_spend_eur":0
    }
    save(a.output,out)
    print("CHACHA_DEV_DYNAMIC_AGENT_ROLE_CONTRACTS=PASS")
    print("CONTRACT_COUNT="+str(len(contracts)))
    print("REGISTERED="+("YES" if a.register else "NO"))

if __name__=="__main__":
    main()
