#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,sqlite3,uuid
from datetime import datetime,timezone
from pathlib import Path
from typing import Any

SCHEMA="chacha.dev/agent-observation-event/v1"

def now_iso()->str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00","Z")

def load(path:Path)->dict[str,Any]:
    x=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise ValueError("JSON_ROOT_NOT_OBJECT:"+str(path))
    return x

def save(path:Path,x:dict[str,Any])->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")

def default_policy_path()->Path:
    return Path(__file__).resolve().parents[1]/"config/agent-observation-bus.v1.json"

def default_policy()->dict[str,Any]:
    return load(default_policy_path())

def default_runtime_root()->Path:
    return Path("/opt/chacha-dev/runtime")

def db_path(runtime_root:Path,policy:dict[str,Any])->Path:
    raw=str(((policy.get("storage") or {}).get("database") or "agent-observation/observations.db"))
    p=Path(raw)
    return p if p.is_absolute() else runtime_root/p

def queue_root(runtime_root:Path,policy:dict[str,Any])->Path:
    raw=str(((policy.get("storage") or {}).get("reassessment_queue") or "agent-evolution/reassessment-queue"))
    p=Path(raw)
    return p if p.is_absolute() else runtime_root/p

def canonical(value:Any)->bytes:
    return json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(",",":")).encode()

def digest(value:Any)->str:
    return "sha256:"+hashlib.sha256(canonical(value)).hexdigest()

def connect(runtime_root:Path,policy:dict[str,Any])->sqlite3.Connection:
    path=db_path(runtime_root,policy);path.parent.mkdir(parents=True,exist_ok=True)
    con=sqlite3.connect(path,timeout=20)
    con.execute("pragma journal_mode=WAL")
    con.execute("pragma synchronous=FULL")
    con.execute("""create table if not exists observations(
      seq integer primary key autoincrement,
      event_id text not null unique,
      observed_at text not null,
      subject_role text not null,
      event_type text not null,
      verification text not null,
      prev_digest text,
      event_digest text not null,
      payload_json text not null
    )""")
    con.execute("create index if not exists idx_agent_observation_subject on observations(subject_role,seq)")
    con.execute("create index if not exists idx_agent_observation_type on observations(event_type,seq)")
    return con

def normalized_verification(event:dict[str,Any],policy:dict[str,Any])->tuple[str,list[str]]:
    requested=str(event.get("verification") or "OBSERVED").upper()
    if requested not in {"SELF_ASSERTED","OBSERVED","VERIFIED"}:requested="OBSERVED"
    source=str(event.get("source_id") or "")
    subject=str(event.get("subject_role") or "")
    refs=[str(x) for x in event.get("evidence_refs") or [] if str(x)]
    reasons=[]
    if source==subject:
        if requested!="SELF_ASSERTED":reasons.append("PRODUCER_SELF_ASSERTION_DOWNGRADED")
        return "SELF_ASSERTED",reasons
    if requested=="VERIFIED":
        allowed=set((policy.get("verification") or {}).get("independent_verified_sources") or [])
        if source not in allowed:
            reasons.append("SOURCE_NOT_INDEPENDENT_VERIFIER")
            return "OBSERVED",reasons
        if not refs:
            reasons.append("VERIFIED_EVIDENCE_REFS_REQUIRED")
            return "OBSERVED",reasons
    return requested,reasons

def validate_event(event:dict[str,Any],policy:dict[str,Any])->None:
    required=(policy.get("lineage") or {}).get("required") or []
    missing=[k for k in required if not str(event.get(k) or "").strip()]
    if missing:raise ValueError("AGENT_OBSERVATION_REQUIRED_FIELDS:"+",".join(missing))
    if event.get("capabilities") is not None and not isinstance(event.get("capabilities"),list):
        raise ValueError("AGENT_OBSERVATION_CAPABILITIES_INVALID")
    if event.get("evidence_refs") is not None and not isinstance(event.get("evidence_refs"),list):
        raise ValueError("AGENT_OBSERVATION_EVIDENCE_REFS_INVALID")

def trigger_type(event:dict[str,Any],policy:dict[str,Any])->str|None:
    if str(event.get("verification") or "")!="VERIFIED":return None
    et=str(event.get("event_type") or "")
    direct=set((policy.get("triggers") or {}).get("event_types") or [])
    if et in direct:return et
    outcome=str(event.get("outcome") or "").upper()
    for row in (policy.get("triggers") or {}).get("derived") or []:
        if not isinstance(row,dict):continue
        if et==str(row.get("event_type")) and outcome==str(row.get("outcome") or "").upper():
            return str(row.get("trigger") or "") or None
    return None

