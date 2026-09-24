#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,shutil
from datetime import datetime,timezone
from pathlib import Path
from typing import Any

PLAN_SCHEMA="chacha.dev/platform-consolidation-plan/v1"
APPROVAL_SCHEMA="chacha.dev/platform-consolidation-approval/v1"

def load(p:Path)->dict[str,Any]:
    x=json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise ValueError("JSON_ROOT_NOT_OBJECT:"+str(p))
    return x
def save(p:Path,x:dict[str,Any])->None:
    p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
def now_iso()->str:return datetime.now(timezone.utc).isoformat().replace("+00:00","Z")
def sha256_file(p:Path)->str:return "sha256:"+hashlib.sha256(p.read_bytes()).hexdigest()
def tree_digest(root:Path)->str:
    h=hashlib.sha256()
    for p in sorted((x for x in root.rglob("*") if x.is_file()),key=lambda x:x.as_posix()):
        rel=p.relative_to(root).as_posix().encode();data=p.read_bytes()
        h.update(len(rel).to_bytes(8,"big"));h.update(rel);h.update(len(data).to_bytes(8,"big"));h.update(data)
    return "sha256:"+h.hexdigest()

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--platform-root",type=Path,required=True)
    ap.add_argument("--plan",type=Path,required=True)
    ap.add_argument("--approval",type=Path,required=True)
    ap.add_argument("--guardian-receipt",type=Path,required=True)
    ap.add_argument("--archive-manifest",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    ap.add_argument("--explicit-destructive-apply",action="store_true")
    a=ap.parse_args()
    if not a.explicit_destructive_apply:raise SystemExit("EXPLICIT_DESTRUCTIVE_APPLY_REQUIRED")
    platform=a.platform_root.resolve();releases=(platform/"releases").resolve();current=(platform/"current").resolve()
    plan=load(a.plan);approval=load(a.approval);guardian=load(a.guardian_receipt)
    if plan.get("schema")!=PLAN_SCHEMA:raise SystemExit("PLAN_SCHEMA_INVALID")
    if approval.get("schema")!=APPROVAL_SCHEMA:raise SystemExit("APPROVAL_SCHEMA_INVALID")
    if approval.get("destructive_apply_authorized") is not True:raise SystemExit("COUNCIL_APPROVAL_REQUIRED")
    if str(guardian.get("verdict") or "") not in {"PASS","WARNING"}:raise SystemExit("GUARDIAN_REALTIME_VERDICT_REQUIRED")
    if str(approval.get("plan_digest") or "")!=sha256_file(a.plan):raise SystemExit("PLAN_DIGEST_MISMATCH")
    if str(approval.get("revision") or "")!=str(plan.get("active_revision") or ""):raise SystemExit("REVISION_MISMATCH")
    if int(plan.get("missing_verified_rollback_count") or 0)>0:raise SystemExit("ROLLBACK_PROTECTION_INCOMPLETE")
    if not str(plan.get("active_version") or "").startswith("7."):raise SystemExit("V7_RUNTIME_REQUIRED")
    retiring=[]
    for row in plan.get("rows") or []:
        if row.get("action")!="RETIRE":continue
        if row.get("reason")!="SUPERSEDED_PHYSICAL_RELEASE":raise SystemExit("RETIRE_REASON_NOT_SAFE")
        p=Path(str(row.get("path") or "")).resolve()
        try:p.relative_to(releases)
        except ValueError:raise SystemExit("RETIRE_PATH_OUTSIDE_RELEASE_ROOT")
        if p==current:raise SystemExit("REFUSE_DELETE_ACTIVE_RELEASE")
        retiring.append((row,p))
    archive={"schema":"chacha.dev/platform-retirement-archive/v2","generated_at":now_iso(),
      "executor":"central-orchestrator","owner_agent":"intendant","revision":plan.get("active_revision"),
      "plan_digest":sha256_file(a.plan),"guardian_verdict":guardian.get("verdict"),"retiring":[],"git_history_preserved":True,
      "remote_branch_deletion":False,"source_code_deletion":False,"automatic_external_spend_eur":0}
    for row,p in retiring:
        item=dict(row);item["tree_sha256"]=tree_digest(p) if p.is_dir() else "MISSING"
        archive["retiring"].append(item)
    save(a.archive_manifest,archive)
    deleted=0;freed=0
    for row,p in retiring:
        if not p.is_dir():continue
        freed+=int(row.get("size_bytes") or 0);shutil.rmtree(p);deleted+=1
    result={"schema":"chacha.dev/central-retirement-execution/v1","executed_at":now_iso(),
      "executor":"central-orchestrator","owner_agent":"intendant","revision":plan.get("active_revision"),
      "plan_digest":sha256_file(a.plan),"deleted_release_count":deleted,"freed_bytes":freed,
      "release_count_after":sum(1 for p in releases.iterdir() if p.is_dir()),
      "active_release_preserved":current.is_dir(),"git_history_preserved":True,
      "remote_branch_deletion":False,"source_code_deletion":False,
      "canonical_observation_bus_rewrite":False,"benchmark_evidence_mutation":False,
      "automatic_external_spend_eur":0}
    save(a.output,result)
    print("CHACHA_DEV_V710_CENTRAL_RETIREMENT_EXECUTION=PASS")
    print("DELETED_RELEASES="+str(deleted))
    print("FREED_MIB="+str(round(freed/1024/1024,1)))
    print("EXECUTOR=central-orchestrator")
    print("OWNER_AGENT=intendant")
    return 0

if __name__=="__main__":raise SystemExit(main())
