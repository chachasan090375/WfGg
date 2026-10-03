#!/usr/bin/env python3
from __future__ import annotations
import argparse,importlib.util,json,time
from pathlib import Path

def load(p:Path):
 x=json.loads(p.read_text(encoding='utf-8'))
 if not isinstance(x,dict):raise ValueError('JSON_ROOT_NOT_OBJECT')
 return x

def save(p:Path,x):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
def module(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

def main()->int:
 ap=argparse.ArgumentParser();ap.add_argument('--intent',type=Path,required=True);ap.add_argument('--infrastructure',type=Path,required=True);ap.add_argument('--requirements',type=Path,required=True);ap.add_argument('--resources',type=Path,required=True);ap.add_argument('--target-matrix',type=Path,required=True);ap.add_argument('--host-inventory',type=Path,required=True);ap.add_argument('--work-dir',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args();root=Path(__file__).resolve().parents[1]
 feas_m=module('feas',root/'bin/infrastructure-feasibility-auditor.py');comp_m=module('comp',root/'bin/solution-composer.py');rec_m=module('rec',root/'bin/recursive-specialization-router.py');spec_m=module('spec',root/'bin/specialist-cell-resolver.py');exe_m=module('exe',root/'bin/execution-planner.py');par_m=module('par',root/'bin/resource-aware-parallel-orchestrator.py');os_m=module('oslab',root/'bin/virtual-os-device-lab-planner.py')
 work=a.work_dir;work.mkdir(parents=True,exist_ok=True);intent=load(a.intent)
 feas=feas_m.audit(load(a.infrastructure),load(a.requirements),load(root/'config/infrastructure-feasibility.v1.json'));save(work/'01-feasibility.json',feas)
 comp=comp_m.compose(intent,feas,load(root/'config/solution-composer.v1.json'));save(work/'02-composition.json',comp)
 rec=rec_m.resolve(comp.get('solution_graph') or {},load(root/'config/specialization-fabric.v2.json'),load(root/'config/deliverable-specialization.v1.json'),load(root/'config/application-archetype-specialization.v1.json'));save(work/'03-recursive-specialization.json',rec)
 spec=spec_m.resolve(rec,load(root/'config/domain-orchestration.v1.json'),load(root/'config/capability-registry.v1.json'),load(root/'config/specialist-cell-resolver.v1.json'));save(work/'04-specialists.json',spec)
 exe=exe_m.compile_plan(comp,spec,load(root/'config/execution-planner.v1.json'));save(work/'05-execution-plan.json',exe)
 parallel=par_m.plan(exe.get('task_graph') or {'tasks':[]},load(a.resources),load(root/'config/resource-aware-parallel-orchestrator.v1.json')) if exe.get('task_graph') else {'status':'BLOCKED','blockers':['EXECUTION_GRAPH_MISSING']};save(work/'06-parallel-plan.json',parallel)
 osplan=os_m.plan(load(a.target_matrix),load(a.host_inventory),load(root/'config/virtual-os-image-registry.v1.json'),load(root/'config/virtual-os-device-lab.v1.json'));save(work/'07-os-lab-plan.json',osplan)
 blockers=[]
 if feas.get('verdict')=='NOT_FIT':blockers.append('INFRASTRUCTURE_NOT_FIT')
 if rec.get('status')!='PASS':blockers.append('RECURSIVE_SPECIALIZATION_BLOCKED')
 if spec.get('status')!='PASS':blockers.append('SPECIALIST_RESOLUTION_BLOCKED')
 if spec.get('foundry_gap_requests'):blockers.append('FOUNDRY_GAPS_UNRESOLVED')
 if exe.get('status')!='PASS':blockers+=list(exe.get('blockers') or ['EXECUTION_PLAN_BLOCKED'])
 if parallel.get('status')!='PASS':blockers.append('PARALLEL_PLAN_NOT_READY')
 if osplan.get('status')!='PASS':blockers.append('TARGET_PLATFORM_MATRIX_NOT_READY')
 blockers=list(dict.fromkeys(blockers));status='SHADOW_PLAN_READY' if not blockers else 'BLOCKED'
 out={'schema':'chacha.dev/creation-runtime-e2e-shadow/v1','status':status,'project_id':intent.get('project_id'),'artifact_ref_count':len(intent.get('artifact_refs') or []),'feasibility':feas.get('verdict'),'recursive_nodes':rec.get('node_count'),'specialist_cells':len(spec.get('specialist_cells') or []),'foundry_gaps':len(spec.get('foundry_gap_requests') or []),'execution_tasks':exe.get('task_count'),'parallel_waves':len(parallel.get('waves') or []),'max_parallel_tasks_planned':parallel.get('max_parallel_tasks_planned'),'os_routes':len(osplan.get('routes') or []),'blockers':blockers,'task_execution_performed':False,'vm_creation_performed':False,'foundry_invoked':False,'production_mutation':False,'automatic_external_spend_eur':0,'receipts':[str((work/x).resolve()) for x in ['01-feasibility.json','02-composition.json','03-recursive-specialization.json','04-specialists.json','05-execution-plan.json','06-parallel-plan.json','07-os-lab-plan.json']],'observed_at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())};save(a.output,out);print('CHACHA_DEV_CREATION_RUNTIME_E2E_SHADOW='+status);print('TASK_EXECUTION=NO');print('VM_CREATION=NO');print('AUTOMATIC_EXTERNAL_SPEND_EUR=0');return 0
if __name__=='__main__':raise SystemExit(main())
