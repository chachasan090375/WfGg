#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,os,re,sqlite3,subprocess,tempfile,time
from collections import defaultdict
from pathlib import Path
from typing import Any

DEFAULT_DELTA_DB=Path("/opt/chacha-dev/runtime/knowledge/learning-deltas.db")
DEFAULT_EXPERIENCE_DB=Path("/opt/chacha-dev/runtime/knowledge/experience.db")
DEFAULT_BRANCH_DB=Path("/opt/chacha-dev/runtime/knowledge/reusable-branches.db")
DEFAULT_ARCH_DB=Path("/opt/chacha-dev/runtime/knowledge/reusable-architectures.db")
DEFAULT_DB=Path("/opt/chacha-dev/runtime/knowledge/central-memory-assimilation.db")
DEFAULT_SNAPSHOT=Path("/opt/chacha-dev/runtime/knowledge/central-memory-assimilation.json")
DEFAULT_POLICY=Path("dev-hub/config/central-memory-assimilation.v1.json")
NAS_ADAPTER=Path(os.environ.get("CHACHA_NAS_ADAPTER","/opt/chacha-dev/adapters/nas-ssh/current/nas-ssh-adapter"))

def now_iso()->str:return time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())
def canon(v:Any)->str:return json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(",",":"))
def digest(v:Any)->str:return hashlib.sha256(canon(v).encode()).hexdigest()
def slug(v:Any)->str:return re.sub(r"[^A-Za-z0-9._-]+","_",str(v)).strip("._")[:120] or "unknown"
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
    db.execute("""CREATE TABLE IF NOT EXISTS knowledge_items(
      item_key TEXT PRIMARY KEY, scope TEXT NOT NULL, project_id TEXT,
      subject_kind TEXT NOT NULL, subject_id TEXT NOT NULL, signal_key TEXT NOT NULL,
      evidence_count INTEGER NOT NULL, positive_count INTEGER NOT NULL,
      negative_count INTEGER NOT NULL, neutral_count INTEGER NOT NULL,
      high_anomaly_count INTEGER NOT NULL, critical_anomaly_count INTEGER NOT NULL,
      distinct_projects INTEGER NOT NULL, confidence REAL NOT NULL,
      state TEXT NOT NULL, generalizable INTEGER NOT NULL,
      latest_observed_at TEXT, evidence_digest TEXT NOT NULL, payload TEXT NOT NULL
    )""")
    db.execute("CREATE INDEX IF NOT EXISTS idx_memory_scope_state ON knowledge_items(scope,state,generalizable)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_memory_subject ON knowledge_items(subject_kind,subject_id,signal_key)")
    return db

def outcome_class(payload:dict[str,Any])->str:
    outcome=str(payload.get("outcome") or "").strip().lower()
    score=payload.get("acceptance_score")
    good={"pass","passed","success","succeeded","accepted","ok","healthy","resolved"}
    bad={"fail","failed","error","rejected","blocked","incident","regression"}
    if outcome in good:return "positive"
    if outcome in bad:return "negative"
    if score is not None:
        try:
            v=float(score)
            if v>1:v=v/100.0
            if v>=0.95:return "positive"
            if v<0.70:return "negative"
        except Exception:pass
    return "neutral"

def state_for(a:dict[str,Any],policy:dict[str,Any])->tuple[str,float]:
    trust=policy["trust"]
    pos=int(a["positive"]);neg=int(a["negative"]);neutral=int(a["neutral"])
    high=int(a["high"]);critical=int(a["critical"]);total=max(1,pos+neg+neutral)
    confidence=round(((pos+1)/(pos+neg+2))*min(1.0,total/max(1,int(trust["minimum_positive_evidence_for_trusted"]))),4)
    if critical>0 and trust.get("critical_anomaly_suspends",True):return "SUSPENDED",0.0
    if pos>=int(trust["contradiction_positive_minimum"]) and neg>=int(trust["contradiction_negative_minimum"]):
        return "CONTRADICTED",confidence
    if high>0 or neg>pos:return "DEGRADED",min(confidence,0.49)
    if pos>=int(trust["minimum_positive_evidence_for_trusted"]) and neg<=int(trust["maximum_negative_evidence_for_trusted"]):
        return "TRUSTED",max(confidence,0.75)
    return "PROVISIONAL",min(confidence,0.74)

