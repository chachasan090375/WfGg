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

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--bundle",required=True);ap.add_argument("--output",required=True)
    a=ap.parse_args();bundle=load(a.bundle)
    contracts=bundle.get("contracts") or []
    producers={}
    mismatches=[]
    for c in contracts:
        for k,t in fields(c.get("outputs")).items():
            producers.setdefault(k,[]).append((c.get("contract_id"),t))
    for c in contracts:
        for k,t in fields(c.get("inputs")).items():
            options=producers.get(k) or []
            if not options:
                mismatches.append({"consumer":c.get("contract_id"),"field":k,"reason":"MISSING_PRODUCER"})
                continue
            if t!="any" and not any(pt in ("any",t) for _,pt in options):
                mismatches.append({"consumer":c.get("contract_id"),"field":k,"reason":"TYPE_MISMATCH","expected":t,"producers":options})
    result={"schema":"chacha.dev/contract-reconciliation/v1","contracts":len(contracts),
            "mismatches":mismatches,"compatible":not mismatches,
            "assembly_allowed":not mismatches}
    Path(a.output).write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n")
    print("CHACHA_CONTRACT_REGISTRY=PASS")
    print("CONTRACTS_COMPATIBLE="+("YES" if not mismatches else "NO"))
if __name__=="__main__":main()
