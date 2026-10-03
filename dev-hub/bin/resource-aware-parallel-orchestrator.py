#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,time
from pathlib import Path
from typing import Any
DIMS=('cpu_cores','ram_gib','gpu_vram_gib','storage_io_units','network_mbps')

def load(p:Path)->dict[str,Any]:
 x=json.loads(p.read_text(encoding='utf-8'))
 if not isinstance(x,dict):raise ValueError('JSON_ROOT_NOT_OBJECT')
 return x

def save(p:Path,x):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
def val(x,k):return float((x or {}).get(k) or 0)
def vec(x):return {k:val(x,k) for k in DIMS}
def fits(req,avail):return all(val(req,k)<=val(avail,k)+1e-9 for k in DIMS)
def subtract(avail,req):return {k:round(val(avail,k)-val(req,k),6) for k in DIMS}

def cycle(tasks:dict[str,dict[str,Any]])->list[str]|None:
 visiting=set();done=set();stack=[]
 def walk(t):
  if t in done:return None
  if t in visiting:
   i=stack.index(t) if t in stack else 0;return stack[i:]+[t]
  visiting.add(t);stack.append(t)
  for d in tasks[t].get('depends_on') or []:
   if d in tasks:
    r=walk(d)
    if r:return r
  stack.pop();visiting.remove(t);done.add(t);return None
 for t in tasks:
  r=walk(t)
  if r:return r
 return None

def critical_scores(tasks:dict[str,dict[str,Any]])->dict[str,float]:
 children={x:[] for x in tasks}
 for tid,t in tasks.items():
  for d in t.get('depends_on') or []:
   if d in tasks:children[d].append(tid)
 memo={}
 def score(tid):
  if tid in memo:return memo[tid]
  own=float(tasks[tid].get('estimated_minutes') or 1)
  memo[tid]=own+(max((score(c) for c in children[tid]),default=0))
  return memo[tid]
 return {tid:score(tid) for tid in tasks}

def effective_host(h:dict[str,Any])->dict[str,float]:
 base=vec(h.get('available_capacity') or h.get('usable_capacity') or {})
 pressure=h.get('pressure') or {}
 # Pressure is a live fraction already consumed from the safe/usable budget.
 return {k:round(max(0.0,base[k]*(1-min(1.0,max(0.0,float(pressure.get(k) or 0))))),6) for k in DIMS}

