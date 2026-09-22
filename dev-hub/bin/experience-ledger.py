#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,os,sqlite3,subprocess,time
from pathlib import Path

DB_DEFAULT=Path("/opt/chacha-dev/runtime/knowledge/experience.db")
NAS_ADAPTER=Path("/opt/chacha-dev/adapters/nas-ssh/current/nas-ssh-adapter")

def now_iso(): return time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())
def canon(x): return json.dumps(x,sort_keys=True,ensure_ascii=False,separators=(",",":"))
def digest(x): return hashlib.sha256(canon(x).encode()).hexdigest()

def db_open(path):
    path.parent.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(path)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("""CREATE TABLE IF NOT EXISTS experience(
      digest TEXT PRIMARY KEY, observed_at TEXT NOT NULL, project_id TEXT NOT NULL,
      learner TEXT NOT NULL, intent_signature TEXT, context_signature TEXT,
      outcome TEXT, acceptance_score REAL, external_spend_eur REAL,
      latency_ms REAL, memory_mb REAL, payload TEXT NOT NULL
    )""")
    db.execute("CREATE INDEX IF NOT EXISTS idx_exp_project ON experience(project_id,observed_at)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_exp_learner ON experience(learner,observed_at)")
    return db

def publish_nas(event,event_digest,workspace):
    if not NAS_ADAPTER.is_file():
        return {"status":"DEFERRED","reason":"NAS_ADAPTER_MISSING"}
    local=workspace/f"{event_digest}.json"
    local.write_text(json.dumps(event,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    day=str(event["observed_at"])[:10].replace("-","")
    remote=f"knowledge/experience/events/{day}/{event_digest}.json"
    envelope={
      "schema":"chacha.dev/dispatch-envelope/v1",
      "project":str(event["project_id"]),
      "transition":"experience-ledger-persist",
      "run_id":"experience-"+event_digest[:16],
      "wave":1,
      "task":{"id":"experience:"+event_digest[:16],"kind":"knowledge-event",
              "description":"Persist immutable cross-project experience event.",
              "owner_role":"knowledge-compiler-agent","permission":"workspace-write",
              "outputs":[{"type":"artifact","id":remote}],
              "verification":{"required":True,"mode":"machine"}},
      "bindings":[{"capability":"backup-store","provider":"nas","adapter":"nas-ssh-adapter",
                   "fallback_used":False,"health_state":"HEALTHY"}],
      "policy_context":{"resource_class":"light","requires_storage_preflight":False,
                        "human_approval_required":False,"approval_id":None,"timeout_seconds":30},
      "workspace":str(workspace),
      "metadata":{"nas_storage":{"action":"put-file","local_path":local.name,
                                 "remote_path":remote,"reserve_mb":1024}}
    }
    p=subprocess.run([str(NAS_ADAPTER)],input=json.dumps(envelope).encode(),
                     stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False,timeout=45)
    if p.returncode!=0:
        return {"status":"DEFERRED","reason":"NAS_PUBLISH_FAILED","stderr":p.stderr.decode("utf-8","replace")[-300:]}
    try:r=json.loads(p.stdout.decode())
    except Exception:return {"status":"DEFERRED","reason":"NAS_RESPONSE_INVALID"}
    if r.get("status")=="OK":return {"status":"PERSISTED","remote":remote}
    if r.get("summary")=="NAS_DESTINATION_ALREADY_EXISTS":return {"status":"PERSISTED","remote":remote,"deduplicated":True}
    return {"status":"DEFERRED","reason":str(r.get("summary") or r.get("status"))}

def record(args):
    payload=json.loads(Path(args.event).read_text(encoding="utf-8"))
    payload.setdefault("schema","chacha.dev/experience-event/v1")
    payload.setdefault("observed_at",now_iso())
    for field in ("project_id","learner"):
        if not payload.get(field):raise SystemExit("EXPERIENCE_"+field.upper()+"_MISSING")
    d=digest(payload)
    db=db_open(args.db)
    with db:
        db.execute("""INSERT OR IGNORE INTO experience
          (digest,observed_at,project_id,learner,intent_signature,context_signature,outcome,
           acceptance_score,external_spend_eur,latency_ms,memory_mb,payload)
          VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
          (d,payload["observed_at"],payload["project_id"],payload["learner"],
           payload.get("intent_signature"),payload.get("context_signature"),payload.get("outcome"),
           payload.get("acceptance_score"),payload.get("external_spend_eur"),
           payload.get("latency_ms"),payload.get("memory_mb"),canon(payload)))
    result={"digest":d,"hot_index":"RECORDED"}
    if args.nas:
        import tempfile
        with tempfile.TemporaryDirectory(prefix="chacha-exp-") as td:
            result["nas"]=publish_nas(payload,d,Path(td))
    print(json.dumps(result,indent=2,ensure_ascii=False))

def search(args):
    db=db_open(args.db)
    q=(args.query or "").lower()
    rows=db.execute("SELECT payload FROM experience ORDER BY observed_at DESC LIMIT ?",(max(1,min(args.limit*20,1000)),)).fetchall()
    scored=[]
    words={x for x in q.replace("-"," ").split() if len(x)>2}
    for (raw,) in rows:
        p=json.loads(raw);text=canon(p).lower()
        score=sum(1 for w in words if w in text)
        if score or not words:scored.append((score,p))
    scored.sort(key=lambda x:x[0],reverse=True)
    print(json.dumps({"results":[p for _,p in scored[:args.limit]]},indent=2,ensure_ascii=False))

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--db",type=Path,default=DB_DEFAULT)
    sub=ap.add_subparsers(dest="cmd",required=True)
    r=sub.add_parser("record");r.add_argument("--event",required=True,type=Path);r.add_argument("--nas",action="store_true")
    s=sub.add_parser("search");s.add_argument("--query",default="");s.add_argument("--limit",type=int,default=10)
    a=ap.parse_args()
    if a.cmd=="record":record(a)
    else:search(a)

if __name__=="__main__":main()
