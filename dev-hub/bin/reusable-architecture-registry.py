#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,sqlite3,time
from pathlib import Path

DEFAULT_DB=Path("/opt/chacha-dev/runtime/knowledge/reusable-architectures.db")

def now_iso(): return time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())
def canon(v): return json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(",",":"))
def digest(v): return hashlib.sha256(canon(v).encode()).hexdigest()

def project_signature(preplan:dict)->str:
    packages=[]
    for p in preplan.get("packages") or []:
        if not isinstance(p,dict): continue
        packages.append({
          "domain":str(p.get("domain") or ""),
          "kind":str(p.get("kind") or ""),
          "capabilities":sorted(set(map(str,p.get("capabilities") or [])))
        })
    packages.sort(key=lambda x:(x["domain"],x["kind"],x["capabilities"]))
    return digest({"packages":packages})

def db_open(path:Path):
    path.parent.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(path)
    db.execute("""CREATE TABLE IF NOT EXISTS reusable_architectures(
      architecture_id TEXT NOT NULL,
      version TEXT NOT NULL,
      functional_signature TEXT NOT NULL,
      state TEXT NOT NULL,
      qualification_status TEXT NOT NULL,
      technology_revalidated_at TEXT,
      technology_snapshot_digest TEXT,
      external_spend_eur REAL NOT NULL DEFAULT 0,
      quality_score REAL NOT NULL DEFAULT 0,
      success_count INTEGER NOT NULL DEFAULT 0,
      failure_count INTEGER NOT NULL DEFAULT 0,
      latency_ms REAL,
      memory_mb REAL,
      incident_count INTEGER NOT NULL DEFAULT 0,
      last_incident_at TEXT,
      last_used_at TEXT,
      payload TEXT NOT NULL,
      PRIMARY KEY(architecture_id,version)
    )""")
    db.execute("CREATE INDEX IF NOT EXISTS idx_arch_sig ON reusable_architectures(functional_signature,qualification_status,state)")
    db.commit()
    return db

def register(args):
    x=json.loads(args.record.read_text(encoding="utf-8"))
    required=("architecture_id","version","functional_signature","components","qualification_status")
    miss=[k for k in required if k not in x]
    if miss: raise SystemExit("REUSABLE_ARCHITECTURE_MISSING="+",".join(miss))
    db=db_open(args.db)
    old=db.execute("SELECT success_count,failure_count,incident_count,last_used_at FROM reusable_architectures WHERE architecture_id=? AND version=?",
                   (str(x["architecture_id"]),str(x["version"]))).fetchone()
    succ=int(x.get("success_count") or 0);fail=int(x.get("failure_count") or 0);inc=int(x.get("incident_count") or 0)
    if old and x.get("increment_existing") is True:
        succ+=int(old[0] or 0);fail+=int(old[1] or 0);inc+=int(old[2] or 0)
    last_used=x.get("last_used_at") or (old[3] if old else None)
    with db:
        db.execute("""INSERT INTO reusable_architectures(
          architecture_id,version,functional_signature,state,qualification_status,
          technology_revalidated_at,technology_snapshot_digest,external_spend_eur,quality_score,
          success_count,failure_count,latency_ms,memory_mb,incident_count,last_incident_at,last_used_at,payload)
          VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
          ON CONFLICT(architecture_id,version) DO UPDATE SET
          functional_signature=excluded.functional_signature,state=excluded.state,
          qualification_status=excluded.qualification_status,
          technology_revalidated_at=excluded.technology_revalidated_at,
          technology_snapshot_digest=excluded.technology_snapshot_digest,
          external_spend_eur=excluded.external_spend_eur,quality_score=excluded.quality_score,
          success_count=excluded.success_count,failure_count=excluded.failure_count,
          latency_ms=excluded.latency_ms,memory_mb=excluded.memory_mb,
          incident_count=excluded.incident_count,last_incident_at=excluded.last_incident_at,
          last_used_at=excluded.last_used_at,payload=excluded.payload""",
          (str(x["architecture_id"]),str(x["version"]),str(x["functional_signature"]),str(x.get("state") or "CATALOG_CANDIDATE"),
           str(x["qualification_status"]),x.get("technology_revalidated_at"),x.get("technology_snapshot_digest"),
           float(x.get("external_spend_eur") or 0),float(x.get("quality_score") or 0),
           succ,fail,None if x.get("latency_ms") is None else float(x["latency_ms"]),
           None if x.get("memory_mb") is None else float(x["memory_mb"]),inc,x.get("last_incident_at"),last_used,canon(x)))
    print(json.dumps({"status":"REGISTERED","architecture_id":x["architecture_id"],"version":x["version"],
                      "functional_signature":x["functional_signature"],"state":x.get("state"),
                      "success_count":succ,"failure_count":fail,"incident_count":inc},indent=2))

