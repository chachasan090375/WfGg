#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,hashlib,re
from pathlib import Path

DIMENSIONS=("functional","integration","quality","security","performance","accessibility","localization","documentation","operability","rollback")

def load(p):
    x=json.loads(Path(p).read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise SystemExit("JSON_ROOT_NOT_OBJECT")
    return x

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--intent",required=True);ap.add_argument("--output",required=True)
    a=ap.parse_args();intent=load(a.intent)
    text=str(intent.get("text") or intent.get("objective") or "").strip()
    if not text:raise SystemExit("FUNCTIONAL_INTENT_MISSING")
    name=str(intent.get("name") or "application")
    key=hashlib.sha256((name+"\n"+text).encode()).hexdigest()[:12]
    explicit=list(intent.get("criteria") or [])
    criteria=[]
    seen=set()
    for c in explicit:
        if not isinstance(c,dict):continue
        cid=str(c.get("criterion_id") or "criterion-"+str(len(criteria)+1))
        criteria.append({
          "criterion_id":cid,"dimension":str(c.get("dimension") or "functional"),
          "statement":str(c.get("statement") or ""), "required":bool(c.get("required",True)),
          "owner":str(c.get("owner") or "product"),"verification":c.get("verification") or "evidence"
        });seen.add(cid)
    for dim in DIMENSIONS:
        cid="baseline-"+dim
        if cid not in seen:
            criteria.append({"criterion_id":cid,"dimension":dim,
              "statement":f"Project satisfies declared {dim} constraints.",
              "required":dim in {"functional","integration","security","documentation","rollback"},
              "owner":"product" if dim=="functional" else ("cybersecurity" if dim=="security" else ("documentation" if dim=="documentation" else "qa")),
              "verification":"evidence"})
    result={
      "schema":"chacha.dev/functional-contract/v1",
      "contract_id":f"functional-{key}",
      "name":name,"functional_intent":text,
      "constraints":intent.get("constraints") or {},
      "deliverables":intent.get("deliverables") or [],
      "audiences":intent.get("audiences") or [],
      "languages":intent.get("languages") or [],
      "styles":intent.get("styles") or [],
      "capability_hints":intent.get("capability_hints") or [],
      "criteria":criteria,
      "invariants":{"functional_intent_immutable_during_replanning":True},
      "version":"1.0.0"
    }
    Path(a.output).write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n")
    print("CHACHA_SPECIFICATION_COMPILER=PASS")
    print("FUNCTIONAL_CONTRACT="+result["contract_id"])
if __name__=="__main__":main()
