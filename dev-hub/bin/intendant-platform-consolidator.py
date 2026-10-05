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
    prep=release/".release-preparation.json"
    if prep.is_file():
        try:
            x=load(prep);v=str(x.get("version") or "").strip()
            if v:return v
        except Exception:pass
    manifest=release/"release-manifest.json"
    if manifest.is_file():
        try:
            x=load(manifest);v=str(x.get("version") or "").strip()
            if v:return v
        except Exception:pass
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

def sovereign_authority_mode(runtime_root:Path)->str:
    p=runtime_root/"sovereign-state/authority.json"
    if not p.is_file():return "D1_REMOTE"
    try:
        x=load(p)
    except Exception:
        return "UNKNOWN"
    if x.get("schema")!="chacha.dev/sovereign-state-authority/v1":return "UNKNOWN"
    return str(x.get("mode") or "UNKNOWN").upper()

def sovereign_release_compatible(release:Path|None)->bool:
    if release is None or not release.is_dir():return False
    required=[
      release/"dev-hub/bin/sovereign_state_authority.py",
      release/"dev-hub/bin/d1-worker-local-runtime.mjs",
      release/"dev-hub/config/sovereign-state-authority.local.v1.json",
      release/"dev-hub/systemd/chacha-dev-sovereign-guardian.service",
      release/"dev-hub/systemd/chacha-dev-sovereign-sentinel.service",
      release/"dev-hub/systemd/chacha-dev-sovereign-assurance-exchange.service",
      release/"dev-hub/systemd/chacha-dev-sovereign-learning-relay.service"
    ]
    return all(x.is_file() for x in required)

def historical_archive_class(release:Path)->str:
    prep=release/".release-preparation.json"
    if not prep.is_file():return "UNFINALIZED_OR_UNKNOWN"
    try:x=load(prep)
    except Exception:return "UNFINALIZED_OR_UNKNOWN"
    activation=str(x.get("activation_status") or "").upper()
    acceptance=str(x.get("promotion_acceptance_status") or "").upper()
    final=str(x.get("promotion_final_verification") or "").upper()
    if acceptance=="PASS" and final.startswith("PASS"):
        return "FINALIZED_PASS"
    if activation=="ROLLED_BACK" or acceptance=="ROLLED_BACK" or bool(x.get("rollback_reason")):
        return "ROLLED_BACK_OR_FAILED"
    return "UNFINALIZED_OR_UNKNOWN"

def historical_archive_priority(release:Path)->int:
    return {"ROLLED_BACK_OR_FAILED":0,"UNFINALIZED_OR_UNKNOWN":1,"FINALIZED_PASS":2}[historical_archive_class(release)]

def strong_installed_revision_ranks(runtime_root:Path)->dict[str,float]:
    out={}
    gates=runtime_root/"release-gates"
    if gates.is_dir():
        for p in gates.rglob("*install-pass.json"):
            try:x=load(p)
            except Exception:continue
            rev=str(x.get("revision") or "").lower()
            if len(rev)!=40 or x.get("status")!="PASS":continue
            if str(x.get("direct_operator_health") or "")!="PASS":continue
            if str(x.get("guardian_realtime") or "")!="PASS":continue
            rank=_evidence_epoch(x,p)
            out[rev]=max(out.get(rev,0.0),rank)
    reports=runtime_root/"intendant/work"
    if reports.is_dir():
        for p in reports.glob("*/release-execution.json"):
            try:x=load(p)
            except Exception:continue
            if x.get("schema")!="chacha.dev/platform-hygiene-execution/v1" or x.get("mode")!="RELEASE_RETIREMENT":continue
            if x.get("active_release_preserved") is not True:continue
            rev=str(x.get("revision") or "").lower()
            if len(rev)!=40:continue
            rank=_evidence_epoch(x,p)
            out[rev]=max(out.get(rev,0.0),rank)
    return out

