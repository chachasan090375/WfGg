#!/usr/bin/env python3
from __future__ import annotations
import fcntl,hashlib,json,os,re,time
from pathlib import Path
from typing import Any

SCHEMA="chacha.dev/learning-delta/v1"
KINDS={"core-orchestrator","domain-orchestrator","foundry","agent","embedded-application-agent","learning-module","runtime-monitor"}
DEFAULT_OUTBOX=Path("/opt/chacha-dev/runtime/learning/outbox")
DEFAULT_STATE=Path("/opt/chacha-dev/runtime/learning/producer-state")

def now_iso()->str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())

def canonical(v:Any)->str:
    return json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(",",":"))

def digest(v:Any)->str:
    return hashlib.sha256(canonical(v).encode()).hexdigest()

def safe(v:str)->str:
    s=re.sub(r"[^A-Za-z0-9._-]+","-",str(v)).strip("-")
    return s[:100] or "unknown"

def _flatten(v:Any,prefix:str="")->dict[str,Any]:
    if isinstance(v,dict):
        out={}
        for k in sorted(v):
            p=(prefix+"/"+str(k)) if prefix else "/"+str(k)
            out.update(_flatten(v[k],p))
        return out
    if isinstance(v,list):
        return {prefix or "/":v}
    return {prefix or "/":v}

def _state_path(source_id:str,deployment_id:str,state_root:Path)->Path:
    key=hashlib.sha256((source_id+"\0"+deployment_id).encode()).hexdigest()[:24]
    return state_root/(safe(source_id)+"-"+key+".json")

def _lock_path(source_id:str,deployment_id:str,state_root:Path)->Path:
    return _state_path(source_id,deployment_id,state_root).with_suffix(".lock")

def _load(path:Path)->dict[str,Any]:
    try:
        x=json.loads(path.read_text(encoding="utf-8"))
        return x if isinstance(x,dict) else {}
    except Exception:
        return {}

def _atomic(path:Path,obj:dict[str,Any])->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name(path.name+f".tmp-{os.getpid()}")
    tmp.write_text(json.dumps(obj,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    os.replace(tmp,path)

def _changes(previous:dict[str,Any],current:dict[str,Any])->list[dict[str,Any]]:
    before=_flatten(previous);after=_flatten(current);rows=[]
    for path in sorted(set(before)|set(after)):
        if path not in after:
            rows.append({"path":path,"op":"remove","before_digest":"sha256:"+digest(before[path])})
        elif path not in before or canonical(before[path])!=canonical(after[path]):
            row={"path":path,"op":"set","value":after[path]}
            if path in before:row["before_digest"]="sha256:"+digest(before[path])
            rows.append(row)
    return rows

def observe(*,project_id:str,source_id:str,source_kind:str,deployment_id:str,
            state:dict[str,Any],anomaly:dict[str,Any]|None=None,evidence_refs:list[str]|None=None,
            lineage:dict[str,Any]|None=None,
            personal_data_class:str="none",outbox_root:Path=DEFAULT_OUTBOX,state_root:Path=DEFAULT_STATE)->dict[str,Any]:
    if source_kind not in KINDS:raise ValueError("UNIVERSAL_LEARNING_SOURCE_KIND_INVALID")
    if personal_data_class not in {"none","aggregated","policy-authorized"}:
        raise ValueError("UNIVERSAL_LEARNING_PERSONAL_DATA_CLASS_INVALID")
    if not isinstance(state,dict):raise ValueError("UNIVERSAL_LEARNING_STATE_MUST_BE_OBJECT")
    if lineage is not None:
        if not isinstance(lineage,dict) or lineage.get("schema")!="chacha.dev/component-lineage/v1":
            raise ValueError("UNIVERSAL_LEARNING_LINEAGE_SCHEMA_INVALID")
        for row in lineage.get("components") or []:
            if not isinstance(row,dict) or not row.get("kind") or not row.get("component_id") or not row.get("version"):
                raise ValueError("UNIVERSAL_LEARNING_LINEAGE_COMPONENT_INVALID")
    state_root.mkdir(parents=True,exist_ok=True);outbox_root.mkdir(parents=True,exist_ok=True)
    sp=_state_path(source_id,deployment_id,state_root);lp=_lock_path(source_id,deployment_id,state_root)
    lp.parent.mkdir(parents=True,exist_ok=True)
    with open(lp,"a+",encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(),fcntl.LOCK_EX)
        prev=_load(sp)
        seq=int(prev.get("sequence") or 0)+1
        changes=_changes(prev.get("state") if isinstance(prev.get("state"),dict) else {},state)
        if not changes and not anomaly:
            return {"schema":"chacha.dev/universal-learning-observation/v1","status":"NO_CHANGE","queued":False,"sequence":int(prev.get("sequence") or 0)}
        change_digest=digest({"changes":changes,"anomaly":anomaly})
        delta_id="ld-"+hashlib.sha256(f"{source_id}\0{deployment_id}\0{seq}\0{change_digest}".encode()).hexdigest()[:40]
        delta={
          "schema":SCHEMA,"delta_id":delta_id,"project_id":str(project_id),"source_id":str(source_id),
          "source_kind":source_kind,"deployment_id":str(deployment_id),"sequence":seq,"observed_at":now_iso(),
          "changes":changes or [{"path":"/anomaly","op":"signal","value":"anomaly-only"}],
          "anomaly":anomaly,
          "lineage":lineage,
          "evidence_refs":[str(x) for x in (evidence_refs or [])],
          "privacy":{"raw_user_content":False,"contains_secrets":False,"personal_data_class":personal_data_class}
        }
        out=outbox_root/(delta_id+".json")
        _atomic(out,delta)
        _atomic(sp,{"schema":"chacha.dev/universal-learning-producer-state/v1","sequence":seq,"state":state,
                    "last_delta_id":delta_id,"last_change_digest":change_digest,"updated_at":now_iso()})
        return {"schema":"chacha.dev/universal-learning-observation/v1","status":"QUEUED","queued":True,
                "delta_id":delta_id,"sequence":seq,"change_count":len(changes),"outbox":str(out)}

def observe_platform(*,project_id:str,source_id:str,source_kind:str,state:dict[str,Any],
                     anomaly:dict[str,Any]|None=None,evidence_refs:list[str]|None=None,
                     lineage:dict[str,Any]|None=None)->dict[str,Any]:
    runtime=Path("/opt/chacha-dev/runtime")
    if not runtime.exists():
        return {"status":"NON_RUNTIME_TEST_BYPASS","queued":False}
    return observe(project_id=project_id,source_id=source_id,source_kind=source_kind,
                   deployment_id="chacha-dev-platform",state=state,anomaly=anomaly,evidence_refs=evidence_refs,lineage=lineage)