def add_ev(bucket:dict[str,dict[str,Any]],*,scope:str,project_id:str|None,subject_kind:str,subject_id:str,
           signal_key:str,observed_at:str,classification:str,anomaly_severity:str|None,evidence_ref:str)->None:
    raw={"scope":scope,"project_id":project_id,"subject_kind":subject_kind,"subject_id":subject_id,"signal_key":signal_key}
    key=digest(raw)
    a=bucket.setdefault(key,{**raw,"positive":0,"negative":0,"neutral":0,"high":0,"critical":0,
                             "projects":set(),"latest":None,"evidence_refs":[]})
    if classification not in {"positive","negative","neutral"}:classification="neutral"
    a[classification]+=1
    sev=str(anomaly_severity or "").lower()
    if sev=="high":a["high"]+=1
    if sev=="critical":a["critical"]+=1
    if project_id:a["projects"].add(str(project_id))
    a["latest"]=max(x for x in [a["latest"],observed_at] if x)
    a["evidence_refs"].append(str(evidence_ref))

def collect(delta_db:Path,experience_db:Path)->dict[str,dict[str,Any]]:
    bucket={}
    if delta_db.is_file():
        db=sqlite3.connect(delta_db)
        try:rows=db.execute("SELECT delta_id,project_id,source_id,source_kind,observed_at,anomaly_severity,payload FROM deltas ORDER BY observed_at").fetchall()
        except sqlite3.Error:rows=[]
        for delta_id,project,source,kind,observed,sev,raw in rows:
            try:x=json.loads(raw)
            except Exception:continue
            anomaly=x.get("anomaly") or {}
            anomaly_class=str(anomaly.get("class") or anomaly.get("signal") or "runtime-health")
            if str(sev or "").lower() in {"high","critical"}:
                add_ev(bucket,scope="PROJECT",project_id=str(project),subject_kind=str(kind),subject_id=str(source),
                       signal_key="anomaly:"+anomaly_class,observed_at=str(observed),classification="negative",
                       anomaly_severity=str(sev),evidence_ref=str(delta_id))
                add_ev(bucket,scope="GLOBAL_CANDIDATE",project_id=None,subject_kind=str(kind),subject_id=str(source),
                       signal_key="anomaly:"+anomaly_class,observed_at=str(observed),classification="negative",
                       anomaly_severity=str(sev),evidence_ref=str(delta_id))
                # Preserve contributing project identity for generalization accounting.
                gkey=digest({"scope":"GLOBAL_CANDIDATE","project_id":None,"subject_kind":str(kind),"subject_id":str(source),"signal_key":"anomaly:"+anomaly_class})
                bucket[gkey]["projects"].add(str(project))
            for ch in x.get("changes") or []:
                if not isinstance(ch,dict):continue
                path=str(ch.get("path") or "/")
                cls="neutral"
                add_ev(bucket,scope="PROJECT",project_id=str(project),subject_kind=str(kind),subject_id=str(source),
                       signal_key="change:"+path,observed_at=str(observed),classification=cls,
                       anomaly_severity=None,evidence_ref=str(delta_id))
                add_ev(bucket,scope="GLOBAL_CANDIDATE",project_id=None,subject_kind=str(kind),subject_id=str(source),
                       signal_key="change:"+path,observed_at=str(observed),classification=cls,
                       anomaly_severity=None,evidence_ref=str(delta_id))
                gkey=digest({"scope":"GLOBAL_CANDIDATE","project_id":None,"subject_kind":str(kind),"subject_id":str(source),"signal_key":"change:"+path})
                bucket[gkey]["projects"].add(str(project))
    if experience_db.is_file():
        db=sqlite3.connect(experience_db)
        try:rows=db.execute("SELECT digest,observed_at,project_id,learner,intent_signature,context_signature,payload FROM experience ORDER BY observed_at").fetchall()
        except sqlite3.Error:rows=[]
        for ev_digest,observed,project,learner,intent,context,raw in rows:
            try:x=json.loads(raw)
            except Exception:x={}
            sig=str(intent or context or "general")
            cls=outcome_class(x)
            for scope,pid in (("PROJECT",str(project)),("GLOBAL_CANDIDATE",None)):
                add_ev(bucket,scope=scope,project_id=pid,subject_kind="experience",subject_id=str(learner),
                       signal_key="intent:"+sig,observed_at=str(observed),classification=cls,
                       anomaly_severity=None,evidence_ref=str(ev_digest))
                if scope=="GLOBAL_CANDIDATE":
                    gkey=digest({"scope":scope,"project_id":None,"subject_kind":"experience","subject_id":str(learner),"signal_key":"intent:"+sig})
                    bucket[gkey]["projects"].add(str(project))
    return bucket

