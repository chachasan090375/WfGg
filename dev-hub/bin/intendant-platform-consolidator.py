#!/usr/bin/env python3
from __future__ import annotations

import argparse, hashlib, json, os, shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA="chacha.dev/platform-consolidation-plan/v1"
APPROVAL_SCHEMA="chacha.dev/platform-consolidation-approval/v1"

def load(path:Path)->dict[str,Any]:
    x=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(x,dict): raise ValueError("JSON_ROOT_NOT_OBJECT:"+str(path))
    return x

def save(path:Path,x:dict[str,Any])->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")

def now_iso()->str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00","Z")

def tree_size(root:Path)->int:
    total=0
    for p in root.rglob("*"):
        try:
            if p.is_file(): total+=p.stat().st_size
        except FileNotFoundError: pass
    return total

def tree_digest(root:Path)->str:
    h=hashlib.sha256()
    for p in sorted((x for x in root.rglob("*") if x.is_file()),key=lambda x:x.as_posix()):
        rel=p.relative_to(root).as_posix().encode("utf-8")
        h.update(len(rel).to_bytes(8,"big"));h.update(rel)
        data=p.read_bytes()
        h.update(len(data).to_bytes(8,"big"));h.update(data)
    return "sha256:"+h.hexdigest()

def revision_of(release:Path)->str:
    p=release/".revision"
    if p.is_file():
        try:return p.read_text(encoding="utf-8").strip()
        except Exception:return ""
    name=release.name
    parts=name.rsplit("-",1)
    return parts[-1] if len(parts)==2 and len(parts[-1])==40 else ""

def version_of(release:Path)->str:
    p=release/"dev-hub/bin/autonomous-project-orchestrator.py"
    if not p.is_file():return ""
    txt=p.read_text(encoding="utf-8",errors="ignore")
    import re
    m=re.search(r'"version"\s*:\s*"([^"]+)"',txt)
    return m.group(1) if m else ""

def latest_for_revision(rows:list[dict[str,Any]],revision:str)->dict[str,Any]|None:
    hits=[x for x in rows if x["revision"]==revision]
    return sorted(hits,key=lambda x:x["name"])[-1] if hits else None

def version_rank(version:str)->tuple[int,int,int,int]:
    import re
    nums=[int(x) for x in re.findall(r"\d+",str(version or ""))[:4]]
    return tuple((nums+[0,0,0,0])[:4])

