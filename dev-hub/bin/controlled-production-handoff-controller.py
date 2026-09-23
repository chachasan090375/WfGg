#!/usr/bin/env python3
"""ChaCha DEV V6.39 controlled RELEASE -> OPERATE handoff controller.

The V6.39 qualification profile is intentionally dry-run only. The controller
proves the two-phase human boundary and the controlled adapter contract without
touching a real production target or advancing the lifecycle to OPERATE.

A future real-production profile may reuse this control structure only after
separate qualification and an explicit real deployment pilot.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

RESULT_SCHEMA="chacha.dev/v639-controlled-production-handoff-result/v1"
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

def digest_file(path:Path)->str:
    return "sha256:"+hashlib.sha256(path.read_bytes()).hexdigest()

def run(argv:list[str],cwd:Path|None=None,timeout:int=300)->subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,cwd=str(cwd) if cwd else None,
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,
        check=False,shell=False,timeout=timeout
    )

def require_ok(p:subprocess.CompletedProcess[str],label:str)->None:
    if p.returncode!=0:
        raise SystemExit(label+"_FAILED\nSTDOUT="+p.stdout[-5000:]+"\nSTDERR="+p.stderr[-3000:])

def require_revision(revision:str)->None:
    if re.fullmatch(r"[0-9a-f]{40}",revision) is None:
        raise SystemExit("V639_PINNED_RELEASE_REVISION_REQUIRED")

def pc(repo:Path,policy:Path,args:list[str])->dict[str,Any]:
    p=run([sys.executable,str(repo/"dev-hub/bin/project-control.py"),
           "--policy",str(policy),"--repo-root",str(repo),"--json",*args],cwd=repo,timeout=300)
    try:
        x=json.loads(p.stdout)
    except Exception as exc:
        raise SystemExit("V639_PROJECT_CONTROL_JSON_INVALID:"+p.stdout[-3000:]+p.stderr[-2000:]) from exc
    if not isinstance(x,dict):
        raise SystemExit("V639_PROJECT_CONTROL_RESPONSE_NOT_OBJECT")
    return x

def runtime_paths(policy:dict[str,Any],project:str)->dict[str,Path]:
    r=policy.get("runtime") or {}
    return {
      "state":Path(str(r["state_root"]))/project/"state.json",
      "ledger":Path(str(r["evidence_root"]))/project/"ledger.json"
    }

def require_release_state(repo:Path,pc_policy_path:Path,pc_policy:dict[str,Any],
                          project:str,revision:str,release_proof:Path)->dict[str,Path]:
    integrity=pc(repo,pc_policy_path,["verify-state","--project",project])
    if integrity.get("status")!="OK":
        raise SystemExit("V639_CONTROL_PLANE_INTEGRITY_FAILED:"+json.dumps(integrity))
    paths=runtime_paths(pc_policy,project)
    if not paths["state"].is_file() or not paths["ledger"].is_file():
        raise SystemExit("V639_PROJECT_RUNTIME_STATE_MISSING")
    state=load(paths["state"])
    stage=str((((state.get("state") or {}).get("lifecycle") or {}).get("stage") or ""))
    if stage!="RELEASE":
        raise SystemExit("V639_SOURCE_STAGE_NOT_RELEASE:"+stage)
    if not release_proof.is_file():
        raise SystemExit("V639_RELEASE_PROOF_MISSING")
    proof=load(release_proof)
    if str(proof.get("project_id") or "")!=project:
        raise SystemExit("V639_RELEASE_PROOF_PROJECT_MISMATCH")
    if str(proof.get("revision") or "")!=revision:
        raise SystemExit("V639_RELEASE_PROOF_REVISION_MISMATCH")
    proof_stage=str(proof.get("lifecycle_stage") or proof.get("stage") or "")
    if proof_stage!="RELEASE":
        raise SystemExit("V639_RELEASE_PROOF_STAGE_NOT_RELEASE:"+proof_stage)
    return paths

def adapter(repo:Path,profile:Path,args:list[str])->subprocess.CompletedProcess[str]:
    return run([sys.executable,str(repo/"dev-hub/bin/controlled-production-adapter.py"),
                "--profile",str(profile),*args],cwd=repo,timeout=180)

def approval_from_ledger(ledger_path:Path,project:str,revision:str,actor:str,
                         evidence_id:str,out:Path)->Path:
    ledger=load(ledger_path)
    item=((ledger.get("approvals") or {}).get(APPROVAL_ID) or {})
    if item.get("status")!="APPROVED":
        raise SystemExit("V639_PROTECTED_DEPLOYMENT_APPROVAL_NOT_RECORDED")
    if item.get("actor")!=actor:
        raise SystemExit("V639_DEPLOYMENT_APPROVAL_ACTOR_MISMATCH")
    if str(item.get("evidence") or "")!=evidence_id:
        raise SystemExit("V639_DEPLOYMENT_APPROVAL_EVIDENCE_MISMATCH")
    value={
      "approval_id":APPROVAL_ID,
      "status":"APPROVED",
      "actor":actor,
      "evidence":evidence_id,
      "observed_at":item.get("observed_at"),
      "project_id":project,
      "revision":revision,
      "source":"PROJECT_CONTROL_EVIDENCE_LEDGER"
    }
    save(out,value)
    return out

def initial(a:argparse.Namespace,repo:Path,pc_policy_path:Path,pc_policy:dict[str,Any],
            profile:Path,result_path:Path)->int:
    if a.human_approval_id or a.human_actor:
        raise SystemExit("V639_INITIAL_RUN_MUST_NOT_PRELOAD_APPROVAL")
    if a.resume_from_awaiting_deployment_approval:
        raise SystemExit("V639_INITIAL_RUN_RESUME_FLAG_FORBIDDEN")
    if result_path.exists():
        raise SystemExit("V639_HANDOFF_RESULT_ALREADY_EXISTS")
    paths=require_release_state(repo,pc_policy_path,pc_policy,a.project,a.revision,a.release_proof)

    out=a.output_dir.resolve();out.mkdir(parents=True,exist_ok=True)
    plan=out/"deployment-plan.json"
    p=adapter(repo,profile,[
      "plan","--project",a.project,"--revision",a.revision,
      "--target",a.target,"--output",str(plan)
    ])
    require_ok(p,"V639_ADAPTER_PLAN")
    pv=load(plan)
    if pv.get("production_mutation") is not False or pv.get("real_production_target") is not False:
        raise SystemExit("V639_PREAPPROVAL_PLAN_NOT_DRY_RUN")

    value={
      "schema":RESULT_SCHEMA,
      "version":"1.0.0",
      "status":"AWAITING_DEPLOYMENT_APPROVAL",
      "project_id":a.project,
      "revision":a.revision,
      "source_stage":"RELEASE",
      "target_stage":"OPERATE",
      "target":a.target,
      "adapter_profile":"dry-run-v1",
      "deployment_plan":str(plan.resolve()),
      "release_proof":str(a.release_proof.resolve()),
      "release_proof_digest":digest_file(a.release_proof),
      "approval_id":APPROVAL_ID,
      "human_boundary_proven":True,
      "production_mutation_before_approval":False,
      "real_production_target":False,
      "operate_advanced":False,
      "automatic_external_spend_eur":0,
      "created_at":now()
    }
    save(result_path,value)

    print("CHACHA_DEV_V639_RELEASE_SOURCE_VERIFIED=PASS")
    print("CHACHA_DEV_V639_CONTROL_PLANE_INTEGRITY=PASS")
    print("CHACHA_DEV_V639_DRY_RUN_PLAN=PASS")
    print("CHACHA_DEV_V639_PREAPPROVAL_PRODUCTION_MUTATION=NO")
    print("CHACHA_DEV_V639_REAL_PRODUCTION_TARGET=NO")
    print("CHACHA_DEV_V639_HANDOFF=AWAITING_DEPLOYMENT_APPROVAL")
    print("CHACHA_DEV_V639_PROJECT_ID="+a.project)
    return 4

def resume(a:argparse.Namespace,repo:Path,pc_policy_path:Path,pc_policy:dict[str,Any],
           profile:Path,result_path:Path)->int:
    if not a.human_approval_id or not a.human_actor:
        raise SystemExit("V639_EXPLICIT_HUMAN_DEPLOYMENT_APPROVAL_REQUIRED")
    if a.human_actor in FORBIDDEN_ACTORS:
        raise SystemExit("V639_HUMAN_ACTOR_CANNOT_BE_AGENT")
    if not result_path.is_file():
        raise SystemExit("V639_AWAITING_DEPLOYMENT_APPROVAL_CHECKPOINT_MISSING")
    r=load(result_path)
    if r.get("schema")!=RESULT_SCHEMA or r.get("status")!="AWAITING_DEPLOYMENT_APPROVAL":
        raise SystemExit("V639_RESUME_CHECKPOINT_INVALID")
    for key,expected in (
        ("project_id",a.project),("revision",a.revision),("target",a.target),
        ("adapter_profile","dry-run-v1")
    ):
        if r.get(key)!=expected:
            raise SystemExit("V639_RESUME_IDENTITY_MISMATCH:"+key)

    paths=require_release_state(repo,pc_policy_path,pc_policy,a.project,a.revision,a.release_proof)
    approval=pc(repo,pc_policy_path,[
      "record-approval","--project",a.project,
      "--approval-id",APPROVAL_ID,
      "--actor",a.human_actor,
      "--evidence",a.human_approval_id
    ])
    if approval.get("status")!="OK":
        raise SystemExit("V639_PROTECTED_DEPLOYMENT_APPROVAL_FAILED:"+json.dumps(approval))

    actual_approval=approval_from_ledger(
        paths["ledger"],a.project,a.revision,a.human_actor,a.human_approval_id,
        a.output_dir/"production-deployment-approval.json"
    )

    deployment=a.output_dir/"dry-run-deployment-receipt.json"
    sandbox=a.output_dir/"adapter-sandbox"
    p=adapter(repo,profile,[
      "deploy","--plan",str(Path(str(r["deployment_plan"]))),
      "--approval",str(actual_approval),
      "--sandbox-root",str(sandbox),
      "--output",str(deployment)
    ])
    require_ok(p,"V639_ADAPTER_DEPLOY")
    dv=load(deployment)
    if dv.get("production_mutation") is not False or dv.get("real_production_target") is not False:
        raise SystemExit("V639_DRY_RUN_DEPLOYMENT_MUTATED_PRODUCTION")

    health=a.output_dir/"dry-run-health.json"
    p=adapter(repo,profile,["health","--deployment",str(deployment),"--output",str(health)])
    require_ok(p,"V639_ADAPTER_HEALTH")

    rollback=a.output_dir/"dry-run-rollback.json"
    p=adapter(repo,profile,[
      "rollback","--deployment",str(deployment),
      "--sandbox-root",str(sandbox),"--output",str(rollback)
    ])
    require_ok(p,"V639_ADAPTER_ROLLBACK")
    rv=load(rollback)
    if rv.get("rollback_proven") is not True or rv.get("production_mutation") is not False:
        raise SystemExit("V639_DRY_RUN_ROLLBACK_NOT_PROVEN")

    integrity=pc(repo,pc_policy_path,["verify-state","--project",a.project])
    if integrity.get("status")!="OK":
        raise SystemExit("V639_POST_DRY_RUN_CONTROL_PLANE_INTEGRITY_FAILED")
    state=load(paths["state"])
    stage=str((((state.get("state") or {}).get("lifecycle") or {}).get("stage") or ""))
    if stage!="RELEASE":
        raise SystemExit("V639_DRY_RUN_MUST_NOT_ADVANCE_OPERATE:"+stage)

    r.update({
      "status":"DRY_RUN_COMPLETE",
      "human_approval_actor":a.human_actor,
      "human_approval_evidence":a.human_approval_id,
      "protected_approval_transaction":"PASS",
      "deployment_receipt":str(deployment.resolve()),
      "health_receipt":str(health.resolve()),
      "rollback_receipt":str(rollback.resolve()),
      "rollback_proven":True,
      "production_mutation":False,
      "real_production_target":False,
      "operate_advanced":False,
      "completed_at":now()
    })
    save(result_path,r)

    print("CHACHA_DEV_V639_RESUME_CHECKPOINT=PASS")
    print("CHACHA_DEV_V639_PROTECTED_DEPLOYMENT_APPROVAL=PASS")
    print("CHACHA_DEV_V639_ADAPTER_DEPLOY_DRY_RUN=PASS")
    print("CHACHA_DEV_V639_ADAPTER_HEALTH_DRY_RUN=PASS")
    print("CHACHA_DEV_V639_ADAPTER_ROLLBACK_DRY_RUN=PASS")
    print("CHACHA_DEV_V639_ROLLBACK_PROVEN=PASS")
    print("CHACHA_DEV_V639_PRODUCTION_MUTATION=NO")
    print("CHACHA_DEV_V639_OPERATE_ADVANCED=NO")
    print("CHACHA_DEV_V639_DRY_RUN=PASS")
    return 0

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--repo-root",type=Path,default=Path.cwd())
    ap.add_argument("--project-control-policy",type=Path,default=Path("dev-hub/config/project-control.v1.json"))
    ap.add_argument("--adapter-profile",type=Path,default=Path("dev-hub/config/controlled-production-adapter-dry-run.v1.json"))
    ap.add_argument("--project",required=True)
    ap.add_argument("--revision",required=True)
    ap.add_argument("--target",required=True)
    ap.add_argument("--release-proof",type=Path,required=True)
    ap.add_argument("--output-dir",type=Path,required=True)
    ap.add_argument("--resume-from-awaiting-deployment-approval",action="store_true")
    ap.add_argument("--human-approval-id")
    ap.add_argument("--human-actor")
    a=ap.parse_args()

    require_revision(a.revision)
    repo=a.repo_root.resolve()
    pc_policy_path=a.project_control_policy if a.project_control_policy.is_absolute() else repo/a.project_control_policy
    profile=a.adapter_profile if a.adapter_profile.is_absolute() else repo/a.adapter_profile
    pc_policy=load(pc_policy_path)
    result_path=a.output_dir.resolve()/"handoff-result.json"

    if a.resume_from_awaiting_deployment_approval:
        return resume(a,repo,pc_policy_path,pc_policy,profile,result_path)
    return initial(a,repo,pc_policy_path,pc_policy,profile,result_path)

if __name__=="__main__":
    raise SystemExit(main())
