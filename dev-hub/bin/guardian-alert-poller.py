#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,os,subprocess,tempfile,time
from pathlib import Path
from typing import Any

DEFAULT_POLICY=Path("/opt/chacha-dev/platform/current/dev-hub/config/guardian-runtime-policy.v1.json")
DEFAULT_CLIENT=Path("/opt/chacha-dev/platform/current/dev-hub/bin/guardian-client.py")

def load(path:Path)->dict[str,Any]:
    x=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(x,dict): raise RuntimeError("JSON_ROOT_NOT_OBJECT")
    return x

def atomic_write(path:Path,obj:dict[str,Any])->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name(path.name+f".tmp-{os.getpid()}")
    tmp.write_text(json.dumps(obj,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    os.replace(tmp,path)

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--policy",type=Path,default=DEFAULT_POLICY)
    ap.add_argument("--client",type=Path,default=DEFAULT_CLIENT)
    a=ap.parse_args()
    policy=load(a.policy)
    alert_dir=Path(policy["local_alert_dir"])
    stop_file=Path(policy["critical_stop_required_file"])
    alert_dir.mkdir(parents=True,exist_ok=True)
    p=subprocess.run(
      ["/usr/bin/python3",str(a.client),"--policy",str(a.policy),"alerts","--status","OPEN","--limit","100"],
      stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=30
    )
    if p.returncode!=0:
        print("CHACHA_DEV_GUARDIAN_ALERT_PULL=DEFERRED")
        return 0
    try:batch=json.loads(p.stdout)
    except Exception:
        print("CHACHA_DEV_GUARDIAN_ALERT_PULL=INVALID")
        return 0
    items=batch.get("items") or []
    new_count=0;critical_count=0
    for item in items:
        if not isinstance(item,dict) or not item.get("alert_id"):continue
        target=alert_dir/(str(item["alert_id"])+".json")
        if not target.exists():
            atomic_write(target,item);new_count+=1
            sev=str(item.get("severity") or "WARNING")
            msg="ChaCha Guardian "+sev+": "+str(item.get("summary") or item["alert_id"])
            subprocess.run(["/usr/bin/logger","-t","chacha-dev-guardian","--",msg],check=False)
        if str(item.get("severity"))=="CRITICAL":
            critical_count+=1
            atomic_write(stop_file,{
              "schema":"chacha.dev/guardian-stop-required/v1",
              "active":True,
              "auto_stop_executed":False,
              "reason":"EXTERNAL_GUARDIAN_CRITICAL_ALERT",
              "alert_id":item["alert_id"],
              "event_id":item.get("event_id"),
              "severity":"CRITICAL",
              "observed_at":item.get("created_at"),
              "human_or_out_of_band_stop_required":True
            })
    print("CHACHA_DEV_GUARDIAN_ALERT_PULL=PASS")
    print("OPEN_ALERTS="+str(len(items)))
    print("NEW_ALERTS="+str(new_count))
    print("CRITICAL_ALERTS="+str(critical_count))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
