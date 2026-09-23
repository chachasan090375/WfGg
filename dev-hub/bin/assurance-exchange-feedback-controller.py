#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,os,re,subprocess
from pathlib import Path
from typing import Any

DEFAULT_POLICY=Path("/opt/chacha-dev/platform/current/dev-hub/config/assurance-exchange-runtime-policy.v1.json")
DEFAULT_CLIENT=Path("/opt/chacha-dev/platform/current/dev-hub/bin/assurance-exchange-client.py")

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
    return x[:140] or "unknown"
def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument("--policy",type=Path,default=DEFAULT_POLICY);ap.add_argument("--client",type=Path,default=DEFAULT_CLIENT)
    a=ap.parse_args();policy=load(a.policy)
    root=Path(policy.get("local_recommendation_dir") or "/opt/chacha-dev/runtime/assurance-exchange/recommendations")
    index=Path(policy.get("local_index") or "/opt/chacha-dev/runtime/assurance-exchange/recommendation-index.json")
    root.mkdir(parents=True,exist_ok=True)
    p=subprocess.run(["/usr/bin/python3",str(a.client),"--policy",str(a.policy),"recommendations","--status","OPEN"],
                     stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=30)
    if p.returncode!=0:
        print("CHACHA_DEV_ASSURANCE_EXCHANGE_PULL=DEFERRED");return 0
    try:x=json.loads(p.stdout)
    except Exception:
        print("CHACHA_DEV_ASSURANCE_EXCHANGE_PULL=INVALID");return 0
    items=[v for v in x.get("items") or [] if isinstance(v,dict) and v.get("correlation_id")]
    delivered=[]
    for rec in items:
        cid=str(rec["correlation_id"])
        atomic(root/(safe(cid)+".json"),rec)
        project=safe(str(rec.get("project_id") or "platform-global"))
        inbox=root.parent/"inbox"/"central-orchestrator"/project
        atomic(inbox/(safe(cid)+".json"),rec);atomic(inbox/"latest.json",rec)
        delivered.append(cid)
        subprocess.run(["/usr/bin/logger","-t","chacha-dev-assurance-exchange","--",
          "ChaCha Assurance "+str(rec.get("priority") or "")+" "+cid+" -> central-orchestrator / "+str(rec.get("recommendation_type") or "")],check=False)
    atomic(index,{"schema":"chacha.dev/assurance-exchange-local-index/v1","items":items,"count":len(items),
                  "direct_mutation":False,"central_orchestrator_owns_remediation":True,
                  "technology_watch_required_if_architecture_change":True,
                  "architecture_council_required_if_architecture_change":True,
                  "automatic_external_spend_eur":0})
    if delivered:
        cmd=["/usr/bin/python3",str(a.client),"--policy",str(a.policy),"mark-delivered"]
        for cid in delivered:cmd+=["--correlation-id",cid]
        subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=30)
    print("CHACHA_DEV_ASSURANCE_EXCHANGE_PULL=PASS")
    print("RECOMMENDATIONS_DELIVERED="+str(len(items)))
    print("CENTRAL_ORCHESTRATOR_OWNS_REMEDIATION=YES")
    print("DIRECT_MUTATION=NO")
    return 0
if __name__=="__main__":raise SystemExit(main())
