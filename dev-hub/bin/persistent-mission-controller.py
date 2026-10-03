#!/usr/bin/env python3
from __future__ import annotations
import argparse, datetime, hashlib, json, os
from pathlib import Path
from typing import Any

POLICY_SCHEMA="chacha.dev/persistent-missions-policy/v1"
PLAN_SCHEMA="chacha.dev/execution-plan/v1"
STATE_SCHEMA="chacha.dev/persistent-mission/v1"
RESUME_SCHEMA="chacha.dev/persistent-mission-resume/v1"

def load(path:Path)->dict[str,Any]:
    value=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value,dict): raise ValueError("JSON_ROOT_NOT_OBJECT:"+str(path))
    return value

def atomic(path:Path,value:dict[str,Any])->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+".tmp")
    tmp.write_text(json.dumps(value,indent=2,ensure_ascii=False,sort_keys=True)+"\n",encoding="utf-8")
    os.replace(tmp,path)

def iso()->str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00","Z")

def digest(path:Path)->str:
    return "sha256:"+hashlib.sha256(path.read_bytes()).hexdigest()

def parse_time(value:str|None)->datetime.datetime|None:
    if not value: return None
    return datetime.datetime.fromisoformat(value.replace("Z","+00:00")).astimezone(datetime.timezone.utc)

def ordered_tasks(plan:dict[str,Any])->list[str]:
    out=[]
    for wave in plan.get("waves") or []:
        for task in wave.get("tasks") or []:
            tid=str(task.get("task_id") or "")
            if tid and tid not in out: out.append(tid)
    return out

def policy(path:Path)->dict[str,Any]:
    value=load(path)
    if value.get("schema")!=POLICY_SCHEMA: raise ValueError("POLICY_SCHEMA_MISMATCH")
    if int(value.get("automatic_external_spend_eur",-1))!=0: raise ValueError("NONZERO_SPEND_POLICY")
    return value

def require_plan(path:Path)->dict[str,Any]:
    value=load(path)
    if value.get("schema")!=PLAN_SCHEMA: raise ValueError("EXECUTION_PLAN_SCHEMA_MISMATCH")
    return value

def journal_for(state_path:Path)->Path:
    return state_path.parent/"checkpoints.jsonl"

def create(args)->dict[str,Any]:
    pol=policy(args.policy);plan=require_plan(args.plan);tasks=ordered_tasks(plan)
    if not tasks: raise ValueError("MISSION_PLAN_HAS_NO_TASKS")
    if args.state.exists(): raise ValueError("MISSION_STATE_EXISTS")
    now=iso()
    state={
        "schema":STATE_SCHEMA,"mission_id":args.mission_id,"goal":args.goal,
        "project":plan.get("project"),"transition":plan.get("transition"),
        "execution_plan_path":str(args.plan.resolve()),"execution_plan_digest":digest(args.plan),
        "task_order":tasks,"completed_tasks":[],"attempts":{},"applied_event_ids":[],
        "status":"ACTIVE","human_boundary":False,"created_at":now,"updated_at":now,
        "deadline_at":args.deadline_at,"next_resume_at":None,
        "automatic_external_spend_eur":0,"controller_executes_tasks":False
    }
    atomic(args.state,state)
    return state

def append_journal(path:Path,event:dict[str,Any],limit:int)->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    count=0
    if path.exists():
        with path.open("r",encoding="utf-8") as handle:
            count=sum(1 for _ in handle)
    if count>=limit: raise ValueError("CHECKPOINT_EVENT_LIMIT_REACHED")
    with path.open("a",encoding="utf-8") as handle:
        handle.write(json.dumps(event,ensure_ascii=False,sort_keys=True)+"\n")

def checkpoint(args)->dict[str,Any]:
    pol=policy(args.policy);state=load(args.state)
    if state.get("schema")!=STATE_SCHEMA: raise ValueError("MISSION_STATE_SCHEMA_MISMATCH")
    if args.event_id in set(state.get("applied_event_ids") or []):
        return state
    if args.task_id not in set(state.get("task_order") or []): raise ValueError("TASK_NOT_IN_MISSION")
    attempts=dict(state.get("attempts") or {})
    completed=list(state.get("completed_tasks") or [])
    if args.result=="PASS":
        if args.task_id not in completed: completed.append(args.task_id)
    elif args.result in {"FAILED","BLOCKED"}:
        attempts[args.task_id]=int(attempts.get(args.task_id,0))+1
    max_attempts=int((pol.get("limits") or {}).get("max_attempts_per_task",3))
    human=bool(args.human_boundary) or any(int(v)>=max_attempts for v in attempts.values())
    all_complete = set(completed) == set(state.get("task_order") or [])
    status = "COMPLETE" if all_complete and not human else ("AWAIT_HUMAN" if human else "ACTIVE")
    state.update({"completed_tasks":completed,"attempts":attempts,"human_boundary":human,
                  "status":status,"next_resume_at":args.next_resume_at,
                  "updated_at":iso(),"automatic_external_spend_eur":0,"controller_executes_tasks":False})
    state.setdefault("applied_event_ids",[]).append(args.event_id)
    event={"schema":"chacha.dev/persistent-mission-checkpoint/v1","event_id":args.event_id,
           "mission_id":state.get("mission_id"),"task_id":args.task_id,"result":args.result,
           "human_boundary":bool(args.human_boundary),"at":state["updated_at"],"automatic_external_spend_eur":0}
    append_journal(journal_for(args.state),event,int((pol.get("limits") or {}).get("max_checkpoint_events",10000)))
    atomic(args.state,state);return state

