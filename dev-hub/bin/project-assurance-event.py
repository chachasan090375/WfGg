#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,os,re,time,uuid
from pathlib import Path
from typing import Any

POLICY_SCHEMA="chacha.dev/project-embedded-assurance-policy/v1"
EVENT_SCHEMA="chacha.dev/project-assurance-event/v1"
FORBIDDEN_DEFAULT=["content","body","prompt","message","email","password","secret","token","authorization","cookie"]

def now()->str:return time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())
def canon(v:Any)->str:return json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(",",":"))
def load(p:Path)->dict[str,Any]:
    x=json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise RuntimeError("JSON_ROOT_NOT_OBJECT:"+str(p))
    return x
def digest(v:Any)->str:return "sha256:"+hashlib.sha256(canon(v).encode()).hexdigest()
def forbidden_key(key:str,policy:dict[str,Any])->bool:
    pats=(policy.get("privacy") or {}).get("forbidden_field_patterns") or FORBIDDEN_DEFAULT
    low=key.lower()
    return any(str(p).lower() in low for p in pats)
def sanitize_fields(fields:dict[str,Any],policy:dict[str,Any])->dict[str,Any]:
    allowed=set((policy.get("privacy") or {}).get("allow_fields") or [])
    out={}
    for k,v in fields.items():
        key=str(k)
        if forbidden_key(key,policy):raise RuntimeError("RAW_OR_SENSITIVE_FIELD_DENIED:"+key)
        if key not in allowed:raise RuntimeError("FIELD_NOT_ALLOWLISTED:"+key)
        if isinstance(v,(dict,list)):raise RuntimeError("NESTED_FIELD_DENIED:"+key)
        if isinstance(v,str) and len(v)>256:raise RuntimeError("FIELD_TOO_LARGE:"+key)
        out[key]=v
    return out
def build_event(project:str,version:str,role:str,event_type:str,severity:str,fields:dict[str,Any],policy:dict[str,Any])->dict[str,Any]:
    role_cfg=((policy.get("local_agents") or {}).get(role) or {})
    if event_type not in set(role_cfg.get("allowed_event_types") or []):
        raise RuntimeError("EVENT_TYPE_DENIED:"+role+":"+event_type)
    safe=sanitize_fields(fields,policy)
    safe["event_type"]=event_type;safe["severity"]=severity
    base={
      "schema":EVENT_SCHEMA,"event_id":"evt-"+uuid.uuid4().hex,
      "project_id":project,"application_version":version,"assurance_role":role,
      "observed_at":safe.pop("observed_at",now()),"fields":safe,
      "privacy":{"raw_user_content":False,"credentials":False,"secrets":False},
      "direct_mutation":False
    }
    base["event_digest"]=digest(base)
    return base
def append_event(outbox:Path,event:dict[str,Any],max_events:int)->Path:
    outbox.mkdir(parents=True,exist_ok=True)
    rows=sorted(outbox.glob("*.json"),key=lambda p:p.stat().st_mtime)
    while len(rows)>=max_events:
        rows.pop(0).unlink(missing_ok=True)
    path=outbox/(event["event_id"]+".json")
    tmp=path.with_suffix(".tmp");tmp.write_text(json.dumps(event,ensure_ascii=False,indent=2)+"\n",encoding="utf-8");os.replace(tmp,path)
    return path
def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument("--policy",type=Path,required=True);ap.add_argument("--bundle",type=Path,required=True)
    ap.add_argument("--role",required=True);ap.add_argument("--event-type",required=True)
    ap.add_argument("--application-version")
    ap.add_argument("--severity",choices=["INFO","WARNING","BLOCK","CRITICAL"],default="INFO");ap.add_argument("--fields-json",default="{}")
    a=ap.parse_args();policy=load(a.policy);manifest=load(a.bundle/"embedded-assurance.json")
    if policy.get("schema")!=POLICY_SCHEMA:raise SystemExit("ASSURANCE_POLICY_SCHEMA_INVALID")
    try:fields=json.loads(a.fields_json)
    except Exception:raise SystemExit("ASSURANCE_FIELDS_JSON_INVALID")
    if not isinstance(fields,dict):raise SystemExit("ASSURANCE_FIELDS_NOT_OBJECT")
    if a.role not in (policy.get("local_agents") or {}):raise SystemExit("ASSURANCE_ROLE_NOT_ACTIVE:"+str(a.role))
    application_version=str(a.application_version or manifest["application_version"])
    try:event=build_event(str(manifest["project_id"]),application_version,a.role,a.event_type,a.severity,fields,policy)
    except RuntimeError as exc:raise SystemExit(str(exc))
    p=append_event(a.bundle/"outbox"/a.role,event,int((policy.get("transport") or {}).get("max_outbox_events") or 5000))
    print("CHACHA_DEV_PROJECT_ASSURANCE_EVENT=QUEUED")
    print("ROLE="+a.role.upper());print("EVENT_ID="+event["event_id"]);print("EVENT="+str(p))
    print("RAW_USER_CONTENT=NO");print("DIRECT_MUTATION=NO");return 0
if __name__=="__main__":raise SystemExit(main())
