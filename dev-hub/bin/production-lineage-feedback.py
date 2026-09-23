#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,os,sqlite3,subprocess,tempfile,time
from pathlib import Path
from typing import Any

DEFAULT_SOURCE=Path("/opt/chacha-dev/runtime/knowledge/learning-deltas.db")
DEFAULT_DB=Path("/opt/chacha-dev/runtime/knowledge/production-lineage-feedback.db")
DEFAULT_BRANCH_DB=Path("/opt/chacha-dev/runtime/knowledge/reusable-branches.db")
DEFAULT_ARCH_DB=Path("/opt/chacha-dev/runtime/knowledge/reusable-architectures.db")
DEFAULT_POLICY=Path("dev-hub/config/production-lineage-feedback.v1.json")
NAS_ADAPTER=Path(os.environ.get("CHACHA_NAS_ADAPTER","/opt/chacha-dev/adapters/nas-ssh/current/nas-ssh-adapter"))

def now_iso(): return time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())
def canon(v:Any)->str:return json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(",",":"))
def digest(v:Any)->str:return hashlib.sha256(canon(v).encode()).hexdigest()
def load(p:Path)->dict[str,Any]:
    x=json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise RuntimeError("JSON_ROOT_NOT_OBJECT:"+str(p))
    return x

def db_open(path:Path)->sqlite3.Connection:
    path.parent.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(path)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("""CREATE TABLE IF NOT EXISTS processed_feedback(
      delta_id TEXT NOT NULL, component_kind TEXT NOT NULL, component_id TEXT NOT NULL,
      version TEXT NOT NULL, action TEXT NOT NULL, observed_at TEXT,
      status TEXT NOT NULL, detail TEXT NOT NULL,
      PRIMARY KEY(delta_id,component_kind,component_id,version,action)
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS component_reputation(
      component_kind TEXT NOT NULL, component_id TEXT NOT NULL, version TEXT NOT NULL,
      observations INTEGER NOT NULL DEFAULT 0,
      anomaly_count INTEGER NOT NULL DEFAULT 0,
      high_anomaly_count INTEGER NOT NULL DEFAULT 0,
      critical_anomaly_count INTEGER NOT NULL DEFAULT 0,
      verified_recovery_count INTEGER NOT NULL DEFAULT 0,
      state TEXT NOT NULL DEFAULT 'OBSERVED',
      last_seen_at TEXT, last_anomaly_at TEXT,
      PRIMARY KEY(component_kind,component_id,version)
    )""")
    return db

def classify(delta:dict[str,Any])->tuple[str,str|None]:
    anomaly=delta.get("anomaly")
    if not isinstance(anomaly,dict):return "OBSERVE_ONLY",None
    sev=str(anomaly.get("severity") or "").lower()
    if anomaly.get("resolution_verified") is True or str(anomaly.get("status") or "").lower() in {"resolved","verified-resolved"}:
        return "VERIFIED_RECOVERY",sev or None
    if sev in {"high","critical"}:return "INCIDENT",sev
    return "OBSERVE_ONLY",sev or None

def lineage_rows(delta:dict[str,Any])->list[dict[str,Any]]:
    lin=delta.get("lineage")
    if not isinstance(lin,dict) or lin.get("schema")!="chacha.dev/component-lineage/v1":return []
    out=[]
    for row in lin.get("components") or []:
        if not isinstance(row,dict):continue
        kind=str(row.get("kind") or "");cid=str(row.get("component_id") or "");ver=str(row.get("version") or "")
        if kind and cid and ver:out.append({"kind":kind,"component_id":cid,"version":ver,
                                           "contract_id":row.get("contract_id"),"artifact_digest":row.get("artifact_digest")})
    return out

def registry_feedback(kind:str,row:dict[str,Any],action:str,severity:str|None,observed_at:str,delta_id:str,
                      branch_db:Path,arch_db:Path)->dict[str,Any]:
    here=Path(__file__).resolve().parent
    if kind=="branch":
        cmd=["python3",str(here/"reusable-branch-registry.py"),"--db",str(branch_db),"apply-feedback",
             "--event-id",delta_id,"--branch-id",row["component_id"],"--version",row["version"],
             "--action",action,"--observed-at",observed_at]
    elif kind=="architecture":
        cmd=["python3",str(here/"reusable-architecture-registry.py"),"--db",str(arch_db),"apply-feedback",
             "--event-id",delta_id,"--architecture-id",row["component_id"],"--version",row["version"],
             "--action",action,"--observed-at",observed_at]
    else:return {"status":"NOT_APPLICABLE"}
    if severity:cmd+=["--severity",severity]
    p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=30)
    if p.returncode!=0:raise RuntimeError("REUSE_REGISTRY_FEEDBACK_FAILED:"+(p.stderr or p.stdout)[-500:])
    x=json.loads(p.stdout)
    if x.get("status") not in {"APPLIED","DEDUPLICATED","NOT_FOUND"}:
        raise RuntimeError("REUSE_REGISTRY_FEEDBACK_STATUS_INVALID:"+str(x))
    return x