def write_trigger(event:dict[str,Any],policy:dict[str,Any],runtime_root:Path)->dict[str,Any]|None:
    trig=trigger_type(event,policy)
    if not trig:return None
    root=queue_root(runtime_root,policy);root.mkdir(parents=True,exist_ok=True)
    request={
      "schema":"chacha.dev/agent-reassessment-request/v1",
      "request_id":"reassess-"+str(event["event_id"]),
      "subject_role":event["subject_role"],
      "project_id":event["project_id"],
      "trigger_type":trig,
      "source_event_id":event["event_id"],
      "source_event_digest":event["event_digest"],
      "observed_at":event["observed_at"],
      "severity":event.get("severity"),
      "action":"REASSESS",
      "direct_agent_mutation":False,
      "direct_candidate_materialization":False,
      "candidate_owner":"agent-foundry",
      "technology_watch_revalidation_required":True,
      "logician_challenge_required":True,
      "guardian_preserved":True,
      "sentinel_preserved":True,
      "architecture_council_final_authority":True,
      "automatic_external_spend_eur":0
    }
    path=root/(request["request_id"]+".json")
    if not path.exists():save(path,request)
    return {"queued":True,"path":str(path),"trigger_type":trig}

def publish(event:dict[str,Any],policy:dict[str,Any]|None=None,runtime_root:Path|None=None)->dict[str,Any]:
    policy=policy or default_policy();runtime_root=runtime_root or default_runtime_root()
    x=dict(event)
    x.setdefault("schema",SCHEMA);x.setdefault("event_id","aobs-"+uuid.uuid4().hex);x.setdefault("observed_at",now_iso())
    x.setdefault("evidence_refs",[]);x.setdefault("capabilities",[]);x.setdefault("details",{})
    validate_event(x,policy)
    verification,reasons=normalized_verification(x,policy)
    x["verification_requested"]=str(x.get("verification") or "OBSERVED").upper()
    x["verification"]=verification
    x["verification_reason_codes"]=reasons
    con=connect(runtime_root,policy)
    try:
        con.execute("begin immediate")
        existing=con.execute("select seq,event_digest,payload_json from observations where event_id=?",(x["event_id"],)).fetchone()
        if existing:
            con.rollback()
            payload=json.loads(existing[2])
            return {"status":"DUPLICATE","inserted":False,"seq":existing[0],"event_digest":existing[1],"event":payload,"trigger":None}
        prev=con.execute("select event_digest from observations order by seq desc limit 1").fetchone()
        prev_digest=str(prev[0]) if prev else None
        x["prev_digest"]=prev_digest
        x["event_digest"]=digest({k:v for k,v in x.items() if k!="event_digest"})
        cur=con.execute(
          "insert into observations(event_id,observed_at,subject_role,event_type,verification,prev_digest,event_digest,payload_json) values(?,?,?,?,?,?,?,?)",
          (x["event_id"],x["observed_at"],x["subject_role"],x["event_type"],x["verification"],prev_digest,x["event_digest"],json.dumps(x,sort_keys=True,ensure_ascii=False))
        )
        con.commit();seq=int(cur.lastrowid)
    finally:
        con.close()
    trigger=write_trigger(x,policy,runtime_root)
    return {"status":"PASS","inserted":True,"seq":seq,"event_digest":x["event_digest"],"event":x,"trigger":trigger}

def read_events(runtime_root:Path,policy:dict[str,Any]|None=None,subject_role:str|None=None)->list[dict[str,Any]]:
    policy=policy or default_policy();path=db_path(runtime_root,policy)
    if not path.exists():return []
    con=connect(runtime_root,policy)
    try:
        if subject_role:
            rows=con.execute("select payload_json from observations where subject_role=? order by seq",(subject_role,)).fetchall()
        else:
            rows=con.execute("select payload_json from observations order by seq").fetchall()
        return [json.loads(r[0]) for r in rows]
    finally:con.close()

def verify_chain(runtime_root:Path,policy:dict[str,Any]|None=None)->dict[str,Any]:
    policy=policy or default_policy();events=read_events(runtime_root,policy)
    prev=None
    for i,x in enumerate(events,1):
        if x.get("prev_digest")!=prev:return {"status":"FAIL","seq":i,"reason":"PREV_DIGEST_MISMATCH"}
        expected=digest({k:v for k,v in x.items() if k!="event_digest"})
        if x.get("event_digest")!=expected:return {"status":"FAIL","seq":i,"reason":"EVENT_DIGEST_MISMATCH"}
        prev=x.get("event_digest")
    return {"status":"PASS","event_count":len(events),"head_digest":prev}

def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument("--runtime-root",type=Path,default=default_runtime_root());ap.add_argument("--policy",type=Path)
    sub=ap.add_subparsers(dest="cmd",required=True)
    p=sub.add_parser("publish");p.add_argument("--event",type=Path,required=True)
    sub.add_parser("verify")
    l=sub.add_parser("list");l.add_argument("--subject-role")
    a=ap.parse_args();policy=load(a.policy) if a.policy else default_policy()
    if a.cmd=="publish":
        out=publish(load(a.event),policy,a.runtime_root);print(json.dumps(out,ensure_ascii=False))
        print("CHACHA_DEV_V648_AGENT_OBSERVATION_PUBLISH="+("PASS" if out["status"] in {"PASS","DUPLICATE"} else "FAIL"))
        return 0
    if a.cmd=="verify":
        out=verify_chain(a.runtime_root,policy);print(json.dumps(out,ensure_ascii=False))
        print("CHACHA_DEV_V648_OBSERVATION_CHAIN="+out["status"]);return 0 if out["status"]=="PASS" else 2
    rows=read_events(a.runtime_root,policy,a.subject_role);print(json.dumps(rows,ensure_ascii=False));return 0

if __name__=="__main__":raise SystemExit(main())
