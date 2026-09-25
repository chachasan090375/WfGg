#!/usr/bin/env python3
from __future__ import annotations
import argparse,fcntl,hashlib,json,os,subprocess,sys,time
from pathlib import Path
from typing import Any

SCHEMA="chacha.dev/dark-intelligence-analysis-queue-job/v1"
DEFAULT_ROOT=Path("/opt/chacha-dev/runtime/dark-intelligence/analysis-queue")
DEFAULT_RESULTS=Path("/opt/chacha-dev/runtime/dark-intelligence/results")
MAX_ATTEMPTS=12
BASE_BACKOFF=900
MAX_BACKOFF=21600

def load(p:Path)->dict[str,Any]:
    x=json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(x,dict): raise ValueError("JSON_ROOT_NOT_OBJECT")
    return x
def save(p:Path,x:dict[str,Any])->None:
    p.parent.mkdir(parents=True,exist_ok=True);t=p.with_suffix(".tmp")
    t.write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf-8");os.replace(t,p)
def digest_file(p:Path)->str:return hashlib.sha256(p.read_bytes()).hexdigest()
def job_id(capture:Path,subject:str,terms:list[str])->str:
    raw=(digest_file(capture)+"\n"+subject+"\n"+"\n".join(sorted(terms))).encode()
    return "diaq-"+hashlib.sha256(raw).hexdigest()[:24]
def enqueue(root:Path,capture:Path,subject:str,terms:list[str])->dict[str,Any]:
    capture=capture.resolve()
    if not capture.is_file(): raise ValueError("QUEUE_CAPTURE_MISSING")
    jid=job_id(capture,subject,terms);p=root/(jid+".json")
    if p.is_file():
        current=load(p)
        if current.get("status")=="COMPLETE": return current
        current["next_attempt_epoch"]=min(int(current.get("next_attempt_epoch") or int(time.time())),int(time.time()))
        current["updated_epoch"]=int(time.time());save(p,current);return current
    now=int(time.time())
    out={"schema":SCHEMA,"job_id":jid,"status":"PENDING","capture_path":str(capture),
         "capture_sha256":digest_file(capture),"subject":subject,"watch_terms":terms[:50],
         "attempt_count":0,"next_attempt_epoch":now,"created_epoch":now,"updated_epoch":now,
         "last_failure_class":None,"automatic_external_spend_eur":0}
    save(p,out);return out
def backoff(attempt:int)->int:return min(MAX_BACKOFF,BASE_BACKOFF*(2**max(0,attempt-1)))
def due_jobs(root:Path,now:int)->list[tuple[Path,dict[str,Any]]]:
    rows=[]
    for p in sorted(root.glob("diaq-*.json")):
        try:x=load(p)
        except Exception:continue
        if x.get("schema")!=SCHEMA:continue
        if x.get("status") not in {"PENDING","DEFERRED_PROVIDER_UNAVAILABLE","RETRYABLE_FAILURE"}:continue
        if int(x.get("next_attempt_epoch") or 0)<=now:rows.append((p,x))
    return rows
