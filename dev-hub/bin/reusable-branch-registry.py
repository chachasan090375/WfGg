#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,sqlite3,time
from pathlib import Path
from typing import Any

DEFAULT_DB=Path("/opt/chacha-dev/runtime/knowledge/reusable-branches.db")

def now_iso(): return time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())
def canon(v): return json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(",",":"))
def digest(v): return hashlib.sha256(canon(v).encode()).hexdigest()

def db_open(path:Path):
    path.parent.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(path)
    db.execute("""CREATE TABLE IF NOT EXISTS reusable_branches(
      branch_id TEXT NOT NULL,
      version TEXT NOT NULL,
      domain TEXT NOT NULL,
      functional_signature TEXT NOT NULL,
      architecture_digest TEXT NOT NULL,
      state TEXT NOT NULL,
      qualification_status TEXT NOT NULL,
      technology_revalidated_at TEXT,
      technology_snapshot_digest TEXT,
      external_spend_eur REAL NOT NULL DEFAULT 0,
      quality_score REAL NOT NULL DEFAULT 0,
      success_count INTEGER NOT NULL DEFAULT 0,
      failure_count INTEGER NOT NULL DEFAULT 0,
      last_used_at TEXT,
      payload TEXT NOT NULL,
      PRIMARY KEY(branch_id,version)
    )""")
    db.execute("CREATE INDEX IF NOT EXISTS idx_reuse_signature ON reusable_branches(functional_signature,qualification_status,state)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_reuse_domain ON reusable_branches(domain,qualification_status,state)")
    return db

def signature(domain:str,capabilities:list[str])->str:
    return digest({"domain":str(domain),"capabilities":sorted(set(map(str,capabilities or [])))})

def register(args):
    x=json.loads(args.record.read_text(encoding="utf-8"))
    required=("branch_id","version","domain","capabilities","architecture","qualification_status")
    missing=[k for k in required if k not in x]
    if missing: raise SystemExit("REUSABLE_BRANCH_MISSING="+",".join(missing))
    sig=signature(x["domain"],x.get("capabilities") or [])
    arch_digest=digest(x["architecture"])
    state=str(x.get("state") or "ADOPT")
    db=db_open(args.db)
    with db:
        db.execute("""INSERT INTO reusable_branches
          (branch_id,version,domain,functional_signature,architecture_digest,state,qualification_status,
           technology_revalidated_at,technology_snapshot_digest,external_spend_eur,quality_score,
           success_count,failure_count,last_used_at,payload)
          VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
          ON CONFLICT(branch_id,version) DO UPDATE SET
           domain=excluded.domain,functional_signature=excluded.functional_signature,
           architecture_digest=excluded.architecture_digest,state=excluded.state,
           qualification_status=excluded.qualification_status,
           technology_revalidated_at=excluded.technology_revalidated_at,
           technology_snapshot_digest=excluded.technology_snapshot_digest,
           external_spend_eur=excluded.external_spend_eur,quality_score=excluded.quality_score,
           success_count=excluded.success_count,failure_count=excluded.failure_count,
           last_used_at=excluded.last_used_at,payload=excluded.payload""",
          (str(x["branch_id"]),str(x["version"]),str(x["domain"]),sig,arch_digest,state,
           str(x["qualification_status"]),x.get("technology_revalidated_at"),x.get("technology_snapshot_digest"),
           float(x.get("external_spend_eur") or 0),float(x.get("quality_score") or 0),
           int(x.get("success_count") or 0),int(x.get("failure_count") or 0),
           x.get("last_used_at"),canon(x)))
    print(json.dumps({"status":"REGISTERED","branch_id":x["branch_id"],"version":x["version"],"functional_signature":sig},indent=2))

def search(args):
    sig=signature(args.domain,args.capability)
    db=db_open(args.db)
    rows=db.execute("""SELECT payload,technology_revalidated_at,technology_snapshot_digest,
                      external_spend_eur,quality_score,success_count,failure_count,last_used_at
                      FROM reusable_branches
                      WHERE functional_signature=? AND qualification_status='PASS' AND state='ADOPT'
                      ORDER BY external_spend_eur ASC, quality_score DESC, success_count DESC, version DESC
                      LIMIT ?""",(sig,max(1,min(args.limit,50)))).fetchall()
    out=[]
    now=time.time()
    for raw,reval,snap,cost,q,succ,fail,last_used in rows:
        x=json.loads(raw)
        fresh=False
        if reval:
            try:fresh=(now-time.mktime(time.strptime(reval,"%Y-%m-%dT%H:%M:%SZ"))) <= args.max_revalidation_age_minutes*60
            except Exception:fresh=False
        out.append({
          "branch_id":x["branch_id"],"version":x["version"],"domain":x["domain"],
          "architecture":x["architecture"],"capabilities":x.get("capabilities") or [],
          "technology_revalidated_at":reval,"technology_snapshot_digest":snap,
          "technology_revalidation_fresh":fresh,
          "external_spend_eur":cost,"quality_score":q,
          "success_count":succ,"failure_count":fail,"last_used_at":last_used,
          "reuse_ready":fresh and cost==0
        })
    print(json.dumps({"schema":"chacha.dev/reusable-branch-search/v1","functional_signature":sig,"candidates":out},indent=2,ensure_ascii=False))

def mark_used(args):
    db=db_open(args.db)
    with db:
        db.execute("UPDATE reusable_branches SET last_used_at=?,success_count=success_count+1 WHERE branch_id=? AND version=?",
                   (now_iso(),args.branch_id,args.version))
    print("CHACHA_DEV_REUSABLE_BRANCH_MARK_USED=PASS")

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--db",type=Path,default=DEFAULT_DB)
    sub=ap.add_subparsers(dest="cmd",required=True)
    r=sub.add_parser("register");r.add_argument("--record",type=Path,required=True)
    s=sub.add_parser("search");s.add_argument("--domain",required=True);s.add_argument("--capability",action="append",default=[]);s.add_argument("--limit",type=int,default=10);s.add_argument("--max-revalidation-age-minutes",type=int,default=60)
    m=sub.add_parser("mark-used");m.add_argument("--branch-id",required=True);m.add_argument("--version",required=True)
    a=ap.parse_args()
    if a.cmd=="register":register(a)
    elif a.cmd=="search":search(a)
    else:mark_used(a)
if __name__=="__main__":main()
