#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,os,re,shutil,subprocess,time
from pathlib import Path
from typing import Any

CONTROL_ROOT=Path("/opt/chacha-dev/runtime/control")
DEFAULT_CLIENT=Path("/opt/chacha-dev/platform/current/dev-hub/bin/specialist-authority-client.py")
DEFAULT_POLICY=Path("/opt/chacha-dev/platform/current/dev-hub/config/bastion-runtime-policy.v1.json")
DEFAULT_EMERGENCY=Path("/opt/chacha-dev/platform/current/dev-hub/bin/emergency-stop-controller.py")
DEFAULT_KEY_ROOT=Path("/opt/chacha-dev/runtime/secrets/project-assurance")
REVOKED_ROOT=Path("/opt/chacha-dev/runtime/secrets/project-assurance-revoked")

def now()->str:return time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())
def safe(v:str)->str:
    x=re.sub(r"[^A-Za-z0-9._-]+","-",str(v)).strip("-")
    return x[:160] or "unknown"
def atomic(path:Path,obj:dict[str,Any])->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name(path.name+f".tmp-{os.getpid()}")
    tmp.write_text(json.dumps(obj,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    os.replace(tmp,path)
def run(argv:list[str],timeout:int=30)->subprocess.CompletedProcess[str]:
    return subprocess.run(argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=timeout)

def record_project_control(kind:str,item:dict[str,Any])->None:
    project=safe(str(item.get("project_id") or "unknown"))
    directive=str(item.get("directive_id") or "")
    path=CONTROL_ROOT/kind/(project+".json")
    atomic(path,{
      "schema":f"chacha.dev/bastion-{kind}-control/v1",
      "active":True,"project_id":project,"directive_id":directive,
      "incident_id":item.get("incident_id"),"reason":item.get("reason"),
      "source":"bastion-central-authority","activated_at":now(),
      "new_mutation_blocked":True,"new_materialization_blocked":kind in {"quarantine","revocation"}
    })

def revoke_local_project_key(project_id:str,directive_id:str)->dict[str,Any]:
    src=DEFAULT_KEY_ROOT/(project_id+".pem")
    result={"local_key_present":src.exists(),"local_key_revoked":False}
    if not src.exists():return result
    REVOKED_ROOT.mkdir(parents=True,exist_ok=True)
    dst=REVOKED_ROOT/(project_id+"-"+safe(directive_id)+"-"+time.strftime("%Y%m%dT%H%M%SZ",time.gmtime())+".pem")
    shutil.move(str(src),str(dst));dst.chmod(0o600)
    result.update({"local_key_revoked":True,"revoked_key_path":str(dst)})
    return result

def survival(item:dict[str,Any])->None:
    atomic(CONTROL_ROOT/"survival-mode.json",{
      "schema":"chacha.dev/bastion-survival-mode/v1","active":True,
      "activated_at":now(),"directive_id":item.get("directive_id"),
      "incident_id":item.get("incident_id"),"reason":item.get("reason"),
      "new_dispatch_blocked":True,"new_materialization_blocked":True,
      "foundries_frozen":True,"evidence_collection_preserved":True,
      "memory_read_only":True,"guardian_preserved":True,"sentinel_preserved":True,
      "bastion_preserved":True,"assurance_exchange_preserved":True,
      "failover_status":"RESERVED_INACTIVE"
    })

def emergency(item:dict[str,Any],emergency_controller:Path)->None:
    if not emergency_controller.is_file():raise RuntimeError("EMERGENCY_CONTROLLER_MISSING")
    p=run(["/usr/bin/python3",str(emergency_controller),"activate",
           "--reason","BASTION:"+str(item.get("directive_id") or item.get("incident_id") or "critical"),
           "--actor","bastion-incident-response-controller"],60)
    if p.returncode!=0:raise RuntimeError("EMERGENCY_CONTROL_FAILED:"+p.stderr[-500:])

def execute(item:dict[str,Any],emergency_controller:Path)->dict[str,Any]:
    action=str(item.get("action") or "OBSERVE").upper()
    project=safe(str(item.get("project_id") or "unknown"))
    result={"directive_id":item.get("directive_id"),"project_id":project,"action":action,"executed_at":now()}
    if action=="OBSERVE":
        result["status"]="OBSERVED"
    elif action=="CONTAIN":
        record_project_control("containment",item);result["status"]="CONTAINED"
    elif action=="QUARANTINE":
        record_project_control("quarantine",item);result["status"]="QUARANTINED"
    elif action=="REVOKE":
        record_project_control("revocation",item);result.update(revoke_local_project_key(project,str(item.get("directive_id") or "")));result["status"]="REVOKED"
    elif action=="SURVIVAL":
        survival(item);result["status"]="SURVIVAL_ACTIVE"
    elif action=="E_STOP":
        emergency(item,emergency_controller);result["status"]="EMERGENCY_ACTIVE"
    elif action=="FAILOVER":
        result["status"]="BLOCKED_RESERVED_INACTIVE";result["failover_status"]="RESERVED_INACTIVE"
        raise RuntimeError("FAILOVER_RESERVED_INACTIVE")
    else:
        raise RuntimeError("UNKNOWN_BASTION_ACTION:"+action)
    return result

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--client",type=Path,default=DEFAULT_CLIENT)
    ap.add_argument("--policy",type=Path,default=DEFAULT_POLICY)
    ap.add_argument("--emergency-controller",type=Path,default=DEFAULT_EMERGENCY)
    ap.add_argument("--evidence-dir",type=Path,default=Path("/opt/chacha-dev/runtime/bastion/response-evidence"))
    a=ap.parse_args()
    p=run(["/usr/bin/python3",str(a.client),"--policy",str(a.policy),"directives"],30)
    if p.returncode!=0:
        print("CHACHA_DEV_BASTION_DIRECTIVE_PULL=DEFERRED");return 0
    try:batch=json.loads(p.stdout)
    except Exception:
        print("CHACHA_DEV_BASTION_DIRECTIVE_PULL=INVALID");return 0
    items=[x for x in batch.get("items") or [] if isinstance(x,dict) and x.get("directive_id")]
    delivered=[]
    for item in items:
        try:
            result=execute(item,a.emergency_controller)
            atomic(a.evidence_dir/(safe(str(item["directive_id"]))+".json"),result)
            delivered.append(str(item["directive_id"]))
        except Exception as exc:
            atomic(a.evidence_dir/(safe(str(item["directive_id"]))+"-failed.json"),{
              "schema":"chacha.dev/bastion-response-failure/v1","directive_id":item.get("directive_id"),
              "action":item.get("action"),"project_id":item.get("project_id"),"failed_at":now(),
              "reason":str(exc)[:500],"failover_status":"RESERVED_INACTIVE"
            })
    if delivered:
        cmd=["/usr/bin/python3",str(a.client),"--policy",str(a.policy),"mark-directives-delivered"]
        for d in delivered:cmd+=["--directive-id",d]
        ack=run(cmd,30)
        if ack.returncode!=0:raise RuntimeError("BASTION_DIRECTIVE_ACK_FAILED")
    print("CHACHA_DEV_BASTION_DIRECTIVE_PULL=PASS")
    print("DIRECTIVES_EXECUTED="+str(len(delivered)))
    print("FAILOVER=RESERVED_INACTIVE")
    return 0
if __name__=="__main__":raise SystemExit(main())
