#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,os,shutil,time
from datetime import datetime,timezone
from pathlib import Path
from typing import Any

def load(p:Path)->dict[str,Any]:
    x=json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise ValueError("JSON_ROOT_NOT_OBJECT:"+str(p))
    return x
def save(p:Path,x:dict[str,Any])->None:
    p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
def now_iso()->str:return datetime.now(timezone.utc).isoformat().replace("+00:00","Z")
def file_digest(p:Path)->str:return "sha256:"+hashlib.sha256(p.read_bytes()).hexdigest()
def tree_size(p:Path)->int:
    if p.is_file():return p.stat().st_size
    return sum(x.stat().st_size for x in p.rglob("*") if x.is_file())
def tree_digest(root:Path)->str:
    h=hashlib.sha256()
    for p in sorted((x for x in root.rglob("*") if x.is_file()),key=lambda x:x.as_posix()):
        rel=p.relative_to(root).as_posix().encode();data=p.read_bytes()
        h.update(len(rel).to_bytes(8,"big"));h.update(rel);h.update(len(data).to_bytes(8,"big"));h.update(data)
    return "sha256:"+h.hexdigest()
def guardian_bound(event:dict[str,Any],result:dict[str,Any],action:str,digest_key:str,digest_value:str)->bool:
    evidence=event.get("evidence") or {}
    return (
      event.get("schema")=="chacha.dev/governance-action/v1" and
      event.get("phase")=="PRE_ACTION" and
      event.get("actor")=="platform-hygiene-executor" and
      event.get("subject_role")=="platform-hygiene-executor" and
      event.get("action")==action and event.get("permission")=="destructive-operation" and
      evidence.get("human_approval") is True and
      str(evidence.get(digest_key) or "")==digest_value and
      str(result.get("action_id") or "")==str(event.get("action_id") or "") and
      str(result.get("verdict") or "") in {"PASS","WARNING"}
    )
def open_under(target:Path)->bool:
    try:real=target.resolve()
    except Exception:return True
    proc=Path("/proc")
    if not proc.is_dir():return True
    for fdroot in proc.glob("[0-9]*/fd"):
        try:links=list(fdroot.iterdir())
        except Exception:continue
        for fd in links:
            try:
                raw=os.readlink(fd)
                link=Path(raw)
                if not link.is_absolute():continue
                resolved=link.resolve()
                if resolved==real or real in resolved.parents:return True
            except Exception:continue
    return False

def release_retirement(a)->dict[str,Any]:
    platform=a.platform_root.resolve();releases=(platform/"releases").resolve();active=(platform/"current").resolve()
    plan=load(a.plan.resolve());approval=load(a.approval.resolve());event=load(a.guardian_event.resolve());guardian=load(a.guardian_result.resolve())
    pd=file_digest(a.plan.resolve())
    if plan.get("schema")!="chacha.dev/platform-consolidation-plan/v1":raise SystemExit("PLAN_SCHEMA_INVALID")
    if approval.get("schema")!="chacha.dev/platform-consolidation-approval/v1":raise SystemExit("APPROVAL_SCHEMA_INVALID")
    if approval.get("destructive_apply_authorized") is not True:raise SystemExit("COUNCIL_APPROVAL_REQUIRED")
    if str(approval.get("plan_digest") or "")!=pd:raise SystemExit("COUNCIL_PLAN_DIGEST_MISMATCH")
    if not guardian_bound(event,guardian,"EXECUTE_PLATFORM_RETIREMENT","consolidation_plan_digest",pd):
        raise SystemExit("GUARDIAN_REALTIME_EXECUTION_GATE_FAILED")
    if str(plan.get("active_release") or "")!=str(active):raise SystemExit("ACTIVE_RELEASE_DRIFT")
    revision=(active/".revision").read_text(encoding="utf-8").strip()
    if str(plan.get("active_revision") or "")!=revision or str(approval.get("revision") or "")!=revision:
        raise SystemExit("ACTIVE_REVISION_DRIFT")
    if not str(plan.get("active_version") or "").strip():raise SystemExit("ACTIVE_VERSION_REQUIRED")
    if int(plan.get("missing_verified_rollback_count") or 0)>0:raise SystemExit("ROLLBACK_PROTECTION_INCOMPLETE")
    retiring=[]
    for row in plan.get("rows") or []:
        if row.get("action")!="RETIRE":continue
        if row.get("reason")!="SUPERSEDED_PHYSICAL_RELEASE":raise SystemExit("RETIRE_REASON_NOT_SAFE")
        p=Path(str(row.get("path") or "")).resolve()
        try:p.relative_to(releases)
        except ValueError:raise SystemExit("RETIRE_PATH_OUTSIDE_RELEASE_ROOT")
        if p==active:raise SystemExit("REFUSE_DELETE_ACTIVE_RELEASE")
        item=dict(row);item["tree_sha256"]=tree_digest(p) if p.is_dir() else "MISSING";retiring.append((item,p))
    archive={"schema":"chacha.dev/platform-retirement-archive/v3","generated_at":now_iso(),"revision":revision,
      "planner_owner":"intendant","executor_component":"platform-hygiene-executor","plan_digest":pd,
      "guardian_action_id":guardian.get("action_id"),"retiring":[x for x,_ in retiring],
      "git_history_preserved":True,"remote_branch_deletion":False,"source_code_deletion":False,
      "canonical_observation_bus_rewrite":False,"benchmark_evidence_mutation":False,"automatic_external_spend_eur":0}
    save(a.archive_manifest.resolve(),archive)
    deleted=0;freed=0
    for row,p in retiring:
        if not p.is_dir():continue
        freed+=int(row.get("size_bytes") or tree_size(p));shutil.rmtree(p);deleted+=1
    return {"schema":"chacha.dev/platform-hygiene-execution/v1","mode":"RELEASE_RETIREMENT","executed_at":now_iso(),
      "revision":revision,"planner_owner":"intendant","executor_component":"platform-hygiene-executor",
      "deleted_release_count":deleted,"freed_bytes":freed,
      "release_count_after":sum(1 for p in releases.iterdir() if p.is_dir()),
      "active_release_preserved":active.is_dir(),"guardian_action_id":guardian.get("action_id"),
      "git_history_preserved":True,"remote_branch_deletion":False,"source_code_deletion":False,
      "canonical_observation_bus_rewrite":False,"benchmark_evidence_mutation":False,
      "architecture_council_final_authority":True,"automatic_external_spend_eur":0}