def approval_ok(path:Path|None,active_revision:str)->tuple[bool,list[str]]:
    if path is None or not path.is_file():return False,["APPROVAL_RECEIPT_MISSING"]
    x=load(path);errors=[]
    if x.get("schema")!=APPROVAL_SCHEMA:errors.append("APPROVAL_SCHEMA_INVALID")
    if str(x.get("revision") or "")!=active_revision:errors.append("APPROVAL_REVISION_MISMATCH")
    checks=x.get("checks") or {}
    for key in ("guardian_pass","sentinel_exact_revision_pass","exact_revision_qualification_pass",
                "architecture_council_approval","rollback_release_verified"):
        if checks.get(key) is not True:errors.append("APPROVAL_"+key.upper()+"_MISSING")
    runtime_health=checks.get("runtime_health_pass")
    if runtime_health is None:
        runtime_health=checks.get("v7_runtime_health_pass")  # legacy evidence compatibility only
    if runtime_health is not True:errors.append("APPROVAL_RUNTIME_HEALTH_PASS_MISSING")
    if x.get("destructive_apply_authorized") is not True:errors.append("DESTRUCTIVE_APPLY_NOT_AUTHORIZED")
    return not errors,errors

def build_plan(platform_root:Path,policy:dict[str,Any],evidence_root:Path|None=None,promotion_staging_candidate_revision:str="",promotion_staging_approval_digest:str="")->dict[str,Any]:
    releases_root=platform_root/"releases";current=platform_root/"current"
    active=current.resolve() if current.is_symlink() else None
    rows=[]
    if releases_root.is_dir():
        for p in sorted(x for x in releases_root.iterdir() if x.is_dir()):
            rows.append({
              "name":p.name,"path":str(p.resolve()),"revision":revision_of(p),
              "version":version_of(p),"size_bytes":tree_size(p),
              "acquired_epoch":p.stat().st_mtime
            })
    active_path=str(active) if active else ""
    active_revision=revision_of(active) if active and active.is_dir() else ""
    retention=policy.get("physical_release_retention") or {}
    runtime_root=Path(str(retention.get("runtime_evidence_root") or "/opt/chacha-dev/runtime"))
    sovereign_mode=sovereign_authority_mode(runtime_root)
    sovereign_local_primary=sovereign_mode=="LOCAL_SQLITE"
    declared_rollback_revision=""
    declared_rollback_ineligible_revision=""
    if active and active.is_dir():
        prep=active/".release-preparation.json"
        if prep.is_file():
            try:
                prep_meta=load(prep)
                candidate=str(prep_meta.get("rollback_revision") or "").lower().strip()
                if not candidate:
                    rollback_path_raw=str(prep_meta.get("rollback_path") or "").strip()
                    if rollback_path_raw:
                        rollback_path=Path(rollback_path_raw)
                        try:
                            rollback_path.resolve().relative_to(releases_root.resolve())
                        except (ValueError,FileNotFoundError):
                            rollback_path=None
                        if rollback_path is not None and rollback_path.is_dir():
                            candidate=str(revision_of(rollback_path) or "").lower().strip()
                if len(candidate)==40 and all(ch in "0123456789abcdef" for ch in candidate) and candidate!=str(active_revision or "").lower():
                    hit=latest_for_revision(rows,candidate)
                    if sovereign_local_primary and (hit is None or not sovereign_release_compatible(Path(str(hit.get("path") or "")))):
                        declared_rollback_ineligible_revision=candidate
                    else:
                        declared_rollback_revision=candidate
            except Exception:
                declared_rollback_revision=""
    protected_paths=set()
    reasons={}
    if active:
        protected_paths.add(active_path);reasons[active_path]="ACTIVE_RELEASE"
    slots=int(retention.get("rollback_slots") or 2)
    staging_rev=str(promotion_staging_candidate_revision or "").lower().strip()
    staging=bool(staging_rev)
    if staging:
        if len(staging_rev)!=40 or not all(ch in "0123456789abcdef" for ch in staging_rev):raise ValueError("PROMOTION_STAGING_CANDIDATE_REVISION_INVALID")
        if staging_rev==str(active_revision or "").lower():raise ValueError("PROMOTION_STAGING_CANDIDATE_ALREADY_ACTIVE")
        if any(str(row.get("revision") or "").lower()==staging_rev for row in rows):raise ValueError("PROMOTION_STAGING_CANDIDATE_ALREADY_MATERIALIZED")
        if not promotion_staging_approval_digest.startswith("sha256:"):raise ValueError("PROMOTION_STAGING_APPROVAL_DIGEST_REQUIRED")
        if slots<2:raise ValueError("PROMOTION_STAGING_REQUIRES_TWO_NORMAL_ROLLBACK_SLOTS")
    effective_slots=slots-1 if staging else slots
    future_rollback_revision=""
    historical_archive_slots=0
    if staging and sovereign_local_primary:
        if not sovereign_release_compatible(active):raise ValueError("SOVEREIGN_ACTIVE_RELEASE_NOT_ROLLBACK_COMPATIBLE")
        # Once LOCAL_SQLITE has accepted writes, pre-Sovereign releases are not safe automatic rollbacks.
        # The currently active Sovereign release becomes the candidate rollback after activation.
        future_rollback_revision=str(active_revision or "").lower()
        effective_slots=0
        target_before=max(1,int(retention.get("max_physical_releases_after_consolidation") or 3)-1)
        historical_archive_slots=max(0,target_before-1)  # active release already occupies one physical slot
    strategy=str(retention.get("rollback_selection_strategy") or "MOST_RECENT_VERIFIED_PRIOR_RELEASES")
    evidence_root=evidence_root or Path(str(retention.get("verification_evidence_root") or "/opt/chacha-dev/evidence"))
    strong_ranks=strong_installed_revision_ranks(runtime_root)
    # A physical release that previously completed a governed production promotion is also
    # strong rollback evidence. This keeps historical rollback proofs durable even after
    # older runtime release-gate files have been pruned.
    for row in rows:
        rev=str(row.get("revision") or "").lower()
        prep_path=Path(str(row.get("path") or ""))/".release-preparation.json"
        if len(rev)!=40 or not prep_path.is_file():continue
        try: prior=load(prep_path)
        except Exception:continue
        final=str(prior.get("promotion_final_verification") or "").upper()
        acceptance=str(prior.get("promotion_acceptance_status") or "").upper()
        if acceptance=="PASS" and final.startswith("PASS"):
            strong_ranks[rev]=max(strong_ranks.get(rev,0.0),_evidence_epoch(prior,prep_path))
    legacy_ranks=verified_revision_ranks(evidence_root)
    verified_ranks=dict(strong_ranks)
    verified=set(verified_ranks)
    selected=[];seen=set();all_candidates=[]
    declared_rollback_protected=False
    if effective_slots>0 and bool(retention.get("protect_declared_active_release_rollback",True)) and declared_rollback_revision:
        hit=latest_for_revision(rows,declared_rollback_revision)
        rank=max(float(strong_ranks.get(declared_rollback_revision,0.0)),float(legacy_ranks.get(declared_rollback_revision,0.0)))
        if hit is not None and rank>0:
            selected.append(hit);seen.add(declared_rollback_revision);verified_ranks[declared_rollback_revision]=rank
            reasons[hit["path"]]="DECLARED_ROLLBACK";declared_rollback_protected=True
    if effective_slots>0 and strategy in {"MOST_RECENT_VERIFIED_PRIOR_RELEASES","MOST_RECENT_STRONGLY_VERIFIED_DISTINCT_REVISIONS"}:
        for rev,rank in strong_ranks.items():
            if rev==str(active_revision or "").lower():continue
            hit=latest_for_revision(rows,rev)
            if hit is not None:
                if sovereign_local_primary and not sovereign_release_compatible(Path(str(hit.get("path") or ""))):continue
                all_candidates.append((float(hit.get("acquired_epoch") or 0),rank,rev,hit))
        for acquired,rank,rev,row in sorted(all_candidates,key=lambda x:(x[0],x[1],x[2]),reverse=True):
            if rev in seen:continue
            selected.append(row);seen.add(rev)
            if len(selected)>=effective_slots:break
        if len(selected)<slots:
            for rev,rank in legacy_ranks.items():
                if rev==str(active_revision or "").lower() or rev in seen:continue
                hit=latest_for_revision(rows,rev)
                if hit is None:continue
                if sovereign_local_primary and not sovereign_release_compatible(Path(str(hit.get("path") or ""))):continue
                selected.append(hit);seen.add(rev);verified_ranks[rev]=rank
                if len(selected)>=effective_slots:break
    for rev in (retention.get("fallback_verified_rollback_revisions") or []) if effective_slots>0 else []:
        if len(selected)>=effective_slots:break
        rev=str(rev).lower()
        if rev==str(active_revision or "").lower() or rev in seen:continue
        hit=latest_for_revision(rows,rev)
        if hit and hit["path"]!=active_path:
            if sovereign_local_primary and not sovereign_release_compatible(Path(str(hit.get("path") or ""))):continue
            selected.append(hit);seen.add(rev)
    for hit in selected[:effective_slots]:
        protected_paths.add(hit["path"])
        reasons.setdefault(hit["path"],"VERIFIED_ROLLBACK")
    for row in rows:
        row["historical_archive_class"]=historical_archive_class(Path(str(row.get("path") or "")))
    archive_selected=[]
    if historical_archive_slots>0:
        candidates=[r for r in rows if r["path"]!=active_path and r["path"] not in protected_paths]
        for row in sorted(candidates,key=lambda x:(historical_archive_priority(Path(str(x.get("path") or ""))),float(x.get("acquired_epoch") or 0),str(x.get("revision") or "")),reverse=True)[:historical_archive_slots]:
            archive_selected.append(row);protected_paths.add(row["path"]);reasons[row["path"]]="HISTORICAL_ARCHIVE_NOT_ROLLBACK_ELIGIBLE"
    missing_rollbacks=0 if (staging and sovereign_local_primary and future_rollback_revision) else max(0,effective_slots-len(selected))
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
      "rollback_slots":slots,"effective_rollback_slots":effective_slots,
      "promotion_staging_slot_reserved":staging,
      "promotion_staging_candidate_revision":staging_rev if staging else None,
      "promotion_staging_approval_digest":promotion_staging_approval_digest if staging else None,
      "promotion_staging_candidate_materialized":False if staging else None,
      "promotion_staging_target_release_count_before_materialization":max(1,int(retention.get("max_physical_releases_after_consolidation") or 3)-1) if staging else None,
      "rollback_revision_must_differ_from_active":True,
      "declared_rollback_revision":declared_rollback_revision,
      "declared_rollback_protected":declared_rollback_protected,
      "declared_rollback_ineligible_revision":declared_rollback_ineligible_revision or None,
      "sovereign_authority_mode":sovereign_mode,
      "sovereign_local_primary_rollback_floor_enforced":sovereign_local_primary,
      "future_candidate_rollback_revision":future_rollback_revision or None,
      "historical_archive_revisions":[str(x.get("revision") or "") for x in archive_selected],
      "historical_archive_selection_policy":"PREFER_FINALIZED_PASS_OVER_UNKNOWN_OVER_ROLLED_BACK_OR_FAILED",
      "selected_rollback_revisions":[str(x.get("revision") or "") for x in selected[:effective_slots]],
      "selected_rollback_evidence_epochs":[verified_ranks.get(str(x.get("revision") or "").lower(),0.0) for x in selected[:effective_slots]],
      "selected_rollback_versions":[str(x.get("version") or "") for x in selected[:effective_slots]],
      "rollback_selection_basis":"DECLARED_ACTIVE_RELEASE_ROLLBACK_THEN_RECENCY_DISTINCT_REVISION_WITH_STRONG_INSTALL_OR_ACTIVE_HISTORY_EVIDENCE",
      "verified_revision_count":len(verified),
      "missing_verified_rollback_count":missing_rollbacks,
      "rows":rows,
      "git_history_preserved":True,"remote_branch_deletion":False,
      "canonical_observation_bus_rewrite":False,"benchmark_evidence_mutation":False,
      "active_self_mutation":False,"self_promotion":False,"permission_expansion":False,
      "architecture_council_final_authority":False,"architecture_council_recommendation_authority":True,"automatic_external_spend_eur":0
    }

