#!/usr/bin/env python3
from __future__ import annotations
import argparse,fcntl,hashlib,json,os,shutil,subprocess,sys,time
from pathlib import Path
from typing import Any

SCHEMA="chacha.dev/dark-intelligence-corroboration-queue-job/v1"
DEFAULT_ROOT=Path("/opt/chacha-dev/runtime/dark-intelligence/corroboration-queue")
DEFAULT_RESULTS=Path("/opt/chacha-dev/runtime/dark-intelligence/corroboration-results")
MAX_ATTEMPTS=12
BASE_BACKOFF=900
MAX_BACKOFF=21600

def load(p:Path)->dict[str,Any]:
    x=json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise ValueError("JSON_ROOT_NOT_OBJECT")
    return x

def save(p:Path,x:dict[str,Any])->None:
    p.parent.mkdir(parents=True,exist_ok=True);t=p.with_suffix(p.suffix+".tmp")
    t.write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf-8");os.replace(t,p)

def digest_file(p:Path)->str:
    return hashlib.sha256(p.read_bytes()).hexdigest()

def job_id(capture:Path,analysis:Path,candidates:Path,subject:str)->str:
    raw="\n".join([digest_file(capture),digest_file(analysis),digest_file(candidates),subject]).encode()
    return "dicq-"+hashlib.sha256(raw).hexdigest()[:24]

def backoff(attempt:int)->int:
    return min(MAX_BACKOFF,BASE_BACKOFF*(2**max(0,attempt-1)))

def enqueue(root:Path,capture:Path,analysis:Path,candidates:Path,subject:str)->dict[str,Any]:
    capture=capture.resolve();analysis=analysis.resolve();candidates=candidates.resolve()
    for p,label in ((capture,"CAPTURE"),(analysis,"ANALYSIS"),(candidates,"CANDIDATES")):
        if not p.is_file():raise ValueError("CORROBORATION_QUEUE_"+label+"_MISSING")
    jid=job_id(capture,analysis,candidates,subject);job_path=root/(jid+".json")
    if job_path.is_file():
        current=load(job_path)
        if current.get("status")=="COMPLETE":return current
        current["next_attempt_epoch"]=min(int(current.get("next_attempt_epoch") or int(time.time())),int(time.time()))
        current["updated_epoch"]=int(time.time());save(job_path,current);return current
    assets=root/"assets"/jid;assets.mkdir(parents=True,exist_ok=True)
    snapshots={}
    for src,name in ((capture,"capture.json"),(analysis,"analysis.json"),(candidates,"candidates.json")):
        dst=assets/name;shutil.copy2(src,dst)
        snapshots[name]={"path":str(dst),"sha256":digest_file(dst),"source_path":str(src)}
    now=int(time.time())
    out={
      "schema":SCHEMA,"job_id":jid,"status":"PENDING","subject":subject,
      "snapshots":snapshots,"attempt_count":0,"next_attempt_epoch":now,
      "created_epoch":now,"updated_epoch":now,"last_failure_class":None,
      "network_recollection_required":False,"automatic_external_spend_eur":0
    }
    save(job_path,out);return out

def due_jobs(root:Path,now:int)->list[tuple[Path,dict[str,Any]]]:
    rows=[]
    for p in sorted(root.glob("dicq-*.json")):
        try:x=load(p)
        except Exception:continue
        if x.get("schema")!=SCHEMA:continue
        if x.get("status") not in {"PENDING","DEFERRED_PROVIDER_UNAVAILABLE","RETRYABLE_FAILURE"}:continue
        if int(x.get("next_attempt_epoch") or 0)<=now:rows.append((p,x))
    return rows

def snapshot(job:dict[str,Any],name:str)->Path:
    row=(job.get("snapshots") or {}).get(name) or {}
    p=Path(str(row.get("path") or ""))
    if not p.is_file() or digest_file(p)!=str(row.get("sha256") or ""):
        raise ValueError("CORROBORATION_QUEUE_SNAPSHOT_MISSING_OR_CHANGED:"+name)
    return p

