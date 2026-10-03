#!/usr/bin/env python3
from __future__ import annotations
import argparse,json
from pathlib import Path
from typing import Any

REGISTRY_SCHEMA='chacha.dev/adaptive-model-registry/v1'
CATALOG_SCHEMA='chacha.dev/cognitive-model-catalog/v1'
OVERLAY_KEYS={'provider','model','health_state','quota_state','status','quality_score','latency_score','evidence_score','context_window','cost_class'}

def load(path:Path)->dict[str,Any]:
    x=json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(x,dict):raise ValueError('JSON_ROOT_NOT_OBJECT')
    return x

def validate(reg:dict[str,Any],gateways:dict[str,Any])->None:
    if reg.get('schema')!=REGISTRY_SCHEMA:raise ValueError('REGISTRY_SCHEMA_INVALID')
    seen=set();known=gateways.get('gateways') or {}
    for m in reg.get('models') or []:
        mid=str(m.get('id') or '')
        if not mid or mid in seen:raise ValueError('MODEL_ID_INVALID_OR_DUPLICATE:'+mid)
        seen.add(mid)
        gw=str(m.get('gateway') or '')
        if gw not in known:raise ValueError('UNKNOWN_GATEWAY:'+gw)
        if known[gw].get('decision_authority') is not False:raise ValueError('GATEWAY_AUTHORITY_FORBIDDEN:'+gw)
        if m.get('model')=='unbound' and m.get('health_state') in {'HEALTHY','DEGRADED'}:raise ValueError('UNBOUND_MODEL_CANNOT_BE_HEALTHY:'+mid)

def compile_catalog(reg:dict[str,Any],gateways:dict[str,Any],overlay:dict[str,Any]|None=None)->dict[str,Any]:
    validate(reg,gateways);models=json.loads(json.dumps(reg.get('models') or []));by={m['id']:m for m in models}
    for mid,changes in ((overlay or {}).get('models') or {}).items():
        if mid not in by:raise ValueError('OVERLAY_UNKNOWN_MODEL:'+mid)
        if not isinstance(changes,dict):raise ValueError('OVERLAY_MODEL_NOT_OBJECT:'+mid)
        illegal=set(changes)-OVERLAY_KEYS
        if illegal:raise ValueError('OVERLAY_FORBIDDEN_KEYS:'+','.join(sorted(illegal)))
        by[mid].update(changes)
    validate({'schema':REGISTRY_SCHEMA,'models':models},gateways)
    return {'schema':CATALOG_SCHEMA,'version':str(reg.get('version') or '1.0.0'),'models':models,
            'routing_authority':'CHACHA_DEV','automatic_external_spend_eur':0}

def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument('--registry',type=Path,required=True);ap.add_argument('--gateways',type=Path,required=True)
    ap.add_argument('--overlay',type=Path);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    reg=load(a.registry);gws=load(a.gateways);overlay=load(a.overlay) if a.overlay else None
    out=compile_catalog(reg,gws,overlay);a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(out,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    healthy=sum(1 for m in out['models'] if m.get('health_state') in {'HEALTHY','DEGRADED'})
    print('CHACHA_DEV_ADAPTIVE_MODEL_REGISTRY=PASS');print('MODELS='+str(len(out['models'])));print('HEALTHY_OR_DEGRADED='+str(healthy))
    print('ROUTING_AUTHORITY=CHACHA_DEV');print('AUTOMATIC_EXTERNAL_SPEND_EUR=0');return 0

if __name__=='__main__':raise SystemExit(main())
