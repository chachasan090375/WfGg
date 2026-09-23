#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,os,sqlite3,subprocess,tempfile,time
from pathlib import Path
from typing import Any

DEFAULT_FEEDBACK=Path("/opt/chacha-dev/runtime/knowledge/production-lineage-feedback.db")
DEFAULT_BRANCH=Path("/opt/chacha-dev/runtime/knowledge/reusable-branches.db")
DEFAULT_ARCH=Path("/opt/chacha-dev/runtime/knowledge/reusable-architectures.db")
DEFAULT_DB=Path("/opt/chacha-dev/runtime/knowledge/component-confidence.db")
DEFAULT_SNAPSHOT=Path("/opt/chacha-dev/runtime/knowledge/component-confidence.json")
DEFAULT_POLICY=Path("dev-hub/config/component-confidence.v1.json")
NAS_ADAPTER=Path(os.environ.get("CHACHA_NAS_ADAPTER","/opt/chacha-dev/adapters/nas-ssh/current/nas-ssh-adapter"))

def now_iso()->str:return time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())
def canon(v:Any)->str:return json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(",",":"))
def digest(v:Any)->str:return hashlib.sha256(canon(v).encode()).hexdigest()
def load(path:Path)->dict[str,Any]:
    x=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise RuntimeError("JSON_ROOT_NOT_OBJECT:"+str(path))
    return x
