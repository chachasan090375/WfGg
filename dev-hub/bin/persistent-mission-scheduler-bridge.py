#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path
from typing import Any

def load(p:Path)->dict[str,Any]:
    x=json.loads(p.read_text(encoding='utf-8'))
    if not isinstance(x,dict):raise ValueError('JSON_OBJECT_REQUIRED:'+str(p))
    return x

def digest(p:Path)->str:return 'sha256:'+hashlib.sha256(p.read_bytes()).hexdigest()

def build(policy:dict[str,Any],mission:dict[str,Any],plan:dict[str,Any],graph:dict[str,Any],stop:dict[str,Any])->dict[str,Any]:
    if policy.get('schema')!='chacha.dev/persistent-mission-scheduler-bridge-policy/v1':raise ValueError('POLICY_SCHEMA_MISMATCH')
    if mission.get('schema')!=policy['mission_schema'] or plan.get('schema')!=policy['plan_schema'] or graph.get('schema')!=policy['graph_schema']:raise ValueError('SCHEMA_MISMATCH')
    if stop.get('active') is not False:return {'schema':policy['handoff_schema'],'status':'BLOCK','reason':'EMERGENCY_STOP_ACTIVE','automatic_external_spend_eur':0}
    completed=set(mission.get('completed_tasks') or []);pending=[x for x in mission.get('task_order') or [] if x not in completed]
    graph_tasks=[]
    for t in graph.get('tasks') or []:
        if t.get('id') not in pending:continue
        row=dict(t);row['depends_on']=[d for d in (t.get('depends_on') or []) if d not in completed];graph_tasks.append(row)
    waves=[]
    for w in plan.get('waves') or []:
        tasks=[dict(t) for t in (w.get('tasks') or []) if t.get('task_id') in pending]
        if tasks:waves.append({**w,'tasks':tasks})
    return {'schema':policy['handoff_schema'],'status':'COMPLETE' if not pending else 'READY','mission_id':mission.get('mission_id'),'pending_tasks':pending,'completed_tasks':sorted(completed),'graph':{**graph,'tasks':graph_tasks},'plan':{**plan,'waves':waves},'scheduler_required':bool(pending),'bridge_executes_tasks':False,'bridge_mutates_mission_state':False,'automatic_external_spend_eur':0}

def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument('--policy',type=Path,required=True);ap.add_argument('--mission',type=Path,required=True);ap.add_argument('--plan',type=Path,required=True);ap.add_argument('--graph',type=Path,required=True);ap.add_argument('--stop',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    try:
        pol,mission,plan,graph,stop=map(load,[a.policy,a.mission,a.plan,a.graph,a.stop])
        expected=str(mission.get('execution_plan_digest') or '')
        if expected and expected!=digest(a.plan):raise ValueError('EXECUTION_PLAN_DRIFT')
        if plan.get('project')!=graph.get('project') or plan.get('transition')!=graph.get('transition'):raise ValueError('PLAN_GRAPH_MISMATCH')
        out=build(pol,mission,plan,graph,stop);a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(out,indent=2,sort_keys=True)+'\n')
        print('CHACHA_DEV_PERSISTENT_MISSION_SCHEDULER_BRIDGE='+out['status']);print('PENDING='+str(len(out.get('pending_tasks') or [])));print('EXECUTION_AUTHORITY=NO');return 0 if out['status'] in {'READY','COMPLETE'} else 20
    except Exception as e:print('CHACHA_DEV_PERSISTENT_MISSION_SCHEDULER_BRIDGE=BLOCK');print('REASON='+str(e));return 20
if __name__=='__main__':raise SystemExit(main())