def run_job(repo:Path,results_root:Path,p:Path,job:dict[str,Any])->dict[str,Any]:
    now=int(time.time());attempt=int(job.get("attempt_count") or 0)+1
    capture=Path(str(job["capture_path"]))
    if not capture.is_file() or digest_file(capture)!=job.get("capture_sha256"):
        job.update(status="STALLED",last_failure_class="CAPTURE_MISSING_OR_CHANGED",attempt_count=attempt,updated_epoch=now)
        save(p,job);return job
    outdir=results_root/str(job["job_id"])/("attempt-"+str(attempt))
    outdir.mkdir(parents=True,exist_ok=True);analysis=outdir/"analysis.json"
    cmd=[sys.executable,str(repo/"dev-hub/bin/dark-intelligence-analysis-adapter.py"),
         "--capture",str(capture),"--subject",str(job.get("subject") or ""),"--output",str(analysis),"--timeout","180"]
    for term in job.get("watch_terms") or []:cmd.extend(["--watch-term",str(term)])
    proc=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=220)
    job["attempt_count"]=attempt;job["updated_epoch"]=now
    if proc.returncode!=0 or not analysis.is_file():
        job["status"]="STALLED" if attempt>=MAX_ATTEMPTS else "RETRYABLE_FAILURE"
        job["last_failure_class"]="ANALYSIS_PROCESS_FAILURE"
        job["next_attempt_epoch"]=now+backoff(attempt);save(p,job);return job
    payload=load(analysis);body=payload.get("analysis") if isinstance(payload.get("analysis"),dict) else {}
    if body.get("status")=="DEFERRED_PROVIDER_UNAVAILABLE":
        job["status"]="STALLED" if attempt>=MAX_ATTEMPTS else "DEFERRED_PROVIDER_UNAVAILABLE"
        job["last_failure_class"]="PROVIDER_UNAVAILABLE"
        job["next_attempt_epoch"]=now+backoff(attempt);job["last_analysis_path"]=str(analysis);save(p,job);return job
    pipeline_dir=outdir/"pipeline"
    pcmd=[sys.executable,str(repo/"dev-hub/bin/dark-intelligence-pipeline.py"),
          "--repo-root",str(repo),"--capture",str(capture),"--subject",str(job.get("subject") or ""),
          "--analysis-result",str(analysis),"--output-dir",str(pipeline_dir)]
    pp=subprocess.run(pcmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=120)
    result_path=pipeline_dir/"pipeline-result.json"
    if pp.returncode!=0 or not result_path.is_file():
        job["status"]="STALLED" if attempt>=MAX_ATTEMPTS else "RETRYABLE_FAILURE"
        job["last_failure_class"]="VERIFICATION_PIPELINE_FAILURE";job["next_attempt_epoch"]=now+backoff(attempt);save(p,job);return job
    result=load(result_path)
    if result.get("status")!="PASS":
        job["status"]="STALLED" if attempt>=MAX_ATTEMPTS else "RETRYABLE_FAILURE"
        job["last_failure_class"]="VERIFICATION_NOT_PASS";job["next_attempt_epoch"]=now+backoff(attempt);save(p,job);return job
    job.update(status="COMPLETE",last_failure_class=None,last_analysis_path=str(analysis),
               result_path=str(result_path),completed_epoch=now,next_attempt_epoch=None)
    save(p,job);return job
def run_due(repo:Path,root:Path,results:Path,limit:int)->list[dict[str,Any]]:
    root.mkdir(parents=True,exist_ok=True);results.mkdir(parents=True,exist_ok=True)
    lock=(root/".lock").open("w")
    with lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        rows=[]
        for p,j in due_jobs(root,int(time.time()))[:max(1,limit)]:
            rows.append(run_job(repo,p= p,job=j,results_root=results))
        return rows
def status(root:Path)->dict[str,Any]:
    counts={};next_due=None
    for p in root.glob("diaq-*.json"):
        try:x=load(p)
        except Exception:continue
        s=str(x.get("status") or "UNKNOWN");counts[s]=counts.get(s,0)+1
        if s in {"PENDING","DEFERRED_PROVIDER_UNAVAILABLE","RETRYABLE_FAILURE"}:
            n=int(x.get("next_attempt_epoch") or 0);next_due=n if next_due is None else min(next_due,n)
    return {"schema":"chacha.dev/dark-intelligence-analysis-queue-status/v1","counts":counts,"next_due_epoch":next_due}
def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument("--repo-root",type=Path,default=Path("/opt/chacha-dev/platform/current"))
    ap.add_argument("--queue-root",type=Path,default=DEFAULT_ROOT);ap.add_argument("--results-root",type=Path,default=DEFAULT_RESULTS)
    sub=ap.add_subparsers(dest="cmd",required=True)
    e=sub.add_parser("enqueue");e.add_argument("--capture",type=Path,required=True);e.add_argument("--subject",default="");e.add_argument("--watch-term",action="append",default=[])
    r=sub.add_parser("run-due");r.add_argument("--limit",type=int,default=2)
    sub.add_parser("status");a=ap.parse_args()
    if a.cmd=="enqueue":out=enqueue(a.queue_root,a.capture,a.subject,a.watch_term)
    elif a.cmd=="run-due":out={"schema":"chacha.dev/dark-intelligence-analysis-queue-run/v1","jobs":run_due(a.repo_root.resolve(),a.queue_root,a.results_root,a.limit)}
    else:out=status(a.queue_root)
    print(json.dumps(out,indent=2,ensure_ascii=False));print("CHACHA_DEV_V801_ANALYSIS_QUEUE_"+a.cmd.upper().replace("-","_")+"=PASS")
    return 0
if __name__=="__main__":raise SystemExit(main())
