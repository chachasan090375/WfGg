#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, math, time
from pathlib import Path
from typing import Any

SCHEMA='chacha.dev/improvement-intelligence-synthesis/v1'
GENERIC_SIGNAL='chacha.dev/improvement-signal/v1'

def load(p:Path)->dict[str,Any]:
    x=json.loads(p.read_text(encoding='utf-8'))
    if not isinstance(x,dict): raise ValueError('JSON_ROOT_NOT_OBJECT:'+str(p))
    return x

def save(p:Path,x:dict[str,Any])->None:
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(x,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')

def digest(v:Any)->str:
    raw=json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()
    return 'sha256:'+hashlib.sha256(raw).hexdigest()

def now()->str:
    return time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())

def clamp(v:Any,lo:float=0,hi:float=100)->float:
    try:return max(lo,min(hi,float(v)))
    except Exception:return lo

def owner_for(source:str,policy:dict[str,Any])->str:
    # Stable source owner prevents one logical collector from inflating corroboration
    source=str(source).strip().lower()
    for cls,members in (policy.get('source_classes') or {}).items():
        if source in [str(x).lower() for x in members or []]: return cls
    return source or 'unknown'

def canonical_signal(raw:dict[str,Any],origin:Path,policy:dict[str,Any])->list[dict[str,Any]]:
    out=[]; schema=str(raw.get('schema') or '')
    if schema==GENERIC_SIGNAL:
        rows=[raw]
    elif schema=='chacha.dev/technology-self-benchmark-report/v1':
        rows=[]
        for m in raw.get('mechanisms') or []:
            rows.append({
              'signal_id':'self-benchmark:'+str(m.get('mechanism_id') or digest(m)[7:23]),
              'source_agent':'technology-watch','capability':m.get('capability') or m.get('mechanism_id'),
              'mechanism_id':m.get('mechanism_id'),'claim':m.get('functional_summary') or m.get('title') or str(m.get('mechanism_id')),
              'confidence':m.get('evidence_score',0),'evidence_refs':m.get('source_refs') or [],'source_timestamp':raw.get('generated_at') or now(),
              'architecture_fit':m.get('utility_gate_pass') is True,'global_value_score':m.get('global_value_score',0),
              'value_dimensions':m.get('platform_value') if isinstance(m.get('platform_value'),dict) else {},
              'maintenance_debt_score':m.get('maintenance_debt_score',0),'duplicate_capability':m.get('duplicate_capability',False),
              'material_gain_over_existing':m.get('material_gain_over_existing',True),'comparison_measured':m.get('comparison_measured',False),
              'recommendation':m.get('recommendation'),'provenance_verified':m.get('provenance_verified',False),
              'source_strategy':m.get('source_strategy'),'license_spdx':m.get('license_spdx'),'source_code_copy_allowed':m.get('source_code_copy_allowed',False),
              'target_component_id':m.get('target_component_id') or 'central-orchestrator','candidate_owner':m.get('candidate_owner') or 'branch-foundry'
            })
    elif schema in {'chacha.dev/dark-intelligence-dossier/v1','chacha.dev/technology-dossier/v1'}:
        rows=[]
        src='dark-intelligence' if 'dark-intelligence' in schema else 'technology-truth'
        claims=raw.get('claims') or raw.get('mechanisms') or []
        for i,c in enumerate(claims):
            rows.append({
              'signal_id':str(c.get('claim_id') or c.get('mechanism_id') or f'{src}:{i}'),'source_agent':src,
              'capability':c.get('capability') or c.get('domain') or 'unknown','mechanism_id':c.get('mechanism_id'),
              'claim':c.get('claim_text') or c.get('summary') or c.get('title') or 'Unspecified signal',
              'confidence':c.get('confidence') or c.get('evidence_score') or raw.get('confidence') or 0,
              'evidence_refs':c.get('evidence_refs') or c.get('source_refs') or raw.get('source_refs') or [],
              'source_timestamp':c.get('observed_at') or raw.get('observed_at') or now(),
              'provenance_verified':bool(c.get('provenance_verified',raw.get('provenance_verified',False))),
              'verification_receipt':c.get('verification_receipt') or raw.get('verification_receipt')
            })
    elif schema=='chacha.dev/agent-observation-event/v1':
        ver=str(raw.get('verification') or 'OBSERVED').upper(); et=str(raw.get('event_type') or 'OBSERVATION')
        severity=str(raw.get('severity') or '').upper(); details=raw.get('details') if isinstance(raw.get('details'),dict) else {}
        source=str(raw.get('source_id') or raw.get('subject_role') or 'runtime-telemetry')
        cap=(raw.get('capabilities') or [raw.get('subject_role') or 'platform-runtime'])[0]
        base_score=90 if ver=='VERIFIED' else 55 if ver=='OBSERVED' else 25
        value={}; global_value=35
        if et in {'VERIFIED_FAILURE','ROLLBACK','HANDOFF_FAILURE','HANDOFF_FAILURE_CLUSTER','REPEATED_REMEDIATION'}:
            value={'reliability':20,'maintainability':5};global_value=82
        elif et in {'SECURITY_INCIDENT','PERMISSION_DRIFT'}:
            value={'security':15,'reliability':10};global_value=90
        elif et=='PERFORMANCE_REGRESSION':
            value={'performance':15,'cost_efficiency':5};global_value=78
        elif et in {'DEPENDENCY_EOL_OR_DEPRECATION','SOURCE_CONFIDENCE_DROP'}:
            value={'maintainability':10,'reliability':10};global_value=72
        elif et=='TECHNOLOGY_WATCH_MATERIAL_DELTA':
            value={'performance':5,'maintainability':5};global_value=55
        claim=str(details.get('summary') or details.get('reason') or details.get('detail') or (et+' '+str(raw.get('outcome') or '')))
        rows=[{'signal_id':str(raw.get('event_id') or digest(raw)[7:23]),'source_agent':source,'capability':cap,
               'mechanism_id':details.get('mechanism_id'),'claim':claim,'confidence':base_score,
               'evidence_refs':raw.get('evidence_refs') or [raw.get('event_digest')],'source_timestamp':raw.get('observed_at') or now(),
               'provenance_verified':ver=='VERIFIED','runtime_local_signal':ver=='VERIFIED',
               'architecture_fit':ver=='VERIFIED','global_value_score':global_value,'value_dimensions':value,
               'recommendation':'RUNTIME_SIGNAL','verification':ver,'event_type':et,'severity':severity}]
    elif schema=='chacha.dev/technology-truth-score/v1':
        rec=str(raw.get('recommendation_class') or 'WATCH')
        tech=str(raw.get('technology_id') or 'technology-truth')
        rows=[{
          'signal_id':'technology-truth:'+tech+':'+str(raw.get('version') or 'unknown'),'source_agent':'technology-truth',
          'capability':tech,'mechanism_id':None,'claim':'Verified Technology Truth signal for '+tech+' '+str(raw.get('version') or ''),
          'confidence':raw.get('technical_truth_score',0),'evidence_refs':[str(origin)],'source_timestamp':now(),
          'provenance_verified':True,'verification_receipt':str(origin),'architecture_fit':float(raw.get('architecture_fit_score') or 0)>=65,
          # Truth is evidence quality, not global product value. Value stays zero until a comparison/utility signal exists.
          'global_value_score':None,'value_dimensions':{},'recommendation':rec,'runtime_local_signal':False,
          'target_component_id':'central-orchestrator','candidate_owner':'branch-foundry'
        }]
    elif schema in {'chacha.dev/guardian-verdict/v3','chacha.dev/sentinel-technical-receipt/v1'}:
        src='guardian' if 'guardian-verdict' in schema else 'sentinel'
        reasons=raw.get('reason_codes') or []
        rows=[{
          'signal_id':f"{src}:{raw.get('event_id') or raw.get('receipt_id') or digest(raw)[7:23]}",
          'source_agent':src,'capability':'governance-assurance','mechanism_id':None,
          'claim':'; '.join(map(str,reasons)) if reasons else f"{src} {raw.get('verdict') or raw.get('status')}",
          'confidence':100 if raw.get('verdict') in {'PASS','BLOCK','CRITICAL'} else 70,
          'evidence_refs':[raw.get('event_id') or raw.get('receipt_id')],'source_timestamp':raw.get('checked_at') or now(),
          'provenance_verified':True,'runtime_local_signal':True,
          'architecture_fit':True,'global_value_score':80 if reasons else 20,
          'value_dimensions':{'reliability':20,'security':20} if reasons else {}
        }]
    else:
        rows=[]
        # Generic adapter for other agents: accept items/signals/findings when minimally structured.
        seq=raw.get('signals') or raw.get('items') or raw.get('findings') or []
        source=str(raw.get('source_agent') or raw.get('agent_id') or raw.get('source') or 'unknown')
        for i,c in enumerate(seq if isinstance(seq,list) else []):
            if not isinstance(c,dict): continue
            rows.append({
              'signal_id':str(c.get('signal_id') or c.get('id') or f'{source}:{i}'),'source_agent':source,
              'capability':c.get('capability') or c.get('domain') or 'unknown','mechanism_id':c.get('mechanism_id'),
              'claim':c.get('claim') or c.get('summary') or c.get('detail') or c.get('title') or 'Unspecified signal',
              'confidence':c.get('confidence') or c.get('score') or 50,'evidence_refs':c.get('evidence_refs') or [],
              'source_timestamp':c.get('observed_at') or c.get('timestamp') or raw.get('generated_at') or now(),
              'provenance_verified':bool(c.get('provenance_verified',False)),
              'architecture_fit':c.get('architecture_fit'),'global_value_score':c.get('global_value_score',0),
              'value_dimensions':c.get('value_dimensions') or {},'runtime_local_signal':c.get('runtime_local_signal',False),
              'target_component_id':c.get('target_component_id') or 'central-orchestrator','candidate_owner':c.get('candidate_owner') or 'branch-foundry',
              'source_strategy':c.get('source_strategy'),'license_spdx':c.get('license_spdx'),'source_code_copy_allowed':c.get('source_code_copy_allowed',False)
            })
    authorized=set(map(str,policy.get('authorized_sources') or []))
    for row in rows:
        source=str(row.get('source_agent') or '').strip()
        if source not in authorized: continue
        claim=str(row.get('claim') or '').strip()
        cap=str(row.get('capability') or '').strip()
        if not claim or not cap: continue
        row['origin_file']=str(origin)
        row['confidence']=clamp(row.get('confidence'))
        row['source_owner']=owner_for(source,policy)
        row['claim_fingerprint']=digest({'capability':cap.casefold(),'claim':' '.join(claim.casefold().split())})
        row['signal_digest']=digest(row)
        out.append(row)
    return out