def search(args):
    pre=json.loads(args.preplan.read_text(encoding="utf-8"))
    sig=project_signature(pre)
    db=db_open(args.db)
    rows=db.execute("""SELECT payload,technology_revalidated_at,technology_snapshot_digest,external_spend_eur,
                      quality_score,success_count,failure_count,latency_ms,memory_mb,incident_count,
                      last_incident_at,last_used_at,state,qualification_status
                      FROM reusable_architectures
                      WHERE functional_signature=? AND qualification_status='PASS' AND state='ADOPT'
                      ORDER BY external_spend_eur ASC,incident_count ASC,failure_count ASC,
                               quality_score DESC,success_count DESC,
                               COALESCE(latency_ms,1e18) ASC,COALESCE(memory_mb,1e18) ASC,version DESC
                      LIMIT ?""",(sig,max(1,min(args.limit,25)))).fetchall()
    out=[];now=time.time()
    for raw,reval,snap,cost,q,succ,fail,lat,mem,inc,last_inc,last_used,state,qualification in rows:
        x=json.loads(raw);fresh=False
        if reval:
            try:fresh=(now-time.mktime(time.strptime(reval,"%Y-%m-%dT%H:%M:%SZ"))) <= args.max_revalidation_age_minutes*60
            except Exception:fresh=False
        attempts=int(succ or 0)+int(fail or 0)
        success_rate=float(succ or 0)/attempts if attempts else 0.0
        ready=bool(fresh and float(cost or 0)==0 and attempts>0 and success_rate>=args.min_success_rate and int(inc or 0)<=args.max_incidents)
        out.append({
          "architecture_id":x["architecture_id"],"version":x["version"],
          "functional_signature":sig,"components":x["components"],
          "technology_revalidated_at":reval,"technology_snapshot_digest":snap,
          "technology_revalidation_fresh":fresh,"external_spend_eur":cost,"quality_score":q,
          "success_count":succ,"failure_count":fail,"success_rate":round(success_rate,4),
          "latency_ms":lat,"memory_mb":mem,"incident_count":inc,"last_incident_at":last_inc,
          "last_used_at":last_used,"state":state,"qualification_status":qualification,"reuse_ready":ready
        })
    print(json.dumps({"schema":"chacha.dev/reusable-architecture-search/v1","functional_signature":sig,"candidates":out},indent=2,ensure_ascii=False))

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--db",type=Path,default=DEFAULT_DB)
    sub=ap.add_subparsers(dest="cmd",required=True)
    r=sub.add_parser("register");r.add_argument("--record",type=Path,required=True)
    s=sub.add_parser("search");s.add_argument("--preplan",type=Path,required=True);s.add_argument("--limit",type=int,default=5)
    s.add_argument("--max-revalidation-age-minutes",type=int,default=60)
    s.add_argument("--min-success-rate",type=float,default=0.95);s.add_argument("--max-incidents",type=int,default=0)
    a=ap.parse_args()
    if a.cmd=="register": register(a)
    else: search(a)

if __name__=="__main__": main()
