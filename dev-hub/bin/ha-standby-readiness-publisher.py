#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path
from typing import Any

POLICY_SCHEMA="chacha.dev/ha-standby-readiness-publisher-policy/v1"

def load(path:Path)->dict[str,Any]:
    x=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(x,dict): raise ValueError("JSON_ROOT_NOT_OBJECT:"+str(path))
    return x

def digest(path:Path)->str:
    return "sha256:"+hashlib.sha256(path.read_bytes()).hexdigest()

def publish(policy:dict[str,Any],readiness:dict[str,Any],manifest:dict[str,Any],
            active_revision:str,readiness_path:Path,manifest_path:Path)->dict[str,Any]:
    if policy.get("schema")!=POLICY_SCHEMA: raise ValueError("POLICY_SCHEMA_INVALID")
    reasons=[];req=policy.get("requirements") or {}
    if readiness.get("schema")!=policy.get("accepted_readiness_schema"): reasons.append("READINESS_SCHEMA_INVALID")
    if manifest.get("schema")!=policy.get("accepted_manifest_schema"): reasons.append("MANIFEST_SCHEMA_INVALID")
    if readiness.get("status")!=policy.get("required_readiness_status"): reasons.append("READINESS_NOT_PASS")
    if readiness.get("state")!=policy.get("required_readiness_state"): reasons.append("READINESS_STATE_INVALID")
    if readiness.get("reasons") not in ([],None): reasons.append("READINESS_HAS_REASONS")
    primary=manifest.get("primary") if isinstance(manifest.get("primary"),dict) else {}
    standby=manifest.get("standby") if isinstance(manifest.get("standby"),dict) else {}
    if manifest.get("mode")!=policy.get("required_mode"): reasons.append("MODE_INVALID")
    if primary.get("role")!=policy.get("required_primary_role"): reasons.append("PRIMARY_ROLE_INVALID")
    if standby.get("role")!=policy.get("required_standby_role"): reasons.append("STANDBY_ROLE_INVALID")
    if not active_revision or len(active_revision)!=40: reasons.append("ACTIVE_REVISION_INVALID")
    if req.get("same_platform_revision") is True:
        if primary.get("platform_revision")!=active_revision: reasons.append("PRIMARY_REVISION_MISMATCH")
        if standby.get("platform_revision")!=active_revision: reasons.append("STANDBY_REVISION_MISMATCH")
    for field,code in (("single_writer_enforced","SINGLE_WRITER_NOT_ENFORCED"),
                       ("fencing_ready","FENCING_NOT_READY"),("rollback_ready","ROLLBACK_NOT_READY")):
        if req.get(field) is True and manifest.get(field) is not True: reasons.append(code)
    if req.get("failover_authorized") is False and readiness.get("failover_authorized") is not False:
        reasons.append("FAILOVER_MUST_REMAIN_UNAUTHORIZED")
    if req.get("production_activation_authorized") is False and readiness.get("production_activation_authorized") is not False:
        reasons.append("PRODUCTION_ACTIVATION_MUST_REMAIN_UNAUTHORIZED")
    if readiness.get("bastion_failover_state")!=policy.get("required_bastion_state"):
        reasons.append("BASTION_STATE_INVALID")
    if float(readiness.get("automatic_external_spend_eur") or 0)!=0 or float(manifest.get("automatic_external_spend_eur") or 0)!=0:
        reasons.append("NONZERO_EXTERNAL_SPEND")
    status="PASS" if not reasons else "BLOCK"
    return {
        "schema":str(policy.get("output_schema")),"status":status,
        "state":str(readiness.get("state") or "NOT_READY"),
        "platform_revision":active_revision,
        "primary_node_id":primary.get("node_id"),"standby_node_id":standby.get("node_id"),
        "checkpoint_id":readiness.get("checkpoint_id"),"reasons":reasons,
        "source_digests":{"readiness":digest(readiness_path),"manifest":digest(manifest_path)},
        "single_writer_enforced":manifest.get("single_writer_enforced") is True,
        "fencing_ready":manifest.get("fencing_ready") is True,
        "rollback_ready":manifest.get("rollback_ready") is True,
        "production_activation_authorized":False,"failover_authorized":False,
        "bastion_failover_state":str(readiness.get("bastion_failover_state") or "RESERVED_INACTIVE"),
        "d1_write_performed":False,"automatic_external_spend_eur":0
    }

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--policy",type=Path,required=True);ap.add_argument("--readiness",type=Path,required=True)
    ap.add_argument("--manifest",type=Path,required=True);ap.add_argument("--active-revision",required=True)
    ap.add_argument("--output",type=Path,required=True);a=ap.parse_args()
    out=publish(load(a.policy),load(a.readiness),load(a.manifest),a.active_revision,a.readiness,a.manifest)
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(out,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print("HA_STANDBY_READINESS_PUBLISHER="+out["status"]);print("PLATFORM_REVISION="+out["platform_revision"])
    print("FAILOVER_AUTHORIZED=NO");print("AUTOMATIC_EXTERNAL_SPEND_EUR=0")
    return 0 if out["status"]=="PASS" else 20

if __name__=="__main__": raise SystemExit(main())
