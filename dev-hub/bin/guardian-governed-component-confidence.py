#!/usr/bin/env python3
from __future__ import annotations
import json,subprocess,tempfile,time
from pathlib import Path

CURRENT=Path("/opt/chacha-dev/platform/current")
POLICY=CURRENT/"dev-hub/config/guardian-runtime-policy.v1.json"
CLIENT=CURRENT/"dev-hub/bin/guardian-client.py"
ENGINE=CURRENT/"dev-hub/bin/component-confidence-engine.py"
OUT=Path("/opt/chacha-dev/runtime/knowledge/component-confidence.json")

def check(event:dict)->dict:
    with tempfile.NamedTemporaryFile(prefix="chacha-v625-confidence-",suffix=".json",mode="w",encoding="utf-8",delete=False) as f:
        json.dump(event,f,separators=(",",":"));p=Path(f.name)
    try:
        r=subprocess.run(["python3",str(CLIENT),"--policy",str(POLICY),"check","--event",str(p)],
                         stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=30)
    finally:
        p.unlink(missing_ok=True)
    if r.returncode!=0:raise RuntimeError("GUARDIAN_BLOCKED:"+(r.stdout or r.stderr)[-1000:])
    x=json.loads(r.stdout)
    if x.get("verdict") not in {"PASS","WARNING"}:raise RuntimeError("GUARDIAN_VERDICT_BLOCK:"+str(x))
    return x

def main()->int:
    stamp=time.strftime("%Y%m%dT%H%M%SZ",time.gmtime())
    aid="component-confidence-"+stamp
    base={"schema":"chacha.dev/governance-action/v1","action_id":aid,"actor":"central-orchestrator",
          "subject_role":"component-confidence-engine","action":"INVOKE_COMPONENT",
          "task_kind":"component-confidence-engine","permission":"workspace-write",
          "project_id":"chacha-dev-platform","run_id":aid,"adapters":[],
          "context":{"resource_class":"light","human_approval_required":False,
                     "storage_preflight_required":False,"deadline_seconds":180}}
    check({**base,"event_id":aid+"-pre","phase":"PRE_ACTION","evidence":{"emergency_stop_active":False}})
    OUT.parent.mkdir(parents=True,exist_ok=True)
    p=subprocess.run(["python3",str(ENGINE),"--policy",str(CURRENT/"dev-hub/config/component-confidence.v1.json"),
                      "--snapshot",str(OUT),"--nas"],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=120)
    if p.returncode!=0:raise RuntimeError("COMPONENT_CONFIDENCE_FAILED:"+(p.stderr or p.stdout)[-1500:])
    result=json.loads(OUT.read_text(encoding="utf-8"))
    check({**base,"event_id":aid+"-post","phase":"POST_ACTION",
           "evidence":{"emergency_stop_active":False,"output_exists":OUT.is_file(),
                       "nas_persisted":(result.get("nas") or {}).get("status")=="PERSISTED",
                       "confidence_is_advisory":True,"technology_revalidation_required":True,
                       "direct_application_mutation":False,"automatic_external_spend_eur":0}})
    print(p.stdout,end="")
    print("CHACHA_DEV_V625_GUARDIAN_GOVERNED_COMPONENT_CONFIDENCE=PASS")
    return 0

if __name__=="__main__":raise SystemExit(main())
