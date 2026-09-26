#!/usr/bin/env python3
from __future__ import annotations
import argparse,fcntl,hashlib,json,os,shutil,subprocess,sys,urllib.request
from datetime import datetime,timezone,timedelta
from pathlib import Path
from typing import Any

REPORT_SCHEMA="chacha.dev/intendant-hygiene-report/v2"
STATE_SCHEMA="chacha.dev/intendant-hygiene-state/v1"
TEMP_PLAN_SCHEMA="chacha.dev/safe-temp-cleanup-plan/v1"

def load(p:Path,default=None):
    if not p.is_file():return {} if default is None else default
    x=json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise ValueError("JSON_ROOT_NOT_OBJECT:"+str(p))
    return x
def save(p:Path,x:dict[str,Any]):
    p.parent.mkdir(parents=True,exist_ok=True)
    tmp=p.with_suffix(p.suffix+".tmp");tmp.write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf-8");tmp.replace(p)
def file_digest(p:Path)->str:return "sha256:"+hashlib.sha256(p.read_bytes()).hexdigest()
def dt(s:str|None)->datetime|None:
    if not s:return None
    try:return datetime.fromisoformat(s.replace("Z","+00:00"))
    except Exception:return None
def iso(t:datetime)->str:return t.astimezone(timezone.utc).isoformat().replace("+00:00","Z")
def run(cmd:list[str],timeout=90)->subprocess.CompletedProcess:
    return subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=timeout)
def tree_bytes(p:Path)->int:
    if not p.exists():return 0
    if p.is_file():
        try:return p.stat().st_size
        except FileNotFoundError:return 0
    total=0
    for x in p.rglob("*"):
        try:
            if x.is_file():total+=x.stat().st_size
        except FileNotFoundError:pass
    return total
def has_open_fd(path:Path)->bool:
    try:target=path.resolve()
    except Exception:return True
    proc=Path("/proc")
    if not proc.is_dir():return True
    for fdroot in proc.glob("[0-9]*/fd"):
        try:links=list(fdroot.iterdir())
        except Exception:continue
        for link in links:
            try:
                raw=os.readlink(link);p=Path(raw)
                if not p.is_absolute():continue
                r=p.resolve()
                if r==target or target in r.parents:return True
            except Exception:continue
    return False
def temp_candidates(cfg:dict[str,Any],now:datetime)->list[dict[str,Any]]:
    out=[];hours=float(cfg.get("minimum_age_hours") or 48);cut=now-timedelta(hours=hours)
    seen=set()
    for root_cfg in cfg.get("roots") or []:
        root=Path(str(root_cfg.get("path") or ""))
        glob=str(root_cfg.get("glob") or "*")
        if not root.is_dir():continue
        rr=root.resolve()
        for p in root.glob(glob):
            if p.is_symlink():continue
            try:
                rp=p.resolve();rp.relative_to(rr)
                if rp==rr or str(rp) in seen:continue
                mtime=datetime.fromtimestamp(rp.stat().st_mtime,timezone.utc)
            except Exception:continue
            if mtime>cut:continue
            seen.add(str(rp))
            out.append({"path":str(rp),"root":str(rr),"size_bytes":tree_bytes(rp),"mtime":iso(mtime),"open_fd":has_open_fd(rp)})
    return sorted(out,key=lambda x:x["path"])
def current_revision(platform:Path)->str:
    cur=(platform/"current").resolve();p=cur/".revision"
    return p.read_text().strip() if p.is_file() else ""
def current_version(platform:Path)->str:
    cur=(platform/"current").resolve()
    for name in (".release-preparation.json","release-manifest.json"):
        p=cur/name
        if not p.is_file():continue
        try:
            v=str(load(p).get("version") or "").strip()
            if v:return v
        except Exception:continue
    return "UNKNOWN"
def release_count(platform:Path)->int:
    root=platform/"releases";return sum(1 for p in root.iterdir() if p.is_dir()) if root.is_dir() else 0
def disk_used_pct(path:Path)->float:
    d=shutil.disk_usage(path);return round((d.used/d.total)*100,1) if d.total else 0.0
def due(last:str|None,now:datetime,hours:float)->bool:
    x=dt(last);return x is None or now-x>=timedelta(hours=hours)
def github_branch_candidates()->list[str]:
    try:
        req=urllib.request.Request("https://api.github.com/repos/chachasan090375/WfGg/branches?per_page=100",
          headers={"User-Agent":"ChaCha-DEV-Intendant-Hygiene/2.0","Accept":"application/vnd.github+json"})
        with urllib.request.urlopen(req,timeout=15) as r:x=json.loads(r.read().decode())
        return sorted(str(b.get("name")) for b in x if isinstance(b,dict) and str(b.get("name") or "").startswith("dev-hub-v6"))
    except Exception:return []
