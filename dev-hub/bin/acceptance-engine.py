#!/usr/bin/env python3
from __future__ import annotations
import argparse,json
from pathlib import Path

def load(p):
    x=json.loads(Path(p).read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise SystemExit("JSON_ROOT_NOT_OBJECT")
    return x

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--contract",required=True);ap.add_argument("--evidence",required=True);ap.add_argument("--output",required=True)
    a=ap.parse_args();contract=load(a.contract);evidence=load(a.evidence)
    emap={str(x.get("criterion_id")):x for x in evidence.get("criteria") or []}
    rows=[];routes={}
    for c in contract.get("criteria") or []:
        cid=str(c.get("criterion_id"));required=bool(c.get("required",True))
        e=emap.get(cid)
        state=str((e or {}).get("state") or "UNVERIFIED")
        passed=state=="PASS"
        rows.append({"criterion_id":cid,"dimension":c.get("dimension"),"required":required,
                     "owner":c.get("owner"),"state":state,"evidence":(e or {}).get("evidence")})
        if required and not passed:
            routes.setdefault(str(c.get("owner") or "core"),[]).append(cid)
    ok=not routes
    result={"schema":"chacha.dev/acceptance-result/v1","accepted":ok,"criteria":rows,
            "return_to_factories":routes,"delivery_allowed":ok}
    Path(a.output).write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n")
    print("CHACHA_ACCEPTANCE_ENGINE=PASS")
    print("ACCEPTED="+("YES" if ok else "NO"))
if __name__=="__main__":main()
