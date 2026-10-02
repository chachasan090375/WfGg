#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path

def stable(x): return json.dumps(x,sort_keys=True,ensure_ascii=False,separators=(",",":"))
def digest(x): return hashlib.sha256(stable(x).encode()).hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument("--current",type=Path,required=True);ap.add_argument("--desired",type=Path,required=True)
 ap.add_argument("--directive",required=True);ap.add_argument("--project-id",required=True);ap.add_argument("--revision",required=True);ap.add_argument("--output",type=Path,required=True);a=ap.parse_args()
 old=json.loads(a.current.read_text());new=json.loads(a.desired.read_text())
 if new.get("schema")!="chacha.dev/functional-contract/v1": raise SystemExit("DESIRED_CONTRACT_SCHEMA_INVALID")
 if old.get("project_id") not in (None,a.project_id) or new.get("project_id") not in (None,a.project_id): raise SystemExit("PROJECT_ID_MISMATCH")
 out={"schema":"chacha.dev/guardian-functional-contract-reconciliation/v1","status":"READY","authority":"central-orchestrator",
 "project_id":a.project_id,"revision":a.revision,"directive_id":a.directive,"old_digest":digest(old),"new_digest":digest(new),
 "changed":digest(old)!=digest(new),"single_writer_required":True,"canonical_stop_required_false":True,
 "rollback":{"contract":old,"digest":digest(old)},"desired_contract":new,"automatic_external_spend_eur":0,"apply":False}
 a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(out,indent=2,ensure_ascii=False)+"\n")
 print("GUARDIAN_FUNCTIONAL_CONTRACT_RECONCILIATION=READY")
if __name__=="__main__":main()
