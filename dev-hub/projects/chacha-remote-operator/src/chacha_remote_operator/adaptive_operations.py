from __future__ import annotations
import json, subprocess, sys, time, uuid
from pathlib import Path
from typing import Any
from .lease import command_lease
from .policy import OperatorPolicy, PolicyError

def guardian_check_event(policy: OperatorPolicy, event_path: str) -> dict[str, Any]:
    policy.require_operational()
    source=Path(event_path).resolve(strict=True)
    allowed=Path(str(policy.raw['guardian_event_allowed_root'])).resolve(strict=True)
    try: source.relative_to(allowed)
    except ValueError as exc: raise PolicyError('GUARDIAN_EVENT_OUTSIDE_ALLOWLIST') from exc
    event=json.loads(source.read_text(encoding='utf-8'))
    if event.get('schema')!='chacha.dev/governance-action/v1': raise PolicyError('GUARDIAN_EVENT_SCHEMA_INVALID')
    if event.get('phase') not in {'PRE_ACTION','POST_ACTION'}: raise PolicyError('GUARDIAN_EVENT_PHASE_INVALID')
    if float(event.get('automatic_external_spend_eur',event.get('evidence',{}).get('automatic_external_spend_eur',-1)))!=0: raise PolicyError('NONZERO_AUTOMATIC_EXTERNAL_SPEND_FORBIDDEN')
    client=Path(str(policy.raw['guardian_client_path'])); gp=Path(str(policy.raw['guardian_policy_path']))
    if not client.is_file() or not gp.is_file(): raise PolicyError('GUARDIAN_RUNTIME_DEPENDENCY_MISSING')
    with command_lease(policy.runtime_root,'guardian_check_event') as lease:
        policy.require_operational()
        proc=subprocess.run([sys.executable,str(client),'--policy',str(gp),'check','--event',str(source)],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,check=False,timeout=int(policy.raw.get('guardian_timeout_seconds',10)),shell=False)
    result=None
    for line in reversed(proc.stdout.splitlines()):
        try:
            v=json.loads(line.strip())
            if isinstance(v,dict): result=v; break
        except Exception: pass
    if result is None: raise PolicyError('GUARDIAN_RESULT_JSON_MISSING')
    return {'operation_id':'guardian_check_event','lease_id':lease['lease_id'],'returncode':proc.returncode,'guardian':result,'event_path':str(source)}
