#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,sys
from datetime import datetime,timezone
from pathlib import Path

INPUT_SCHEMA="chacha.dev/dispatch-envelope/v1"
OUTPUT_SCHEMA="chacha.dev/task-result/v1"
ADAPTER_ID="platform-selftest-adapter"
PROVIDER_ID="platform-selftest-runtime"
REVISION=Path("/opt/chacha-dev/platform/current/.revision")

def now_iso():return datetime.now(timezone.utc).isoformat()

def sha256_file(path:Path)->str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""):h.update(chunk)
    return "sha256:"+h.hexdigest()

def emit(req,status,summary,evidence,outputs,code=0):
    task=req.get("task") if isinstance(req.get("task"),dict) else {}
    payload={
      "schema":OUTPUT_SCHEMA,"project":str(req.get("project") or "unknown"),
      "task_id":str(task.get("id") or "unknown"),"status":status,"producer":ADAPTER_ID,
      "observed_at":now_iso(),"summary":summary,"evidence":evidence,
      "verification":{"status":"UNVERIFIED","method":"none","verifier":"none",
                      "observed_at":now_iso(),"notes":"Independent verification required."},
      "outputs":outputs
    }
    sys.stdout.write(json.dumps(payload,ensure_ascii=False,separators=(",",":"))+"\n")
    return code

def main():
    try:req=json.load(sys.stdin)
    except Exception:return emit({},"BLOCKED","INPUT_JSON_INVALID",[],[],2)
    if req.get("schema")!=INPUT_SCHEMA:return emit(req,"BLOCKED","INPUT_SCHEMA_INVALID",[],[],2)
    task=req.get("task") if isinstance(req.get("task"),dict) else {}
    if str(task.get("permission") or "")!="read":
        return emit(req,"BLOCKED","PLATFORM_SELFTEST_READ_ONLY_REQUIRED",[],[],2)
    bindings=req.get("bindings") or []
    if not any(isinstance(x,dict) and x.get("provider")==PROVIDER_ID and x.get("adapter")==ADAPTER_ID for x in bindings):
        return emit(req,"BLOCKED","PLATFORM_SELFTEST_BINDING_MISSING",[],[],2)
    meta=req.get("metadata") if isinstance(req.get("metadata"),dict) else {}
    st=meta.get("platform_selftest") if isinstance(meta.get("platform_selftest"),dict) else {}
    if st.get("action")!="revision-proof":
        return emit(req,"BLOCKED","PLATFORM_SELFTEST_ACTION_INVALID",[],[],2)
    if not REVISION.is_file():
        return emit(req,"FAILED","PLATFORM_REVISION_MISSING",[],[],1)
    outputs=[]
    for row in task.get("outputs") or []:
        if isinstance(row,dict) and row.get("type") and row.get("id"):
            outputs.append({"type":row["type"],"id":row["id"],"status":"OK"})
    evidence=[{"kind":"file","source":str(REVISION),"digest":sha256_file(REVISION),
               "details":{"read_only":True,"application_mutation":False,"external_spend_eur":0}}]
    return emit(req,"OK","PLATFORM_SELFTEST_REVISION_PROOF_OK",evidence,outputs,0)

if __name__=="__main__":raise SystemExit(main())