def _evidence_epoch(x:dict[str,Any],path:Path)->float:
    for key in ("observed_at","generated_at","applied_at","executed_at"):
        raw=str(x.get(key) or "").strip()
        if not raw:continue
        try:
            if len(raw)==16 and raw.endswith("Z") and "T" in raw and "-" not in raw:
                return datetime.strptime(raw,"%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc).timestamp()
            return datetime.fromisoformat(raw.replace("Z","+00:00")).timestamp()
        except Exception:
            continue
    try:return path.stat().st_mtime
    except Exception:return 0.0

def verified_revision_ranks(evidence_root:Path)->dict[str,float]:
    out={}
    if not evidence_root.is_dir():return out
    for p in evidence_root.rglob("*.json"):
        try:
            x=load(p)
        except Exception:
            continue
        rev=str(x.get("revision") or "").lower()
        if len(rev)!=40 or not all(ch in "0123456789abcdef" for ch in rev):continue
        rank=_evidence_epoch(x,p)
        if rank>out.get(rev,0.0):out[rev]=rank
    return out

def approval_ok(path:Path|None,active_revision:str)->tuple[bool,list[str]]:
    if path is None or not path.is_file():return False,["APPROVAL_RECEIPT_MISSING"]
    x=load(path);errors=[]
    if x.get("schema")!=APPROVAL_SCHEMA:errors.append("APPROVAL_SCHEMA_INVALID")
    if str(x.get("revision") or "")!=active_revision:errors.append("APPROVAL_REVISION_MISMATCH")
    checks=x.get("checks") or {}
    for key in (
      "guardian_pass","sentinel_exact_revision_pass","architecture_council_approval",
      "v7_runtime_health_pass","rollback_release_verified"
    ):
        if checks.get(key) is not True:errors.append("APPROVAL_"+key.upper()+"_MISSING")
    if x.get("destructive_apply_authorized") is not True:errors.append("DESTRUCTIVE_APPLY_NOT_AUTHORIZED")
    return not errors,errors

def build_plan(platform_root:Path,policy:dict[str,Any],evidence_root:Path|None=None)->dict[str,Any]:
    releases_root=platform_root/"releases";current=platform_root/"current"
    active=current.resolve() if current.is_symlink() else None
    rows=[]
    if releases_root.is_dir():
        for p in sorted(x for x in releases_root.iterdir() if x.is_dir()):
            rows.append({
              "name":p.name,"path":str(p.resolve()),"revision":revision_of(p),
              "version":version_of(p),"size_bytes":tree_size(p)
            })
    active_path=str(active) if active else ""
    active_revision=revision_of(active) if active and active.is_dir() else ""
    protected_paths=set()
    reasons={}
    if active:
        protected_paths.add(active_path);reasons[active_path]="ACTIVE_RELEASE"
    retention=policy.get("physical_release_retention") or {}
    slots=int(retention.get("rollback_slots") or 2)
    strategy=str(retention.get("rollback_selection_strategy") or "MOST_RECENT_VERIFIED_PRIOR_RELEASES")
    evidence_root=evidence_root or Path(str(retention.get("verification_evidence_root") or "/opt/chacha-dev/evidence"))
    verified_ranks=verified_revision_ranks(evidence_root)
    verified=set(verified_ranks)
    selected=[];seen=set();selected_versions=set();all_candidates=[]
    if strategy=="MOST_RECENT_VERIFIED_PRIOR_RELEASES":
        for rev,rank in verified_ranks.items():
            if rev==str(active_revision or "").lower():continue
            hit=latest_for_revision(rows,rev)
            if hit is not None:
                all_candidates.append((version_rank(str(hit.get("version") or "")),rank,rev,hit))
        # First pass: preserve rollback generation diversity. Keep only the newest
        # acquired revision for each platform version, then prefer the newest
        # platform versions.
        best_by_version={}
        for vrank,rank,rev,row in all_candidates:
            version=str(row.get("version") or "")
            current=best_by_version.get(version)
            if current is None or (rank,rev)>(current[1],current[2]):
                best_by_version[version]=(vrank,rank,rev,row)
        for vrank,rank,rev,row in sorted(best_by_version.values(),key=lambda x:(x[0],x[1],x[2]),reverse=True):
            if rev in seen:continue
            selected.append(row);seen.add(rev);selected_versions.add(str(row.get("version") or ""))
            if len(selected)>=slots:break
        # Second pass: if fewer distinct platform generations exist physically,
        # fill remaining slots with the next newest verified revisions.
        if len(selected)<slots:
            for vrank,rank,rev,row in sorted(all_candidates,key=lambda x:(x[0],x[1],x[2]),reverse=True):
                if rev in seen:continue
                selected.append(row);seen.add(rev)
                if len(selected)>=slots:break
    for rev in retention.get("fallback_verified_rollback_revisions") or []:
        if len(selected)>=slots:break
        rev=str(rev).lower()
        if rev==str(active_revision or "").lower() or rev in seen:continue
        hit=latest_for_revision(rows,rev)
        if hit and hit["path"]!=active_path:
            selected.append(hit);seen.add(rev)
    for hit in selected[:slots]:
        protected_paths.add(hit["path"])
        reasons.setdefault(hit["path"],"VERIFIED_ROLLBACK")
    missing_rollbacks=max(0,slots-len(selected))
    for row in rows:
        if row["path"] in protected_paths:
            row["action"]="KEEP";row["reason"]=reasons[row["path"]]
        else:
            row["action"]="RETIRE";row["reason"]="SUPERSEDED_PHYSICAL_RELEASE"
    retire=[x for x in rows if x["action"]=="RETIRE"]
    keep=[x for x in rows if x["action"]=="KEEP"]
    return {
      "schema":SCHEMA,"generated_at":now_iso(),"owner_agent":"intendant",
      "mode":"DRY_RUN","platform_root":str(platform_root),"active_release":active_path,
      "active_revision":active_revision,"active_version":version_of(active) if active else "",
      "release_count_before":len(rows),"keep_count":len(keep),"retire_count":len(retire),
      "bytes_before":sum(x["size_bytes"] for x in rows),
      "bytes_retirable":sum(x["size_bytes"] for x in retire),
      "estimated_bytes_after":sum(x["size_bytes"] for x in keep),
      "rollback_slots":slots,
      "rollback_revision_must_differ_from_active":True,
      "selected_rollback_revisions":[str(x.get("revision") or "") for x in selected[:slots]],
      "selected_rollback_evidence_epochs":[verified_ranks.get(str(x.get("revision") or "").lower(),0.0) for x in selected[:slots]],
      "selected_rollback_versions":[str(x.get("version") or "") for x in selected[:slots]],
      "rollback_selection_basis":"PLATFORM_VERSION_THEN_ACQUISITION_EVIDENCE_TIME",
      "verified_revision_count":len(verified),
      "missing_verified_rollback_count":missing_rollbacks,
      "rows":rows,
      "git_history_preserved":True,"remote_branch_deletion":False,
      "canonical_observation_bus_rewrite":False,"benchmark_evidence_mutation":False,
      "active_self_mutation":False,"self_promotion":False,"permission_expansion":False,
      "architecture_council_final_authority":True,"automatic_external_spend_eur":0
    }

def apply_plan(plan:dict[str,Any],policy:dict[str,Any],approval:Path|None,archive:Path,explicit:bool)->dict[str,Any]:
    if not explicit:raise SystemExit("EXPLICIT_APPLY_FLAG_REQUIRED")
    active_version=str(plan.get("active_version") or "")
    if not active_version.startswith("7."):raise SystemExit("V7_ACTIVE_RUNTIME_REQUIRED")
    if int(plan.get("missing_verified_rollback_count") or 0)>0:raise SystemExit("VERIFIED_ROLLBACK_RELEASE_MISSING")
    ok,errors=approval_ok(approval,str(plan.get("active_revision") or ""))
    if not ok:raise SystemExit("APPROVAL_BLOCK:"+",".join(errors))
    rows=plan.get("rows") or []
    for row in rows:
        if row.get("action")=="RETIRE":
            p=Path(str(row["path"]))
            row["tree_sha256"]=tree_digest(p)
    archive_doc={
      "schema":"chacha.dev/platform-retirement-archive/v1","generated_at":now_iso(),
      "active_revision":plan.get("active_revision"),"owner_agent":"intendant",
      "retiring":[x for x in rows if x.get("action")=="RETIRE"],
      "git_history_preserved":True,"automatic_external_spend_eur":0
    }
    save(archive,archive_doc)
    deleted=0;freed=0
    active=Path(str(plan["active_release"])).resolve()
    for row in rows:
        if row.get("action")!="RETIRE":continue
        p=Path(str(row["path"])).resolve()
        if p==active:raise SystemExit("REFUSE_DELETE_ACTIVE_RELEASE")
        if not p.is_dir():continue
        size=int(row.get("size_bytes") or 0)
        shutil.rmtree(p)
        deleted+=1;freed+=size
    out=dict(plan)
    out.update({
      "mode":"APPLY","applied_at":now_iso(),"archive_manifest":str(archive),
      "deleted_release_count":deleted,"freed_bytes":freed,
      "release_count_after":sum(1 for p in (Path(plan["platform_root"])/"releases").iterdir() if p.is_dir())
    })
    return out

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--platform-root",type=Path,default=Path("/opt/chacha-dev/platform"))
    ap.add_argument("--policy",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    ap.add_argument("--archive-manifest",type=Path)
    ap.add_argument("--approval",type=Path)
    ap.add_argument("--apply",action="store_true")
    ap.add_argument("--explicit-destructive-apply",action="store_true")
    a=ap.parse_args()
    policy=load(a.policy.resolve())
    retention=policy.get("physical_release_retention") or {}
    evidence_root=Path(str(retention.get("verification_evidence_root") or "/opt/chacha-dev/evidence"))
    plan=build_plan(a.platform_root.resolve(),policy,evidence_root)
    if a.apply:
        raise SystemExit("INTENDANT_DIRECT_MUTATION_FORBIDDEN_USE_CENTRAL_ORCHESTRATOR")
    save(a.output.resolve(),plan)
    mib=lambda n:round(float(n or 0)/1024/1024,1)
    print("CHACHA_DEV_V7_CONSOLIDATION_PLAN=PASS")
    print("MODE="+plan["mode"])
    print("OWNER_AGENT=intendant")
    print("ACTIVE_VERSION="+str(plan.get("active_version") or ""))
    print("RELEASES_BEFORE="+str(plan.get("release_count_before")))
    print("RELEASES_RETIRE="+str(plan.get("retire_count")))
    print("ROLLBACK_SELECTION_BASIS="+str(plan.get("rollback_selection_basis") or ""))
    print("SELECTED_ROLLBACK_REVISIONS="+",".join(plan.get("selected_rollback_revisions") or []))
    print("ESTIMATED_SAVINGS_MIB="+str(mib(plan.get("bytes_retirable"))))
    if plan["mode"]=="APPLY":
        print("DELETED_RELEASES="+str(plan.get("deleted_release_count")))
        print("FREED_MIB="+str(mib(plan.get("freed_bytes"))))
    print("GIT_HISTORY_PRESERVED=YES")
    print("REMOTE_BRANCH_DELETION=NO")
    print("CANONICAL_OBSERVATION_BUS_REWRITE=NO")
    print("BENCHMARK_EVIDENCE_MUTATION=NO")
    print("SELF_MUTATION=NO")
    print("SELF_PROMOTION=NO")
    print("ARCHITECTURE_COUNCIL_FINAL_AUTHORITY=YES")
    print("AUTOMATIC_EXTERNAL_SPEND_EUR=0")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