def apply_plan(plan:dict[str,Any],policy:dict[str,Any],approval:Path|None,archive:Path,explicit:bool)->dict[str,Any]:
    if not explicit:raise SystemExit("EXPLICIT_APPLY_FLAG_REQUIRED")
    active_version=str(plan.get("active_version") or "")
    if not active_version.strip():raise SystemExit("ACTIVE_RUNTIME_VERSION_REQUIRED")
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

def promotion_staging_approval(path:Path|None)->tuple[str,str]:
    if path is None:return "",""
    x=load(path.resolve())
    rev=str(x.get("revision") or "").lower().strip()
    if x.get("schema")!="chacha.dev/production-approval/v1":raise ValueError("PROMOTION_STAGING_APPROVAL_SCHEMA_INVALID")
    if x.get("scope")!="platform-promotion-release-slot-reservation":raise ValueError("PROMOTION_STAGING_APPROVAL_SCOPE_INVALID")
    if x.get("approved") is not True or x.get("approved_by")!="operator":raise ValueError("PROMOTION_STAGING_OPERATOR_APPROVAL_REQUIRED")
    if len(rev)!=40 or not all(ch in "0123456789abcdef" for ch in rev):raise ValueError("PROMOTION_STAGING_APPROVAL_REVISION_INVALID")
    tree=str(x.get("tree") or "").lower().strip()
    if len(tree)!=40 or not all(ch in "0123456789abcdef" for ch in tree):raise ValueError("PROMOTION_STAGING_APPROVAL_TREE_INVALID")
    return rev,"sha256:"+hashlib.sha256(path.resolve().read_bytes()).hexdigest()

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--platform-root",type=Path,default=Path("/opt/chacha-dev/platform"))
    ap.add_argument("--policy",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    ap.add_argument("--archive-manifest",type=Path)
    ap.add_argument("--approval",type=Path)
    ap.add_argument("--apply",action="store_true")
    ap.add_argument("--explicit-destructive-apply",action="store_true")
    ap.add_argument("--promotion-staging-approval",type=Path)
    a=ap.parse_args()
    policy=load(a.policy.resolve())
    retention=policy.get("physical_release_retention") or {}
    evidence_root=Path(str(retention.get("verification_evidence_root") or "/opt/chacha-dev/evidence"))
    staging_rev,staging_digest=promotion_staging_approval(a.promotion_staging_approval)
    plan=build_plan(a.platform_root.resolve(),policy,evidence_root,staging_rev,staging_digest)
    if a.apply:
        raise SystemExit("INTENDANT_DIRECT_MUTATION_FORBIDDEN_USE_CENTRAL_ORCHESTRATOR")
    save(a.output.resolve(),plan)
    mib=lambda n:round(float(n or 0)/1024/1024,1)
    print("CHACHA_DEV_PLATFORM_CONSOLIDATION_PLAN=PASS")
    print("MODE="+plan["mode"])
    print("OWNER_AGENT=intendant")
    print("ACTIVE_VERSION="+str(plan.get("active_version") or ""))
    print("RELEASES_BEFORE="+str(plan.get("release_count_before")))
    print("RELEASES_RETIRE="+str(plan.get("retire_count")))
    print("PROMOTION_STAGING_SLOT_RESERVED="+("YES" if plan.get("promotion_staging_slot_reserved") else "NO"))
    if plan.get("promotion_staging_slot_reserved"):print("PROMOTION_STAGING_CANDIDATE="+str(plan.get("promotion_staging_candidate_revision")))
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
    print("ARCHITECTURE_COUNCIL_FINAL_AUTHORITY=NO")
    print("ARCHITECTURE_COUNCIL_RECOMMENDATION_AUTHORITY=YES")
    print("AUTOMATIC_EXTERNAL_SPEND_EUR=0")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