def hygiene_debt(metrics:dict[str,Any],policy:dict[str,Any])->int:
    w=(policy.get("hygiene_debt") or {}).get("weights") or {};score=0
    if metrics["release_count"]>3:score+=int(w.get("release_overage") or 30)
    limit=int((((policy.get("cycles") or {}).get("THRESHOLD_WATCH") or {}).get("triggers") or {}).get("runtime_temp_bytes_gte") or 1073741824)
    score+=min(int(w.get("temp_storage_pressure") or 20),int((metrics["temp_bytes"]/max(1,limit))*int(w.get("temp_storage_pressure") or 20)))
    if metrics["stale_temp_count"]>0:score+=min(int(w.get("stale_artifacts") or 15),metrics["stale_temp_count"])
    score+=min(int(w.get("deprecated_code_candidates") or 15),metrics.get("deprecated_code_candidates",0))
    score+=min(int(w.get("duplicate_surfaces") or 10),metrics.get("duplicate_surfaces",0))
    score+=min(int(w.get("unused_configs") or 10),metrics.get("unused_configs",0))
    return max(0,min(100,score))
def guardian_check(client:Path,policy:Path,event_path:Path,result_path:Path,event:dict[str,Any])->tuple[bool,dict[str,Any]]:
    save(event_path,event)
    p=run([sys.executable,str(client),"--policy",str(policy),"check","--event",str(event_path)],45)
    parsed={}
    lines=[x.strip() for x in p.stdout.splitlines() if x.strip()]
    if lines:
        try:parsed=json.loads(lines[-1])
        except Exception:parsed={"raw":lines[-1]}
    save(result_path,parsed)
    return p.returncode==0 and str(parsed.get("verdict") or "") in {"PASS","WARNING"},parsed
def governance_event(action_id:str,phase:str,action:str,evidence:dict[str,Any],revision:str)->dict[str,Any]:
    return {
      "schema":"chacha.dev/governance-action/v1","event_id":action_id+"-"+phase.lower(),"action_id":action_id,
      "phase":phase,"actor":"platform-hygiene-executor","subject_role":"platform-hygiene-executor",
      "action":action,"permission":"destructive-operation","project_id":"chacha-dev-platform","revision":revision,
      "evidence":evidence,"context":{"resource_class":"normal","deadline_seconds":900},
      "capabilities":["platform-hygiene"],"automatic_external_spend_eur":0
    }
