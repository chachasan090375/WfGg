#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,time,re
from pathlib import Path
from typing import Any

def load(p:Path)->dict[str,Any]:
 x=json.loads(p.read_text());
 if not isinstance(x,dict):raise ValueError('JSON_ROOT_NOT_OBJECT')
 return x

def save(p:Path,x):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,indent=2,ensure_ascii=False)+'\n')
def slug(x:str)->str:return re.sub(r'[^a-z0-9]+','-',x.casefold()).strip('-') or 'module'

def module_class(kind:str)->tuple[str,str|None,str|None,list[str]]:
 k=kind.casefold()
 table={
  'management':('application','business_management',None,['product','data-backend','ui-layout','cybersecurity']),
  'game':('application','game_realtime',None,['development','graphics','animation','data-backend']),
  'documentation':('document',None,'manual',['documentation','knowledge-research','translation','publication']),
  'reporting':('data_artifact',None,'dashboard',['data-backend','ui-layout']),
  'api':('application','system_infrastructure',None,['development','data-backend','cybersecurity']),
  'backend':('application','system_infrastructure',None,['development','data-backend','cybersecurity']),
  'frontend':('application','consumer_application',None,['development','ui-layout','graphics']),
  'animation':('animation_motion',None,'ui_animation',['animation','graphics']),
  'infrastructure':('infrastructure_system',None,'service_platform',['platform-release','cybersecurity','recovery'])}
 return table.get(k,('mixed_composite',None,'multi_deliverable_project',['product','development','qa']))

def compose(intent:dict[str,Any],feas:dict[str,Any],policy:dict[str,Any])->dict[str,Any]:
 if feas.get('schema')!='chacha.dev/infrastructure-feasibility-report/v1' or feas.get('status')!='PASS':
  return {'schema':'chacha.dev/solution-composition/v1','status':'BLOCKED','blockers':['INFRASTRUCTURE_FEASIBILITY_REPORT_REQUIRED'],'automatic_external_spend_eur':0}
 root_class=str(intent.get('deliverable_class') or 'application');root_arch=intent.get('archetype')
 root_id='solution-root';global_constraints=dict(intent.get('global_constraints') or {})
 nodes=[{'node_id':root_id,'node_kind':'project','classification':{'deliverable_class':root_class,'archetype':root_arch,'subtype':intent.get('subtype'),'confidence':float(intent.get('classification_confidence') or .9)},'constraints_local':global_constraints,'domain_requirements':list(intent.get('root_domains') or ['product','development','qa']),'dependencies':[]}]
 ids={};interfaces=[];reuse={}
 for idx,m in enumerate(intent.get('modules') or []):
  name=str(m.get('name') or f'Module {idx+1}');nid=slug(name);base=nid;s=2
  while nid in ids or nid==root_id:nid=f'{base}-{s}';s+=1
  ids[name]=nid
  dc,arch,sub,domains=module_class(str(m.get('kind') or 'mixed'))
  domains=list(dict.fromkeys(list(m.get('domains') or domains)))
  refs=list(m.get('reuse_candidates') or [])
  for r in refs:reuse.setdefault(str(r),[]).append(nid)
  nodes.append({'node_id':nid,'parent_id':root_id,'node_kind':'module','classification':{'deliverable_class':dc,'archetype':arch,'subtype':sub,'confidence':float(m.get('classification_confidence') or .9)},'constraints_local':dict(m.get('constraints') or {}),'domain_requirements':domains,'capability_requirements':list(m.get('capabilities') or []),'shared_component_refs':refs,'dependencies':[],'data_ownership':list(m.get('owns_data') or [])})
 for m in intent.get('modules') or []:
  src=ids.get(str(m.get('name') or '')); 
  if not src:continue
  row=next(x for x in nodes if x['node_id']==src)
  for depname in m.get('depends_on') or []:
   dep=ids.get(str(depname));
   if dep:row['dependencies'].append(dep)
  for iface in m.get('interfaces') or []:
   target=ids.get(str(iface.get('target') or ''))
   interfaces.append({'source':src,'target':target,'kind':iface.get('kind') or 'api','contract':iface.get('contract') or 'TO_BE_REFINED','status':'DESIGN_CONTRACT_REQUIRED'})
 verdict=feas['verdict'];execution_blocked=verdict=='NOT_FIT'
 status='DESIGN_READY_EXECUTION_BLOCKED_INFRASTRUCTURE' if execution_blocked else 'DESIGN_READY'
 return {'schema':'chacha.dev/solution-composition/v1','status':status,'project_id':intent.get('project_id'),'artifact_refs':list(intent.get('artifact_refs') or []),'feasibility_verdict':verdict,'design_infrastructure':'target_infrastructure_architecture' if execution_blocked else 'current_infrastructure','target_infrastructure_architecture':feas.get('target_infrastructure_architecture'),'solution_graph':{'schema':'chacha.dev/recursive-specialization-graph/v1','project_id':intent.get('project_id'),'nodes':nodes},'interfaces':interfaces,'reuse_candidates':reuse,'execution_blocked':execution_blocked,'requires_recursive_specialization_resolution':True,'requires_logician_challenge':True,'requires_guardian_sentinel_before_production':True,'production_authority':False,'execution_authority':False,'automatic_external_spend_eur':0,'composed_at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())}

def main()->int:
 ap=argparse.ArgumentParser();ap.add_argument('--intent',type=Path,required=True);ap.add_argument('--feasibility',type=Path,required=True);ap.add_argument('--policy',type=Path,default=Path('dev-hub/config/solution-composer.v1.json'));ap.add_argument('--output',type=Path,required=True);a=ap.parse_args();out=compose(load(a.intent),load(a.feasibility),load(a.policy));save(a.output,out);print('CHACHA_DEV_SOLUTION_COMPOSER='+out['status']);print('AUTOMATIC_EXTERNAL_SPEND_EUR=0');return 0 if not out['status'].startswith('BLOCKED') else 2
if __name__=='__main__':raise SystemExit(main())
