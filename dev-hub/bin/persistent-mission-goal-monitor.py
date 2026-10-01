#!/usr/bin/env python3
from __future__ import annotations
import argparse,datetime,json
from pathlib import Path
from typing import Any
POLICY_SCHEMA="chacha.dev/persistent-mission-goal-monitor-policy/v1"
MISSION_SCHEMA="chacha.dev/persistent-mission/v1"
OUT_SCHEMA="chacha.dev/persistent-mission-goal-status/v1"

def load(path:Path)->dict[str,Any]:
    x=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise ValueError("JSON_ROOT_NOT_OBJECT")
    return x

def parse_time(v:str|None)->datetime.datetime|None:
    if not v:return None
    return datetime.datetime.fromisoformat(v.replace("Z","+00:00")).astimezone(datetime.timezone.utc)

def assess(policy:dict[str,Any],mission:dict[str,Any],now:datetime.datetime,stop_active:bool=False)->dict[str,Any]:
    if policy.get("schema")!=POLICY_SCHEMA:raise ValueError("POLICY_SCHEMA_MISMATCH")
    if mission.get("schema")!=MISSION_SCHEMA:raise ValueError("MISSION_SCHEMA_MISMATCH")
    total=len(mission.get("task_order") or []);done=len(set(mission.get("completed_tasks") or []))
    progress=1.0 if total==0 else done/total
    updated=parse_time(str(mission.get("updated_at") or ""));deadline=parse_time(mission.get("deadline_at"))
    stale_hours=((now-updated).total_seconds()/3600) if updated else 1e9
    reasons=[];state="HEALTHY"
    if stop_active:state="BLOCKED";reasons.append("EMERGENCY_STOP_ACTIVE")
    elif mission.get("human_boundary") is True:state="AWAIT_HUMAN";reasons.append("HUMAN_BOUNDARY_REQUIRED")
    elif deadline and now>deadline:state="AWAIT_HUMAN";reasons.append("MISSION_DEADLINE_EXCEEDED")
    elif stale_hours>float(policy.get("stale_after_hours") or 24):state="STALE";reasons.append("MISSION_PROGRESS_STALE")
    elif deadline and 0<=(deadline-now).total_seconds()/3600<=float(policy.get("deadline_warning_hours") or 6):state="WARNING";reasons.append("MISSION_DEADLINE_NEAR")
    if progress>=1 and state=="HEALTHY":state="COMPLETE"
    return {"schema":OUT_SCHEMA,"status":"PASS","mission_id":mission.get("mission_id"),"goal":mission.get("goal"),
            "state":state,"reasons":reasons,"progress":round(progress,4),"completed_tasks":done,"total_tasks":total,
            "stale_hours":round(stale_hours,2),"monitor_executes_tasks":False,"mission_state_mutation":False,
            "automatic_external_spend_eur":0}

def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument("--policy",type=Path,required=True);ap.add_argument("--mission",type=Path,required=True)
    ap.add_argument("--stop-state",type=Path);ap.add_argument("--output",type=Path,required=True);a=ap.parse_args()
    try:
        stop=bool(load(a.stop_state).get("active")) if a.stop_state and a.stop_state.exists() else False
        out=assess(load(a.policy),load(a.mission),datetime.datetime.now(datetime.timezone.utc),stop)
        a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(out,indent=2,sort_keys=True)+"\n")
        print("CHACHA_DEV_PERSISTENT_MISSION_GOAL_MONITOR=PASS");print("MISSION_STATE_MUTATION=NO");return 0
    except Exception as exc:
        print("CHACHA_DEV_PERSISTENT_MISSION_GOAL_MONITOR=BLOCK reason="+str(exc));return 20

if __name__=="__main__":raise SystemExit(main())
