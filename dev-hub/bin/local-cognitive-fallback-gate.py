#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,os
from pathlib import Path
from typing import Any
POLICY_SCHEMA="chacha.dev/local-cognitive-fallback-policy/v1"
MANIFEST_SCHEMA="chacha.dev/local-cognitive-provider-manifest/v1"
HEALTH_SCHEMA="chacha.dev/provider-health-snapshot/v1"
RESOURCE_SCHEMA="chacha.dev/local-resource-snapshot/v1"

def load(path:Path)->dict[str,Any]:
    value=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value,dict): raise ValueError("JSON_ROOT_NOT_OBJECT:"+str(path))
    return value

def file_digest(path:Path)->str:
    return "sha256:"+hashlib.sha256(path.read_bytes()).hexdigest()

def check(policy:dict[str,Any],manifest:dict[str,Any],health:dict[str,Any],resources:dict[str,Any])->dict[str,Any]:
    if policy.get("schema")!=POLICY_SCHEMA: raise ValueError("POLICY_SCHEMA_MISMATCH")
    if manifest.get("schema")!=MANIFEST_SCHEMA: raise ValueError("MANIFEST_SCHEMA_MISMATCH")
    if health.get("schema")!=HEALTH_SCHEMA: raise ValueError("HEALTH_SCHEMA_MISMATCH")
    if resources.get("schema")!=RESOURCE_SCHEMA: raise ValueError("RESOURCE_SCHEMA_MISMATCH")
    reasons=[];req=policy.get("requirements") or {};head=policy.get("resource_headroom") or {}
    pid=str(manifest.get("provider_id") or "")
    if not pid: reasons.append("PROVIDER_ID_MISSING")
    if manifest.get("execution")!=req.get("execution"): reasons.append("EXECUTION_NOT_LOCAL_VPS")
    if manifest.get("inference_network_access")!=req.get("inference_network_access"): reasons.append("INFERENCE_REQUIRES_NETWORK")
    if str(manifest.get("cost_class") or "") not in set(policy.get("allowed_cost_classes") or []): reasons.append("COST_CLASS_NOT_LOCAL_OR_OWNED")
    if float(manifest.get("automatic_external_spend_eur") or 0)!=0: reasons.append("NONZERO_EXTERNAL_SPEND")
    exe=Path(str(manifest.get("executable") or ""));model=Path(str(manifest.get("model_artifact") or ""))
    if not exe.is_file() or not os.access(exe,os.X_OK): reasons.append("EXECUTABLE_NOT_READY")
    if not model.is_file(): reasons.append("LOCAL_MODEL_ARTIFACT_MISSING")
    expected=str(manifest.get("model_digest") or "")
    if not expected.startswith("sha256:"): reasons.append("MODEL_DIGEST_INVALID")
    elif model.is_file() and file_digest(model)!=expected: reasons.append("MODEL_DIGEST_MISMATCH")
    required=set(policy.get("required_capabilities") or []);provided=set(manifest.get("capabilities") or [])
    missing=sorted(required-provided)
    if missing: reasons.append("CAPABILITIES_MISSING:"+",".join(missing))
    snap=(health.get("providers") or {}).get(pid) if pid else None
    if not isinstance(snap,dict) or snap.get("state")!=req.get("health_state"): reasons.append("PROVIDER_NOT_HEALTHY")
    mem_need=int(manifest.get("memory_required_mb") or 0);disk_need=int(manifest.get("disk_required_mb") or 0)
    mem_avail=int(resources.get("available_memory_mb") or 0);disk_avail=int(resources.get("free_disk_mb") or 0)
    if mem_need<=0 or mem_avail-mem_need<int(head.get("minimum_free_memory_after_load_mb") or 0): reasons.append("MEMORY_HEADROOM_INSUFFICIENT")
    if disk_need<=0 or disk_avail-disk_need<int(head.get("minimum_free_disk_after_install_mb") or 0): reasons.append("DISK_HEADROOM_INSUFFICIENT")
    if manifest.get("structured_adapter") is not True: reasons.append("STRUCTURED_ADAPTER_REQUIRED")
    if manifest.get("rollback_ready") is not True: reasons.append("ROLLBACK_REQUIRED")
    ready=not reasons
    return {"schema":"chacha.dev/local-cognitive-fallback-readiness/v1","status":"PASS" if ready else "BLOCK",
      "state":"READY_FOR_GOVERNED_PILOT" if ready else "NOT_READY","provider_id":pid,"reasons":reasons,
      "required_capabilities":sorted(required),"provided_capabilities":sorted(provided),
      "production_activation_authorized":False,"promotion_authorized":False,"d1_write_performed":False,
      "automatic_external_spend_eur":0}

def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument("--policy",type=Path,required=True);ap.add_argument("--manifest",type=Path,required=True)
    ap.add_argument("--health",type=Path,required=True);ap.add_argument("--resources",type=Path,required=True);ap.add_argument("--output",type=Path,required=True);a=ap.parse_args()
    try: out=check(load(a.policy),load(a.manifest),load(a.health),load(a.resources))
    except Exception as exc: out={"schema":"chacha.dev/local-cognitive-fallback-readiness/v1","status":"BLOCK","state":"NOT_READY","reasons":[str(exc)],"production_activation_authorized":False,"promotion_authorized":False,"d1_write_performed":False,"automatic_external_spend_eur":0}
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(out,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print("LOCAL_COGNITIVE_FALLBACK_GATE="+out["status"]);print("STATE="+out["state"]);print("PRODUCTION_ACTIVATION_AUTHORIZED=NO");print("AUTOMATIC_EXTERNAL_SPEND_EUR=0")
    return 0 if out["status"]=="PASS" else 20

if __name__=="__main__": raise SystemExit(main())