def plan(graph:dict[str,Any],resources:dict[str,Any],policy:dict[str,Any])->dict[str,Any]:
 raw=graph.get('tasks') or [];tasks={};blockers=[];warnings=[]
 for t in raw:
  tid=str(t.get('task_id') or '')
  if not tid or tid in tasks:blockers.append('TASK_ID_MISSING_OR_DUPLICATE:'+tid);continue
  tasks[tid]=dict(t)
 for tid,t in tasks.items():
  for d in t.get('depends_on') or []:
   if d not in tasks:blockers.append(f'DEPENDENCY_NOT_FOUND:{tid}:{d}')
 c=cycle(tasks)
 if c:blockers.append('TASK_DAG_CYCLE:'+'->'.join(c))
 allowed_health=set(policy.get('host_health_allowed') or [])
 hosts=[]
 for h in resources.get('hosts') or []:
  if str(h.get('health') or '').upper() not in allowed_health:continue
  eh=dict(h);eh['effective_capacity']=effective_host(h);hosts.append(eh)
 if not hosts:blockers.append('NO_HEALTHY_RESOURCE_HOST')
 scores=critical_scores(tasks) if not c else {tid:0 for tid in tasks}
 completed=set();waves=[];blocked_contract=[];unfit=[];remaining=set(tasks)
 wave_idx=0
 while remaining and not blockers:
  dependency_ready=[tid for tid in remaining if set(tasks[tid].get('depends_on') or []).issubset(completed)]
  contract_ready=[]
  for tid in dependency_ready:
   cs=str(tasks[tid].get('interface_contract_state') or 'NOT_REQUIRED').upper()
   if cs in set(policy.get('contract_states_allowed_for_execution') or []):contract_ready.append(tid)
   else:blocked_contract.append({'task_id':tid,'contract_state':cs});warnings.append(f'INTERFACE_CONTRACT_NOT_STABLE:{tid}:{cs}')
  candidates=sorted(contract_ready,key=lambda tid:(-scores.get(tid,0),-float(tasks[tid].get('priority') or 0),tid))
  residual={str(h['host_id']):dict(h['effective_capacity']) for h in hosts};assignments=[];scheduled=set()
  for tid in candidates:
   req=vec(tasks[tid].get('resources') or {})
   roles=set(map(str,tasks[tid].get('required_host_roles') or []))
   viable=[]
   for h in hosts:
    hid=str(h['host_id']);hroles=set(map(str,h.get('roles') or []))
    if roles and not roles.issubset(hroles):continue
    if fits(req,residual[hid]):
     # Prefer tightest RAM fit, then CPU, to leave larger hosts for heavier critical tasks.
     slack=(residual[hid]['ram_gib']-req['ram_gib'],residual[hid]['cpu_cores']-req['cpu_cores'],hid);viable.append((slack,hid))
   if not viable:continue
   _,hid=min(viable);residual[hid]=subtract(residual[hid],req);scheduled.add(tid)
   assignments.append({'task_id':tid,'host_id':hid,'resources':req,'critical_path_remaining_minutes':scores.get(tid,0),'priority':tasks[tid].get('priority') or 0,'integration_barrier':bool(tasks[tid].get('integration_barrier'))})
  if not scheduled:
   # If dependencies are ready but nothing fits, distinguish contract block from resource unfit.
   resource_candidates=[tid for tid in contract_ready]
   for tid in resource_candidates:
    req=vec(tasks[tid].get('resources') or {});roles=set(map(str,tasks[tid].get('required_host_roles') or []))
    ever=False
    for h in hosts:
     if roles and not roles.issubset(set(map(str,h.get('roles') or []))):continue
     if fits(req,h['effective_capacity']):ever=True;break
    if not ever:unfit.append({'task_id':tid,'resources':req,'required_host_roles':sorted(roles)})
   break
  waves.append({'wave':wave_idx,'parallel_task_count':len(assignments),'assignments':assignments,'host_residual_after_assignment':residual})
  completed.update(scheduled);remaining-=scheduled;wave_idx+=1
 # Tasks can remain because contract is unstable, dependency on such tasks, or unfit resources.
 remaining_rows=[]
 for tid in sorted(remaining):
  deps=[d for d in tasks[tid].get('depends_on') or [] if d not in completed]
  cs=str(tasks[tid].get('interface_contract_state') or 'NOT_REQUIRED').upper()
  reason='WAITING_DEPENDENCY' if deps else 'INTERFACE_CONTRACT_UNSTABLE' if cs not in set(policy.get('contract_states_allowed_for_execution') or []) else 'RESOURCE_UNFIT_OR_HOST_ROLE_UNAVAILABLE'
  remaining_rows.append({'task_id':tid,'reason':reason,'waiting_on':deps,'contract_state':cs})
 status='BLOCKED' if blockers else 'PARTIAL' if remaining else 'PASS'
 max_parallel=max([w['parallel_task_count'] for w in waves],default=0)
 return {'schema':'chacha.dev/resource-aware-parallel-plan/v1','status':status,'project_id':graph.get('project_id'),'waves':waves,'planned_task_count':len(completed),'total_task_count':len(tasks),'remaining_tasks':remaining_rows,'contract_blocks':blocked_contract,'resource_unfit':unfit,'critical_path_scores':scores,'max_parallel_tasks_planned':max_parallel,'adaptive_worker_count':max_parallel,'fixed_max_workers_used':False,'work_stealing_ready_queue':bool(policy.get('rules',{}).get('work_stealing_ready_queue')),'backpressure_enabled':bool(policy.get('rules',{}).get('backpressure')),'blockers':blockers,'warnings':sorted(set(warnings)),'execution_authority':False,'production_authority':False,'automatic_external_spend_eur':0,'planned_at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())}

def main()->int:
 ap=argparse.ArgumentParser();ap.add_argument('--graph',type=Path,required=True);ap.add_argument('--resources',type=Path,required=True);ap.add_argument('--policy',type=Path,default=Path('dev-hub/config/resource-aware-parallel-orchestrator.v1.json'));ap.add_argument('--output',type=Path,required=True);a=ap.parse_args();out=plan(load(a.graph),load(a.resources),load(a.policy));save(a.output,out);print('CHACHA_DEV_RESOURCE_AWARE_PARALLEL_ORCHESTRATOR='+out['status']);print('MAX_PARALLEL='+str(out['max_parallel_tasks_planned']));print('AUTOMATIC_EXTERNAL_SPEND_EUR=0');return 0 if out['status'] in {'PASS','PARTIAL'} else 2
if __name__=='__main__':raise SystemExit(main())