def post_guardian(client,policy,work,action_id,action,evidence,revision):
    ev=governance_event(action_id,"POST_ACTION",action,evidence,revision)
    ok,_=guardian_check(client,policy,work/(action_id+"-post-event.json"),work/(action_id+"-post-result.json"),ev)
    return ok

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--repo-root",type=Path,default=Path("/opt/chacha-dev/platform/current"))
    ap.add_argument("--runtime-root",type=Path,default=Path("/opt/chacha-dev/runtime"))
    ap.add_argument("--platform-root",type=Path,default=Path("/opt/chacha-dev/platform"))
    ap.add_argument("--policy",type=Path,required=True);ap.add_argument("--consolidation-policy",type=Path,required=True)
    ap.add_argument("--guardian-client",type=Path,required=True);ap.add_argument("--guardian-policy",type=Path,required=True)
    ap.add_argument("--guardian-coverage",type=Path,required=True);ap.add_argument("--council",type=Path,required=True)
    ap.add_argument("--consolidator",type=Path,required=True);ap.add_argument("--hygiene-executor",type=Path,required=True)
    ap.add_argument("--github-runs-json",type=Path)
    ap.add_argument("--qualification-gate",type=Path)
    ap.add_argument("--sentinel-gate",type=Path)
    ap.add_argument("--force-cycle",choices=["LIGHT_DAILY","WEEKLY_DRY_RUN","MONTHLY_CONSOLIDATION"])
    ap.add_argument("--now");ap.add_argument("--dry-run",action="store_true")
    a=ap.parse_args();now=dt(a.now) if a.now else datetime.now(timezone.utc)
    if now is None:raise SystemExit("INVALID_NOW")
    policy=load(a.policy);consolidation=load(a.consolidation_policy)
    sched=policy.get("scheduler") or {}
    state_path=Path(str(sched.get("state_file") or a.runtime_root/"intendant/hygiene-state.json"))
    report_dir=Path(str(sched.get("report_dir") or a.runtime_root/"intendant/hygiene-reports"))
    latest_path=Path(str(sched.get("latest_report") or a.runtime_root/"intendant/hygiene-latest.json"))
    lock_path=Path(str(sched.get("lock_file") or a.runtime_root/"intendant/hygiene.lock"))
    lock_path.parent.mkdir(parents=True,exist_ok=True)
    lock_fd=open(lock_path,"a+")
    try:fcntl.flock(lock_fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:
        print("CHACHA_DEV_V710_INTENDANT_HYGIENE_CYCLE=SKIPPED_LOCKED");return 0
    state=load(state_path,{"schema":STATE_SCHEMA,"last_success":{}});report_dir.mkdir(parents=True,exist_ok=True)
    cycle_cfg=policy.get("cycles") or {};light_cfg=cycle_cfg.get("LIGHT_DAILY") or {}
    candidates=temp_candidates(light_cfg.get("safe_temp_cleanup") or {},now)
    temp_bytes=sum(x["size_bytes"] for x in candidates)
    active=(a.platform_root/"current").resolve();deprecated=0
    if active.is_dir():
        for p in (active/"dev-hub").rglob("*"):
            if p.is_file() and ("deprecated" in p.name.lower() or "obsolete" in p.name.lower()):deprecated+=1
    metrics={"disk_used_pct":disk_used_pct(a.platform_root),"release_count":release_count(a.platform_root),
      "temp_bytes":temp_bytes,"stale_temp_count":len(candidates),"deprecated_code_candidates":deprecated,
      "duplicate_surfaces":0,"unused_configs":0}
    metrics["hygiene_debt_score"]=hygiene_debt(metrics,policy)
    last=state.setdefault("last_success",{});cycles=[]
    if a.force_cycle:
        cfg=cycle_cfg.get(a.force_cycle) or {}
        if cfg.get("enabled") is True:cycles=[a.force_cycle]
    else:
        for name in ("LIGHT_DAILY","WEEKLY_DRY_RUN","MONTHLY_CONSOLIDATION"):
            cfg=cycle_cfg.get(name) or {}
            if cfg.get("enabled") is True and due(last.get(name),now,float(cfg.get("minimum_interval_hours") or 24)):
                cycles.append(name)
    trig=((cycle_cfg.get("THRESHOLD_WATCH") or {}).get("triggers") or {});threshold_reasons=[]
    if metrics["disk_used_pct"]>=float(trig.get("filesystem_used_pct_gte") or 75):threshold_reasons.append("FILESYSTEM_PRESSURE")
    if metrics["release_count"]>int(trig.get("physical_release_count_gt") or 3):threshold_reasons.append("RELEASE_OVERAGE")
    if metrics["temp_bytes"]>=int(trig.get("runtime_temp_bytes_gte") or 1073741824):threshold_reasons.append("TEMP_PRESSURE")
    if metrics["hygiene_debt_score"]>=int(trig.get("hygiene_debt_score_gte") or 60):threshold_reasons.append("HYGIENE_DEBT")
    if not a.force_cycle and threshold_reasons and "WEEKLY_DRY_RUN" not in cycles:
        cycles.append("WEEKLY_DRY_RUN")
    coverage=load(a.guardian_coverage,{})
    coverage_ok=coverage.get("all_hooks_active") is True
    stamp=now.strftime("%Y%m%dT%H%M%SZ");work=a.runtime_root/"intendant"/"work"/stamp;work.mkdir(parents=True,exist_ok=True)
    revision=current_revision(a.platform_root);results=[]
    for name in cycles:
        row={"cycle":name,"status":"PASS","actions":[]}
        if not coverage_ok:
            row.update({"status":"BLOCKED","reason":"GUARDIAN_COVERAGE_NOT_ACTIVE"});results.append(row);continue
        if name=="LIGHT_DAILY":
            deletable=[x for x in candidates if not x["open_fd"]]
            manifest=work/"safe-temp-plan.json"
            save(manifest,{"schema":TEMP_PLAN_SCHEMA,"generated_at":iso(now),"owner_agent":"intendant",
              "candidates":deletable,"minimum_age_hours":float((light_cfg.get("safe_temp_cleanup") or {}).get("minimum_age_hours") or 48),
              "standing_operator_approval":bool((light_cfg.get("safe_temp_cleanup") or {}).get("standing_operator_approval")),
              "automatic_external_spend_eur":0})
            if deletable and not a.dry_run:
                md=file_digest(manifest);action_id="hygiene-temp-"+stamp
                evidence={"human_approval":True,"safe_temp_manifest_digest":md,"safe_scope_verified":True}
                pre=governance_event(action_id,"PRE_ACTION","EXECUTE_SAFE_TEMP_CLEANUP",evidence,revision)
                ok,_=guardian_check(a.guardian_client,a.guardian_policy,work/"guardian-temp-pre-event.json",work/"guardian-temp-pre-result.json",pre)
                if not ok:
                    row.update({"status":"BLOCKED","reason":"GUARDIAN_REALTIME_BLOCK"});results.append(row);continue
                out=work/"temp-execution.json"
                e=run([sys.executable,str(a.hygiene_executor),"safe-temp-cleanup","--manifest",str(manifest),
                  "--hygiene-config",str(a.policy),"--guardian-event",str(work/"guardian-temp-pre-event.json"),
                  "--guardian-result",str(work/"guardian-temp-pre-result.json"),"--output",str(out)],120)
                if e.returncode!=0:
                    row.update({"status":"BLOCKED","reason":"PLATFORM_HYGIENE_EXECUTOR_FAILED","stderr":e.stderr[-1200:]});results.append(row);continue
                ex=load(out);post_evidence={**evidence,"execution_receipt":file_digest(out)}
                post_ok=post_guardian(a.guardian_client,a.guardian_policy,work,action_id,"EXECUTE_SAFE_TEMP_CLEANUP",post_evidence,revision)
                row["actions"].append({"action":"SAFE_TEMP_CLEANUP","deleted":ex.get("deleted_candidate_count"),"freed_bytes":ex.get("freed_bytes"),
                  "executor":"platform-hygiene-executor","guardian_post_action":post_ok})
                if not post_ok:row["status"]="WARNING"
            else:
                row["actions"].append({"action":"SAFE_TEMP_SCAN","candidates":len(deletable),"dry_run":True})
        elif name=="WEEKLY_DRY_RUN":
            plan=work/"consolidation-plan.json"
            p=run([sys.executable,str(a.consolidator),"--platform-root",str(a.platform_root),"--policy",str(a.consolidation_policy),"--output",str(plan)])
            if p.returncode!=0:
                row.update({"status":"BLOCKED","reason":"CONSOLIDATOR_FAILED","stderr":p.stderr[-1200:]});results.append(row);continue
            px=load(plan);row["actions"].append({"action":"RELEASE_RETIREMENT_DRY_RUN","retire_count":px.get("retire_count"),
              "bytes_retirable":px.get("bytes_retirable"),"selected_rollback_revisions":px.get("selected_rollback_revisions"),
              "selected_rollback_evidence_epochs":px.get("selected_rollback_evidence_epochs"),
              "rollback_selection_basis":px.get("rollback_selection_basis")})
            safe=((cycle_cfg.get("WEEKLY_DRY_RUN") or {}).get("safe_release_retirement") or {})
            standing=bool(sched.get("standing_operator_approval_authorized")) and bool(safe.get("standing_operator_approval"))
            if int(px.get("retire_count") or 0)>0 and safe.get("auto_apply_when_fully_governed") is True and standing and not a.dry_run:
                approval=work/"consolidation-approval.json"
                council_cmd=[sys.executable,str(a.council),"--plan",str(plan),"--policy",str(a.consolidation_policy),
                  "--guardian-coverage",str(a.guardian_coverage),"--revision",revision,"--operator-explicit-purge-approval","--output",str(approval)]
                if a.github_runs_json:council_cmd += ["--github-runs-json",str(a.github_runs_json)]
                if a.qualification_gate:council_cmd += ["--qualification-gate",str(a.qualification_gate)]
                if a.sentinel_gate:council_cmd += ["--sentinel-gate",str(a.sentinel_gate)]
                q=run(council_cmd,60)
                if q.returncode!=0:
                    row.update({"status":"BLOCKED","reason":"ARCHITECTURE_COUNCIL_BLOCK","stderr":(q.stderr+q.stdout)[-1600:]});results.append(row);continue
                pd=file_digest(plan);ad=file_digest(approval);action_id="hygiene-release-"+stamp
                evidence={"human_approval":True,"consolidation_plan_digest":pd,"architecture_council_approval":True,
                  "architecture_council_approval_digest":ad,"rollback_verified":int(px.get("missing_verified_rollback_count") or 0)==0}
                pre=governance_event(action_id,"PRE_ACTION","EXECUTE_PLATFORM_RETIREMENT",evidence,revision)
                ok,_=guardian_check(a.guardian_client,a.guardian_policy,work/"guardian-release-pre-event.json",work/"guardian-release-pre-result.json",pre)
                if not ok:
                    row.update({"status":"BLOCKED","reason":"GUARDIAN_REALTIME_BLOCK"});results.append(row);continue
                out=work/"release-execution.json";archive=report_dir/("retirement-archive-"+stamp+".json")
                e=run([sys.executable,str(a.hygiene_executor),"release-retirement","--platform-root",str(a.platform_root),
                  "--plan",str(plan),"--approval",str(approval),"--guardian-event",str(work/"guardian-release-pre-event.json"),
                  "--guardian-result",str(work/"guardian-release-pre-result.json"),"--archive-manifest",str(archive),"--output",str(out)],180)
                if e.returncode!=0:
                    row.update({"status":"BLOCKED","reason":"PLATFORM_HYGIENE_EXECUTOR_FAILED","stderr":e.stderr[-1600:]});results.append(row);continue
                ex=load(out);post_evidence={**evidence,"execution_receipt":file_digest(out)}
                post_ok=post_guardian(a.guardian_client,a.guardian_policy,work,action_id,"EXECUTE_PLATFORM_RETIREMENT",post_evidence,revision)
                row["actions"].append({"action":"SAFE_RELEASE_RETIREMENT_APPLY","executor":"platform-hygiene-executor",
                  "deleted_release_count":ex.get("deleted_release_count"),"freed_bytes":ex.get("freed_bytes"),"guardian_post_action":post_ok})
                if not post_ok:row["status"]="WARNING"
        elif name=="MONTHLY_CONSOLIDATION":
            branches=github_branch_candidates()
            row["actions"].append({"action":"DEEP_CONSOLIDATION_REVIEW","deprecated_code_candidates":deprecated,
              "v6_remote_branch_candidates":branches,"remote_branch_deletion":False,"source_code_deletion":False,
              "next_action":"REVIEW_ONLY"})
        if row["status"] in {"PASS","WARNING"}:last[name]=iso(now)
        results.append(row)
    post_metrics=dict(metrics)
    post_metrics["disk_used_pct"]=disk_used_pct(a.platform_root)
    post_metrics["release_count"]=release_count(a.platform_root)
    post_metrics["hygiene_debt_score"]=hygiene_debt(post_metrics,policy)
    post_threshold_reasons=[]
    if post_metrics["disk_used_pct"]>=float(trig.get("filesystem_used_pct_gte") or 75):post_threshold_reasons.append("FILESYSTEM_PRESSURE")
    if post_metrics["release_count"]>int(trig.get("physical_release_count_gt") or 3):post_threshold_reasons.append("RELEASE_OVERAGE")
    if post_metrics["temp_bytes"]>=int(trig.get("runtime_temp_bytes_gte") or 1073741824):post_threshold_reasons.append("TEMP_PRESSURE")
    if post_metrics["hygiene_debt_score"]>=int(trig.get("hygiene_debt_score_gte") or 60):post_threshold_reasons.append("HYGIENE_DEBT")
    state.update({"schema":STATE_SCHEMA,"updated_at":iso(now),"last_success":last,"last_metrics":post_metrics,
      "last_threshold_reasons":post_threshold_reasons});save(state_path,state)
    report={"schema":REPORT_SCHEMA,"generated_at":iso(now),"owner_agent":"intendant","physical_executor":"platform-hygiene-executor",
      "platform_revision":revision,"platform_version":current_version(a.platform_root),"cycles_requested":cycles,"results":results,
      "metrics_before":metrics,"metrics":post_metrics,"threshold_reasons_before":threshold_reasons,
      "threshold_reasons":post_threshold_reasons,"git_history_preserved":True,"remote_branch_deletion":False,
      "source_code_deletion":False,"canonical_observation_bus_rewrite":False,"benchmark_evidence_mutation":False,
      "intendant_direct_mutation":False,"architecture_council_final_authority":True,"automatic_external_spend_eur":0}
    report_path=report_dir/("hygiene-"+stamp+".json");save(report_path,report);save(latest_path,report)
    print("CHACHA_DEV_INTENDANT_HYGIENE_CYCLE=PASS")
    print("CYCLES="+(",".join(cycles) if cycles else "NONE"));print("HYGIENE_DEBT_SCORE="+str(post_metrics["hygiene_debt_score"]))
    print("DISK_USED_PCT="+str(post_metrics["disk_used_pct"]));print("RELEASE_COUNT="+str(post_metrics["release_count"]))
    print("THRESHOLD_REASONS="+(",".join(post_threshold_reasons) if post_threshold_reasons else "NONE"));print("REPORT="+str(report_path))
    print("INTENDANT_DIRECT_MUTATION=NO");print("PHYSICAL_HYGIENE_EXECUTOR=platform-hygiene-executor")
    return 0 if all(x.get("status") in {"PASS","WARNING"} for x in results) else 20

if __name__=="__main__":raise SystemExit(main())