def run_job(repo:Path,results_root:Path,p:Path,job:dict[str,Any])->dict[str,Any]:
    now=int(time.time());attempt=int(job.get("attempt_count") or 0)+1
    job["attempt_count"]=attempt;job["updated_epoch"]=now
    try:
        capture=snapshot(job,"capture.json");analysis=snapshot(job,"analysis.json");candidates=snapshot(job,"candidates.json")
    except Exception as exc:
        job.update(status="STALLED",last_failure_class=str(exc)[:300],next_attempt_epoch=None);save(p,job);return job
    outdir=results_root/str(job["job_id"])/("attempt-"+str(attempt));outdir.mkdir(parents=True,exist_ok=True)
    evidence=outdir/"evidence.json"
    classifier=repo/"dev-hub/bin/dark-intelligence-corroboration-analysis.py"
    proc=subprocess.run([sys.executable,str(classifier),"--candidates",str(candidates),"--output",str(evidence),"--timeout","180"],
      stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=240)
    if proc.returncode!=0 or not evidence.is_file():
        job["status"]="STALLED" if attempt>=MAX_ATTEMPTS else "RETRYABLE_FAILURE"
        job["last_failure_class"]="CORROBORATION_CLASSIFIER_PROCESS_FAILURE"
        job["next_attempt_epoch"]=None if attempt>=MAX_ATTEMPTS else now+backoff(attempt);save(p,job);return job
    ev=load(evidence)
    if ev.get("status")=="DEFERRED_PROVIDER_UNAVAILABLE":
        job["status"]="STALLED" if attempt>=MAX_ATTEMPTS else "DEFERRED_PROVIDER_UNAVAILABLE"
        job["last_failure_class"]="CORROBORATION_CLASSIFIER_PROVIDER_UNAVAILABLE"
        job["next_attempt_epoch"]=None if attempt>=MAX_ATTEMPTS else now+backoff(attempt)
        job["last_evidence_path"]=str(evidence);save(p,job);return job

    pipeline_dir=outdir/"pipeline"
    cmd=[sys.executable,str(repo/"dev-hub/bin/dark-intelligence-pipeline.py"),
      "--repo-root",str(repo),"--capture",str(capture),"--subject",str(job.get("subject") or ""),
      "--analysis-result",str(analysis),"--corroboration-evidence",str(evidence),
      "--no-auto-corroboration","--output-dir",str(pipeline_dir)]
    pp=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=180)
    result_path=pipeline_dir/"pipeline-result.json"
    if pp.returncode!=0 or not result_path.is_file():
        job["status"]="STALLED" if attempt>=MAX_ATTEMPTS else "RETRYABLE_FAILURE"
        job["last_failure_class"]="CORROBORATION_VERIFICATION_PIPELINE_FAILURE"
        job["next_attempt_epoch"]=None if attempt>=MAX_ATTEMPTS else now+backoff(attempt);save(p,job);return job
    result=load(result_path)
    if result.get("status")!="PASS":
        job["status"]="STALLED" if attempt>=MAX_ATTEMPTS else "RETRYABLE_FAILURE"
        job["last_failure_class"]="CORROBORATION_VERIFICATION_NOT_PASS"
        job["next_attempt_epoch"]=None if attempt>=MAX_ATTEMPTS else now+backoff(attempt);save(p,job);return job
    job.update(status="COMPLETE",last_failure_class=None,last_evidence_path=str(evidence),
      result_path=str(result_path),completed_epoch=now,next_attempt_epoch=None,
      network_recollection_performed=False)
    save(p,job);return job

def run_due(repo:Path,root:Path,results:Path,limit:int)->list[dict[str,Any]]:
    root.mkdir(parents=True,exist_ok=True);results.mkdir(parents=True,exist_ok=True)
    with (root/".lock").open("w") as lock:
        fcntl.flock(lock,fcntl.LOCK_EX);rows=[]
        for p,j in due_jobs(root,int(time.time()))[:max(1,limit)]:
            rows.append(run_job(repo,results,p,j))
        return rows

def status(root:Path)->dict[str,Any]:
    counts={};next_due=None
    for p in root.glob("dicq-*.json"):
        try:x=load(p)
        except Exception:continue
        s=str(x.get("status") or "UNKNOWN");counts[s]=counts.get(s,0)+1
        if s in {"PENDING","DEFERRED_PROVIDER_UNAVAILABLE","RETRYABLE_FAILURE"}:
            n=int(x.get("next_attempt_epoch") or 0);next_due=n if next_due is None else min(next_due,n)
    return {"schema":"chacha.dev/dark-intelligence-corroboration-queue-status/v1",
      "counts":counts,"next_due_epoch":next_due,"network_recollection_on_retry":False}

def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument("--repo-root",type=Path,default=Path("/opt/chacha-dev/platform/current"))
    ap.add_argument("--queue-root",type=Path,default=DEFAULT_ROOT);ap.add_argument("--results-root",type=Path,default=DEFAULT_RESULTS)
    sub=ap.add_subparsers(dest="cmd",required=True)
    e=sub.add_parser("enqueue");e.add_argument("--capture",type=Path,required=True);e.add_argument("--analysis",type=Path,required=True)
    e.add_argument("--candidates",type=Path,required=True);e.add_argument("--subject",default="")
    r=sub.add_parser("run-due");r.add_argument("--limit",type=int,default=2);sub.add_parser("status")
    a=ap.parse_args()
    if a.cmd=="enqueue":out=enqueue(a.queue_root,a.capture,a.analysis,a.candidates,a.subject)
    elif a.cmd=="run-due":out={"schema":"chacha.dev/dark-intelligence-corroboration-queue-run/v1",
      "jobs":run_due(a.repo_root.resolve(),a.queue_root,a.results_root,a.limit)}
    else:out=status(a.queue_root)
    print(json.dumps(out,indent=2,ensure_ascii=False))
    print("CHACHA_DEV_V801_CORROBORATION_QUEUE_"+a.cmd.upper().replace("-","_")+"=PASS")
    return 0

if __name__=="__main__":raise SystemExit(main())
