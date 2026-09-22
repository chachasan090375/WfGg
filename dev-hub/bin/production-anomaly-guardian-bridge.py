#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,os,shutil,subprocess,time
from pathlib import Path
from typing import Any

DEFAULT_QUEUE=Path("/opt/chacha-dev/runtime/learning/anomaly-queue")
DEFAULT_DONE=Path("/opt/chacha-dev/runtime/learning/anomaly-processed")
DEFAULT_CLIENT=Path("/opt/chacha-dev/platform/current/dev-hub/bin/guardian-client.py")
DEFAULT_POLICY=Path("/opt/chacha-dev/platform/current/dev-hub/config/guardian-runtime-policy.v1.json")

def now_iso():return time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())
def load(p:Path)->dict[str,Any]:
    x=json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise RuntimeError("ANOMALY_ROOT_NOT_OBJECT")
    return x
def atomic(p:Path,obj:dict[str,Any]):
    p.parent.mkdir(parents=True,exist_ok=True)
    t=p.with_name(p.name+f".tmp-{os.getpid()}")
    t.write_text(json.dumps(obj,indent=2,ensure_ascii=False)+"\n",encoding="utf-8");os.replace(t,p)

def normalize(candidate:dict[str,Any])->dict[str,Any]:
    sev=str(candidate.get("severity") or (candidate.get("anomaly") or {}).get("severity") or "").lower()
    if sev not in {"high","critical"}:raise RuntimeError("ANOMALY_NOT_ACTIONABLE")
    return {
      "schema":"chacha.dev/production-learning-anomaly/v1",
      "delta_id":str(candidate.get("delta_id") or ""),
      "project_id":str(candidate.get("project_id") or ""),
      "source_id":str(candidate.get("source_id") or ""),
      "deployment_id":str(candidate.get("deployment_id") or ""),
      "severity":sev,
      "anomaly":candidate.get("anomaly") or {},
      "evidence_refs":[str(x) for x in (candidate.get("evidence_refs") or [])],
      "observed_at":str(candidate.get("queued_at") or now_iso()),
      "automatic_production_mutation_authorized":False
    }

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--queue",type=Path,default=DEFAULT_QUEUE);ap.add_argument("--processed",type=Path,default=DEFAULT_DONE)
    ap.add_argument("--client",type=Path,default=DEFAULT_CLIENT);ap.add_argument("--policy",type=Path,default=DEFAULT_POLICY)
    ap.add_argument("--limit",type=int,default=100)
    a=ap.parse_args();a.queue.mkdir(parents=True,exist_ok=True);a.processed.mkdir(parents=True,exist_ok=True)
    sent=0;deferred=0
    for p in sorted(a.queue.glob("*.json"))[:max(1,min(a.limit,500))]:
        try:
            candidate=load(p);event=normalize(candidate)
            if not all(event[k] for k in ("delta_id","project_id","source_id","deployment_id")):
                raise RuntimeError("ANOMALY_IDENTITY_INCOMPLETE")
            tmp=a.queue/(p.stem+".guardian.json");atomic(tmp,event)
            q=subprocess.run(["/usr/bin/python3",str(a.client),"--policy",str(a.policy),"report-anomaly","--anomaly",str(tmp)],
                             stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=30)
            tmp.unlink(missing_ok=True)
            if q.returncode!=0:
                deferred+=1;continue
            ack=json.loads(q.stdout)
            if ack.get("status")!="DIRECTIVE_ISSUED":deferred+=1;continue
            receipt={"schema":"chacha.dev/production-learning-anomaly-bridge-receipt/v1","reported_at":now_iso(),
                     "candidate":candidate,"guardian_ack":ack,"production_mutation_performed":False}
            target=a.processed/p.name;atomic(target,receipt);p.unlink();sent+=1
        except Exception:
            deferred+=1
    print(json.dumps({"schema":"chacha.dev/production-learning-anomaly-bridge-run/v1","status":"PASS",
                      "reported":sent,"deferred":deferred,"automatic_external_spend_eur":0},indent=2))
    print("CHACHA_DEV_PRODUCTION_ANOMALY_GUARDIAN_BRIDGE=PASS")
    return 0
if __name__=="__main__":raise SystemExit(main())
