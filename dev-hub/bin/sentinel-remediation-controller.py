#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,os,re,subprocess
from pathlib import Path
from typing import Any

DEFAULT_POLICY=Path("/opt/chacha-dev/platform/current/dev-hub/config/sentinel-runtime-policy.v1.json")
DEFAULT_CLIENT=Path("/opt/chacha-dev/platform/current/dev-hub/bin/sentinel-client.py")

def load(path:Path)->dict[str,Any]:
    x=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise RuntimeError("JSON_ROOT_NOT_OBJECT")
    return x
def atomic(path:Path,obj:dict[str,Any])->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name(path.name+f".tmp-{os.getpid()}")
    tmp.write_text(json.dumps(obj,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    os.replace(tmp,path)
def safe(v:str)->str:
    x=re.sub(r"[^A-Za-z0-9._-]+","-",str(v)).strip("-")
    return x[:120] or "unknown"
def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument("--policy",type=Path,default=DEFAULT_POLICY);ap.add_argument("--client",type=Path,default=DEFAULT_CLIENT)
    a=ap.parse_args();policy=load(a.policy)
    root=Path(policy.get("local_directive_dir") or "/opt/chacha-dev/runtime/sentinel/directives")
    index=root.parent/"directive-index.json";root.mkdir(parents=True,exist_ok=True)
    items=[]
    for state in ("OPEN","DELIVERED"):
        p=subprocess.run(["/usr/bin/python3",str(a.client),"--policy",str(a.policy),"directives","--status",state],
                         stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=30)
        if p.returncode!=0:
            print("CHACHA_DEV_SENTINEL_DIRECTIVE_PULL=DEFERRED");return 0
        try:x=json.loads(p.stdout)
        except Exception:
            print("CHACHA_DEV_SENTINEL_DIRECTIVE_PULL=INVALID");return 0
        items.extend(v for v in x.get("items") or [] if isinstance(v,dict) and v.get("directive_id"))
    dedup={str(x["directive_id"]):x for x in items};items=list(dedup.values())
    delivered=[]
    for d in items:
        did=str(d["directive_id"])
        atomic(root/(safe(did)+".json"),d)
        inbox=root/"inbox"/"central-orchestrator"
        atomic(inbox/(safe(did)+".json"),d);atomic(inbox/"latest.json",d)
        if str(d.get("status") or "")=="OPEN":delivered.append(did)
        subprocess.run(["/usr/bin/logger","-t","chacha-dev-sentinel-remediation","--",
          "ChaCha Sentinel technical directive "+did+" -> central-orchestrator: "+str(d.get("required_action") or "")],check=False)
    atomic(index,{"schema":"chacha.dev/sentinel-directive-index/v1","items":items,"count":len(items),
                  "direct_code_mutation":False,"central_orchestrator_owns_remediation":True,"automatic_external_spend_eur":0})
    if delivered:
        cmd=["/usr/bin/python3",str(a.client),"--policy",str(a.policy),"mark-delivered"]
        for did in delivered:cmd+=["--directive-id",did]
        subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=30)
    print("CHACHA_DEV_SENTINEL_DIRECTIVE_PULL=PASS")
    print("OPEN_DIRECTIVES="+str(len(items)))
    print("CENTRAL_ORCHESTRATOR_OWNS_REMEDIATION=YES")
    return 0
if __name__=="__main__":raise SystemExit(main())
