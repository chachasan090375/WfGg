#!/usr/bin/env python3
from __future__ import annotations
import json,subprocess,sys,tempfile,time
from pathlib import Path

HERE=Path(__file__).resolve().parent
CURRENT=Path("/opt/chacha-dev/platform/current")
POLICY=CURRENT/"dev-hub/config/guardian-runtime-policy.v1.json"
CLIENT=CURRENT/"dev-hub/bin/guardian-client.py"
RECON=CURRENT/"dev-hub/bin/production-lineage-feedback.py"
OUT=Path("/opt/chacha-dev/runtime/knowledge/production-lineage-feedback-latest.json")

def check(event:dict)->dict:
    with tempfile.NamedTemporaryFile(prefix="chacha-v624-guardian-",suffix=".json",mode="w",encoding="utf-8",delete=False) as f:
        json.dump(event,f,separators=(",",":"));p=Path(f.name)
    try:
        r=subprocess.run(["python3",str(CLIENT),"--policy",str(POLICY),"check","--event",str(p)],
                         stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=30)
    finally:
        p.unlink(missing_ok=True)
    if r.returncode!=0:
        raise RuntimeError("GUARDIAN_BLOCKED:"+(r.stdout or r.stderr)[-1000:])
    x=json.loads(r.stdout)
    if x.get("verdict") not in {"PASS","WARNING"}:raise RuntimeError("GUARDIAN_VERDICT_BLOCK:"+str(x))
    return x

def main()->int:
    stamp=time.strftime("%Y%m%dT%H%M%SZ",time.gmtime())
    aid="production-lineage-feedback-"+stamp
    base={"schema":"chacha.dev/governance-action/v1","action_id":aid,"actor":"central-orchestrator",
          "subject_role":"production-lineage-feedback","action":"INVOKE_COMPONENT",
          "task_kind":"production-lineage-feedback","permission":"workspace-write",
          "project_id":"chacha-dev-platform","run_id":aid,"adapters":[],
          "context":{"resource_class":"light","human_approval_required":False,
                     "storage_preflight_required":False,"deadline_seconds":180}}
    pre={**base,"event_id":aid+"-pre","phase":"PRE_ACTION","evidence":{"emergency_stop_active":False}}
    check(pre)
    OUT.parent.mkdir(parents=True,exist_ok=True)
    p=subprocess.run(["python3",str(RECON),"--policy",str(CURRENT/"dev-hub/config/production-lineage-feedback.v1.json"),
                      "--output",str(OUT),"--nas"],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=120)
    if p.returncode!=0:raise RuntimeError("PRODUCTION_LINEAGE_FEEDBACK_FAILED:"+(p.stderr or p.stdout)[-1500:])
    result=json.loads(OUT.read_text(encoding="utf-8"))
    post={**base,"event_id":aid+"-post","phase":"POST_ACTION",
          "evidence":{"emergency_stop_active":False,"output_exists":OUT.is_file(),
                      "nas_persisted":(result.get("nas") or {}).get("status")=="PERSISTED",
                      "exact_lineage_required_for_reuse_mutation":True,
                      "direct_application_mutation":False,"automatic_external_spend_eur":0}}
    check(post)
    print(p.stdout,end="")
    print("CHACHA_DEV_V624_GUARDIAN_GOVERNED_FEEDBACK=PASS")
    return 0
if __name__=="__main__":raise SystemExit(main())
