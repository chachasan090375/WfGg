#!/usr/bin/env python3
"""ChaCha DEV V6.39 controlled production adapter.

The first V6.39 adapter is deliberately NON-PRODUCTION. It proves the
deployment contract, approval handoff, health proof and rollback semantics
inside a local filesystem sandbox. It must never perform network mutation or
advance a real project to OPERATE.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import time
from pathlib import Path
from typing import Any

PROFILE_SCHEMA="chacha.dev/controlled-production-adapter-profile/v1"
PLAN_SCHEMA="chacha.dev/controlled-production-plan/v1"
RECEIPT_SCHEMA="chacha.dev/controlled-production-adapter-receipt/v1"
APPROVAL_ID="production-deployment"
FORBIDDEN_ACTORS={
    "central-orchestrator","guardian","sentinel","curator",
    "bastion","intendant","logician","ergonomist"
}

def now()->str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())

def load(path:Path)->dict[str,Any]:
    x=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(x,dict):
        raise SystemExit("JSON_ROOT_NOT_OBJECT:"+str(path))
    return x

def save(path:Path,obj:dict[str,Any])->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")

def digest_bytes(data:bytes)->str:
    return "sha256:"+hashlib.sha256(data).hexdigest()

def digest_file(path:Path)->str:
    return digest_bytes(path.read_bytes())

def require_profile(path:Path)->dict[str,Any]:
    p=load(path)
    if p.get("schema")!=PROFILE_SCHEMA:
        raise SystemExit("V639_ADAPTER_PROFILE_SCHEMA_INVALID")
    if p.get("profile")!="dry-run-v1":
        raise SystemExit("V639_ADAPTER_PROFILE_NOT_DRY_RUN")
    if p.get("production_capable") is not False or p.get("real_production_target") is not False:
        raise SystemExit("V639_DRY_RUN_PROFILE_PRODUCTION_CAPABLE_FORBIDDEN")
    if p.get("filesystem_sandbox_only") is not True or p.get("network_mutation") is not False:
        raise SystemExit("V639_DRY_RUN_PROFILE_NOT_ISOLATED")
    if p.get("reversible") is not True:
        raise SystemExit("V639_DRY_RUN_PROFILE_NOT_REVERSIBLE")
    if float(p.get("external_spend_eur") or 0)!=0:
        raise SystemExit("V639_DRY_RUN_NONZERO_EXTERNAL_SPEND")
    return p

def require_revision(revision:str)->None:
    if re.fullmatch(r"[0-9a-f]{40}",revision) is None:
        raise SystemExit("V639_PINNED_REVISION_REQUIRED")

def require_target(target:str)->None:
    if not target.startswith("dry-run://"):
        raise SystemExit("V639_DRY_RUN_TARGET_SCHEME_REQUIRED")
    tail=target[len("dry-run://"):]
    if not tail or "/" in tail or ".." in tail:
        raise SystemExit("V639_DRY_RUN_TARGET_INVALID")

def receipt(project:str,revision:str,target:str,action:str,status:str,**extra:Any)->dict[str,Any]:
    base={
      "schema":RECEIPT_SCHEMA,
      "project_id":project,
      "revision":revision,
      "target":target,
      "action":action,
      "status":status,
      "production_mutation":False,
      "real_production_target":False,
      "external_spend_eur":0,
      "observed_at":now()
    }
    base.update(extra)
    return base

def action_plan(args:argparse.Namespace,profile:dict[str,Any])->int:
    require_revision(args.revision);require_target(args.target)
    plan={
      "schema":PLAN_SCHEMA,
      "profile":profile["profile"],
      "project_id":args.project,
      "revision":args.revision,
      "target":args.target,
      "approval_id":APPROVAL_ID,
      "requires_explicit_human_approval":True,
      "first_production_mutation_after_approval_only":True,
      "production_capable":False,
      "real_production_target":False,
      "production_mutation":False,
      "network_mutation":False,
      "reversible":True,
      "automatic_external_spend_eur":0,
      "planned_at":now()
    }
    save(args.output,plan)
    print("CHACHA_DEV_V639_ADAPTER_PLAN=PASS")
    print("PRODUCTION_MUTATION=NO")
    return 0

def require_approval(path:Path,project:str,revision:str)->dict[str,Any]:
    x=load(path)
    if x.get("approval_id")!=APPROVAL_ID or x.get("status")!="APPROVED":
        raise SystemExit("V639_DEPLOYMENT_APPROVAL_REQUIRED")
    actor=str(x.get("actor") or "").strip()
    if not actor or actor in FORBIDDEN_ACTORS:
        raise SystemExit("V639_REAL_HUMAN_APPROVAL_ACTOR_REQUIRED")
    if x.get("project_id")!=project or x.get("revision")!=revision:
        raise SystemExit("V639_APPROVAL_IDENTITY_MISMATCH")
    return x

def sandbox_marker(root:Path,project:str,target:str)->Path:
    token=target[len("dry-run://"):]
    return root/project/token/"deployed.json"

def action_deploy(args:argparse.Namespace,profile:dict[str,Any])->int:
    plan=load(args.plan)
    if plan.get("schema")!=PLAN_SCHEMA:
        raise SystemExit("V639_DEPLOY_PLAN_SCHEMA_INVALID")
    project=str(plan.get("project_id") or "")
    revision=str(plan.get("revision") or "")
    target=str(plan.get("target") or "")
    require_revision(revision);require_target(target)
    approval=require_approval(args.approval,project,revision)
    marker=sandbox_marker(args.sandbox_root,project,target)
    if marker.exists():
        raise SystemExit("V639_DRY_RUN_TARGET_ALREADY_DEPLOYED")
    marker.parent.mkdir(parents=True,exist_ok=True)
    payload={
      "project_id":project,"revision":revision,"target":target,
      "approval_actor":approval["actor"],"deployed_at":now(),
      "production_mutation":False,"real_production_target":False
    }
    save(marker,payload)
    out=receipt(project,revision,target,"deploy","PASS",
                approval_actor=approval["actor"],
                sandbox_marker=str(marker.resolve()),
                sandbox_marker_digest=digest_file(marker),
                rollback_available=True)
    save(args.output,out)
    print("CHACHA_DEV_V639_ADAPTER_DEPLOY_DRY_RUN=PASS")
    print("PRODUCTION_MUTATION=NO")
    return 0

def action_health(args:argparse.Namespace,profile:dict[str,Any])->int:
    dep=load(args.deployment)
    project=str(dep.get("project_id") or "")
    revision=str(dep.get("revision") or "")
    target=str(dep.get("target") or "")
    marker=Path(str(dep.get("sandbox_marker") or ""))
    require_revision(revision);require_target(target)
    if dep.get("status")!="PASS" or dep.get("production_mutation") is not False:
        raise SystemExit("V639_DRY_RUN_DEPLOYMENT_RECEIPT_INVALID")
    if not marker.is_file():
        raise SystemExit("V639_DRY_RUN_SANDBOX_MARKER_MISSING")
    marker_value=load(marker)
    if marker_value.get("revision")!=revision or marker_value.get("project_id")!=project:
        raise SystemExit("V639_DRY_RUN_SANDBOX_MARKER_IDENTITY_MISMATCH")
    out=receipt(project,revision,target,"health","PASS",
                sandbox_marker=str(marker.resolve()),
                sandbox_marker_digest=digest_file(marker),
                health="HEALTHY")
    save(args.output,out)
    print("CHACHA_DEV_V639_ADAPTER_HEALTH_DRY_RUN=PASS")
    return 0

def action_rollback(args:argparse.Namespace,profile:dict[str,Any])->int:
    dep=load(args.deployment)
    project=str(dep.get("project_id") or "")
    revision=str(dep.get("revision") or "")
    target=str(dep.get("target") or "")
    marker=Path(str(dep.get("sandbox_marker") or ""))
    require_revision(revision);require_target(target)
    existed=marker.is_file()
    if marker.exists():
        marker.unlink()
    parent=marker.parent
    while parent!=args.sandbox_root and parent.exists():
        try:
            parent.rmdir()
        except OSError:
            break
        parent=parent.parent
    out=receipt(project,revision,target,"rollback","PASS",
                sandbox_marker=str(marker),
                marker_existed_before_rollback=existed,
                marker_present_after_rollback=marker.exists(),
                rollback_proven=not marker.exists())
    save(args.output,out)
    if marker.exists():
        raise SystemExit("V639_DRY_RUN_ROLLBACK_FAILED")
    print("CHACHA_DEV_V639_ADAPTER_ROLLBACK_DRY_RUN=PASS")
    print("PRODUCTION_MUTATION=NO")
    return 0

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--profile",type=Path,required=True)
    sub=ap.add_subparsers(dest="action",required=True)

    p=sub.add_parser("plan")
    p.add_argument("--project",required=True)
    p.add_argument("--revision",required=True)
    p.add_argument("--target",required=True)
    p.add_argument("--output",type=Path,required=True)

    d=sub.add_parser("deploy")
    d.add_argument("--plan",type=Path,required=True)
    d.add_argument("--approval",type=Path,required=True)
    d.add_argument("--sandbox-root",type=Path,required=True)
    d.add_argument("--output",type=Path,required=True)

    h=sub.add_parser("health")
    h.add_argument("--deployment",type=Path,required=True)
    h.add_argument("--output",type=Path,required=True)

    r=sub.add_parser("rollback")
    r.add_argument("--deployment",type=Path,required=True)
    r.add_argument("--sandbox-root",type=Path,required=True)
    r.add_argument("--output",type=Path,required=True)

    a=ap.parse_args()
    profile=require_profile(a.profile)
    if a.action=="plan":return action_plan(a,profile)
    if a.action=="deploy":return action_deploy(a,profile)
    if a.action=="health":return action_health(a,profile)
    if a.action=="rollback":return action_rollback(a,profile)
    raise SystemExit("V639_ADAPTER_ACTION_UNKNOWN")

if __name__=="__main__":
    raise SystemExit(main())
