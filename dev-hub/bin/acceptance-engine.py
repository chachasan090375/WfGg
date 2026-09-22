#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,subprocess,sys
from pathlib import Path

def load(p):
    x=json.loads(Path(p).read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise SystemExit("JSON_ROOT_NOT_OBJECT")
    return x

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--contract",required=True);ap.add_argument("--evidence",required=True);ap.add_argument("--output",required=True)
    ap.add_argument("--branch-topology");ap.add_argument("--preplan");ap.add_argument("--technology-snapshot")
    ap.add_argument("--reusable-registry");ap.add_argument("--reusable-registry-db");ap.add_argument("--learning-output")
    ap.add_argument("--metrics");ap.add_argument("--incidents")
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
    learning_requested=all([a.branch_topology,a.preplan,a.technology_snapshot,a.reusable_registry,a.reusable_registry_db,a.learning_output])
    if ok and learning_requested:
        learner=Path(__file__).with_name("reusable-branch-learning.py")
        cmd=[sys.executable,str(learner),"--acceptance",str(a.output),"--branch-topology",a.branch_topology,
             "--preplan",a.preplan,"--technology-snapshot",a.technology_snapshot,
             "--registry",a.reusable_registry,"--registry-db",a.reusable_registry_db,"--output",a.learning_output]
        if a.metrics: cmd+=["--metrics",a.metrics]
        if a.incidents: cmd+=["--incidents",a.incidents]
        p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=60)
        if p.returncode!=0: raise SystemExit("ACCEPTANCE_BRANCH_LEARNING_FAILED:"+p.stderr+p.stdout)
        result["reusable_branch_learning"]=a.learning_output
        Path(a.output).write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n")
        print("CHACHA_DEV_V612_ACCEPTANCE_TO_REUSE_MEMORY=PASS")
    elif ok and any([a.branch_topology,a.preplan,a.technology_snapshot,a.reusable_registry,a.reusable_registry_db,a.learning_output]):
        raise SystemExit("ACCEPTANCE_BRANCH_LEARNING_CONTEXT_INCOMPLETE")
    print("CHACHA_ACCEPTANCE_ENGINE=PASS")
    print("ACCEPTED="+("YES" if ok else "NO"))
if __name__=="__main__":main()
