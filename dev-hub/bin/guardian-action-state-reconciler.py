#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,subprocess
from pathlib import Path
from typing import Any

DEFAULT_CLIENT=Path("/opt/chacha-dev/platform/current/dev-hub/bin/guardian-client.py")
DEFAULT_POLICY=Path("/opt/chacha-dev/platform/current/dev-hub/config/guardian-runtime-policy.v1.json")

def load(path:Path)->dict[str,Any]:
    x=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(x,dict): raise RuntimeError("JSON_ROOT_NOT_OBJECT")
    return x

def stable(v:Any)->str:
    return json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(",",":"))

def build(spec:dict[str,Any])->dict[str,Any]:
    if spec.get("schema")!="chacha.dev/action-lease-reconciliation-spec/v1":
        raise RuntimeError("SPEC_SCHEMA_INVALID")
    evidence=spec.get("evidence") if isinstance(spec.get("evidence"),dict) else {}
    if evidence.get("final_state_verified") is not True: raise RuntimeError("FINAL_STATE_NOT_VERIFIED")
    if evidence.get("original_action_outcome") not in {"COMPLETED","NOOP","ROLLED_BACK"}:
        raise RuntimeError("ORIGINAL_ACTION_OUTCOME_INVALID")
    if evidence.get("action_reexecuted") is not False: raise RuntimeError("ACTION_REPLAY_FORBIDDEN")
    identity=spec.get("original_identity") if isinstance(spec.get("original_identity"),dict) else {}
    for key in ("actor","subject_role","action","permission"):
        if not str(identity.get(key) or ""): raise RuntimeError("ORIGINAL_IDENTITY_MISSING:"+key)
    if identity.get("permission")=="destructive-operation" and evidence.get("human_approval_verified") is not True:
        raise RuntimeError("DESTRUCTIVE_HUMAN_APPROVAL_EVIDENCE_MISSING")
    sources=evidence.get("sources") if isinstance(evidence.get("sources"),list) else []
    if not sources: raise RuntimeError("EVIDENCE_SOURCES_MISSING")
    for source in sources:
        digest=str((source or {}).get("digest") or "")
        if not digest.startswith("sha256:") or len(digest)!=71: raise RuntimeError("EVIDENCE_SOURCE_DIGEST_INVALID")
    action_id=str(spec.get("action_id") or "")
    if not action_id: raise RuntimeError("ACTION_ID_MISSING")
    expected_alert="lease-expired-"+action_id
    expected_directive="remed-"+expected_alert
    if str(spec.get("source_alert_id") or "")!=expected_alert: raise RuntimeError("SOURCE_ALERT_ID_MISMATCH")
    if str(spec.get("remediation_directive_id") or "")!=expected_directive: raise RuntimeError("REMEDIATION_DIRECTIVE_ID_MISMATCH")
    return {
      "schema":"chacha.dev/action-lease-reconciliation-request/v1",
      "reconciler_actor":"guardian-action-state-reconciler",
      "action_id":action_id,"source_alert_id":expected_alert,
      "remediation_directive_id":expected_directive,
      "original_identity":identity,"evidence":evidence,
      "evidence_digest":"sha256:"+hashlib.sha256(stable(evidence).encode()).hexdigest()
    }

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--spec",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    ap.add_argument("--apply",action="store_true")
    ap.add_argument("--client",type=Path,default=DEFAULT_CLIENT)
    ap.add_argument("--policy",type=Path,default=DEFAULT_POLICY)
    a=ap.parse_args()
    request=build(load(a.spec))
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(request,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print("CHACHA_DEV_GUARDIAN_ACTION_STATE_RECONCILER=PASS")
    print("ACTION_REPLAY=FORBIDDEN")
    print("AUTOMATIC_EXTERNAL_SPEND_EUR=0")
    if not a.apply:return 0
    p=subprocess.run(["/usr/bin/python3",str(a.client),"--policy",str(a.policy),
                      "reconcile-action-state","--request",str(a.output)],check=False)
    return p.returncode

if __name__=="__main__":
    raise SystemExit(main())
