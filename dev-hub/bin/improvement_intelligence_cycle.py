#!/usr/bin/env python3
from __future__ import annotations
import argparse,json
from pathlib import Path
from typing import Any
import agent_observation_bus as aob
import improvement_intelligence_fabric as iif
import autonomous_improvement_factory as aif
import canonical_component_registry as ccr

def load(p:Path)->dict[str,Any]:
    x=json.loads(p.read_text(encoding='utf-8'));return x if isinstance(x,dict) else {}
def save(p:Path,x:dict[str,Any]):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
def resolve_target(axis:dict[str,Any],registry:dict[str,Any])->tuple[str,str]:
    cap=str(axis.get('capability') or '')
    rows=[x for x in registry.get('components') or [] if isinstance(x,dict)]
    # Prefer exact/suffix match to an existing component; otherwise route a platform evolution through central-orchestrator.
    candidates=[r for r in rows if str(r.get('component_id') or '')==cap or str(r.get('component_id') or '').endswith(':'+cap)]
    row=candidates[0] if len(candidates)==1 else next((r for r in rows if str(r.get('component_id') or '').endswith(':central-orchestrator')),None)
    if row is None: row=next((r for r in rows if str(r.get('component_id') or '')=='central-orchestrator'),None)
    if row is None:return 'central-orchestrator','branch-foundry'
    return str(row.get('component_id') or 'central-orchestrator').split(':')[-1],str(row.get('evolution_owner') or 'branch-foundry')
def run(repo:Path,runtime:Path)->dict[str,Any]:
    cfg=repo/'dev-hub/config';ip=load(cfg/'improvement-intelligence-fabric.v1.json');fp=load(cfg/'autonomous-improvement-factory.v1.json')
    busp=load(cfg/'agent-observation-bus.v1.json');events=aob.read_events(runtime,busp)
    signals=[]
    for e in events:
        signals+=iif.canonical_signal(e,Path('agent-observation-bus:'+str(e.get('event_id') or 'event')),ip)
    inbox=runtime/'improvement-intelligence/signals'
    if inbox.is_dir():
        for p in sorted(inbox.glob('*.json')):
            try:signals+=iif.canonical_signal(load(p),p,ip)
            except Exception:continue
    synthesis=iif.synthesize(signals,ip);save(runtime/'improvement-intelligence/current/synthesis.json',synthesis)
    queue=aif.build_queue(synthesis,fp);save(runtime/'update-center/queue.json',queue)
    registry=ccr.build_registry(repo,load(cfg/'canonical-component-registry.v1.json'))
    outq=runtime/'platform-evolution/reassessment-queue';outq.mkdir(parents=True,exist_ok=True);created=[]
    for axis in synthesis.get('items') or []:
        if axis.get('improvement_request_authorized') is not True:continue
        target,owner=resolve_target(axis,registry)
        req={
          'schema':'chacha.dev/platform-component-reassessment-request/v1','request_id':'improvement-'+str(axis.get('axis_id')),
          'component_id':target,'candidate_owner':owner,
          'trigger_reasons':['IMPROVEMENT_INTELLIGENCE_CANDIDATE',str(axis.get('axis_id')),'VALUE_SCORE_'+str(axis.get('global_value_score'))],
          'improvement_axis':axis,'shadow_required':True,'pilot_required':True,
          'technology_watch_revalidation_required':True,'logician_falsification_required':True,
          'architecture_council_final_authority':True,'direct_component_mutation':False,'self_promotion':False,
          'production_authority':False,'automatic_external_spend_eur':0
        }
        path=outq/(req['request_id']+'.json')
        if not path.exists():save(path,req);created.append(str(path))
    return {'schema':'chacha.dev/improvement-intelligence-cycle/v1','status':'PASS','observation_event_count':len(events),
            'signal_count':len(signals),'axis_count':synthesis.get('axis_count'),'improvement_candidate_count':sum(1 for x in synthesis.get('items') or [] if x.get('improvement_request_authorized') is True),
            'new_reassessment_request_count':len(created),'created_requests':created,'update_center_item_count':len(queue.get('items') or []),
            'direct_component_mutation':False,'self_promotion':False,'production_authority':False,'automatic_external_spend_eur':0}
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--repo-root',type=Path,required=True);ap.add_argument('--runtime-root',type=Path,default=Path('/opt/chacha-dev/runtime'));ap.add_argument('--output',type=Path);a=ap.parse_args();out=run(a.repo_root.resolve(),a.runtime_root.resolve());
    if a.output:save(a.output,out)
    print(json.dumps(out,ensure_ascii=False));print('CHACHA_DEV_IMPROVEMENT_INTELLIGENCE_CYCLE=PASS');print('PRODUCTION_AUTHORITY=NO')
if __name__=='__main__':main()