def resume(args)->dict[str,Any]:
    pol=policy(args.policy);state=load(args.state);plan=require_plan(args.plan)
    if state.get("schema")!=STATE_SCHEMA: raise ValueError("MISSION_STATE_SCHEMA_MISMATCH")
    if digest(args.plan)!=state.get("execution_plan_digest"): raise ValueError("EXECUTION_PLAN_DRIFT")
    stop_active=False
    if args.stop_state and args.stop_state.exists(): stop_active=load(args.stop_state).get("active") is True
    now=datetime.datetime.now(datetime.timezone.utc)
    deadline=parse_time(state.get("deadline_at"));reason=None;status="READY"
    if stop_active: status="BLOCKED";reason="EMERGENCY_STOP_ACTIVE"
    elif deadline and now>deadline: status="AWAIT_HUMAN";reason="MISSION_DEADLINE_EXCEEDED"
    elif state.get("human_boundary") is True: status="AWAIT_HUMAN";reason="HUMAN_BOUNDARY_REQUIRED"
    pending=[tid for tid in state.get("task_order") or [] if tid not in set(state.get("completed_tasks") or [])]
    if not pending and status=="READY": status="COMPLETE"
    out={"schema":RESUME_SCHEMA,"status":status,"reason":reason,"mission_id":state.get("mission_id"),
         "project":state.get("project"),"transition":state.get("transition"),"pending_tasks":pending,
         "completed_tasks":list(state.get("completed_tasks") or []),"attempts":dict(state.get("attempts") or {}),
         "next_resume_at":state.get("next_resume_at"),"execution_plan_digest":state.get("execution_plan_digest"),
         "scheduler_required":status=="READY","controller_executes_tasks":False,
         "production_mutation":False,"automatic_external_spend_eur":0,"generated_at":iso()}
    if args.output: atomic(args.output,out)
    return out

def complete(args)->dict[str,Any]:
    state=load(args.state)
    if set(state.get("completed_tasks") or [])!=set(state.get("task_order") or []): raise ValueError("MISSION_TASKS_INCOMPLETE")
    state.update({"status":"COMPLETE","updated_at":iso(),"next_resume_at":None,"automatic_external_spend_eur":0})
    atomic(args.state,state);return state

def main()->int:
    ap=argparse.ArgumentParser();sp=ap.add_subparsers(dest="cmd",required=True)
    p=sp.add_parser("create");p.add_argument("--mission-id",required=True);p.add_argument("--goal",required=True)
    p.add_argument("--plan",type=Path,required=True);p.add_argument("--policy",type=Path,required=True)
    p.add_argument("--state",type=Path,required=True);p.add_argument("--deadline-at")
    p=sp.add_parser("checkpoint");p.add_argument("--state",type=Path,required=True);p.add_argument("--policy",type=Path,required=True)
    p.add_argument("--event-id",required=True);p.add_argument("--task-id",required=True);p.add_argument("--result",choices=["PASS","FAILED","BLOCKED"],required=True)
    p.add_argument("--human-boundary",action="store_true");p.add_argument("--next-resume-at")
    p=sp.add_parser("resume");p.add_argument("--state",type=Path,required=True);p.add_argument("--plan",type=Path,required=True)
    p.add_argument("--policy",type=Path,required=True);p.add_argument("--stop-state",type=Path);p.add_argument("--output",type=Path)
    p=sp.add_parser("complete");p.add_argument("--state",type=Path,required=True);p.add_argument("--policy",type=Path,required=True)
    args=ap.parse_args()
    try:
        out={"create":create,"checkpoint":checkpoint,"resume":resume,"complete":complete}[args.cmd](args)
        print(json.dumps(out,ensure_ascii=False,sort_keys=True));return 0
    except Exception as exc:
        print(json.dumps({"schema":"chacha.dev/persistent-mission-error/v1","status":"BLOCK","reason":str(exc),"automatic_external_spend_eur":0},ensure_ascii=False));return 20

if __name__=="__main__": raise SystemExit(main())
