#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,os,re,sqlite3,subprocess,tempfile,time
from pathlib import Path

DB_DEFAULT=Path("/opt/chacha-dev/runtime/knowledge/learning-deltas.db")
NAS_ADAPTER=Path(os.environ.get("CHACHA_NAS_ADAPTER","/opt/chacha-dev/adapters/nas-ssh/current/nas-ssh-adapter"))
SAFE=re.compile(r"^[A-Za-z0-9._:-]{1,160}$")
KINDS={"core-orchestrator","domain-orchestrator","foundry","agent","embedded-application-agent","learning-module","runtime-monitor"}

def canon(x): return json.dumps(x,sort_keys=True,ensure_ascii=False,separators=(",",":"))
def sha(x): return hashlib.sha256(canon(x).encode()).hexdigest()
def slug(x): return re.sub(r"[^A-Za-z0-9._-]+","_",str(x)).strip("._")[:120] or "unknown"
def db_open(path):
    path.parent.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(path)
    db.execute("""CREATE TABLE IF NOT EXISTS deltas(
      delta_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, source_id TEXT NOT NULL,
      source_kind TEXT NOT NULL, deployment_id TEXT NOT NULL, sequence INTEGER NOT NULL,
      observed_at TEXT NOT NULL, anomaly_severity TEXT, digest TEXT NOT NULL, payload TEXT NOT NULL)""")
    db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_delta_source_seq ON deltas(source_id,deployment_id,sequence)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_delta_project_time ON deltas(project_id,observed_at)")
    return db
def validate(x):
    req=("schema","delta_id","project_id","source_id","source_kind","deployment_id","sequence","observed_at","changes","privacy")
    miss=[k for k in req if k not in x]
    if miss: raise SystemExit("LEARNING_DELTA_MISSING="+",".join(miss))
    if x["schema"]!="chacha.dev/learning-delta/v1": raise SystemExit("LEARNING_DELTA_SCHEMA_INVALID")
    if not SAFE.fullmatch(str(x["delta_id"])): raise SystemExit("LEARNING_DELTA_ID_INVALID")
    if str(x["source_kind"]) not in KINDS: raise SystemExit("LEARNING_DELTA_SOURCE_KIND_INVALID")
    if int(x["sequence"])<1: raise SystemExit("LEARNING_DELTA_SEQUENCE_INVALID")
    if not isinstance(x["changes"],list) or not x["changes"]: raise SystemExit("LEARNING_DELTA_CHANGES_REQUIRED")
    p=x["privacy"]
    if not isinstance(p,dict) or p.get("raw_user_content") is not False: raise SystemExit("LEARNING_DELTA_RAW_USER_CONTENT_FORBIDDEN")
    if p.get("contains_secrets") is not False: raise SystemExit("LEARNING_DELTA_SECRETS_FORBIDDEN")
    if p.get("personal_data_class") not in {"none","aggregated","policy-authorized"}: raise SystemExit("LEARNING_DELTA_PERSONAL_DATA_POLICY_INVALID")
    return x
def persist_nas(x,d):
    if not NAS_ADAPTER.is_file(): return {"status":"DEFERRED","reason":"NAS_ADAPTER_MISSING"}
    day=str(x["observed_at"])[:10].replace("-","")
    remote=f"knowledge/learning-deltas/{slug(x['project_id'])}/{slug(x['source_id'])}/{day}/{slug(x['delta_id'])}-{d[:12]}.json"
    with tempfile.TemporaryDirectory(prefix="chacha-learning-delta-") as td:
        td=Path(td); local=td/"delta.json"; local.write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
        env={"schema":"chacha.dev/dispatch-envelope/v1","project":str(x["project_id"]),"transition":"learning-delta-persist","run_id":"delta-"+d[:16],"wave":1,
        "task":{"id":"learning-delta:"+d[:16],"kind":"knowledge-event","description":"Persist immutable incremental learning delta.","owner_role":"knowledge-compiler-agent","permission":"workspace-write","outputs":[{"type":"artifact","id":remote}],"verification":{"required":True,"mode":"machine"}},
        "bindings":[{"capability":"backup-store","provider":"nas","adapter":"nas-ssh-adapter","fallback_used":False,"health_state":"HEALTHY"}],
        "policy_context":{"resource_class":"light","requires_storage_preflight":False,"human_approval_required":False,"approval_id":None,"timeout_seconds":30},
        "workspace":str(td),"metadata":{"nas_storage":{"action":"put-file","local_path":"delta.json","remote_path":remote,"reserve_mb":1024}}}
        p=subprocess.run([str(NAS_ADAPTER)],input=json.dumps(env).encode(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False,timeout=45)
        if p.returncode!=0:return {"status":"DEFERRED","reason":"NAS_PUBLISH_FAILED"}
        try:r=json.loads(p.stdout)
        except Exception:return {"status":"DEFERRED","reason":"NAS_RESPONSE_INVALID"}
        if r.get("status")=="OK" or r.get("summary")=="NAS_DESTINATION_ALREADY_EXISTS": return {"status":"PERSISTED","remote":remote}
        return {"status":"DEFERRED","reason":str(r.get("summary") or r.get("status"))}
def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--db",type=Path,default=DB_DEFAULT); ap.add_argument("--delta",type=Path,required=True); ap.add_argument("--nas",action="store_true")
    a=ap.parse_args(); x=validate(json.loads(a.delta.read_text(encoding="utf-8"))); d=sha(x); db=db_open(a.db)
    prev=db.execute("SELECT MAX(sequence) FROM deltas WHERE source_id=? AND deployment_id=?",(x["source_id"],x["deployment_id"])).fetchone()[0]
    existing=db.execute("SELECT digest FROM deltas WHERE delta_id=?",(x["delta_id"],)).fetchone()
    if existing:
        if existing[0]!=d: raise SystemExit("LEARNING_DELTA_ID_COLLISION")
        out={"status":"DEDUPLICATED","delta_id":x["delta_id"],"digest":d}
        if a.nas: out["nas"]=persist_nas(x,d)
        print(json.dumps(out,indent=2,ensure_ascii=False)); return
    if prev is not None and int(x["sequence"])<=int(prev): raise SystemExit("LEARNING_DELTA_SEQUENCE_NON_MONOTONIC")
    sev=str((x.get("anomaly") or {}).get("severity") or "").lower() or None
    with db:
        db.execute("INSERT INTO deltas VALUES(?,?,?,?,?,?,?,?,?,?)",(x["delta_id"],x["project_id"],x["source_id"],x["source_kind"],x["deployment_id"],int(x["sequence"]),x["observed_at"],sev,d,canon(x)))
    out={"status":"RECORDED","delta_id":x["delta_id"],"digest":d,"hot_index":"RECORDED","remediation_candidate":sev in {"high","critical"}}
    if a.nas: out["nas"]=persist_nas(x,d)
    print(json.dumps(out,indent=2,ensure_ascii=False))
if __name__=="__main__": main()
