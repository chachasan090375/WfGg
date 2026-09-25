#!/usr/bin/env python3
from __future__ import annotations
import calendar,json,os,time
from pathlib import Path
from typing import Any

SCHEMA="chacha.dev/d1-account-quota-circuit/v1"
DEFAULT_STATE=Path("/opt/chacha-dev/runtime/control/d1-account-quota-circuit.json")

def now_epoch()->int:
    return int(time.time())

def now_iso(epoch:int|None=None)->str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime(now_epoch() if epoch is None else epoch))

def next_utc_midnight(epoch:int|None=None)->int:
    t=now_epoch() if epoch is None else int(epoch)
    g=time.gmtime(t)
    today_midnight=calendar.timegm((g.tm_year,g.tm_mon,g.tm_mday,0,0,0,0,0,0))
    return today_midnight+86400+5

def state_path()->Path:
    return Path(os.environ.get("CHACHA_D1_CIRCUIT_STATE",str(DEFAULT_STATE)))

def _strings(v:Any):
    if isinstance(v,dict):
        for k,x in v.items():
            yield str(k)
            yield from _strings(x)
    elif isinstance(v,list):
        for x in v: yield from _strings(x)
    elif v is not None:
        yield str(v)

def quota_class(payload:Any)->str|None:
    text=" ".join(_strings(payload)).casefold()
    if "d1_read_quota_exhausted" in text or "daily row read limit" in text:
        return "D1_READ_QUOTA_EXHAUSTED"
    if "d1_write_quota_exhausted" in text or "daily row write limit" in text:
        return "D1_WRITE_QUOTA_EXHAUSTED"
    return None

def read_state()->dict[str,Any]|None:
    p=state_path()
    try:
        x=json.loads(p.read_text(encoding="utf-8"))
        return x if isinstance(x,dict) else None
    except Exception:
        return None

def clear_if_expired(epoch:int|None=None)->bool:
    x=read_state()
    if not x:return False
    now=now_epoch() if epoch is None else int(epoch)
    if x.get("status")=="OPEN" and int(x.get("resume_epoch") or 0)>now:return False
    try:state_path().unlink(missing_ok=True)
    except Exception:pass
    return True

def blocked(epoch:int|None=None)->dict[str,Any]|None:
    clear_if_expired(epoch)
    x=read_state()
    if not x or x.get("status")!="OPEN":return None
    now=now_epoch() if epoch is None else int(epoch)
    if int(x.get("resume_epoch") or 0)<=now:return None
    return x

def open_circuit(reason:str,source:str,payload:Any=None,epoch:int|None=None)->dict[str,Any]:
    now=now_epoch() if epoch is None else int(epoch)
    resume=next_utc_midnight(now)
    prior=read_state() or {}
    sources=sorted(set([str(source),*[str(x) for x in prior.get("sources",[])]]))
    x={
      "schema":SCHEMA,"status":"OPEN","reason":str(reason),
      "opened_at":now_iso(now),"opened_epoch":now,
      "resume_at":now_iso(resume),"resume_epoch":resume,
      "sources":sources,"fail_closed":True,
      "automatic_paid_upgrade":False,"automatic_external_spend_eur":0
    }
    p=state_path();p.parent.mkdir(parents=True,exist_ok=True)
    tmp=p.with_suffix(p.suffix+".tmp")
    tmp.write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    os.replace(tmp,p)
    return x

def observe_response(payload:Any,source:str,epoch:int|None=None)->dict[str,Any]|None:
    reason=quota_class(payload)
    return open_circuit(reason,source,payload,epoch) if reason else None

def unavailable_payload(source:str,epoch:int|None=None)->dict[str,Any]|None:
    x=blocked(epoch)
    if not x:return None
    return {
      "schema":"chacha.dev/d1-quota-unavailable/v1",
      "status":"UNAVAILABLE","reason":"D1_ACCOUNT_QUOTA_CIRCUIT_OPEN",
      "quota_reason":x.get("reason"),"source":source,
      "resume_at":x.get("resume_at"),"fail_closed":True,
      "automatic_paid_upgrade":False,"automatic_external_spend_eur":0
    }