def value_score(rows:list[dict[str,Any]],policy:dict[str,Any])->tuple[float,dict[str,float]]:
    weights=(policy.get('utility_gate') or {}).get('dimensions') or {}
    dims={str(k):0.0 for k in weights}
    explicit=[]
    for r in rows:
        if r.get('global_value_score') is not None: explicit.append(clamp(r.get('global_value_score')))
        vd=r.get('value_dimensions') if isinstance(r.get('value_dimensions'),dict) else {}
        for k in dims: dims[k]=max(dims[k],clamp(vd.get(k),0,float(weights[k])))
    denom=sum(float(v) for v in weights.values()) or 1
    weighted=sum(dims[k] for k in dims)/denom*100
    if explicit: weighted=max(weighted,sum(explicit)/len(explicit))
    return round(clamp(weighted),2),{k:round(v,2) for k,v in dims.items()}

def synthesize(signals:list[dict[str,Any]],policy:dict[str,Any])->dict[str,Any]:
    groups={};order=list((policy.get('fusion') or {}).get('cluster_key_order') or ['capability','mechanism_id','claim_fingerprint'])
    for s in signals:
        key=''
        for field in order:
            value=s.get(str(field))
            if value not in (None,''):
                key=str(value);break
        if not key:key=str(s.get('claim_fingerprint') or s.get('signal_id') or 'unknown')
        groups.setdefault(key,[]).append(s)
    items=[]
    u=policy.get('utility_gate') or {}; minv=float(u.get('minimum_global_value_score') or 65)
    for key,rows in sorted(groups.items()):
        owners=sorted({str(r.get('source_owner')) for r in rows}); sources=sorted({str(r.get('source_agent')) for r in rows})
        confidence=round(sum(clamp(r.get('confidence')) for r in rows)/max(1,len(rows)),2)
        score,dims=value_score(rows,policy)
        runtime_local=any(r.get('runtime_local_signal') is True for r in rows)
        dark=any(r.get('source_agent')=='dark-intelligence' for r in rows)
        provenance=all(r.get('provenance_verified') is True for r in rows if r.get('source_agent') in {'dark-intelligence','technology-truth'})
        architecture_fit=any(r.get('architecture_fit') is True for r in rows) or runtime_local
        supported=sum(1 for v in dims.values() if v>0)
        reasons=[]
        if score<minv: reasons.append('GLOBAL_VALUE_SCORE_TOO_LOW')
        if u.get('architecture_fit_required') and not architecture_fit: reasons.append('ARCHITECTURE_FIT_NOT_PROVEN')
        if supported<int(u.get('minimum_supported_dimensions') or 1): reasons.append('NO_MEASURABLE_VALUE_DIMENSION')
        if dark and len(owners)<2: reasons.append('DARK_INTELLIGENCE_INDEPENDENT_CORROBORATION_REQUIRED')
        if dark and not provenance: reasons.append('DARK_INTELLIGENCE_PROVENANCE_NOT_VERIFIED')
        if any(float(r.get('maintenance_debt_score') or 0)>float(u.get('maximum_maintenance_debt_score') or 60) for r in rows): reasons.append('MAINTENANCE_DEBT_TOO_HIGH')
        contradictory=len({str(r.get('recommendation')) for r in rows if r.get('recommendation')})>1
        if contradictory: reasons.append('CONTRADICTORY_RECOMMENDATIONS')
        if contradictory: cls='CONTRADICTION_REVIEW'
        elif not reasons: cls='IMPROVEMENT_CANDIDATE'
        elif score>=40 or runtime_local: cls='WATCH'
        else: cls='IGNORE'
        title=next((r.get('title') for r in rows if r.get('title')),None) or str(key)
        claim=next((r.get('claim') for r in rows if r.get('claim')),str(key))
        items.append({
          'axis_id':'axis-'+hashlib.sha256(str(key).encode()).hexdigest()[:16], 'cluster_key':key,'title':title,
          'capability':rows[0].get('capability'),'functional_summary':claim,'recommendation':cls,
          'global_value_score':score,'value_dimensions':dims,'confidence':confidence,
          'source_agents':sources,'source_owners':owners,'distinct_source_classes':len(owners),
          'evidence_refs':sorted({str(e) for r in rows for e in (r.get('evidence_refs') or []) if e}),
          'signal_digests':[r.get('signal_digest') for r in rows], 'architecture_fit':architecture_fit,
          'provenance_verified':provenance or not dark,
          'source_strategy':next((r.get('source_strategy') for r in rows if r.get('source_strategy')),None),
          'license_spdx':next((r.get('license_spdx') for r in rows if r.get('license_spdx')),None),
          'source_code_copy_allowed':any(r.get('source_code_copy_allowed') is True for r in rows),
          'target_component_id':next((r.get('target_component_id') for r in rows if r.get('target_component_id')),'central-orchestrator'),
          'candidate_owner':next((r.get('candidate_owner') for r in rows if r.get('candidate_owner')),'branch-foundry'),
          'reason_codes':reasons,
          'improvement_request_authorized':cls=='IMPROVEMENT_CANDIDATE',
          'production_authority':False,'automatic_external_spend_eur':0
        })
    return {'schema':SCHEMA,'status':'PASS','generated_at':now(),'signal_count':len(signals),'axis_count':len(items),'items':items,
            'central_orchestrator_handoff_required':True,'direct_build_authority':False,'production_authority':False,
            'automatic_external_spend_eur':0}

