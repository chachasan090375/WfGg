#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,subprocess,tempfile
from pathlib import Path
from typing import Any
import dynamic_component_contracts as dcc

DEFAULT_POLICY=Path("/opt/chacha-dev/platform/current/dev-hub/config/guardian-runtime-policy.v1.json")
DEFAULT_CLIENT=Path("/opt/chacha-dev/platform/current/dev-hub/bin/guardian-client.py")

def load(path:Path)->dict[str,Any]:
    x=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise SystemExit("JSON_ROOT_NOT_OBJECT")
    return x

def save(path:Path,x:dict[str,Any]):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")

def collect(preplan:dict[str,Any],topology:dict[str,Any],capfoundry:dict[str,Any])->list[dict[str,Any]]:
    project_id=str(topology.get("project_id") or preplan.get("project_id") or "")
    pkgmap={str(x.get("id")):x for x in preplan.get("packages") or [] if isinstance(x,dict)}
    created_domains={str(x.get("owner_domain")) for x in capfoundry.get("plans") or [] if isinstance(x,dict) and x.get("create_domain")}
    rows=[]
    for row in topology.get("decisions") or []:
        if not isinstance(row,dict): continue
        pid=str(row.get("package_id") or "")
        pkg=pkgmap.get(pid) or {}
        caps=[str(x) for x in pkg.get("capabilities") or []]
        # Logical branch contracts exist for every non-memory-only branch. Runtime-required
        # branches are the primary execution target; reusable virtual branches are still governed.
        if str(row.get("decision") or "")!="MEMORY_ONLY":
            rows.append(dcc.build_branch_contract(row=row,project_id=project_id,capabilities=caps))
        dedicated=str(row.get("orchestrator_strategy") or "")=="DEDICATED_EPHEMERAL"
        generated_domain=str(row.get("domain") or "") in created_domains
        if dedicated or generated_domain:
            oid=f"{row.get('branch_id')}:orchestrator"
            rows.append(dcc.build_orchestrator_contract(
              component_id=oid,project_id=project_id,domain=str(row.get("domain") or ""),
              package_id=pid,capabilities=caps,
              source="branch-foundry" if dedicated else "capability-foundry"
            ))
    return rows

def register(contract:dict[str,Any],client:Path,policy:Path)->dict[str,Any]:
    with tempfile.TemporaryDirectory(prefix="chacha-component-contract-") as td:
        p=Path(td)/"contract.json";p.write_text(json.dumps(contract,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
        q=subprocess.run(
          ["/usr/bin/python3",str(client),"--policy",str(policy),"register-component-contract","--contract",str(p)],
          stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=30
        )
    try:result=json.loads(q.stdout.strip())
    except Exception:result={"status":"UNAVAILABLE","stdout":q.stdout[-500:],"stderr":q.stderr[-500:]}
    if q.returncode!=0 or result.get("status")!="PASS":
        raise RuntimeError("GUARDIAN_DYNAMIC_COMPONENT_CONTRACT_REGISTRATION_FAILED:"+str(result))
    return result

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--preplan",type=Path,required=True)
    ap.add_argument("--branch-topology",type=Path,required=True)
    ap.add_argument("--capability-foundry",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    ap.add_argument("--client",type=Path,default=DEFAULT_CLIENT)
    ap.add_argument("--policy",type=Path,default=DEFAULT_POLICY)
    ap.add_argument("--register",action="store_true")
    a=ap.parse_args()
    contracts=collect(load(a.preplan),load(a.branch_topology),load(a.capability_foundry))
    regs=[register(c,a.client,a.policy) for c in contracts] if a.register else []
    kinds={}
    for c in contracts:kinds[c["component_kind"]]=kinds.get(c["component_kind"],0)+1
    out={
      "schema":"chacha.dev/dynamic-component-role-contract-batch/v1",
      "contract_count":len(contracts),"kinds":kinds,"contracts":contracts,"registrations":regs,
      "registered":bool(a.register),"all_registered":bool((not a.register) or len(regs)==len(contracts)),
      "automatic_external_spend_eur":0
    }
    save(a.output,out)
    print("CHACHA_DEV_DYNAMIC_COMPONENT_ROLE_CONTRACTS=PASS")
    print("CONTRACT_COUNT="+str(len(contracts)))
    print("BRANCH_CONTRACTS="+str(kinds.get("branch",0)))
    print("ORCHESTRATOR_CONTRACTS="+str(kinds.get("orchestrator",0)))
    print("REGISTERED="+("YES" if a.register else "NO"))

if __name__=="__main__":main()