def reuse_catalog(branch_db:Path,arch_db:Path)->dict[str,Any]:
    branches=[];architectures=[]
    if branch_db.is_file():
        db=sqlite3.connect(branch_db)
        try:
            rows=db.execute("""SELECT branch_id,version,domain,functional_signature,state,qualification_status,
                              external_spend_eur,quality_score,success_count,failure_count,incident_count,
                              technology_revalidated_at,last_used_at FROM reusable_branches
                              ORDER BY functional_signature,external_spend_eur,incident_count,failure_count,quality_score DESC,success_count DESC,version DESC""").fetchall()
        except sqlite3.Error:rows=[]
        seen=set()
        for r in rows:
            sig=str(r[3]);status="CURRENT_BEST" if sig not in seen else "SUPERSEDED";seen.add(sig)
            branches.append({"branch_id":r[0],"version":r[1],"domain":r[2],"functional_signature":sig,
              "state":r[4],"qualification_status":r[5],"external_spend_eur":r[6],"quality_score":r[7],
              "success_count":r[8],"failure_count":r[9],"incident_count":r[10],"technology_revalidated_at":r[11],
              "last_used_at":r[12],"version_status":status})
    if arch_db.is_file():
        db=sqlite3.connect(arch_db)
        try:
            rows=db.execute("""SELECT architecture_id,version,functional_signature,state,qualification_status,
                              external_spend_eur,quality_score,success_count,failure_count,incident_count,
                              technology_revalidated_at,last_used_at FROM reusable_architectures
                              ORDER BY functional_signature,external_spend_eur,incident_count,failure_count,quality_score DESC,success_count DESC,version DESC""").fetchall()
        except sqlite3.Error:rows=[]
        seen=set()
        for r in rows:
            sig=str(r[2]);status="CURRENT_BEST" if sig not in seen else "SUPERSEDED";seen.add(sig)
            architectures.append({"architecture_id":r[0],"version":r[1],"functional_signature":sig,
              "state":r[3],"qualification_status":r[4],"external_spend_eur":r[5],"quality_score":r[6],
              "success_count":r[7],"failure_count":r[8],"incident_count":r[9],"technology_revalidated_at":r[10],
              "last_used_at":r[11],"version_status":status})
    return {"branches":branches,"architectures":architectures}

