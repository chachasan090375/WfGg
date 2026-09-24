#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,shutil
from datetime import datetime,timezone
from pathlib import Path
from typing import Any

APPROVAL_SCHEMA="chacha.dev/platform-consolidation-approval/v1"
PLAN_SCHEMA="chacha.dev/platform-consolidation-plan/v1"

def load(p:Path)->dict[str,Any]:
    x=json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise ValueError("JSON_ROOT_NOT_OBJECT:"+str(p))
    return x
def save(p:Path,x:dict[str,Any])->None:
    p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
def now_iso()->str:return datetime.now(timezone.utc).isoformat().replace("+00:00","Z")
def file_digest(p:Path)->str:return "sha256:"+hashlib.sha256(p.read_bytes()).hexdigest()
def tree_digest(root:Path)->str:
    h=hashlib.sha256()
    for p in sorted((x for x in root.rglob("*") if x.is_file()),key=lambda x:x.as_posix()):
        rel=p.relative_to(root).as_posix().encode();data=p.read_bytes()
        h.update(len(rel).to_bytes(8,"big"));h.update(rel);h.update(len(data).to_bytes(8,"big"));h.update(data)
    return "sha256:"+h.hexdigest()

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--platform-root",type=Path,default=Path("/opt/chacha-dev/platform"))
    ap.add_argument("--plan",type=Path,required=True)
    ap.add_argument("--approval",type=Path,required=True)
    ap.add_argument("--archive-manifest",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    ap.add_argument("--explicit-destructive-apply",action="store_true")
    a=ap.parse_args()
    if not a.explicit_destructive_apply:raise SystemExit("EXPLICIT_DESTRUCTIVE_APPLY_REQUIRED")
    platform=a.platform_root.resolve();plan=load(a.plan.resolve());approval=load(a.approval.resolve())
    if plan.get("schema")!=PLAN_SCHEMA:raise SystemExit("PLAN_SCHEMA_INVALID")
    if approval.get("schema")!=APPROVAL_SCHEMA:raise SystemExit("APPROVAL_SCHEMA_INVALID")
    if approval.get("destructive_apply_authorized") is not True:raise SystemExit("COUNCIL_DESTRUCTIVE_APPLY_NOT_AUTHORIZED")
    if str(approval.get("plan_digest") or "")!=file_digest(a.plan.resolve()):raise SystemExit("COUNCIL_PLAN_DIGEST_MISMATCH")
    active=(platform/"current").resolve()
    if str(plan.get("active_release") or "")!=str(active):raise SystemExit("ACTIVE_RELEASE_DRIFT")
    active_rev=(active/".revision").read_text(encoding="utf-8").strip()
    if str(plan.get("active_revision") or "")!=active_rev or str(approval.get("revision") or "")!=active_rev:
        raise SystemExit("ACTIVE_REVISION_DRIFT")
    version=str(plan.get("active_version") or "")
    if not version.startswith("7."):raise SystemExit("V7_ACTIVE_RUNTIME_REQUIRED")
    if int(plan.get("missing_verified_rollback_count") or 0)>0:raise SystemExit("VERIFIED_ROLLBACK_RELEASE_MISSING")
    rows=plan.get("rows") or []
    retiring=[]
    for row in rows:
        if row.get("action")!="RETIRE":continue
        p=Path(str(row.get("path") or "")).resolve()
        if p==active:raise SystemExit("REFUSE_DELETE_ACTIVE_RELEASE")
        releases=(platform/"releases").resolve()
        if releases not in p.parents:raise SystemExit("RETIRE_PATH_OUTSIDE_RELEASES")
        if p.is_dir():
            retiring.append({**row,"tree_sha256":tree_digest(p)})
    archive={
      "schema":"chacha.dev/platform-retirement-archive/v2","generated_at":now_iso(),
      "revision":active_rev,"plan_digest":file_digest(a.plan.resolve()),
      "planner_owner":"intendant","executor_component":"central-orchestrator",
      "retiring":retiring,"git_history_preserved":True,"remote_branch_deletion":False,
      "canonical_observation_bus_rewrite":False,"benchmark_evidence_mutation":False,
      "automatic_external_spend_eur":0
    }
    save(a.archive_manifest.resolve(),archive)
    deleted=0;freed=0
    for row in retiring:
        p=Path(row["path"])
        if not p.is_dir():continue
        freed+=int(row.get("size_bytes") or 0)
        shutil.rmtree(p);deleted+=1
    after=sum(1 for p in (platform/"releases").iterdir() if p.is_dir())
    result={
      "schema":"chacha.dev/platform-retirement-execution/v1","executed_at":now_iso(),
      "revision":active_rev,"planner_owner":"intendant","executor_component":"central-orchestrator",
      "plan_digest":file_digest(a.plan.resolve()),"approval_digest":file_digest(a.approval.resolve()),
      "deleted_release_count":deleted,"freed_bytes":freed,"release_count_after":after,
      "active_release":str(active),"active_release_preserved":active.is_dir(),
      "git_history_preserved":True,"remote_branch_deletion":False,
      "canonical_observation_bus_rewrite":False,"benchmark_evidence_mutation":False,
      "architecture_council_final_authority":True,"automatic_external_spend_eur":0
    }
    save(a.output.resolve(),result)
    print("CHACHA_DEV_V71_PLATFORM_RETIREMENT_EXECUTION=PASS")
    print("EXECUTOR_COMPONENT=central-orchestrator")
    print("PLANNER_OWNER=intendant")
    print("DELETED_RELEASES="+str(deleted))
    print("FREED_MIB="+str(round(freed/1024/1024,1)))
    print("ACTIVE_RELEASE_PRESERVED=YES")
    print("GIT_HISTORY_PRESERVED=YES")
    print("REMOTE_BRANCH_DELETION=NO")
    print("CANONICAL_OBSERVATION_BUS_REWRITE=NO")
    print("BENCHMARK_EVIDENCE_MUTATION=NO")
    return 0
if __name__=="__main__":raise SystemExit(main())
