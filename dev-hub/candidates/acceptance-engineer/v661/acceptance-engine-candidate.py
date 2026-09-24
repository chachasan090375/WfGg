#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path

def load(p):
    x=json.loads(Path(p).read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise SystemExit("JSON_ROOT_NOT_OBJECT")
    return x

def verified_sha256_ref(value)->bool:
    ref=str(value or "")
    if "#sha256:" not in ref:return False
    raw,digest=ref.rsplit("#sha256:",1)
    if len(digest)!=64:return False
    p=Path(raw)
    return p.is_file() and hashlib.sha256(p.read_bytes()).hexdigest()==digest

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--contract",required=True);ap.add_argument("--evidence",required=True);ap.add_argument("--output",required=True)
    a=ap.parse_args();contract=load(a.contract);evidence=load(a.evidence)
    emap={str(x.get("criterion_id")):x for x in evidence.get("criteria") or [] if isinstance(x,dict)}
    rows=[];routes={}
    for c in contract.get("criteria") or []:
        if not isinstance(c,dict):continue
        cid=str(c.get("criterion_id"));required=bool(c.get("required",True));e=emap.get(cid)
        state=str((e or {}).get("state") or "UNVERIFIED");eref=(e or {}).get("evidence")
        if state=="PASS" and not verified_sha256_ref(eref):
            state="UNVERIFIED"
        passed=state=="PASS"
        rows.append({"criterion_id":cid,"dimension":c.get("dimension"),"required":required,
                     "owner":c.get("owner"),"state":state,"evidence":eref})
        if required and not passed:
            routes.setdefault(str(c.get("owner") or "core"),[]).append(cid)
    ok=not routes
    result={"schema":"chacha.dev/acceptance-result/v1","accepted":ok,"criteria":rows,
            "return_to_factories":routes,"delivery_allowed":ok,"local_acceptance_candidate":ok,
            "final_delivery_allowed":False,"final_delivery_gate":"seven-agent-final-compromise",
            "final_delivery_receipt_required":True}
    Path(a.output).write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print("CHACHA_DEV_V661_ACCEPTANCE_CANDIDATE=PASS")
    print("ACCEPTED="+("YES" if ok else "NO"))
    print("DIRECT_MUTATION=NO")
    print("AUTOMATIC_EXTERNAL_SPEND_EUR=0")

if __name__=="__main__":main()