def atomic(path:Path,obj:dict[str,Any])->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name(path.name+f".tmp-{os.getpid()}")
    tmp.write_text(json.dumps(obj,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    os.replace(tmp,path)
def db_open(path:Path)->sqlite3.Connection:
    path.parent.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(path)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("""CREATE TABLE IF NOT EXISTS component_confidence(
      component_kind TEXT NOT NULL,component_id TEXT NOT NULL,version TEXT NOT NULL,
      confidence REAL NOT NULL,state TEXT NOT NULL,verified_success_count INTEGER NOT NULL,
      verified_failure_count INTEGER NOT NULL,incident_count INTEGER NOT NULL,
      high_anomaly_count INTEGER NOT NULL,critical_anomaly_count INTEGER NOT NULL,
      verified_recovery_count INTEGER NOT NULL,evidence_count INTEGER NOT NULL,
      evidence_source TEXT NOT NULL,reuse_advisory_eligible INTEGER NOT NULL,
      updated_at TEXT NOT NULL,payload TEXT NOT NULL,
      PRIMARY KEY(component_kind,component_id,version)
    )""")
    db.execute("CREATE INDEX IF NOT EXISTS idx_component_confidence_state ON component_confidence(state,confidence)")
    return db

def confidence_state(*,success:int,failure:int,incidents:int,high:int,critical:int,recovery:int,
                     current_state:str|None,policy:dict[str,Any])->tuple[str,float,bool]:
    t=policy["trust"]
    weighted_negative=failure + high*int(t["high_anomaly_weight"]) + critical*int(t["critical_anomaly_weight"])
    alpha=float(t["prior_positive"])+success
    beta=float(t["prior_negative"])+weighted_negative
    posterior=alpha/max(alpha+beta,1.0)
    explicit_evidence=success+failure+incidents+recovery
    needed=max(1,int(t["minimum_verified_successes_for_trusted"]))
    maturity=min(1.0,explicit_evidence/needed)
    score=round(max(0.0,min(1.0,posterior*(0.5+0.5*maturity))),4)
    cs=str(current_state or "")
    if cs=="QUARANTINED" or critical>0:state="QUARANTINED"
    elif cs=="DEGRADED" or high>0 or failure>0:state="DEGRADED"
    elif cs=="RECOVERY_CANDIDATE":state="RECOVERY_CANDIDATE"
    elif success>=int(t["minimum_verified_successes_for_trusted"]) and failure<=int(t["maximum_verified_failures_for_trusted"]) and incidents<=int(t["maximum_incidents_for_trusted"]):
        state="TRUSTED"
    elif success>0:state="PROVISIONAL"
    else:state="OBSERVED"
    excluded=set(policy["reuse"]["exclude_states_from_fast_reuse"])
    eligible=state not in excluded
    return state,score,eligible

def collect_feedback(path:Path)->dict[tuple[str,str,str],dict[str,Any]]:
    out={}
    if not path.is_file():return out
    db=sqlite3.connect(path)
    cols={r[1] for r in db.execute("PRAGMA table_info(component_reputation)").fetchall()}
    if not {"component_kind","component_id","version"}.issubset(cols):return out
    suc="verified_success_count" if "verified_success_count" in cols else "0"
    fail="verified_failure_count" if "verified_failure_count" in cols else "0"
    q=f"""SELECT component_kind,component_id,version,observations,{suc},{fail},
                 anomaly_count,high_anomaly_count,critical_anomaly_count,verified_recovery_count,state,last_seen_at
          FROM component_reputation"""
    for r in db.execute(q).fetchall():
        out[(str(r[0]),str(r[1]),str(r[2]))]={
          "kind":str(r[0]),"component_id":str(r[1]),"version":str(r[2]),"observations":int(r[3] or 0),
          "success":int(r[4] or 0),"failure":int(r[5] or 0),"incidents":int(r[6] or 0),
          "high":int(r[7] or 0),"critical":int(r[8] or 0),"recovery":int(r[9] or 0),
          "current_state":str(r[10] or "OBSERVED"),"last_seen_at":r[11],
          "evidence_source":"LINEAGE_REPUTATION"
        }
    return out

def add_legacy_registry(out:dict[tuple[str,str,str],dict[str,Any]],path:Path,kind:str)->None:
    if not path.is_file():return
    db=sqlite3.connect(path)
    if kind=="branch":
        q="""SELECT branch_id,version,state,success_count,failure_count,incident_count,last_used_at
             FROM reusable_branches"""
    else:
        q="""SELECT architecture_id,version,state,success_count,failure_count,incident_count,last_used_at
             FROM reusable_architectures"""
    try:rows=db.execute(q).fetchall()
    except sqlite3.Error:return
    for r in rows:
        key=(kind,str(r[0]),str(r[1]))
        if key in out:continue
        out[key]={"kind":kind,"component_id":str(r[0]),"version":str(r[1]),
                  "observations":int(r[3] or 0)+int(r[4] or 0)+int(r[5] or 0),
                  "success":int(r[3] or 0),"failure":int(r[4] or 0),"incidents":int(r[5] or 0),
                  "high":0,"critical":0,"recovery":0,"current_state":str(r[2] or "OBSERVED"),
                  "last_seen_at":r[6],"evidence_source":"REUSE_REGISTRY_BOOTSTRAP"}

def publish_nas(snapshot:dict[str,Any])->dict[str,Any]:
    if not NAS_ADAPTER.is_file():return {"status":"DEFERRED","reason":"NAS_ADAPTER_MISSING"}
    d=digest(snapshot);day=now_iso()[:10].replace("-","");remote=f"knowledge/component-confidence/{day}/{d[:24]}.json"
    with tempfile.TemporaryDirectory(prefix="chacha-component-confidence-") as td:
        td=Path(td);local=td/"snapshot.json";local.write_text(json.dumps(snapshot,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
        env={"schema":"chacha.dev/dispatch-envelope/v1","project":"chacha-dev","transition":"component-confidence-persist",
             "run_id":"component-confidence-"+d[:16],"wave":1,
             "task":{"id":"component-confidence:"+d[:16],"kind":"knowledge-event",
                     "description":"Persist component confidence snapshot.","owner_role":"knowledge-compiler-agent",
                     "permission":"workspace-write","outputs":[{"type":"artifact","id":remote}],
                     "verification":{"required":True,"mode":"machine"}},
             "bindings":[{"capability":"backup-store","provider":"nas","adapter":"nas-ssh-adapter","fallback_used":False,"health_state":"HEALTHY"}],
             "policy_context":{"resource_class":"light","requires_storage_preflight":False,"human_approval_required":False,
                               "approval_id":None,"timeout_seconds":30},
             "workspace":str(td),"metadata":{"nas_storage":{"action":"put-file","local_path":"snapshot.json","remote_path":remote,"reserve_mb":1024}}}
        p=subprocess.run([str(NAS_ADAPTER)],input=json.dumps(env).encode(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False,timeout=45)
        if p.returncode!=0:return {"status":"DEFERRED","reason":"NAS_PUBLISH_FAILED"}
        try:r=json.loads(p.stdout)
        except Exception:return {"status":"DEFERRED","reason":"NAS_RESPONSE_INVALID"}
        if r.get("status")=="OK" or r.get("summary")=="NAS_DESTINATION_ALREADY_EXISTS":return {"status":"PERSISTED","remote":remote}
        return {"status":"DEFERRED","reason":str(r.get("summary") or r.get("status"))}

def build(args)->dict[str,Any]:
    policy=load(args.policy)
    raw=collect_feedback(args.feedback_db)
    add_legacy_registry(raw,args.branch_db,"branch")
    add_legacy_registry(raw,args.architecture_db,"architecture")
    rows=[]
    for key in sorted(raw):
        x=raw[key]
        state,score,eligible=confidence_state(success=x["success"],failure=x["failure"],incidents=x["incidents"],
          high=x["high"],critical=x["critical"],recovery=x["recovery"],current_state=x["current_state"],policy=policy)
        rows.append({
          "schema":"chacha.dev/component-confidence-item/v1",
          "component_kind":x["kind"],"component_id":x["component_id"],"version":x["version"],
          "confidence":score,"state":state,
          "verified_success_count":x["success"],"verified_failure_count":x["failure"],
          "incident_count":x["incidents"],"high_anomaly_count":x["high"],"critical_anomaly_count":x["critical"],
          "verified_recovery_count":x["recovery"],"evidence_count":x["success"]+x["failure"]+x["incidents"]+x["recovery"],
          "observation_count":x["observations"],"evidence_source":x["evidence_source"],
          "reuse_advisory_eligible":eligible,"last_seen_at":x["last_seen_at"],
          "confidence_is_advisory":True,"technology_revalidation_required":True
        })
    counts={}
    for x in rows:counts[x["state"]]=counts.get(x["state"],0)+1
    snap={"schema":"chacha.dev/component-confidence-snapshot/v1","generated_at":now_iso(),
          "policy_version":policy.get("version"),"component_count":len(rows),"state_counts":dict(sorted(counts.items())),
          "trusted_count":sum(1 for x in rows if x["state"]=="TRUSTED"),
          "negative_state_count":sum(1 for x in rows if x["state"] in {"DEGRADED","QUARANTINED","RECOVERY_CANDIDATE"}),
          "items":rows,"confidence_is_advisory_not_final_authority":True,
          "absence_of_anomaly_is_not_success":True,"technology_revalidation_required":True,
          "architecture_council_final_authority":True,"automatic_external_spend_eur":0}
    snap["snapshot_digest"]=digest(snap)
    db=db_open(args.db)
    with db:
        db.execute("DELETE FROM component_confidence")
        for x in rows:
            db.execute("""INSERT INTO component_confidence VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
              (x["component_kind"],x["component_id"],x["version"],x["confidence"],x["state"],
               x["verified_success_count"],x["verified_failure_count"],x["incident_count"],
               x["high_anomaly_count"],x["critical_anomaly_count"],x["verified_recovery_count"],
               x["evidence_count"],x["evidence_source"],1 if x["reuse_advisory_eligible"] else 0,
               snap["generated_at"],canon(x)))
    nas={"status":"DISABLED"} if not args.nas else publish_nas(snap)
    snap["nas"]=nas
    atomic(args.snapshot,snap)
    if args.nas and nas.get("status")!="PERSISTED":raise RuntimeError("COMPONENT_CONFIDENCE_NAS_NOT_PERSISTED:"+str(nas))
    return snap

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--policy",type=Path,default=DEFAULT_POLICY)
    ap.add_argument("--feedback-db",type=Path,default=DEFAULT_FEEDBACK)
    ap.add_argument("--branch-db",type=Path,default=DEFAULT_BRANCH)
    ap.add_argument("--architecture-db",type=Path,default=DEFAULT_ARCH)
    ap.add_argument("--db",type=Path,default=DEFAULT_DB)
    ap.add_argument("--snapshot",type=Path,default=DEFAULT_SNAPSHOT)
    ap.add_argument("--nas",action="store_true")
    a=ap.parse_args();out=build(a)
    print(json.dumps({"schema":"chacha.dev/component-confidence-result/v1","status":"PASS",
      "component_count":out["component_count"],"trusted_count":out["trusted_count"],
      "negative_state_count":out["negative_state_count"],"state_counts":out["state_counts"],
      "nas":out["nas"],"snapshot_digest":out["snapshot_digest"],"automatic_external_spend_eur":0},indent=2))
    print("CHACHA_DEV_V625_COMPONENT_CONFIDENCE=PASS")
    return 0

if __name__=="__main__":raise SystemExit(main())