def update_reputation(db:sqlite3.Connection,row:dict[str,Any],action:str,severity:str|None,observed_at:str)->None:
    old=db.execute("""SELECT observations,anomaly_count,high_anomaly_count,critical_anomaly_count,
                     verified_recovery_count,state FROM component_reputation
                     WHERE component_kind=? AND component_id=? AND version=?""",
                   (row["kind"],row["component_id"],row["version"])).fetchone()
    obs=(old[0] if old else 0)+1;an=(old[1] if old else 0);hi=(old[2] if old else 0);cr=(old[3] if old else 0);rec=(old[4] if old else 0)
    state=str(old[5] if old else "OBSERVED");last_anom=None
    if action=="INCIDENT":
        an+=1;last_anom=observed_at
        if severity=="critical":cr+=1;state="QUARANTINED"
        elif severity=="high":hi+=1;state="DEGRADED"
    elif action=="VERIFIED_RECOVERY":
        rec+=1;state="RECOVERY_CANDIDATE"
    db.execute("""INSERT INTO component_reputation(
      component_kind,component_id,version,observations,anomaly_count,high_anomaly_count,critical_anomaly_count,
      verified_recovery_count,state,last_seen_at,last_anomaly_at)
      VALUES(?,?,?,?,?,?,?,?,?,?,?)
      ON CONFLICT(component_kind,component_id,version) DO UPDATE SET
      observations=excluded.observations,anomaly_count=excluded.anomaly_count,
      high_anomaly_count=excluded.high_anomaly_count,critical_anomaly_count=excluded.critical_anomaly_count,
      verified_recovery_count=excluded.verified_recovery_count,state=excluded.state,
      last_seen_at=excluded.last_seen_at,last_anomaly_at=COALESCE(excluded.last_anomaly_at,component_reputation.last_anomaly_at)""",
      (row["kind"],row["component_id"],row["version"],obs,an,hi,cr,rec,state,observed_at,last_anom))

