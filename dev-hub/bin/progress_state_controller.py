#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,os,time
from pathlib import Path
from typing import Any

SCHEMA="chacha.dev/platform-progress/v1"
POLICY_SCHEMA="chacha.dev/progress-reporting-policy/v1"
VALID={"IDLE","QUEUED","RUNNING","WAITING","COMPLETE","BLOCKED","ERROR"}

def now_iso()->str:return time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())
def load(p:Path,default=None):
    try:x=json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        if default is not None:return default
        raise
    if not isinstance(x,dict):raise ValueError("JSON_ROOT_NOT_OBJECT:"+str(p))
    return x
def atomic(p:Path,x:dict[str,Any])->None:
    p.parent.mkdir(parents=True,exist_ok=True)
    tmp=p.with_name(p.name+".tmp-"+str(os.getpid()))
    tmp.write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    os.replace(tmp,p)
def clamp(v:Any)->int:
    try:n=int(v)
    except Exception:n=0
    return max(0,min(100,n))

class ProgressStore:
    def __init__(self,policy:dict[str,Any]):
        if policy.get("schema")!=POLICY_SCHEMA:raise ValueError("PROGRESS_POLICY_SCHEMA_INVALID")
        self.policy=policy
        self.path=Path(str(policy.get("runtime_state") or ""))
        if not self.path.is_absolute():raise ValueError("PROGRESS_RUNTIME_STATE_ABSOLUTE_REQUIRED")
    def blank(self)->dict[str,Any]:
        modules={}
        for row in self.policy.get("modules") or []:
            mid=str(row.get("id") or "")
            if not mid:continue
            modules[mid]={"id":mid,"label":str(row.get("label") or mid),"icon":str(row.get("icon") or "•"),
                          "percent":0,"state":"IDLE","detail":"En attente","updated_at":now_iso()}
        maturity=self.policy.get("platform_maturity") or {}
        return {"schema":SCHEMA,"status":"IDLE",
                "platform_maturity_percent":clamp(maturity.get("percent") or 0),
                "platform_maturity_label":str(maturity.get("label") or "ChaCha DEV global"),
                "active_work_percent":0,"headline":"ChaCha est prêt ✨",
                "active_operation":None,"project_id":"chacha-dev-platform","modules":modules,
                "updated_at":now_iso(),"persistent":True,"execution_authority":False,
                "automatic_external_spend_eur":0}
    def snapshot(self)->dict[str,Any]:
        x=load(self.path,self.blank())
        if x.get("schema")!=SCHEMA:return self.blank()
        return x
    def write(self,x:dict[str,Any])->dict[str,Any]:
        x["schema"]=SCHEMA;x["updated_at"]=now_iso();x["persistent"]=True
        x["execution_authority"]=False;x["automatic_external_spend_eur"]=0
        atomic(self.path,x);return x
    def begin(self,operation_id:str,title:str,project_id:str)->dict[str,Any]:
        previous=self.snapshot()
        x=self.blank()
        x["platform_maturity_percent"]=clamp(previous.get("platform_maturity_percent",x["platform_maturity_percent"]))
        x["platform_maturity_label"]=str(previous.get("platform_maturity_label") or x["platform_maturity_label"])
        x.update({"status":"RUNNING","active_work_percent":3,
          "headline":title or "Nouvelle demande","active_operation":operation_id,
          "project_id":project_id or "chacha-dev-platform"})
        first=next(iter(x["modules"].values()),None)
        if first:first.update({"percent":10,"state":"RUNNING","detail":"Demande reçue","updated_at":now_iso()})
        return self.write(x)
    def update(self,module_id:str,percent:int,state:str,detail:str,overall_percent:int|None=None,
               headline:str|None=None)->dict[str,Any]:
        x=self.snapshot();state=state if state in VALID else "RUNNING"
        modules=x.setdefault("modules",{})
        row=modules.get(module_id)
        if not isinstance(row,dict):
            row={"id":module_id,"label":module_id,"icon":"•"};modules[module_id]=row
        row.update({"percent":clamp(percent),"state":state,"detail":detail,"updated_at":now_iso()})
        if overall_percent is not None:x["active_work_percent"]=clamp(overall_percent)
        if headline is not None:x["headline"]=headline
        x["status"]="RUNNING" if state not in {"BLOCKED","ERROR"} else state
        return self.write(x)
    def complete(self,headline:str,status:str="COMPLETE")->dict[str,Any]:
        x=self.snapshot();x["active_work_percent"]=100;x["status"]=status;x["headline"]=headline
        for row in (x.get("modules") or {}).values():
            if row.get("state")!="IDLE":
                row["percent"]=100;row["state"]="COMPLETE";row["detail"]="Terminé";row["updated_at"]=now_iso()
        return self.write(x)
    def fail(self,headline:str)->dict[str,Any]:
        x=self.snapshot();x["status"]="ERROR";x["headline"]=headline
        return self.write(x)
    def set_maturity(self,percent:int,label:str|None=None)->dict[str,Any]:
        x=self.snapshot();x["platform_maturity_percent"]=clamp(percent)
        if label:x["platform_maturity_label"]=label
        return self.write(x)

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--policy",type=Path,required=True)
    sub=ap.add_subparsers(dest="command",required=True)
    sub.add_parser("snapshot")
    b=sub.add_parser("begin");b.add_argument("--operation",required=True);b.add_argument("--title",required=True);b.add_argument("--project",default="chacha-dev-platform")
    u=sub.add_parser("update");u.add_argument("--module",required=True);u.add_argument("--percent",type=int,required=True);u.add_argument("--state",required=True);u.add_argument("--detail",required=True);u.add_argument("--overall",type=int);u.add_argument("--headline")
    c=sub.add_parser("complete");c.add_argument("--headline",required=True)
    f=sub.add_parser("fail");f.add_argument("--headline",required=True)
    m=sub.add_parser("set-maturity");m.add_argument("--percent",type=int,required=True);m.add_argument("--label")
    a=ap.parse_args();store=ProgressStore(load(a.policy))
    if a.command=="snapshot":out=store.snapshot()
    elif a.command=="begin":out=store.begin(a.operation,a.title,a.project)
    elif a.command=="update":out=store.update(a.module,a.percent,a.state,a.detail,a.overall,a.headline)
    elif a.command=="complete":out=store.complete(a.headline)
    elif a.command=="fail":out=store.fail(a.headline)
    else:out=store.set_maturity(a.percent,a.label)
    print(json.dumps(out,ensure_ascii=False));return 0

if __name__=="__main__":raise SystemExit(main())
