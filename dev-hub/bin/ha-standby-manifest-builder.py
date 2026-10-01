#!/usr/bin/env python3
from __future__ import annotations
import argparse,json
from pathlib import Path
from typing import Any

PROFILE_SCHEMA="chacha.dev/ha-standby-profile/v1"
RESOURCES_SCHEMA="chacha.dev/ha-node-resources/v1"
MANIFEST_SCHEMA="chacha.dev/ha-standby-manifest/v1"

def load(path:Path)->dict[str,Any]:
    value=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value,dict):
        raise ValueError("JSON_ROOT_NOT_OBJECT:"+str(path))
    return value

def require(value:dict[str,Any],schema:str,label:str)->None:
    if value.get("schema")!=schema:
        raise ValueError(f"SCHEMA_MISMATCH:{label}:{value.get('schema')}")

def build(profile:dict[str,Any],revision:str,resources:dict[str,Any],
          checkpoint_project:str,runtime_memory_mb:int,runtime_disk_mb:int)->dict[str,Any]:
    require(profile,PROFILE_SCHEMA,"profile")
    require(resources,RESOURCES_SCHEMA,"resources")
    if len(revision)!=40:
        raise ValueError("EXACT_REVISION_REQUIRED")
    safety=profile.get("safety") if isinstance(profile.get("safety"),dict) else {}
    requirements=profile.get("requirements") if isinstance(profile.get("requirements"),dict) else {}
    if safety.get("failover_authorized") is not False:
        raise ValueError("FAILOVER_MUST_REMAIN_DISABLED")
    if safety.get("active_writer") is not False:
        raise ValueError("STANDBY_ACTIVE_WRITER_FORBIDDEN")
    primary=profile.get("primary") if isinstance(profile.get("primary"),dict) else {}
    standby_profile=profile.get("standby") if isinstance(profile.get("standby"),dict) else {}
    if primary.get("failure_domain")==standby_profile.get("failure_domain"):
        raise ValueError("FAILURE_DOMAIN_NOT_DISTINCT")
    standby=resources.get("standby") if isinstance(resources.get("standby"),dict) else {}
    services=set(str(x) for x in (requirements.get("required_services") or []))
    return {
        "schema":MANIFEST_SCHEMA,
        "mode":profile["mode"],
        "checkpoint_project":checkpoint_project,
        "primary":{**primary,"platform_revision":revision},
        "standby":{**standby_profile,"platform_revision":revision,
                   "available_memory_mb":int(standby.get("available_memory_mb") or 0),
                   "free_disk_mb":int(standby.get("free_disk_mb") or 0),
                   "cpu_count":int(standby.get("cpu_count") or 0)},
        "runtime_memory_required_mb":runtime_memory_mb,
        "runtime_disk_required_mb":runtime_disk_mb,
        "state_replication":requirements.get("state_replication"),
        "single_writer_enforced":bool(requirements.get("single_writer_enforced")),
        "fencing_ready":bool(requirements.get("fencing_ready")),
        "rollback_ready":bool(requirements.get("rollback_ready")),
        "guardian_required":"guardian" in services,
        "sentinel_required":"sentinel" in services,
        "automatic_external_spend_eur":0,
    }

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--profile",type=Path,required=True)
    ap.add_argument("--revision",required=True)
    ap.add_argument("--resources",type=Path,required=True)
    ap.add_argument("--checkpoint-project",required=True)
    ap.add_argument("--runtime-memory-mb",type=int,required=True)
    ap.add_argument("--runtime-disk-mb",type=int,required=True)
    ap.add_argument("--output",type=Path,required=True)
    a=ap.parse_args()
    out=build(load(a.profile),a.revision,load(a.resources),a.checkpoint_project,
              a.runtime_memory_mb,a.runtime_disk_mb)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(out,indent=2)+"\n",encoding="utf-8")
    print("HA_STANDBY_MANIFEST=PASS")
    print("FAILOVER_AUTHORIZED=NO")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