def publish_nas(report:dict[str,Any])->dict[str,Any]:
    if not NAS_ADAPTER.is_file():return {"status":"DEFERRED","reason":"NAS_ADAPTER_MISSING"}
    d=digest(report);day=now_iso()[:10].replace("-","");remote=f"knowledge/production-lineage-feedback/{day}/{d[:24]}.json"
    with tempfile.TemporaryDirectory(prefix="chacha-prod-feedback-") as td:
        td=Path(td);local=td/"report.json";local.write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
        env={"schema":"chacha.dev/dispatch-envelope/v1","project":"chacha-dev","transition":"production-lineage-feedback-persist",
             "run_id":"prod-feedback-"+d[:16],"wave":1,
             "task":{"id":"prod-feedback:"+d[:16],"kind":"knowledge-event","description":"Persist production lineage feedback report.",
                     "owner_role":"knowledge-compiler-agent","permission":"workspace-write",
                     "outputs":[{"type":"artifact","id":remote}],"verification":{"required":True,"mode":"machine"}},
             "bindings":[{"capability":"backup-store","provider":"nas","adapter":"nas-ssh-adapter","fallback_used":False,"health_state":"HEALTHY"}],
             "policy_context":{"resource_class":"light","requires_storage_preflight":False,"human_approval_required":False,"approval_id":None,"timeout_seconds":30},
             "workspace":str(td),"metadata":{"nas_storage":{"action":"put-file","local_path":"report.json","remote_path":remote,"reserve_mb":1024}}}
        p=subprocess.run([str(NAS_ADAPTER)],input=json.dumps(env).encode(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False,timeout=45)
        if p.returncode!=0:return {"status":"DEFERRED","reason":"NAS_PUBLISH_FAILED"}
        try:x=json.loads(p.stdout)
        except Exception:return {"status":"DEFERRED","reason":"NAS_RESPONSE_INVALID"}
        if x.get("status")=="OK" or x.get("summary")=="NAS_DESTINATION_ALREADY_EXISTS":return {"status":"PERSISTED","remote":remote}
        return {"status":"DEFERRED","reason":str(x.get("summary") or x.get("status"))}

def reconcile(args)->dict[str,Any]:
    policy=load(args.policy)
    db=db_open(args.db)
    if not args.source_db.is_file():
        return {"schema":"chacha.dev/production-lineage-feedback-result/v1","status":"PASS","deltas_scanned":0,
                "lineage_components":0,"reuse_updates":0,"missing_lineage":0,"nas":{"status":"NOT_REQUIRED_EMPTY"},
                "automatic_external_spend_eur":0}
    src=sqlite3.connect(args.source_db)
    rows=src.execute("SELECT delta_id,observed_at,payload FROM deltas ORDER BY observed_at,delta_id").fetchall()
    scanned=0;lineage_count=0;reuse_updates=0;missing=0;applied=[];dedup=0
    with db:
      for delta_id,observed_at,raw in rows:
        scanned+=1
        try:delta=json.loads(raw)
        except Exception:continue
        lineage=lineage_rows(delta)
        if not lineage:
            missing+=1;continue
        action,severity=classify(delta)
        for row in lineage:
            lineage_count+=1
            exists=db.execute("""SELECT 1 FROM processed_feedback WHERE delta_id=? AND component_kind=? AND component_id=? AND version=? AND action=?""",
                              (delta_id,row["kind"],row["component_id"],row["version"],action)).fetchone()
            if exists:dedup+=1;continue
            update_reputation(db,row,action,severity,str(observed_at))
            reg={"status":"NOT_APPLICABLE"}
            if action in {"INCIDENT","VERIFIED_RECOVERY"} and row["kind"] in {"branch","architecture"}:
                reg=registry_feedback(row["kind"],row,action,severity,str(observed_at),str(delta_id),args.branch_db,args.architecture_db)
                if reg.get("status")=="APPLIED":reuse_updates+=1
            detail={"lineage":row,"action":action,"severity":severity,"registry":reg,
                    "project_id":delta.get("project_id"),"source_id":delta.get("source_id"),
                    "deployment_id":delta.get("deployment_id")}
            db.execute("""INSERT INTO processed_feedback(delta_id,component_kind,component_id,version,action,observed_at,status,detail)
                          VALUES(?,?,?,?,?,?,?,?)""",
                       (delta_id,row["kind"],row["component_id"],row["version"],action,observed_at,"APPLIED",canon(detail)))
            applied.append({"delta_id":delta_id,**detail})
    report={"schema":"chacha.dev/production-lineage-feedback-report/v1","generated_at":now_iso(),
            "deltas_scanned":scanned,"lineage_components":lineage_count,"reuse_updates":reuse_updates,
            "missing_lineage":missing,"deduplicated":dedup,"applied":applied[-100:],
            "exact_lineage_required_for_reuse_mutation":True,
            "missing_lineage_still_learns_centrally":True,
            "positive_success_inferred_from_absence_of_anomaly":False,
            "verified_recovery_auto_adopt":False,
            "technology_revalidation_required":True,
            "automatic_external_spend_eur":0}
    report["report_digest"]=digest(report)
    nas={"status":"DISABLED"} if not args.nas else publish_nas(report)
    report["nas"]=nas
    if args.nas and nas.get("status")!="PERSISTED":raise RuntimeError("PRODUCTION_LINEAGE_FEEDBACK_NAS_NOT_PERSISTED:"+str(nas))
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    return report

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--policy",type=Path,default=DEFAULT_POLICY)
    ap.add_argument("--source-db",type=Path,default=DEFAULT_SOURCE)
    ap.add_argument("--db",type=Path,default=DEFAULT_DB)
    ap.add_argument("--branch-db",type=Path,default=DEFAULT_BRANCH_DB)
    ap.add_argument("--architecture-db",type=Path,default=DEFAULT_ARCH_DB)
    ap.add_argument("--output",type=Path,default=Path("/opt/chacha-dev/runtime/knowledge/production-lineage-feedback-latest.json"))
    ap.add_argument("--nas",action="store_true")
    a=ap.parse_args();out=reconcile(a)
    print(json.dumps({"schema":"chacha.dev/production-lineage-feedback-result/v1","status":"PASS",
      "deltas_scanned":out["deltas_scanned"],"lineage_components":out["lineage_components"],
      "reuse_updates":out["reuse_updates"],"missing_lineage":out["missing_lineage"],
      "deduplicated":out.get("deduplicated",0),"nas":out["nas"],"automatic_external_spend_eur":0},indent=2))
    print("CHACHA_DEV_V624_PRODUCTION_LINEAGE_FEEDBACK=PASS")
    return 0
if __name__=="__main__":raise SystemExit(main())
