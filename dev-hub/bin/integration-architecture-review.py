#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,hashlib
from pathlib import Path

def load(p):
    x=json.loads(Path(p).read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise SystemExit("JSON_ROOT_NOT_OBJECT")
    return x
def canonical(x):return json.dumps(x,sort_keys=True,ensure_ascii=False,separators=(",",":")).encode()
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--plan",required=True);ap.add_argument("--contract-reconciliation",required=True)
    ap.add_argument("--component-contracts",required=True);ap.add_argument("--architecture-council",required=True)
    ap.add_argument("--project-id");ap.add_argument("--output",required=True);a=ap.parse_args()
    plan=load(a.plan);rec=load(a.contract_reconciliation);batch=load(a.component_contracts);council=load(a.architecture_council)
    contracts=[x for x in (batch.get("contracts") or []) if isinstance(x,dict) and x.get("component_kind")=="branch"]
    by_pkg={str(x.get("package_id") or ""):x for x in contracts if x.get("package_id")}
    runtime=[x for x in (plan.get("packages") or []) if isinstance(x,dict) and x.get("runtime_required") is True]
    link=[]
    for pkg in runtime:
        pid=str(pkg.get("id") or "");c=by_pkg.get(pid)
        ok=bool(c) and str(c.get("component_id") or "")==str(pkg.get("branch_id") or "")
        link.append({"package_id":pid,"branch_id":pkg.get("branch_id"),"contract_id":(c or {}).get("contract_id"),"linked":ok})
    linkage_ok=all(x["linked"] for x in link)
    contract_ok=rec.get("schema")=="chacha.dev/contract-reconciliation/v1" and rec.get("compatible") is True and rec.get("assembly_allowed") is True
    council_ok=council.get("schema")=="chacha.dev/architecture-decision-council/v1"
    integration_ready=bool(contract_ok and linkage_ok and council_ok)
    result={
      "schema":"chacha.dev/integration-architecture-review/v1","project_id":str(a.project_id or ""),
      "runtime_package_count":len(runtime),"linked_package_count":sum(1 for x in link if x["linked"]),
      "linkage":link,"contract_reconciliation_compatible":contract_ok,
      "architecture_council_present":council_ok,
      "architecture_dispatch_allowed":council.get("dispatch_allowed") is True,
      "integration_ready":integration_ready,
      "assembly_allowed":integration_ready and plan.get("dispatch_allowed") is True,
      "direct_mutation":False,"decision_authority":False,
      "architecture_council_final_authority":True,"automatic_external_spend_eur":0
    }
    result["review_digest"]="sha256:"+hashlib.sha256(canonical(result)).hexdigest()
    Path(a.output).write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print("CHACHA_INTEGRATION_ARCHITECT_REVIEW=PASS")
    print("INTEGRATION_READY="+("YES" if integration_ready else "NO"))
    print("ASSEMBLY_ALLOWED="+("YES" if result["assembly_allowed"] else "NO"))
if __name__=="__main__":main()
