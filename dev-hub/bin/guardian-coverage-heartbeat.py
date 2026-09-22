#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,subprocess,time,uuid
from pathlib import Path
from typing import Any

DEFAULT_ROOT=Path("/opt/chacha-dev/platform/current")
DEFAULT_MANIFEST=DEFAULT_ROOT/"dev-hub/config/guardian-coverage-manifest.v1.json"
DEFAULT_POLICY=DEFAULT_ROOT/"dev-hub/config/guardian-runtime-policy.v1.json"
DEFAULT_CLIENT=DEFAULT_ROOT/"dev-hub/bin/guardian-client.py"
DEFAULT_OUT=Path("/opt/chacha-dev/runtime/guardian/coverage-latest.json")

def load(path:Path)->dict[str,Any]:
    x=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(x,dict): raise RuntimeError("JSON_ROOT_NOT_OBJECT:"+str(path))
    return x

def digest(path:Path)->str|None:
    try:return hashlib.sha256(path.read_bytes()).hexdigest()
    except Exception:return None

def proof_status(root:Path,component:dict[str,Any])->tuple[bool,dict[str,Any]]:
    proof=component.get("proof") if isinstance(component.get("proof"),dict) else {}
    rel=str(proof.get("file") or "")
    marker=str(proof.get("marker") or "")
    if not rel:return False,{"reason":"PROOF_FILE_MISSING"}
    path=root/rel
    if not path.is_file():return False,{"reason":"PROOF_TARGET_MISSING","file":rel}
    try:text=path.read_text(encoding="utf-8")
    except Exception as exc:return False,{"reason":"PROOF_READ_FAILED","file":rel,"error":type(exc).__name__}
    ok=bool(marker and marker in text)
    return ok,{"file":rel,"marker":marker,"marker_present":ok,"sha256":digest(path)}

def dynamic_class_status(root:Path,component:dict[str,Any])->tuple[bool,dict[str,Any]]:
    cid=str(component.get("component_id") or "")
    run_controller=root/"dev-hub/bin/run-controller.py"
    policy=root/"dev-hub/config/run-controller.v1.json"
    if not run_controller.is_file() or not policy.is_file():
        return False,{"reason":"RUN_CONTROLLER_GOVERNANCE_MISSING"}
    source=run_controller.read_text(encoding="utf-8")
    cfg=load(policy)
    guardian_enabled=bool((cfg.get("guardian") or {}).get("enabled"))
    if cid=="class:dynamic-agents":
        ok=guardian_enabled and "owner_role" in source and "guardian_gate(" in source
        return ok,{"guardian_enabled":guardian_enabled,"owner_role_hook":"owner_role" in source,"guardian_gate":"guardian_gate(" in source}
    if cid=="class:registered-adapters":
        adapters_path=root/"dev-hub/config/provider-adapters.v1.json"
        if not adapters_path.is_file():return False,{"reason":"ADAPTER_REGISTRY_MISSING"}
        adapters=load(adapters_path)
        rows=adapters.get("adapters") or {}
        providers=adapters.get("providers") or {}
        mapped=set()
        for p in providers.values():
            if isinstance(p,dict) and p.get("adapter"):mapped.add(str(p["adapter"]))
        all_ids=set(map(str,rows.keys()))
        complete=bool(all_ids) and all_ids.issubset(mapped) and all(isinstance(v,dict) and isinstance(v.get("supports"),list) for v in rows.values())
        ok=guardian_enabled and "guardian_gate(" in source and complete
        return ok,{"guardian_enabled":guardian_enabled,"adapter_count":len(rows),"provider_mapped_adapter_count":len(mapped),
                   "registry_complete":complete,"guardian_gate":"guardian_gate(" in source}
    return proof_status(root,component)

def build(root:Path,manifest_path:Path)->dict[str,Any]:
    m=load(manifest_path)
    rows=[]
    for component in m.get("expected_components") or []:
        if not isinstance(component,dict) or not component.get("component_id"):continue
        cid=str(component["component_id"])
        if str(component.get("kind"))=="dynamic-class":
            active,details=dynamic_class_status(root,component)
        else:
            active,details=proof_status(root,component)
        rows.append({
          "component_id":cid,
          "role":str(component.get("role") or ""),
          "kind":str(component.get("kind") or ""),
          "enforcement_point":str(component.get("enforcement_point") or ""),
          "hook_active":bool(active),
          "details":details
        })
    return {
      "schema":"chacha.dev/guardian-coverage-heartbeat/v1",
      "snapshot_id":"coverage-"+uuid.uuid4().hex,
      "observed_at":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),
      "platform_revision":(root/".revision").read_text(encoding="utf-8").strip() if (root/".revision").is_file() else None,
      "components":rows,
      "component_count":len(rows),
      "all_hooks_active":all(x["hook_active"] for x in rows),
      "automatic_external_spend_eur":0
    }

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--repo-root",type=Path,default=DEFAULT_ROOT)
    ap.add_argument("--manifest",type=Path,default=DEFAULT_MANIFEST)
    ap.add_argument("--policy",type=Path,default=DEFAULT_POLICY)
    ap.add_argument("--client",type=Path,default=DEFAULT_CLIENT)
    ap.add_argument("--output",type=Path,default=DEFAULT_OUT)
    a=ap.parse_args()
    snap=build(a.repo_root,a.manifest)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(snap,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    p=subprocess.run(
      ["/usr/bin/python3",str(a.client),"--policy",str(a.policy),"coverage","--snapshot",str(a.output)],
      stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=30
    )
    if p.stdout.strip(): print(p.stdout.strip())
    if p.returncode==0:
        print("CHACHA_DEV_GUARDIAN_COVERAGE_HEARTBEAT=PASS")
        print("ALL_HOOKS_ACTIVE="+("YES" if snap["all_hooks_active"] else "NO"))
        return 0
    print("CHACHA_DEV_GUARDIAN_COVERAGE_HEARTBEAT=BLOCKED")
    if p.stderr.strip():print(p.stderr.strip())
    return p.returncode

if __name__=="__main__":
    raise SystemExit(main())
