#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,os,tempfile,time,uuid
from pathlib import Path
from typing import Any

POLICY_SCHEMA="chacha.dev/progress-coordinator-policy/v1"
STATE_SCHEMA="chacha.dev/platform-progress-state/v1"

def now_iso()->str:return time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())

def load(path:Path,default=None):
    try:x=json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        if default is not None:return default
        raise
    if not isinstance(x,dict):raise RuntimeError("JSON_ROOT_NOT_OBJECT:"+str(path))
    return x

def atomic(path:Path,value:dict[str,Any])->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix=path.name+".",suffix=".tmp",dir=str(path.parent))
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as fh:
            json.dump(value,fh,indent=2,ensure_ascii=False);fh.write("\n");fh.flush();os.fsync(fh.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)

def validate_policy(policy:dict[str,Any])->None:
    if policy.get("schema")!=POLICY_SCHEMA:raise RuntimeError("PROGRESS_POLICY_SCHEMA_INVALID")
    inv=policy.get("invariants") if isinstance(policy.get("invariants"),dict) else {}
    required=["single_canonical_progress_source","interfaces_read_same_state","atomic_writes_required",
              "monotonic_within_run","module_progress_bounded_0_100","overall_progress_bounded_0_100",
              "no_execution_authority","no_architecture_authority","no_production_mutation"]
    bad=[x for x in required if inv.get(x) is not True]
    if bad:raise RuntimeError("PROGRESS_POLICY_WEAKENED:"+",".join(bad))
    if float(inv.get("automatic_external_spend_eur") or 0)!=0:raise RuntimeError("PROGRESS_EXTERNAL_SPEND_FORBIDDEN")

def default_state(policy:dict[str,Any])->dict[str,Any]:
    return {
      "schema":STATE_SCHEMA,"version":"1.0.0","updated_at":now_iso(),
      "run_id":None,"project_id":"chacha-dev-platform","state":"IDLE","stage":"IDLE",
      "overall_percent":0,"label":"Prêt","message":"Aucune opération en cours.",
      "active_module":None,
      "modules":{m:{"state":"IDLE","percent":0,"label":m} for m in policy.get("modules") or []},
      "history":[],
      "execution_authority":False,"architecture_authority":False,
      "production_mutation":False,"automatic_external_spend_eur":0
    }

def state_path(policy:dict[str,Any],override:Path|None=None)->Path:
    if override:return override
    raw=str(policy.get("canonical_state") or "")
    if not raw:raise RuntimeError("PROGRESS_STATE_PATH_MISSING")
    return Path(raw)

def bounded(value:int)->int:return max(0,min(100,int(value)))

def append_history(st:dict[str,Any],policy:dict[str,Any],event:dict[str,Any])->None:
    h=st.setdefault("history",[])
    h.append(event)
    limit=max(10,int(policy.get("history_limit") or 120))
    del h[:-limit]

def update(policy:dict[str,Any],path:Path,*,run_id:str|None=None,project_id:str|None=None,
           stage:str|None=None,percent:int|None=None,label:str|None=None,message:str|None=None,
           module:str|None=None,module_state:str|None=None,module_percent:int|None=None)->dict[str,Any]:
    validate_policy(policy)
    st=load(path,default_state(policy))
    if st.get("schema")!=STATE_SCHEMA:raise RuntimeError("PROGRESS_STATE_SCHEMA_INVALID")
    if run_id is not None:
        if st.get("run_id") not in {None,run_id} and st.get("state") not in {"IDLE","COMPLETE","FAILED","STOPPED"}:
            raise RuntimeError("PROGRESS_ACTIVE_RUN_CONFLICT")
        if st.get("run_id")!=run_id:
            st=default_state(policy);st["run_id"]=run_id
    if project_id:st["project_id"]=project_id
    if stage:
        stages=policy.get("stages") or {}
        if stage not in stages:raise RuntimeError("PROGRESS_STAGE_UNKNOWN:"+stage)
        next_percent=bounded(percent if percent is not None else int(stages[stage]))
        current=bounded(int(st.get("overall_percent") or 0))
        if st.get("run_id")==run_id and stage not in {"FAILED","STOPPED"} and next_percent<current:
            raise RuntimeError("PROGRESS_NON_MONOTONIC")
        st["stage"]=stage;st["state"]=stage;st["overall_percent"]=next_percent
    elif percent is not None:
        next_percent=bounded(percent);current=bounded(int(st.get("overall_percent") or 0))
        if run_id and st.get("run_id")==run_id and next_percent<current:raise RuntimeError("PROGRESS_NON_MONOTONIC")
        st["overall_percent"]=next_percent
    if label is not None:st["label"]=label
    if message is not None:st["message"]=message
    if module:
        mods=st.setdefault("modules",{})
        row=mods.setdefault(module,{"state":"IDLE","percent":0,"label":module})
        if module_state is not None:row["state"]=module_state
        if module_percent is not None:row["percent"]=bounded(module_percent)
        row["updated_at"]=now_iso();st["active_module"]=module
    st["updated_at"]=now_iso()
    append_history(st,policy,{"at":st["updated_at"],"run_id":st.get("run_id"),"stage":st.get("stage"),
                              "overall_percent":st.get("overall_percent"),"module":module,
                              "module_state":module_state,"message":message})
    atomic(path,st);return st

def begin(policy:dict[str,Any],path:Path,project_id:str,label:str,message:str)->dict[str,Any]:
    rid="progress-"+uuid.uuid4().hex
    st=default_state(policy);st.update({"run_id":rid,"project_id":project_id,"state":"QUEUED","stage":"QUEUED",
      "overall_percent":int((policy.get("stages") or {}).get("QUEUED",5)),"label":label,"message":message,"updated_at":now_iso()})
    append_history(st,policy,{"at":st["updated_at"],"run_id":rid,"stage":"QUEUED","overall_percent":st["overall_percent"],"message":message})
    atomic(path,st);return st

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--policy",type=Path,required=True)
    ap.add_argument("--state",type=Path)
    sub=ap.add_subparsers(dest="cmd",required=True)
    b=sub.add_parser("begin");b.add_argument("--project",default="chacha-dev-platform");b.add_argument("--label",default="ChaCha GPT");b.add_argument("--message",default="Démarrage…")
    s=sub.add_parser("stage");s.add_argument("--run-id",required=True);s.add_argument("--project");s.add_argument("--stage",required=True);s.add_argument("--percent",type=int);s.add_argument("--label");s.add_argument("--message")
    m=sub.add_parser("module");m.add_argument("--run-id",required=True);m.add_argument("--module",required=True);m.add_argument("--state",required=True);m.add_argument("--percent",type=int,required=True);m.add_argument("--message")
    sub.add_parser("show")
    args=ap.parse_args();policy=load(args.policy);validate_policy(policy);path=state_path(policy,args.state)
    if args.cmd=="begin":out=begin(policy,path,args.project,args.label,args.message)
    elif args.cmd=="stage":out=update(policy,path,run_id=args.run_id,project_id=args.project,stage=args.stage,percent=args.percent,label=args.label,message=args.message)
    elif args.cmd=="module":out=update(policy,path,run_id=args.run_id,module=args.module,module_state=args.state,module_percent=args.percent,message=args.message)
    else:out=load(path,default_state(policy))
    print(json.dumps(out,ensure_ascii=False));return 0

if __name__=="__main__":raise SystemExit(main())
