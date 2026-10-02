#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,subprocess,sys,uuid
from pathlib import Path

def run(cmd:list[str])->subprocess.CompletedProcess[str]:
 return subprocess.run(cmd,capture_output=True,text=True)
def load(p:Path):return json.loads(p.read_text())
def tasks(record:dict):
 for wave in record.get('waves') or []:
  for task in wave.get('tasks') or []:yield task

def main()->int:
 ap=argparse.ArgumentParser();ap.add_argument('--state',type=Path,required=True);ap.add_argument('--mission-policy',type=Path,required=True)
 ap.add_argument('--bridge',type=Path,required=True);ap.add_argument('--bridge-policy',type=Path,required=True);ap.add_argument('--plan',type=Path,required=True);ap.add_argument('--graph',type=Path,required=True);ap.add_argument('--stop',type=Path,required=True)
 ap.add_argument('--run-controller',type=Path,required=True);ap.add_argument('--ledger',type=Path,required=True);ap.add_argument('--run-policy',type=Path,required=True);ap.add_argument('--adapters',type=Path,required=True);ap.add_argument('--output-dir',type=Path,required=True);ap.add_argument('--workspace');ap.add_argument('--max-hops',type=int,default=64)
 ap.add_argument('--continuation-judge',type=Path);ap.add_argument('--continuation-authorization',type=Path);a=ap.parse_args()
 controller=Path(__file__).with_name('persistent-mission-controller.py');handoff=a.output_dir/'auto-chain-handoff.json';a.output_dir.mkdir(parents=True,exist_ok=True)
 if bool(a.continuation_judge) != bool(a.continuation_authorization):
  print('PERSISTENT_MISSION_AUTO_CHAIN=BLOCK\nREASON=INCOMPLETE_CONTINUATION_BOUNDARY');return 20
 for hop in range(a.max_hops):
  state=load(a.state)
  if state.get('status')=='COMPLETE' or len(state.get('completed_tasks') or [])==len(state.get('task_order') or []):
   print('PERSISTENT_MISSION_AUTO_CHAIN=COMPLETE');print('HOPS='+str(hop));return 0
  if a.continuation_judge:
   verdict=a.output_dir/f'continuation-verdict-{hop}.json'
   j=run([sys.executable,str(a.continuation_judge),'--mission',str(a.state),'--authorization',str(a.continuation_authorization),'--stop',str(a.stop),'--output',str(verdict)])
   if j.returncode or load(verdict).get('verdict')!='CONTINUE':
    print('PERSISTENT_MISSION_AUTO_CHAIN=BLOCK\nREASON=CONTINUATION_BOUNDARY');return 20
  c=run([sys.executable,str(a.bridge),'--policy',str(a.bridge_policy),'--mission',str(a.state),'--plan',str(a.plan),'--graph',str(a.graph),'--stop',str(a.stop),'--output',str(handoff)])
  if c.returncode:return 20
  h=load(handoff)
  if h.get('status')!='READY':print('PERSISTENT_MISSION_AUTO_CHAIN='+h.get('status','BLOCK'));return 20
  hp=a.output_dir/f"handoff-{hop}.json";hp.write_text(json.dumps(h,indent=2)+"\n")
  pp=a.output_dir/f"plan-{hop}.json";gp=a.output_dir/f"graph-{hop}.json";pp.write_text(json.dumps(h["plan"],indent=2)+"\n");gp.write_text(json.dumps(h["graph"],indent=2)+"\n")
  before=set(state.get("completed_tasks") or [])
  cmd=[sys.executable,str(a.run_controller),"--plan",str(pp),"--graph",str(gp),"--ledger",str(a.ledger),"--policy",str(a.run_policy),"--adapters",str(a.adapters),"--output-dir",str(a.output_dir/"runs"),"--execute"]
  if a.workspace:cmd += ["--workspace",a.workspace]
  c=run(cmd);runs=sorted((a.output_dir/"runs").glob("run-*/run-record.json"),key=lambda p:p.stat().st_mtime)
  if c.returncode or not runs:print("PERSISTENT_MISSION_AUTO_CHAIN=BLOCK\nREASON=RUN_CONTROLLER_FAILED");return 20
  rec=load(runs[-1]);progress=0
  for t in tasks(rec):
   tid=str(t.get("task_id") or "")
   if tid in before:continue
   status=str(t.get("status") or "");result="PASS" if status=="SUCCEEDED" else "FAILED" if status=="FAILED" else "BLOCKED"
   q=run([sys.executable,str(controller),"checkpoint","--state",str(a.state),"--policy",str(a.mission_policy),"--event-id","auto-"+str(uuid.uuid4()),"--task-id",tid,"--result",result])
   if q.returncode:return 20
   progress+=1
   if result!="PASS":print("PERSISTENT_MISSION_AUTO_CHAIN=BLOCK\nTASK="+tid);return 20
  if progress==0:print("PERSISTENT_MISSION_AUTO_CHAIN=BLOCK\nREASON=NO_PROGRESS");return 20
 print("PERSISTENT_MISSION_AUTO_CHAIN=BLOCK\nREASON=MAX_HOPS");return 20
if __name__=="__main__":raise SystemExit(main())
