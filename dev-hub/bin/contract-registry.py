#!/usr/bin/env python3
from __future__ import annotations
import argparse,json
from pathlib import Path

def load(p):
    x=json.loads(Path(p).read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise SystemExit("JSON_ROOT_NOT_OBJECT")
    return x

def fields(items):
    out={}
    for x in items or []:
        if isinstance(x,str):out[x]="any"
        elif isinstance(x,dict) and x.get("name"):out[str(x["name"])]=str(x.get("type") or "any")
    return out

def reconcile_bundle(bundle):
    contracts=bundle.get("contracts") or []
    producers={};mismatches=[]
    for c in contracts:
        if not isinstance(c,dict):continue
        for k,t in fields(c.get("outputs")).items():
            producers.setdefault(k,[]).append((c.get("contract_id"),t))
    for c in contracts:
        if not isinstance(c,dict):continue
        for k,t in fields(c.get("inputs")).items():
            options=producers.get(k) or []
            if not options:
                mismatches.append({"consumer":c.get("contract_id"),"field":k,"reason":"MISSING_PRODUCER"})
                continue
            if t!="any" and not any(pt in ("any",t) for _,pt in options):
                mismatches.append({"consumer":c.get("contract_id"),"field":k,"reason":"TYPE_MISMATCH","expected":t,"producers":options})
    return {"schema":"chacha.dev/contract-reconciliation/v1","mode":"IO_CONTRACTS","contracts":len(contracts),
            "mismatches":mismatches,"compatible":not mismatches,"assembly_allowed":not mismatches}

def reconcile_dynamic(plan,component_batch):
    packages=[x for x in (plan.get("packages") or []) if isinstance(x,dict) and x.get("runtime_required") is True]
    contracts=[x for x in (component_batch.get("contracts") or []) if isinstance(x,dict) and x.get("component_kind")=="branch"]
    by_pkg={str(x.get("package_id") or ""):x for x in contracts if x.get("package_id")}
    mismatches=[]
    checked=0
    for pkg in packages:
        pid=str(pkg.get("id") or "")
        c=by_pkg.get(pid)
        if not c:
            mismatches.append({"package_id":pid,"reason":"MISSING_COMPONENT_CONTRACT"});continue
        checked+=1
        branch_id=str(pkg.get("branch_id") or "")
        if branch_id and str(c.get("component_id") or "")!=branch_id:
            mismatches.append({"package_id":pid,"reason":"BRANCH_ID_MISMATCH","expected":branch_id,"actual":c.get("component_id")})
        required=set(str(x) for x in (pkg.get("capabilities") or []))
        allowed=set(str(x) for x in (c.get("allowed_capabilities") or []))
        missing=sorted(required-allowed)
        if missing:
            mismatches.append({"package_id":pid,"reason":"CAPABILITY_CONTRACT_GAP","missing_capabilities":missing})
        if c.get("production_permissions_allowed") is not False:
            mismatches.append({"package_id":pid,"reason":"UNEXPECTED_PRODUCTION_PERMISSION"})
        if float(c.get("automatic_external_spend_eur") or 0)!=0:
            mismatches.append({"package_id":pid,"reason":"NONZERO_AUTOMATIC_EXTERNAL_SPEND"})
    return {
      "schema":"chacha.dev/contract-reconciliation/v1",
      "mode":"DYNAMIC_COMPONENT_ROLE_CONTRACTS",
      "contracts":len(contracts),"runtime_packages":len(packages),"checked_packages":checked,
      "mismatches":mismatches,"compatible":not mismatches,"assembly_allowed":not mismatches,
      "direct_mutation":False,"architecture_council_final_authority":True,"automatic_external_spend_eur":0
    }

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--bundle");ap.add_argument("--plan");ap.add_argument("--component-contracts");ap.add_argument("--project-id");ap.add_argument("--output",required=True)
    a=ap.parse_args()
    if a.bundle:
        if a.plan or a.component_contracts:raise SystemExit("CONTRACT_REGISTRY_MODE_CONFLICT")
        result=reconcile_bundle(load(a.bundle))
    else:
        if not a.plan or not a.component_contracts:raise SystemExit("CONTRACT_REGISTRY_DYNAMIC_INPUTS_REQUIRED")
        result=reconcile_dynamic(load(a.plan),load(a.component_contracts))
    if a.project_id: result["project_id"]=str(a.project_id)
    Path(a.output).write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print("CHACHA_CONTRACT_REGISTRY=PASS")
    print("CONTRACTS_COMPATIBLE="+("YES" if result["compatible"] else "NO"))
    print("ASSEMBLY_ALLOWED="+("YES" if result["assembly_allowed"] else "NO"))
if __name__=="__main__":main()
