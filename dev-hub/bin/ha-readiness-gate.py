#!/usr/bin/env python3
from __future__ import annotations
import argparse,importlib.util,json
from datetime import datetime,timezone
from pathlib import Path
from typing import Any
POLICY_SCHEMA="chacha.dev/ha-readiness-policy/v1"
MANIFEST_SCHEMA="chacha.dev/ha-standby-manifest/v1"
HEALTH_SCHEMA="chacha.dev/ha-node-health/v1"

def load(path:Path)->dict[str,Any]:
    value=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value,dict): raise ValueError("JSON_ROOT_NOT_OBJECT:"+str(path))
    return value

def load_crypto(repo_root:Path):
    path=repo_root/"dev-hub/bin/crypto-trust.py"
    spec=importlib.util.spec_from_file_location("ha_crypto_trust",path)
    if spec is None or spec.loader is None: raise ValueError("CRYPTO_TRUST_LOAD_FAILED")
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod

def parse_iso(value:Any)->datetime|None:
    try:return datetime.fromisoformat(str(value).replace("Z","+00:00")).astimezone(timezone.utc)
    except Exception:return None

def check(policy:dict[str,Any],manifest:dict[str,Any],primary_health:dict[str,Any],standby_health:dict[str,Any],
          checkpoint:dict[str,Any],public_key:Path,restore:dict[str,Any],recovery:dict[str,Any],repo_root:Path,
          now:datetime|None=None)->dict[str,Any]:
    if policy.get("schema")!=POLICY_SCHEMA: raise ValueError("POLICY_SCHEMA_MISMATCH")
    if manifest.get("schema")!=MANIFEST_SCHEMA: raise ValueError("MANIFEST_SCHEMA_MISMATCH")
    if primary_health.get("schema")!=HEALTH_SCHEMA or standby_health.get("schema")!=HEALTH_SCHEMA:
        raise ValueError("HEALTH_SCHEMA_MISMATCH")
    reasons=[];req=policy.get("requirements") or {};head=policy.get("resource_headroom") or {}
    primary=manifest.get("primary") if isinstance(manifest.get("primary"),dict) else {}
    standby=manifest.get("standby") if isinstance(manifest.get("standby"),dict) else {}
    pid=str(primary.get("node_id") or "");sid=str(standby.get("node_id") or "")
    if str(manifest.get("mode") or "")!=str(policy.get("mode") or ""): reasons.append("MODE_NOT_ACTIVE_PASSIVE")
    if not pid or not sid: reasons.append("NODE_ID_MISSING")
    elif pid==sid: reasons.append("PRIMARY_STANDBY_NOT_DISTINCT")
    if primary.get("role")!=req.get("primary_role"): reasons.append("PRIMARY_ROLE_INVALID")
    if standby.get("role")!=req.get("standby_role"): reasons.append("STANDBY_ROLE_INVALID")
    if req.get("distinct_failure_domains") is True:
        pfd=str(primary.get("failure_domain") or "");sfd=str(standby.get("failure_domain") or "")
        if not pfd or not sfd or pfd==sfd: reasons.append("FAILURE_DOMAIN_NOT_DISTINCT")
    if req.get("same_platform_revision") is True:
        if not str(primary.get("platform_revision") or "") or primary.get("platform_revision")!=standby.get("platform_revision"):
            reasons.append("PLATFORM_REVISION_MISMATCH")
    for label,node_id,health in (("PRIMARY",pid,primary_health),("STANDBY",sid,standby_health)):
        if str(health.get("node_id") or "")!=node_id: reasons.append(label+"_HEALTH_NODE_MISMATCH")
        if health.get("state")!=req.get("health_state"): reasons.append(label+"_NOT_HEALTHY")
    services=standby_health.get("services") if isinstance(standby_health.get("services"),dict) else {}
    missing=[s for s in policy.get("required_services") or [] if services.get(s)!="READY"]
    if missing: reasons.append("STANDBY_SERVICE_PARITY_MISSING:"+",".join(sorted(missing)))
    if manifest.get("state_replication")!=req.get("state_replication"): reasons.append("STATE_REPLICATION_CONTRACT_INVALID")
    for field,code in (("single_writer_enforced","SINGLE_WRITER_NOT_ENFORCED"),("fencing_ready","FENCING_NOT_READY"),
                       ("rollback_ready","ROLLBACK_NOT_READY"),("guardian_required","GUARDIAN_NOT_REQUIRED"),
                       ("sentinel_required","SENTINEL_NOT_REQUIRED")):
        if req.get(field) is True and manifest.get(field) is not True: reasons.append(code)
    if float(manifest.get("automatic_external_spend_eur") or 0)!=0: reasons.append("NONZERO_EXTERNAL_SPEND")
    mem_need=int(manifest.get("runtime_memory_required_mb") or 0);disk_need=int(manifest.get("runtime_disk_required_mb") or 0)
    mem_avail=int(standby.get("available_memory_mb") or 0);disk_avail=int(standby.get("free_disk_mb") or 0);cpus=int(standby.get("cpu_count") or 0)
    if cpus<int(head.get("minimum_cpu_count") or 1): reasons.append("STANDBY_CPU_INSUFFICIENT")
    if mem_need<=0 or mem_avail-mem_need<int(head.get("minimum_free_memory_after_load_mb") or 0): reasons.append("STANDBY_MEMORY_HEADROOM_INSUFFICIENT")
    if disk_need<=0 or disk_avail-disk_need<int(head.get("minimum_free_disk_after_install_mb") or 0): reasons.append("STANDBY_DISK_HEADROOM_INSUFFICIENT")
    cp_policy=policy.get("checkpoint") or {}
    if checkpoint.get("schema")!=cp_policy.get("schema"): reasons.append("CHECKPOINT_SCHEMA_INVALID")
    if checkpoint.get("algorithm")!=cp_policy.get("algorithm"): reasons.append("CHECKPOINT_ALGORITHM_INVALID")
    if str(manifest.get("checkpoint_project") or "") and checkpoint.get("project")!=manifest.get("checkpoint_project"):
        reasons.append("CHECKPOINT_PROJECT_MISMATCH")
    if not public_key.is_file(): reasons.append("CHECKPOINT_PUBLIC_KEY_MISSING")
    else:
        try:
            errors=load_crypto(repo_root).verify_checkpoint(checkpoint,public_key)
            reasons.extend("CHECKPOINT_"+str(x) for x in errors)
        except BaseException as exc:
            reasons.append("CHECKPOINT_VERIFY_FAILED:"+str(exc))
    created=parse_iso(checkpoint.get("created_at"));now=now or datetime.now(timezone.utc)
    max_age=max(1,int(cp_policy.get("maximum_age_seconds") or 3600))
    if created is None: reasons.append("CHECKPOINT_CREATED_AT_INVALID")
    elif (now-created).total_seconds()<0 or (now-created).total_seconds()>max_age: reasons.append("CHECKPOINT_STALE")
    if restore.get("schema") not in set(policy.get("accepted_restore_evidence_schemas") or []): reasons.append("RESTORE_EVIDENCE_SCHEMA_INVALID")
    if restore.get("status")!="PASS": reasons.append("RESTORE_EVIDENCE_NOT_PASS")
    verifier=restore.get("verifier") if isinstance(restore.get("verifier"),dict) else {}
    restored=restore.get("restore") if isinstance(restore.get("restore"),dict) else {}
    if verifier.get("independent") is not True: reasons.append("RESTORE_VERIFIER_NOT_INDEPENDENT")
    if restored.get("sqlite_integrity") not in {None,"PASS"}: reasons.append("RESTORE_INTEGRITY_NOT_PASS")
    if recovery.get("schema") not in set(policy.get("accepted_recovery_evidence_schemas") or []): reasons.append("RECOVERY_EVIDENCE_SCHEMA_INVALID")
    if recovery.get("status")!="PASS": reasons.append("RECOVERY_DRILL_NOT_PASS")
    summary=recovery.get("summary") if isinstance(recovery.get("summary"),dict) else {}
    if int(summary.get("failed") or 0)!=0: reasons.append("RECOVERY_DRILL_FAILURES_PRESENT")
    ready=not reasons
    return {"schema":"chacha.dev/ha-readiness/v1","status":"PASS" if ready else "BLOCK",
      "state":"READY_FOR_GOVERNED_FAILOVER_PILOT" if ready else "NOT_READY","primary_node_id":pid,"standby_node_id":sid,
      "reasons":reasons,"checkpoint_id":checkpoint.get("checkpoint_id"),"production_activation_authorized":False,
      "failover_authorized":False,"bastion_failover_state":"RESERVED_INACTIVE","d1_write_performed":False,"automatic_external_spend_eur":0}
