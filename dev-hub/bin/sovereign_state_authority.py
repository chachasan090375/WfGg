#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path
from typing import Any
DEFAULT=Path('/opt/chacha-dev/runtime/sovereign-state/authority.json')
REMOTE={
 'guardian':'chacha-route://guardian.authority',
 'sentinel':'chacha-route://sentinel.authority',
 'assurance-exchange':'chacha-route://assurance.exchange',
 'learning-relay':'chacha-route://learning.relay'}
LOCAL={'guardian':'chacha-route://guardian.authority','sentinel':'chacha-route://sentinel.authority','assurance-exchange':'chacha-route://assurance.exchange','learning-relay':'chacha-route://learning.relay'}
def load(path:Path|None=None)->dict[str,Any]:
 path=path or DEFAULT
 if not path.is_file():return {'schema':'chacha.dev/sovereign-state-authority/v1','mode':'D1_REMOTE','generation':0,'services':REMOTE,'fallback_services':LOCAL,'source':'DEFAULT_REMOTE'}
 x=json.loads(path.read_text(encoding='utf-8'))
 if x.get('schema')!='chacha.dev/sovereign-state-authority/v1':raise RuntimeError('SOVEREIGN_STATE_AUTHORITY_SCHEMA_INVALID')
 if x.get('mode') not in {'D1_REMOTE','LOCAL_SQLITE'}:raise RuntimeError('SOVEREIGN_STATE_AUTHORITY_MODE_INVALID')
 services=x.get('services');
 if not isinstance(services,dict):raise RuntimeError('SOVEREIGN_STATE_AUTHORITY_SERVICES_INVALID')
 expected=LOCAL if x['mode']=='LOCAL_SQLITE' else REMOTE
 for k in expected:
  if str(services.get(k) or '')!=expected[k]:raise RuntimeError('SOVEREIGN_STATE_AUTHORITY_ENDPOINT_INVALID:'+k)
 return x
def endpoint(service:str,path:Path|None=None)->str:
 x=load(path);u=str((x.get('services') or {}).get(service) or '').rstrip('/')
 if not u:raise RuntimeError('SOVEREIGN_STATE_SERVICE_UNKNOWN:'+service)
 return u
def is_local_url(url:str)->bool:
 from urllib.parse import urlsplit
 return (urlsplit(url).hostname or '').lower() in {'127.0.0.1','localhost','::1'}
def d1_quota_applies(url:str)->bool:return not is_local_url(url)