def publish_nas(snapshot:dict[str,Any])->dict[str,Any]:
    if not NAS_ADAPTER.is_file():return {"status":"DEFERRED","reason":"NAS_ADAPTER_MISSING"}
    d=digest(snapshot);day=now_iso()[:10].replace("-","")
    remote=f"knowledge/central-memory/assimilation/{day}/{d[:24]}.json"
    with tempfile.TemporaryDirectory(prefix="chacha-memory-assimilation-") as td:
        td=Path(td);local=td/"snapshot.json";local.write_text(json.dumps(snapshot,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
        env={"schema":"chacha.dev/dispatch-envelope/v1","project":"chacha-dev","transition":"central-memory-assimilation-persist",
             "run_id":"memory-assimilation-"+d[:16],"wave":1,
             "task":{"id":"memory-assimilation:"+d[:16],"kind":"knowledge-event",
                     "description":"Persist central memory assimilation snapshot.","owner_role":"knowledge-compiler-agent",
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
        if r.get("status")=="OK" or r.get("summary")=="NAS_DESTINATION_ALREADY_EXISTS":
            return {"status":"PERSISTED","remote":remote}
        return {"status":"DEFERRED","reason":str(r.get("summary") or r.get("status"))}

def assimilate(args)->dict[str,Any]:
    policy=load(args.policy)
    bucket=collect(args.delta_db,args.experience_db)
    general=policy["generalization"]
    rows=[]
    for key,a in bucket.items():
        state,confidence=state_for(a,policy)
        projects=len(a["projects"])
        generalizable=bool(a["scope"]=="GLOBAL_CANDIDATE" and state=="TRUSTED" and
                           projects>=int(general["minimum_distinct_projects"]) and
                           a["positive"]>=int(general["minimum_positive_evidence"]) and
                           a["negative"]<=int(general["maximum_negative_evidence"]) and
                           a["critical"]==0 and a["high"]==0)
        payload={"schema":"chacha.dev/assimilated-memory-item/v1","item_key":key,"scope":a["scope"],
                 "project_id":a["project_id"],"subject_kind":a["subject_kind"],"subject_id":a["subject_id"],
                 "signal_key":a["signal_key"],"evidence_count":a["positive"]+a["negative"]+a["neutral"],
                 "positive_count":a["positive"],"negative_count":a["negative"],"neutral_count":a["neutral"],
                 "high_anomaly_count":a["high"],"critical_anomaly_count":a["critical"],
                 "distinct_projects":projects,"confidence":confidence,"state":state,"generalizable":generalizable,
                 "latest_observed_at":a["latest"],"evidence_digest":digest(sorted(a["evidence_refs"]))}
        rows.append(payload)
    db=db_open(args.db)
    with db:
        db.execute("DELETE FROM knowledge_items")
        for x in rows:
            db.execute("""INSERT INTO knowledge_items VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
              (x["item_key"],x["scope"],x["project_id"],x["subject_kind"],x["subject_id"],x["signal_key"],
               x["evidence_count"],x["positive_count"],x["negative_count"],x["neutral_count"],
               x["high_anomaly_count"],x["critical_anomaly_count"],x["distinct_projects"],x["confidence"],
               x["state"],1 if x["generalizable"] else 0,x["latest_observed_at"],x["evidence_digest"],canon(x)))
    catalog=reuse_catalog(args.branch_db,args.architecture_db)
    counts=defaultdict(int)
    for x in rows:counts[x["state"]]+=1
    snapshot={"schema":"chacha.dev/central-memory-assimilation/v1","generated_at":now_iso(),
              "policy_version":policy.get("version"),"item_count":len(rows),"state_counts":dict(sorted(counts.items())),
              "trusted_generalizable_count":sum(1 for x in rows if x["generalizable"]),
              "single_observation_never_trusted":True,
              "project_specific_by_default":True,
              "negative_memory_can_quarantine_candidate":True,
              "technology_revalidation_required_before_reuse":True,
              "reuse_catalog":catalog,
              "items":sorted(rows,key=lambda x:(x["scope"],x["project_id"] or "",x["subject_kind"],x["subject_id"],x["signal_key"])),
              "automatic_external_spend_eur":0}
    snapshot["snapshot_digest"]=digest(snapshot)
    nas={"status":"DISABLED"} if not args.nas else publish_nas(snapshot)
    snapshot["nas"]=nas
    atomic(args.snapshot,snapshot)
    if args.nas and nas.get("status")!="PERSISTED":raise RuntimeError("CENTRAL_MEMORY_ASSIMILATION_NAS_NOT_PERSISTED:"+str(nas))
    return snapshot

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--policy",type=Path,default=DEFAULT_POLICY)
    ap.add_argument("--delta-db",type=Path,default=DEFAULT_DELTA_DB)
    ap.add_argument("--experience-db",type=Path,default=DEFAULT_EXPERIENCE_DB)
    ap.add_argument("--branch-db",type=Path,default=DEFAULT_BRANCH_DB)
    ap.add_argument("--architecture-db",type=Path,default=DEFAULT_ARCH_DB)
    ap.add_argument("--db",type=Path,default=DEFAULT_DB)
    ap.add_argument("--snapshot",type=Path,default=DEFAULT_SNAPSHOT)
    ap.add_argument("--nas",action="store_true")
    a=ap.parse_args()
    out=assimilate(a)
    print(json.dumps({"schema":"chacha.dev/central-memory-assimilation-result/v1","status":"PASS",
      "snapshot":str(a.snapshot),"item_count":out["item_count"],"state_counts":out["state_counts"],
      "trusted_generalizable_count":out["trusted_generalizable_count"],"nas":out["nas"],
      "snapshot_digest":out["snapshot_digest"],"automatic_external_spend_eur":0},indent=2,ensure_ascii=False))
    print("CHACHA_DEV_V622_CENTRAL_MEMORY_ASSIMILATION=PASS")
    return 0

if __name__=="__main__":raise SystemExit(main())