def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--repo-root",type=Path,required=True);ap.add_argument("--policy",type=Path,required=True)
    ap.add_argument("--manifest",type=Path,required=True);ap.add_argument("--primary-health",type=Path,required=True)
    ap.add_argument("--standby-health",type=Path,required=True);ap.add_argument("--checkpoint",type=Path,required=True)
    ap.add_argument("--public-key",type=Path,required=True);ap.add_argument("--restore-evidence",type=Path,required=True)
    ap.add_argument("--recovery-evidence",type=Path,required=True);ap.add_argument("--output",type=Path,required=True)
    a=ap.parse_args()
    try:
        out=check(load(a.policy),load(a.manifest),load(a.primary_health),load(a.standby_health),load(a.checkpoint),
                  a.public_key,load(a.restore_evidence),load(a.recovery_evidence),a.repo_root.resolve())
    except Exception as exc:
        out={"schema":"chacha.dev/ha-readiness/v1","status":"BLOCK","state":"NOT_READY","reasons":[str(exc)],
             "production_activation_authorized":False,"failover_authorized":False,"bastion_failover_state":"RESERVED_INACTIVE",
             "d1_write_performed":False,"automatic_external_spend_eur":0}
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(out,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print("HA_READINESS_GATE="+out["status"]);print("STATE="+out["state"])
    print("FAILOVER_AUTHORIZED=NO");print("BASTION_FAILOVER=RESERVED_INACTIVE");print("AUTOMATIC_EXTERNAL_SPEND_EUR=0")
    return 0 if out["status"]=="PASS" else 20

if __name__=="__main__": raise SystemExit(main())
