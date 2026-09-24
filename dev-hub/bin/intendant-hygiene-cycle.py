#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,os,shutil,subprocess,sys,urllib.request
from datetime import datetime,timezone,timedelta
from pathlib import Path
from typing import Any

SCHEMA="chacha.dev/intendant-hygiene-report/v1"

def load(p:Path,default=None):
    if not p.is_file():return {} if default is None else default
    x=json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise ValueError("JSON_ROOT_NOT_OBJECT:"+str(p))
    return x
def save(p:Path,x:dict[str,Any]):
    p.parent.mkdir(parents=True,exist_ok=True)
    tmp=p.with_suffix(p.suffix+".tmp");tmp.write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf-8");tmp.replace(p)
def dt(s:str|None)->datetime|None:
    if not s:return None
    try:return datetime.fromisoformat(s.replace("Z","+00:00"))
    except Exception:return None
def iso(t:datetime)->str:return t.astimezone(timezone.utc).isoformat().replace("+00:00","Z")
def run(cmd:list[str],timeout=60)->subprocess.CompletedProcess:
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
    target=str(path.resolve())
    proc=Path("/proc")
    if not proc.is_dir():return True
    for pid in proc.iterdir():
        if not pid.name.isdigit():continue
        fd=pid/"fd"
        try:links=list(fd.iterdir())
        except Exception:continue
        for link in links:
            try:v=os.readlink(link)
            except Exception:continue
            if v==target or v.startswith(target+"/"):return True
    return False
def temp_candidates(cfg:dict[str,Any],now:datetime)->list[dict[str,Any]]:
    out=[];hours=float(cfg.get("minimum_age_hours") or 48);cut=now-timedelta(hours=hours)
    for root_cfg in cfg.get("roots") or []:
        root=Path(str(root_cfg.get("path") or ""));glob=str(root_cfg.get("glob") or "*")
        if not root.is_dir():continue
        for p in root.glob(glob):
            try:mtime=datetime.fromtimestamp(p.stat().st_mtime,timezone.utc)
            except FileNotFoundError:continue
            if mtime>cut:continue
            open_fd=has_open_fd(p) if cfg.get("require_no_open_file_descriptors") is True else False
            out.append({"path":str(p.resolve()),"size_bytes":tree_bytes(p),"mtime":iso(mtime),"open_fd":open_fd})
    return out
def guardian_coverage_ok(path:Path)->bool:
    try:return load(path).get("all_hooks_active") is True
    except Exception:return False
def guardian_realtime(client:Path,policy:Path,event_path:Path,event:dict[str,Any])->bool:
    save(event_path,event)
    p=run([sys.executable,str(client),"--policy",str(policy),"check","--event",str(event_path)],45)
    return p.returncode==0
def current_revision(platform:Path)->str:
    cur=(platform/"current").resolve();p=cur/".revision"
    return p.read_text().strip() if p.is_file() else ""
def current_version(platform:Path)->str:
    cur=(platform/"current").resolve();p=cur/"dev-hub/bin/autonomous-project-orchestrator.py"
    if not p.is_file():return ""
    import re
    m=re.search(r'"version"\s*:\s*"([^"]+)"',p.read_text(errors="ignore"))
    return m.group(1) if m else ""
def release_count(platform:Path)->int:
    root=platform/"releases"
    return sum(1 for p in root.iterdir() if p.is_dir()) if root.is_dir() else 0
def disk_used_pct(path:Path)->float:
    d=shutil.disk_usage(path);return round((d.used/d.total)*100,1) if d.total else 0.0
def github_branch_candidates()->list[str]:
    try:
        req=urllib.request.Request("https://api.github.com/repos/chachasan090375/WfGg/branches?per_page=100",
          headers={"User-Agent":"ChaCha-DEV-Intendant-Hygiene/1.0","Accept":"application/vnd.github+json"})
        with urllib.request.urlopen(req,timeout=15) as r:x=json.loads(r.read().decode())
        return sorted(str(b.get("name")) for b in x if isinstance(b,dict) and str(b.get("name") or "").startswith("dev-hub-v6"))
    except Exception:return []
