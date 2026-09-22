#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,os,re,subprocess
from pathlib import Path
from typing import Any

DEFAULT_POLICY=Path("/opt/chacha-dev/platform/current/dev-hub/config/guardian-runtime-policy.v1.json")
DEFAULT_CLIENT=Path("/opt/chacha-dev/platform/current/dev-hub/bin/guardian-client.py")

def load(path:Path)->dict[str,Any]:
    x=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise RuntimeError("JSON_ROOT_NOT_OBJECT")
    return x

def atomic(path:Path,obj:dict[str,Any])->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name(path.name+f".tmp-{os.getpid()}")
    tmp.write_text(json.dumps(obj,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    os.replace(tmp,path)

def safe(s:str)->str:
    x=re.sub(r"[^A-Za-z0-9._-]+","-",str(s)).strip("-")
    return x[:120] or "unknown"

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--policy",type=Path,default=DEFAULT_POLICY)
    ap.add_argument("--client",type=Path,default=DEFAULT_CLIENT)
    a=ap.parse_args()
    policy=load(a.policy)
    root=Path(policy.get("local_remediation_dir") or "/opt/chacha-dev/runtime/guardian/remediations")
    index_path=Path(policy.get("local_remediation_index") or "/opt/chacha-dev/runtime/guardian/remediation-index.json")
    stop_file=Path(policy["critical_stop_required_file"])
    root.mkdir(parents=True,exist_ok=True)

    p=subprocess.run(
      ["/usr/bin/python3",str(a.client),"--policy",str(a.policy),"remediations","--status","OPEN","--limit","100"],
      stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=30
    )
    if p.returncode!=0:
        print("CHACHA_DEV_GUARDIAN_REMEDIATION_PULL=DEFERRED")
        return 0
    try:batch=json.loads(p.stdout)
    except Exception:
        print("CHACHA_DEV_GUARDIAN_REMEDIATION_PULL=INVALID")
        return 0
    items=[x for x in (batch.get("items") or []) if isinstance(x,dict) and x.get("directive_id")]
    delivered=[]
    for d in items:
        did=str(d["directive_id"])
        target=str(d.get("target_actor") or d.get("target_role") or "unknown")
        atomic(root/(safe(did)+".json"),d)
        inbox=root/"inbox"/safe(target)
        atomic(inbox/(safe(did)+".json"),d)
        atomic(inbox/"latest.json",d)
        delivered.append(did)
        msg="ChaCha Guardian corrective directive "+did+" -> "+target+": "+str(d.get("required_action") or "")
        subprocess.run(["/usr/bin/logger","-t","chacha-dev-guardian-remediation","--",msg],check=False)
        if str(d.get("severity"))=="CRITICAL":
            atomic(stop_file,{
              "schema":"chacha.dev/guardian-stop-required/v1",
              "active":True,
              "auto_stop_executed":False,
              "reason":"GUARDIAN_CORRECTIVE_DIRECTIVE_CRITICAL",
              "directive_id":did,
              "source_alert_id":d.get("source_alert_id"),
              "target":target,
              "required_action":d.get("required_action"),
              "human_or_out_of_band_stop_required":True
            })
    atomic(index_path,{
      "schema":"chacha.dev/guardian-remediation-index/v1",
      "items":items,
      "count":len(items),
      "automatic_external_spend_eur":0
    })
    if delivered:
        cmd=["/usr/bin/python3",str(a.client),"--policy",str(a.policy),"mark-remediations-delivered"]
        for did in delivered:cmd+=["--directive-id",did]
        q=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=30)
        if q.returncode!=0:
            print("CHACHA_DEV_GUARDIAN_REMEDIATION_DELIVERY_ACK=DEFERRED")
        else:
            print("CHACHA_DEV_GUARDIAN_REMEDIATION_DELIVERY_ACK=PASS")
    print("CHACHA_DEV_GUARDIAN_REMEDIATION_PULL=PASS")
    print("OPEN_DIRECTIVES="+str(len(items)))
    print("DELIVERED="+str(len(delivered)))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
