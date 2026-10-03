#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,time
from pathlib import Path
from typing import Any

def load(p:Path)->dict[str,Any]:
 x=json.loads(p.read_text(encoding='utf-8'))
 if not isinstance(x,dict):raise ValueError('JSON_ROOT_NOT_OBJECT')
 return x

def save(p:Path,x):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
def uniq(xs):return list(dict.fromkeys(str(x) for x in xs if str(x)))

def nodes_from(inp:dict[str,Any])->list[dict[str,Any]]:
 if isinstance(inp.get('nodes'),list):return inp['nodes']
 graph=inp.get('solution_graph') if isinstance(inp.get('solution_graph'),dict) else {}
 if isinstance(graph.get('nodes'),list):return graph['nodes']
 return []

def resolve(inp:dict[str,Any],domains_cfg:dict[str,Any],caps_cfg:dict[str,Any],policy:dict[str,Any])->dict[str,Any]:
 domains=domains_cfg.get('domains') or {};caps=caps_cfg.get('capabilities') or {}
 blockers=[];warnings=[];cells=[];gaps=[];reuse=[]
 for node in nodes_from(inp):
  nid=str(node.get('node_id') or '')
  node_domains=uniq(node.get('domain_requirements') or [x.get('domain') for x in (node.get('specialist_cells') or []) if isinstance(x,dict)])
  explicit_caps=uniq(node.get('capability_requirements') or [])
  resolved_node=[]
  required_caps=[]
  for did in node_domains:
   d=domains.get(did)
   if not isinstance(d,dict):
    gaps.append({'gap_id':f'domain:{did}','node_id':nid,'kind':'DOMAIN_SPECIALIST','requested_id':did,'owner_foundry':'agent-foundry','state':'FOUNDRY_GAP_REQUEST','materialized':False,'execution_authority':False})
    warnings.append(f'DOMAIN_SPECIALIST_MISSING:{nid}:{did}');continue
   d_caps=uniq(d.get('capabilities') or [])
   required_caps.extend(d_caps)
   roles=uniq(d.get('roles') or [])
   transversal=list(policy.get('transversal',{}).get('always') or [])
   if did=='cybersecurity':transversal+=list(policy.get('transversal',{}).get('security_domains') or [])
   if did in {'ui-layout','graphics','animation','product'}:transversal+=list(policy.get('transversal',{}).get('ux_domains') or [])
   cell={'node_id':nid,'domain_id':did,'head':{'memory_namespace':str(policy.get('memory_namespace_pattern') or 'specialist:domain:{domain_id}').replace('{domain_id}',did),'roles':roles,'orchestrator':d.get('orchestrator'),'model':'CANONICAL_DOMAIN_HEAD_REFERENCE'},'arm':{'capability_ids':d_caps,'model':'CANONICAL_CAPABILITY_REFERENCES'},'transversal_support':uniq(transversal),'cloned':False,'execution_authority':False,'production_authority':False}
   resolved_node.append(cell);cells.append(cell)
  required_caps=uniq(required_caps+explicit_caps)
  cap_rows=[]
  for cid in required_caps:
   c=caps.get(cid)
   if isinstance(c,dict):
    providers=[p for p in (c.get('providers') or []) if isinstance(p,dict)]
    reusable=[p for p in providers if str(p.get('status') or '').upper() in {'ADOPT','PILOT','WATCH','ASSESS'}]
    row={'node_id':nid,'capability_id':cid,'resolution':'REUSE','provider_ids':[str(p.get('id')) for p in reusable if p.get('id')],'capability_class':c.get('class'),'materialize_new':False}
    cap_rows.append(row);reuse.append(row)
   else:
    gap={'gap_id':f'capability:{cid}','node_id':nid,'kind':'CAPABILITY','requested_id':cid,'owner_foundry':'capability-foundry','state':'FOUNDRY_GAP_REQUEST','materialized':False,'execution_authority':False}
    gaps.append(gap);cap_rows.append({'node_id':nid,'capability_id':cid,'resolution':'FOUNDRY_GAP_REQUEST','materialize_new':False})
  # node assembly summary, no duplicated operational Arm.
  if nid:
   node['resolved_specialist_cell_count']=len(resolved_node)
   node['resolved_capabilities']=cap_rows
 # Dedupe identical gaps from multiple domain declarations on same node but preserve cross-node needs.
 seen=set();dg=[]
 for g in gaps:
  k=(g['node_id'],g['kind'],g['requested_id'])
  if k in seen:continue
  seen.add(k);dg.append(g)
 gaps=dg
 return {'schema':'chacha.dev/specialist-cell-resolution/v1','status':'PASS' if not blockers else 'BLOCKED','project_id':inp.get('project_id'),'specialist_cells':cells,'reused_capabilities':reuse,'foundry_gap_requests':gaps,'blockers':blockers,'warnings':sorted(set(warnings)),'foundry_invoked':False,'automatic_materialization':False,'release_gate_support':list(policy.get('transversal',{}).get('release_gates') or []),'execution_authority':False,'production_authority':False,'automatic_external_spend_eur':0,'resolved_at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())}

def main()->int:
 ap=argparse.ArgumentParser();ap.add_argument('--input',type=Path,required=True);ap.add_argument('--domains',type=Path,default=Path('dev-hub/config/domain-orchestration.v1.json'));ap.add_argument('--capabilities',type=Path,default=Path('dev-hub/config/capability-registry.v1.json'));ap.add_argument('--policy',type=Path,default=Path('dev-hub/config/specialist-cell-resolver.v1.json'));ap.add_argument('--output',type=Path,required=True);a=ap.parse_args();out=resolve(load(a.input),load(a.domains),load(a.capabilities),load(a.policy));save(a.output,out);print('CHACHA_DEV_SPECIALIST_CELL_RESOLVER='+out['status']);print('FOUNDRY_INVOKED=NO');print('AUTOMATIC_EXTERNAL_SPEND_EUR=0');return 0 if out['status']=='PASS' else 2
if __name__=='__main__':raise SystemExit(main())
