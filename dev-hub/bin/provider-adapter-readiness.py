#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,os
from pathlib import Path
from typing import Any

SCHEMA="chacha.dev/provider-adapter-readiness/v1"

def load(path:Path)->dict[str,Any]:
    value=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value,dict):raise SystemExit("JSON_ROOT_NOT_OBJECT="+str(path))
    return value

def save(path:Path,value:dict[str,Any])->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")

def inspect(repo_root:Path,requirements:Path,output:Path)->dict[str,Any]:
    req=load(requirements)
    if req.get("schema")!="chacha.dev/provider-health-requirements/v1":
        raise SystemExit("PROVIDER_HEALTH_REQUIREMENTS_SCHEMA_INVALID")
    registry=load(repo_root/"dev-hub/config/provider-adapters.v1.json")
    if registry.get("schema")!="chacha.dev/provider-adapter-registry/v1":
        raise SystemExit("PROVIDER_ADAPTER_REGISTRY_SCHEMA_INVALID")
    providers=registry.get("providers") or {}
    adapters=registry.get("adapters") or {}
    rows=[]
    counts={
      "ADAPTER_READY":0,
      "HEALTH_PROBE_REQUIRED":0,
      "ADAPTER_BUILD_REQUIRED":0,
      "ADAPTER_EXECUTABLE_MISSING":0,
      "PROVIDER_BINDING_MISSING":0
    }
    for item in req.get("providers") or []:
        if not isinstance(item,dict):continue
        pid=str(item.get("provider") or "")
        binding=providers.get(pid) if isinstance(providers,dict) else None
        state="PROVIDER_BINDING_MISSING"
        reason="provider-not-bound-in-adapter-registry"
        adapter_id=None;adapter={};executable=None;execution=None;kind=None
        if isinstance(binding,dict):
            adapter_id=str(binding.get("adapter") or "")
            execution=binding.get("execution")
            kind=binding.get("kind")
            adapter=adapters.get(adapter_id) if isinstance(adapters,dict) and adapter_id else None
            if not isinstance(adapter,dict):
                state="ADAPTER_BUILD_REQUIRED";reason="adapter-definition-missing";adapter={}
            else:
                executable=adapter.get("executable")
                status=str(adapter.get("status") or "")
                if execution=="external":
                    state="HEALTH_PROBE_REQUIRED";reason="external-provider-needs-fresh-functional-health-probe"
                elif isinstance(executable,str) and executable:
                    p=Path(executable)
                    if p.is_file() and os.access(p,os.X_OK):
                        state="HEALTH_PROBE_REQUIRED";reason="adapter-executable-ready-health-not-yet-proved"
                    else:
                        state="ADAPTER_EXECUTABLE_MISSING";reason="configured-adapter-executable-not-ready"
                elif status in {"ENABLED","PILOT"}:
                    state="ADAPTER_EXECUTABLE_MISSING";reason="enabled-adapter-has-no-executable"
                else:
                    state="ADAPTER_BUILD_REQUIRED";reason="adapter-not-executable"
        counts[state]=counts.get(state,0)+1
        rows.append({
          "provider":pid,
          "capabilities":[str(x) for x in item.get("capabilities") or []],
          "state":state,"reason":reason,
          "adapter_id":adapter_id,
          "adapter_status":adapter.get("status") if isinstance(adapter,dict) else None,
          "adapter_kind":kind,
          "execution":execution,
          "executable":executable,
          "network_access":adapter.get("network_access") if isinstance(adapter,dict) else None,
          "credentials_required":adapter.get("credentials_required") if isinstance(adapter,dict) else None
        })
    build_blockers=sum(counts.get(k,0) for k in (
      "ADAPTER_BUILD_REQUIRED","ADAPTER_EXECUTABLE_MISSING","PROVIDER_BINDING_MISSING"
    ))
    next_stage="PROVIDER_ADAPTER_BUILD_REQUIRED" if build_blockers else "PROVIDER_HEALTH_PROBE_REQUIRED"
    result={
      "schema":SCHEMA,
      "project_id":req.get("project_id"),
      "status":"BLOCKED" if rows else "READY",
      "next_stage":next_stage if rows else "DOMAIN_EXECUTION",
      "providers":rows,
      "summary":{
        "provider_count":len(rows),
        **counts,
        "adapter_build_blocker_count":build_blockers
      },
      "provider_health_not_inferred_from_adapter_presence":True,
      "automatic_external_spend_eur":0
    }
    save(output,result)
    return result

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--repo-root",type=Path,default=Path("/opt/chacha-dev/platform/current"))
    ap.add_argument("--requirements",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    a=ap.parse_args()
    result=inspect(a.repo_root.resolve(),a.requirements.resolve(),a.output.resolve())
    print("CHACHA_DEV_V819_PROVIDER_ADAPTER_READINESS=PASS")
    print("PROVIDERS="+str(result["summary"]["provider_count"]))
    print("ADAPTER_BUILD_BLOCKERS="+str(result["summary"]["adapter_build_blocker_count"]))
    print("NEXT_STAGE="+str(result["next_stage"]))
    print("AUTOMATIC_EXTERNAL_SPEND_EUR=0")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
