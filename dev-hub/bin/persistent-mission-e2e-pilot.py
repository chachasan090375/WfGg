#!/usr/bin/env python3
from __future__ import annotations
import argparse
import json
import subprocess
import tempfile
from pathlib import Path

def run(args:list[str]):
    return subprocess.run(args,capture_output=True,text=True)

def blocked(reason:str)->dict:
    return {
        'schema':'chacha.dev/persistent-mission-e2e-pilot/v1',
        'status':'BLOCK',
        'reason':reason,
        'task_execution_performed':False,
        'production_mutation':False,
        'automatic_external_spend_eur':0,
    }

def pilot(controller:Path,mission_policy:Path,bridge:Path,bridge_policy:Path)->dict:
    td=Path(tempfile.mkdtemp(prefix='chacha-mission-e2e-pilot-'))
    plan=td/'plan.json';graph=td/'graph.json';state=td/'mission.json'
    resume=td/'resume.json';handoff=td/'handoff.json';stop=td/'stop.json'
    plan.write_text(json.dumps({
        'schema':'chacha.dev/execution-plan/v1','project':'pilot','transition':'BUILD',
        'waves':[{'index':1,'tasks':[{'task_id':'a'}]},{'index':2,'tasks':[{'task_id':'b'}]}],
    }))
    graph.write_text(json.dumps({
        'schema':'chacha.dev/task-graph/v1','project':'pilot','transition':'BUILD',
        'tasks':[{'id':'a','depends_on':[]},{'id':'b','depends_on':['a']}],
    }))
    stop.write_text(json.dumps({'active':False}))
    c=run(['python3',str(controller),'create','--mission-id','pilot-mission','--goal','prove resume',
           '--plan',str(plan),'--policy',str(mission_policy),'--state',str(state)])
    if c.returncode:return blocked('CREATE_FAILED')
    c=run(['python3',str(controller),'checkpoint','--state',str(state),'--policy',str(mission_policy),
           '--event-id','e1','--task-id','a','--result','PASS'])
    if c.returncode:return blocked('CHECKPOINT_FAILED')
    c=run(['python3',str(controller),'resume','--state',str(state),'--plan',str(plan),
           '--policy',str(mission_policy),'--stop-state',str(stop),'--output',str(resume)])
    if c.returncode:return blocked('RESUME_FAILED')
    c=run(['python3',str(bridge),'--policy',str(bridge_policy),'--mission',str(state),
           '--plan',str(plan),'--graph',str(graph),'--stop',str(stop),'--output',str(handoff)])
    h=json.loads(handoff.read_text()) if handoff.exists() else {}
    ok=c.returncode==0 and h.get('status')=='READY' and h.get('pending_tasks')==['b']
    ok=ok and h.get('bridge_executes_tasks') is False
    return {
        'schema':'chacha.dev/persistent-mission-e2e-pilot/v1','status':'PASS' if ok else 'BLOCK',
        'resume_status':json.loads(resume.read_text()).get('status'),'pending_tasks':h.get('pending_tasks'),
        'scheduler_handoff_ready':ok,'task_execution_performed':False,'production_mutation':False,
        'automatic_external_spend_eur':0,
    }

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument('--controller',type=Path,required=True);ap.add_argument('--mission-policy',type=Path,required=True)
    ap.add_argument('--bridge',type=Path,required=True);ap.add_argument('--bridge-policy',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    out=pilot(a.controller,a.mission_policy,a.bridge,a.bridge_policy)
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(out,indent=2,sort_keys=True)+'\n')
    print('CHACHA_DEV_PERSISTENT_MISSION_E2E_PILOT='+out['status']);print('TASK_EXECUTION_PERFORMED=NO')
    return 0 if out['status']=='PASS' else 20
if __name__=='__main__':raise SystemExit(main())
