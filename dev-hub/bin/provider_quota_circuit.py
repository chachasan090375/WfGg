#!/usr/bin/env python3
from __future__ import annotations
import json,os,re,time
from datetime import datetime,timezone,timedelta
from pathlib import Path
from typing import Any

SCHEMA='chacha.dev/provider-model-quota-circuit/v1'
DEFAULT_STATE=Path('/opt/chacha-dev/runtime/provider-economics/provider-model-quota-circuit.json')

def now_epoch()->int:return int(time.time())
def iso(epoch:int)->str:return datetime.fromtimestamp(int(epoch),timezone.utc).isoformat().replace('+00:00','Z')
def state_path()->Path:return Path(os.environ.get('CHACHA_PROVIDER_QUOTA_CIRCUIT_STATE',str(DEFAULT_STATE)))
def load_state()->dict[str,Any]:
    p=state_path()
    try:x=json.loads(p.read_text(encoding='utf-8'));return x if isinstance(x,dict) else {'schema':SCHEMA,'circuits':{}}
    except Exception:return {'schema':SCHEMA,'circuits':{}}
def save_state(x:dict[str,Any])->None:
    p=state_path();p.parent.mkdir(parents=True,exist_ok=True);tmp=p.with_suffix(p.suffix+'.tmp');tmp.write_text(json.dumps(x,indent=2,ensure_ascii=False)+'\n',encoding='utf-8');os.replace(tmp,p)
def key(provider:str,model:str)->str:return str(provider).strip().casefold()+'::'+str(model).strip().casefold()
def reset_epoch_from_text(text:str,epoch:int|None=None)->int|None:
    now=now_epoch() if epoch is None else int(epoch)
    for rx in [r'quotaResetTimeStamp["\s:=]+(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z)',r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z)']:
        m=re.search(rx,text,re.I)
        if m:
            try:return int(datetime.fromisoformat(m.group(1).replace('Z','+00:00')).timestamp())+5
            except Exception:pass
    m=re.search(r'Resets?\s+in\s+(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?',text,re.I)
    if m and any(m.groups()):return now+int(m.group(1) or 0)*3600+int(m.group(2) or 0)*60+int(m.group(3) or 0)+5
    m=re.search(r'quotaResetDelay["\s:=]+([0-9.]+)s',text,re.I)
    if m:
        try:return now+int(float(m.group(1)))+5
        except Exception:pass
    return None
def quota_exhausted(text:str)->bool:
    u=str(text or '').upper()
    signals=('RESOURCE_EXHAUSTED','QUOTA_EXHAUSTED','INDIVIDUAL QUOTA REACHED','PROVIDER_MODEL_QUOTA_EXHAUSTED')
    return any(x in u for x in signals) or ('HTTP 429' in u and 'QUOTA' in u)
def clear_expired(epoch:int|None=None)->dict[str,Any]:
    now=now_epoch() if epoch is None else int(epoch);x=load_state();rows=x.get('circuits') if isinstance(x.get('circuits'),dict) else {};changed=False
    for k in list(rows):
        r=rows[k]
        if not isinstance(r,dict) or int(r.get('resume_epoch') or 0)<=now:rows.pop(k,None);changed=True
    x={'schema':SCHEMA,'circuits':rows,'updated_at':iso(now),'automatic_paid_upgrade':False,'automatic_external_spend_eur':0}
    if changed:save_state(x)
    return x
def blocked(provider:str,model:str,epoch:int|None=None)->dict[str,Any]|None:
    x=clear_expired(epoch);r=(x.get('circuits') or {}).get(key(provider,model));return r if isinstance(r,dict) else None
def open_circuit(provider:str,model:str,text:str,source:str,epoch:int|None=None)->dict[str,Any]:
    now=now_epoch() if epoch is None else int(epoch);resume=reset_epoch_from_text(text,now) or now+3600
    x=clear_expired(now);rows=x.setdefault('circuits',{});k=key(provider,model);prior=rows.get(k) if isinstance(rows.get(k),dict) else {}
    row={'status':'OPEN','reason':'PROVIDER_MODEL_QUOTA_EXHAUSTED','provider':provider,'model':model,'opened_at':iso(now),'opened_epoch':now,'resume_at':iso(resume),'resume_epoch':resume,'sources':sorted(set([source,*prior.get('sources',[])])),'fail_closed':True,'automatic_paid_upgrade':False,'automatic_external_spend_eur':0}
    rows[k]=row;x['updated_at']=iso(now);x['automatic_paid_upgrade']=False;x['automatic_external_spend_eur']=0;save_state(x);return row
def observe_text(provider:str,model:str,text:str,source:str,epoch:int|None=None)->dict[str,Any]|None:
    return open_circuit(provider,model,text,source,epoch) if quota_exhausted(text) else None