def safe_temp_cleanup(a)->dict[str,Any]:
    manifest=load(a.manifest.resolve());config=load(a.hygiene_config.resolve());event=load(a.guardian_event.resolve());guardian=load(a.guardian_result.resolve())
    md=file_digest(a.manifest.resolve())
    if manifest.get("schema")!="chacha.dev/safe-temp-cleanup-plan/v1":raise SystemExit("TEMP_MANIFEST_SCHEMA_INVALID")
    if not guardian_bound(event,guardian,"EXECUTE_SAFE_TEMP_CLEANUP","safe_temp_manifest_digest",md):
        raise SystemExit("GUARDIAN_REALTIME_EXECUTION_GATE_FAILED")
    cfg=((config.get("cycles") or {}).get("LIGHT_DAILY") or {}).get("safe_temp_cleanup") or {}
    roots=[Path(str(x.get("path"))).resolve() for x in (cfg.get("roots") or []) if x.get("path")]
    min_age=float(cfg.get("minimum_age_hours") or 48)*3600;now=time.time()
    deleted=0;freed=0;skipped=[]
    for row in manifest.get("candidates") or []:
        p=Path(str(row.get("path") or ""))
        if p.is_symlink():skipped.append({"path":str(p),"reason":"SYMLINK"});continue
        try:rp=p.resolve()
        except Exception:skipped.append({"path":str(p),"reason":"UNRESOLVED"});continue
        if not any(rp!=root and root in rp.parents for root in roots):raise SystemExit("TEMP_PATH_OUTSIDE_WHITELIST:"+str(rp))
        if not rp.exists():continue
        if now-rp.stat().st_mtime<min_age:skipped.append({"path":str(rp),"reason":"TOO_NEW"});continue
        if open_under(rp):skipped.append({"path":str(rp),"reason":"OPEN_FD"});continue
        size=tree_size(rp)
        if rp.is_dir():shutil.rmtree(rp)
        else:rp.unlink()
        freed+=size;deleted+=1
    return {"schema":"chacha.dev/platform-hygiene-execution/v1","mode":"SAFE_TEMP_CLEANUP","executed_at":now_iso(),
      "planner_owner":"intendant","executor_component":"platform-hygiene-executor",
      "deleted_candidate_count":deleted,"freed_bytes":freed,"skipped":skipped,
      "guardian_action_id":guardian.get("action_id"),"git_history_preserved":True,
      "remote_branch_deletion":False,"source_code_deletion":False,
      "canonical_observation_bus_rewrite":False,"benchmark_evidence_mutation":False,
      "architecture_council_final_authority":True,"automatic_external_spend_eur":0}

def main()->int:
    ap=argparse.ArgumentParser();sub=ap.add_subparsers(dest="mode",required=True)
    r=sub.add_parser("release-retirement");r.add_argument("--platform-root",type=Path,default=Path("/opt/chacha-dev/platform"))
    r.add_argument("--plan",type=Path,required=True);r.add_argument("--approval",type=Path,required=True)
    r.add_argument("--guardian-event",type=Path,required=True);r.add_argument("--guardian-result",type=Path,required=True)
    r.add_argument("--archive-manifest",type=Path,required=True);r.add_argument("--output",type=Path,required=True)
    t=sub.add_parser("safe-temp-cleanup");t.add_argument("--manifest",type=Path,required=True);t.add_argument("--hygiene-config",type=Path,required=True)
    t.add_argument("--guardian-event",type=Path,required=True);t.add_argument("--guardian-result",type=Path,required=True);t.add_argument("--output",type=Path,required=True)
    a=ap.parse_args();out=release_retirement(a) if a.mode=="release-retirement" else safe_temp_cleanup(a);save(a.output.resolve(),out)
    print("CHACHA_DEV_V710_CENTRAL_PLATFORM_HYGIENE_EXECUTION=PASS");print("MODE="+out["mode"])
    print("EXECUTOR_COMPONENT=central-orchestrator");print("PLANNER_OWNER=intendant")
    print("FREED_MIB="+str(round(float(out.get("freed_bytes") or 0)/1024/1024,1)))
    return 0
if __name__=="__main__":raise SystemExit(main())
