#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,re,time
from pathlib import Path
from typing import Any

def load(p:Path)->dict[str,Any]:
 x=json.loads(p.read_text(encoding='utf-8'))
 if not isinstance(x,dict):raise ValueError('JSON_ROOT_NOT_OBJECT')
 return x

def save(p:Path,x):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
def safe(x):return re.sub(r'[^a-zA-Z0-9._:-]+','-',str(x)).strip('-')
def uniq(xs):return list(dict.fromkeys(str(x) for x in xs if str(x)))

def choose_cap(node_id:str,spec:dict[str,Any],node:dict[str,Any],policy:dict[str,Any])->str:
 available=[x.get('capability_id') for x in spec.get('reused_capabilities') or [] if x.get('node_id')==node_id]
 available=uniq(available)
 for p in policy.get('preferred_capabilities') or []:
  if p in available:return p
 # Safe planning fallback to a canonical implementation capability where specialist resolution omitted a direct one.
 dc=str((node.get('classification') or {}).get('deliverable_class') or '')
 if dc=='document' and 'documentation' in available:return 'documentation'
 return available[0] if available else 'code-edit'

def task(tid,kind,cap,deps,res,mins,contract='NOT_REQUIRED',priority=0,barrier=False,node_id=None):
 return {'task_id':tid,'task_kind':kind,'node_id':node_id,'depends_on':uniq(deps),'runtime_capability':cap,'capabilities':[cap],'resources':dict(res),'estimated_minutes':float(mins),'interface_contract_state':contract,'priority':int(priority),'required_host_roles':['linux'],'integration_barrier':bool(barrier)}

def compile_plan(composition:dict[str,Any],specialists:dict[str,Any],policy:dict[str,Any])->dict[str,Any]:
 graph=composition.get('solution_graph') or {};nodes=[x for x in graph.get('nodes') or [] if isinstance(x,dict)];by={str(x.get('node_id')):x for x in nodes if x.get('node_id')}
 root_ids={nid for nid,n in by.items() if n.get('node_kind')=='project'}
 gaps=list(specialists.get('foundry_gap_requests') or [])
 tasks=[];contract_tasks={};touch={}
 # Interface contract stabilization comes before implementations on either side.
 for i,iface in enumerate(composition.get('interfaces') or []):
  src=str(iface.get('source') or '');dst=str(iface.get('target') or '')
  if not src or not dst:continue
  cid='contract:'+safe(src)+':'+safe(dst)+':'+str(i)
  contract_tasks[(src,dst,i)]=cid
  touch.setdefault(src,[]).append(cid);touch.setdefault(dst,[]).append(cid)
  tasks.append(task(cid,'INTERFACE_CONTRACT','integration-design',[],policy['default_resource_profiles']['contract'],4,'NOT_REQUIRED',100,False,None))
 impl_ids={nid:'implement:'+safe(nid) for nid in by if nid not in root_ids}
 for nid,n in by.items():
  if nid in root_ids:continue
  deps=list(touch.get(nid,[]))
  for d in n.get('dependencies') or []:
   if str(d) in impl_ids:deps.append(impl_ids[str(d)])
  cap=choose_cap(nid,specialists,n,policy)
  cells=sum(1 for x in specialists.get('specialist_cells') or [] if x.get('node_id')==nid)
  rp=dict(policy['default_resource_profiles']['implementation']);rp['cpu_cores']=round(float(rp['cpu_cores'])+max(0,cells-1)*0.08,3);rp['ram_gib']=round(float(rp['ram_gib'])+max(0,cells-1)*0.07,3)
  tasks.append(task(impl_ids[nid],'IMPLEMENT_NODE',cap,deps,rp,10+cells*2,'STABLE' if touch.get(nid) else 'NOT_REQUIRED',50,False,nid))
 impl=list(impl_ids.values())
 integration_id='integration:project'
 tasks.append(task(integration_id,'INTEGRATION','integration-design',impl,policy['default_resource_profiles']['integration'],8,'NOT_REQUIRED',90,True,None))
 tasks.append(task('verification:project','VERIFICATION','code-review',[integration_id],policy['default_resource_profiles']['verification'],7,'NOT_REQUIRED',100,True,None))
 # Atomic invariant: exactly one capability on each task.
 invariant_ok=all(len(x.get('capabilities') or [])==1 and x['capabilities'][0]==x.get('runtime_capability') for x in tasks)
 blockers=[]
 if not invariant_ok:blockers.append('ATOMIC_RUNTIME_CAPABILITY_INVARIANT_FAILED')
 if gaps:blockers.append('FOUNDRY_GAPS_UNRESOLVED')
 if composition.get('execution_blocked'):blockers.append('INFRASTRUCTURE_FEASIBILITY_BLOCKS_EXECUTION')
 status='PASS' if not blockers else 'BLOCKED'
 return {'schema':'chacha.dev/execution-plan/v1','status':status,'project_id':composition.get('project_id'),'task_graph':{'schema':'chacha.dev/execution-task-graph/v1','project_id':composition.get('project_id'),'tasks':tasks},'task_count':len(tasks),'interface_contract_task_count':len(contract_tasks),'implementation_task_count':len(impl),'foundry_gaps':gaps,'blockers':blockers,'execution_allowed':not blockers,'one_runtime_capability_per_task':invariant_ok,'foundry_invoked':False,'execution_authority':False,'production_authority':False,'automatic_external_spend_eur':0,'planned_at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())}

def main()->int:
 ap=argparse.ArgumentParser();ap.add_argument('--composition',type=Path,required=True);ap.add_argument('--specialists',type=Path,required=True);ap.add_argument('--policy',type=Path,default=Path('dev-hub/config/execution-planner.v1.json'));ap.add_argument('--output',type=Path,required=True);a=ap.parse_args();out=compile_plan(load(a.composition),load(a.specialists),load(a.policy));save(a.output,out);print('CHACHA_DEV_EXECUTION_PLANNER='+out['status']);print('TASKS='+str(out['task_count']));print('EXECUTION_ALLOWED='+('YES' if out['execution_allowed'] else 'NO'));print('AUTOMATIC_EXTERNAL_SPEND_EUR=0');return 0
if __name__=='__main__':raise SystemExit(main())