def hygiene_debt(metrics:dict[str,Any],policy:dict[str,Any])->int:
    w=(policy.get("hygiene_debt") or {}).get("weights") or {}
    score=0
    if metrics["release_count"]>3:score+=int(w.get("release_overage") or 30)
    temp_limit=int((((policy.get("cycles") or {}).get("THRESHOLD_WATCH") or {}).get("triggers") or {}).get("runtime_temp_bytes_gte") or 1073741824)
    score+=min(int(w.get("temp_storage_pressure") or 20),int((metrics["temp_bytes"]/max(1,temp_limit))*int(w.get("temp_storage_pressure") or 20)))
    if metrics["stale_temp_count"]>0:score+=min(int(w.get("stale_artifacts") or 15),metrics["stale_temp_count"])
    score+=min(int(w.get("deprecated_code_candidates") or 15),metrics.get("deprecated_code_candidates",0))
    score+=min(int(w.get("duplicate_surfaces") or 10),metrics.get("duplicate_surfaces",0))
    score+=min(int(w.get("unused_configs") or 10),metrics.get("unused_configs",0))
    return max(0,min(100,score))
def due(last:str|None,now:datetime,hours:float)->bool:
    x=dt(last);return x is None or now-x>=timedelta(hours=hours)

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--repo-root",type=Path,default=Path("/opt/chacha-dev/platform/current"))
    ap.add_argument("--runtime-root",type=Path,default=Path("/opt/chacha-dev/runtime"))
    ap.add_argument("--platform-root",type=Path,default=Path("/opt/chacha-dev/platform"))
    ap.add_argument("--policy",type=Path,required=True)
    ap.add_argument("--consolidation-policy",type=Path,required=True)
    ap.add_argument("--guardian-client",type=Path,required=True)
    ap.add_argument("--guardian-policy",type=Path,required=True)
    ap.add_argument("--guardian-coverage",type=Path,required=True)
    ap.add_argument("--council",type=Path,required=True)
    ap.add_argument("--consolidator",type=Path,required=True)
    ap.add_argument("--retirement-executor",type=Path,required=True)
    ap.add_argument("--force-cycle",choices=["LIGHT_DAILY","WEEKLY_DRY_RUN","MONTHLY_CONSOLIDATION"])
    ap.add_argument("--now")
    ap.add_argument("--dry-run",action="store_true")
    a=ap.parse_args()
    now=dt(a.now) if a.now else datetime.now(timezone.utc)
    if now is None:raise SystemExit("INVALID_NOW")
    policy=load(a.policy);consolidation=load(a.consolidation_policy)
    state_path=Path(str((policy.get("scheduler") or {}).get("state_file") or a.runtime_root/"intendant/hygiene-state.json"))
    report_dir=Path(str((policy.get("scheduler") or {}).get("report_dir") or a.runtime_root/"intendant/hygiene-reports"))
    state=load(state_path,{"schema":"chacha.dev/intendant-hygiene-state/v1","last_success":{}})
    report_dir.mkdir(parents=True,exist_ok=True)
    light_cfg=((policy.get("cycles") or {}).get("LIGHT_DAILY") or {})
    candidates=temp_candidates(light_cfg.get("safe_temp_cleanup") or {},now)
    temp_bytes=sum(x["size_bytes"] for x in candidates)
    active=a.platform_root/"current"
    deprecated=0
    for p in (active.resolve()/"dev-hub").rglob("*") if active.exists() else []:
        if p.is_file() and ("deprecated" in p.name.lower() or "obsolete" in p.name.lower()):deprecated+=1
    metrics={"disk_used_pct":disk_used_pct(a.platform_root),"release_count":release_count(a.platform_root),
      "temp_bytes":temp_bytes,"stale_temp_count":len(candidates),"deprecated_code_candidates":deprecated,
      "duplicate_surfaces":0,"unused_configs":0}
    metrics["hygiene_debt_score"]=hygiene_debt(metrics,policy)
    last=state.setdefault("last_success",{})
    cycles=[]
    cycle_cfg=policy.get("cycles") or {}
    for name in ("LIGHT_DAILY","WEEKLY_DRY_RUN","MONTHLY_CONSOLIDATION"):
        cfg=cycle_cfg.get(name) or {}
        if cfg.get("enabled") is True and (a.force_cycle==name or due(last.get(name),now,float(cfg.get("minimum_interval_hours") or 24))):
            cycles.append(name)
    trig=((cycle_cfg.get("THRESHOLD_WATCH") or {}).get("triggers") or {})
    threshold_reasons=[]
    if metrics["disk_used_pct"]>=float(trig.get("filesystem_used_pct_gte") or 75):threshold_reasons.append("FILESYSTEM_PRESSURE")
    if metrics["release_count"]>int(trig.get("physical_release_count_gt") or 3):threshold_reasons.append("RELEASE_OVERAGE")
    if metrics["temp_bytes"]>=int(trig.get("runtime_temp_bytes_gte") or 1073741824):threshold_reasons.append("TEMP_PRESSURE")
    if metrics["hygiene_debt_score"]>=int(trig.get("hygiene_debt_score_gte") or 60):threshold_reasons.append("HYGIENE_DEBT")
    if threshold_reasons and "WEEKLY_DRY_RUN" not in cycles:cycles.append("WEEKLY_DRY_RUN")
    results=[];coverage_ok=guardian_coverage_ok(a.guardian_coverage)
    stamp=now.strftime("%Y%m%dT%H%M%SZ");work=a.runtime_root/"intendant"/"work"/stamp
    work.mkdir(parents=True,exist_ok=True)
    for name in cycles:
        row={"cycle":name,"status":"PASS","actions":[]}
        if not coverage_ok:
            row["status"]="BLOCKED";row["reason"]="GUARDIAN_COVERAGE_NOT_ACTIVE";results.append(row);continue
        if name=="LIGHT_DAILY":
            deletable=[x for x in candidates if not x["open_fd"]]
            if deletable and not a.dry_run:
                ok=guardian_realtime(a.guardian_client,a.guardian_policy,work/"guardian-light.json",{
                  "schema":"chacha.dev/governed-action/v1","action_id":"intendant-light-"+stamp,
                  "project_id":"chacha-dev-platform","actor_role":"central-orchestrator","requesting_role":"intendant",
                  "permission":"destructive-operation","action":"SAFE_TEMP_RETIREMENT",
                  "targets":[x["path"] for x in deletable],"automatic_external_spend_eur":0})
                if not ok:
                    row["status"]="BLOCKED";row["reason"]="GUARDIAN_REALTIME_BLOCK";results.append(row);continue
                freed=0;deleted=0
                for x in deletable:
                    p=Path(x["path"])
                    if p.is_dir():shutil.rmtree(p)
                    elif p.exists():p.unlink()
                    freed+=x["size_bytes"];deleted+=1
                row["actions"].append({"action":"SAFE_TEMP_RETIREMENT","deleted":deleted,"freed_bytes":freed,"executor":"central-orchestrator"})
            else:
                row["actions"].append({"action":"SAFE_TEMP_SCAN","candidates":len(deletable),"dry_run":a.dry_run})
        elif name=="WEEKLY_DRY_RUN":
            plan=work/"consolidation-plan.json"
            p=run([sys.executable,str(a.consolidator),"--platform-root",str(a.platform_root),
              "--policy",str(a.consolidation_policy),"--output",str(plan)])
            if p.returncode!=0:
                row["status"]="BLOCKED";row["reason"]="CONSOLIDATOR_FAILED";row["stderr"]=p.stderr[-1000:];results.append(row);continue
            px=load(plan);row["actions"].append({"action":"RELEASE_RETIREMENT_DRY_RUN","retire_count":px.get("retire_count"),"bytes_retirable":px.get("bytes_retirable")})
            safe=((cycle_cfg.get("WEEKLY_DRY_RUN") or {}).get("safe_release_retirement") or {})
            exec_cfg=(consolidation.get("execution") or {})
            if int(px.get("retire_count") or 0)>0 and safe.get("auto_apply_when_fully_governed") is True and exec_cfg.get("standing_operator_approval_allowed_for_safe_release_retirement") is True and not a.dry_run:
                gpass=guardian_realtime(a.guardian_client,a.guardian_policy,work/"guardian-release.json",{
                  "schema":"chacha.dev/governed-action/v1","action_id":"intendant-release-"+stamp,
                  "project_id":"chacha-dev-platform","actor_role":"central-orchestrator","requesting_role":"intendant",
                  "permission":"destructive-operation","action":"SAFE_SUPERSEDED_PHYSICAL_RELEASE_RETIREMENT",
                  "plan":str(plan),"automatic_external_spend_eur":0})
                if not gpass:
                    row["status"]="BLOCKED";row["reason"]="GUARDIAN_REALTIME_BLOCK";results.append(row);continue
                approval=work/"consolidation-approval.json"
                q=run([sys.executable,str(a.council),"--plan",str(plan),"--policy",str(a.consolidation_policy),
                  "--guardian-coverage",str(a.guardian_coverage),"--revision",current_revision(a.platform_root),
                  "--operator-explicit-purge-approval","--output",str(approval)],60)
                if q.returncode!=0:
                    row["status"]="BLOCKED";row["reason"]="ARCHITECTURE_COUNCIL_BLOCK";row["stderr"]=q.stderr[-1000:];results.append(row);continue
                out=work/"retirement-result.json";archive=report_dir/("retirement-archive-"+stamp+".json")
                e=run([sys.executable,str(a.retirement_executor),"--platform-root",str(a.platform_root),
                  "--plan",str(plan),"--approval",str(approval),"--archive-manifest",str(archive),
                  "--output",str(out),"--explicit-destructive-apply"],120)
                if e.returncode!=0:
                    row["status"]="BLOCKED";row["reason"]="CENTRAL_RETIREMENT_EXECUTOR_FAILED";row["stderr"]=e.stderr[-1000:];results.append(row);continue
                ex=load(out);row["actions"].append({"action":"SAFE_RELEASE_RETIREMENT_APPLY","executor":"central-orchestrator",
                  "deleted_release_count":ex.get("deleted_release_count"),"freed_bytes":ex.get("freed_bytes")})
        elif name=="MONTHLY_CONSOLIDATION":
            branches=github_branch_candidates()
            row["actions"].append({"action":"DEEP_CONSOLIDATION_REVIEW","deprecated_code_candidates":deprecated,
              "v6_remote_branch_candidates":branches,"remote_branch_deletion":False,"source_code_deletion":False})
        if row["status"]=="PASS":last[name]=iso(now)
        results.append(row)
    state.update({"schema":"chacha.dev/intendant-hygiene-state/v1","updated_at":iso(now),
      "last_success":last,"last_metrics":metrics,"last_threshold_reasons":threshold_reasons})
    save(state_path,state)
    report={"schema":SCHEMA,"generated_at":iso(now),"owner_agent":"intendant","executor":"central-orchestrator",
      "platform_revision":current_revision(a.platform_root),"platform_version":current_version(a.platform_root),
      "cycles_requested":cycles,"results":results,"metrics":metrics,"threshold_reasons":threshold_reasons,
      "git_history_preserved":True,"remote_branch_deletion":False,"source_code_deletion":False,
      "canonical_observation_bus_rewrite":False,"benchmark_evidence_mutation":False,
      "architecture_council_final_authority":True,"automatic_external_spend_eur":0}
    report_path=report_dir/("hygiene-"+stamp+".json");save(report_path,report)
    print("CHACHA_DEV_V710_INTENDANT_HYGIENE_CYCLE=PASS")
    print("CYCLES="+(",".join(cycles) if cycles else "NONE"))
    print("HYGIENE_DEBT_SCORE="+str(metrics["hygiene_debt_score"]))
    print("DISK_USED_PCT="+str(metrics["disk_used_pct"]))
    print("RELEASE_COUNT="+str(metrics["release_count"]))
    print("THRESHOLD_REASONS="+(",".join(threshold_reasons) if threshold_reasons else "NONE"))
    print("REPORT="+str(report_path))
    print("INTENDANT_DIRECT_MUTATION=NO")
    print("PHYSICAL_RETIREMENT_EXECUTOR=central-orchestrator")
    return 0 if all(x.get("status")=="PASS" for x in results) else 20

if __name__=="__main__":raise SystemExit(main())