def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument('--policy',type=Path,required=True);ap.add_argument('--input',type=Path,action='append',default=[]);ap.add_argument('--input-dir',type=Path,action='append',default=[]);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    policy=load(a.policy); files=list(a.input)
    for d in a.input_dir:
        if d.is_dir(): files += sorted(d.glob('*.json'))
    signals=[]
    for p in files:
        try: signals += canonical_signal(load(p),p,policy)
        except Exception as exc:
            signals.append({'signal_id':'ingest-error:'+p.name,'source_agent':'runtime-telemetry','capability':'intelligence-ingest','claim':str(exc)[:300],
                            'confidence':100,'evidence_refs':[str(p)],'source_timestamp':now(),'provenance_verified':True,'runtime_local_signal':True,
                            'architecture_fit':True,'global_value_score':60,'value_dimensions':{'reliability':10},'source_owner':'runtime_efficiency',
                            'claim_fingerprint':digest(str(exc)),'signal_digest':digest({'file':str(p),'error':str(exc)})})
    out=synthesize(signals,policy);save(a.output,out)
    print('CHACHA_DEV_IMPROVEMENT_INTELLIGENCE_FABRIC=PASS')
    print('SIGNALS='+str(out['signal_count']));print('AXES='+str(out['axis_count']))
    print('DIRECT_BUILD_AUTHORITY=NO');print('PRODUCTION_AUTHORITY=NO');print('AUTOMATIC_EXTERNAL_SPEND_EUR=0')
    return 0
if __name__=='__main__': raise SystemExit(main())
