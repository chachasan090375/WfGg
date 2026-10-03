#!/usr/bin/env python3
from __future__ import annotations
import argparse,json
from pathlib import Path
from typing import Any
POLICY_SCHEMA="chacha.dev/canonical-route-authority/v1"
STATE_SCHEMA="chacha.dev/route-health-snapshot/v1"

def load(p:Path)->dict[str,Any]:
    x=json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(x,dict): raise ValueError("JSON_OBJECT_REQUIRED:"+str(p))
    return x

def resolve(policy:dict[str,Any],state:dict[str,Any],preferred_route:str)->dict[str,Any]:
    if policy.get("schema")!=POLICY_SCHEMA: raise ValueError("ROUTE_POLICY_SCHEMA_MISMATCH")
    if state.get("schema")!=STATE_SCHEMA: raise ValueError("ROUTE_STATE_SCHEMA_MISMATCH")
    principles=policy.get("principles") or {}
    if principles.get("unknown_route_fails_closed") is not True: raise ValueError("UNKNOWN_ROUTE_FAIL_CLOSED_REQUIRED")
    routes={r.get("route_id"):r for r in policy.get("routes") or [] if isinstance(r,dict)}
    route=routes.get(preferred_route)
    if not route:
        return {"status":"BLOCK","reason":"UNKNOWN_ROUTE","selected_route":None,"execution_authority":False}
    if state.get("canonical_stop_clear") is not True:
        return {"status":"BLOCK","reason":"CANONICAL_STOP_ACTIVE_OR_UNREADABLE","selected_route":None,"execution_authority":False}
    if state.get("security_gates_available") is not True:
        return {"status":"BLOCK","reason":"SECURITY_GATE_UNAVAILABLE","selected_route":None,"execution_authority":False}
    row=(state.get("routes") or {}).get(preferred_route) or {}
    if row.get("policy_allowed") is not True:
        return {"status":"BLOCK","reason":"POLICY_DENIED","selected_route":None,"execution_authority":False}
    supported=row.get("capability_supported") is True
    health=str(row.get("runtime_health") or "UNKNOWN")
    if supported and health=="HEALTHY":
        return {"status":"READY","reason":"PREFERRED_ROUTE_HEALTHY","selected_route":preferred_route,"fallback":False,"execution_authority":False}
    reason="CAPABILITY_NOT_SUPPORTED" if not supported else "PREFERRED_ROUTE_UNAVAILABLE" if health in {"UNAVAILABLE","UNKNOWN"} else "PREFERRED_ROUTE_UNHEALTHY"
    fallbacks=[]
    for candidate in routes.values():
        if preferred_route in (candidate.get("allowed_fallback_from") or []): fallbacks.append(candidate)
    if not fallbacks:
        return {"status":"BLOCK","reason":reason+":NO_PREDECLARED_FALLBACK","selected_route":None,"execution_authority":False}
    fallback=sorted(fallbacks,key=lambda x:int(x.get("priority") or 0),reverse=True)[0]
    allowed=set(fallback.get("allowed_reasons") or [])
    mapped={"CAPABILITY_NOT_SUPPORTED":"capability-not-supported","PREFERRED_ROUTE_UNAVAILABLE":"preferred-route-unavailable","PREFERRED_ROUTE_UNHEALTHY":"runtime-unhealthy"}[reason]
    if mapped not in allowed:
        return {"status":"BLOCK","reason":reason+":FALLBACK_REASON_NOT_AUTHORIZED","selected_route":None,"execution_authority":False}
    return {"status":"HUMAN_FALLBACK_REQUIRED","reason":reason,"selected_route":fallback.get("route_id"),"fallback":True,"execution_authority":False}

def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument('--policy',type=Path,required=True);ap.add_argument('--state',type=Path,required=True);ap.add_argument('--preferred-route',required=True);a=ap.parse_args()
    out=resolve(load(a.policy),load(a.state),a.preferred_route);print(json.dumps(out,indent=2,sort_keys=True));return 0 if out['status'] in {'READY','HUMAN_FALLBACK_REQUIRED'} else 20
if __name__=='__main__':raise SystemExit(main())
