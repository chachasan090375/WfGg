#!/usr/bin/env python3
from __future__ import annotations
import argparse,base64,json,shutil,subprocess,tempfile,urllib.error,urllib.request
from pathlib import Path
from typing import Any
import universal_learning_runtime as ul

DEFAULT_RELAY="https://chacha-dev-learning-relay.chachasan090375.workers.dev"
DEFAULT_INGEST=Path("/opt/chacha-dev/platform/current/dev-hub/bin/learning-delta-ingest.py")
DEFAULT_DB=Path("/opt/chacha-dev/runtime/knowledge/learning-deltas.db")

def load(path:Path)->dict[str,Any]:
    x=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise RuntimeError("JSON_ROOT_NOT_OBJECT")
    return x

def sign(private_key:Path,message:bytes)->str:
    with tempfile.NamedTemporaryFile(prefix="chacha-learning-sign-",delete=True) as f:
        f.write(message);f.flush()
        p=subprocess.run(["/usr/bin/openssl","pkeyutl","-sign","-rawin","-inkey",str(private_key),"-in",f.name],
                         stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False,timeout=15)
    if p.returncode!=0:raise RuntimeError("LEARNING_PRODUCER_SIGN_FAILED")
    return base64.urlsafe_b64encode(p.stdout).decode().rstrip("=")

def public_b64(private_key:Path)->str:
    p=subprocess.run(["/usr/bin/openssl","pkey","-in",str(private_key),"-pubout","-outform","DER"],
                     stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False,timeout=15)
    if p.returncode!=0:raise RuntimeError("LEARNING_PRODUCER_PRIVATE_KEY_READ_FAILED")
    return base64.b64encode(p.stdout).decode()

def key_id(private_key:Path)->str:
    import hashlib
    return "producer-"+hashlib.sha256(public_b64(private_key).encode()).hexdigest()[:16]

def send_local(delta_path:Path,ingest:Path,db:Path)->dict[str,Any]:
    p=subprocess.run(["/usr/bin/python3",str(ingest),"--db",str(db),"--delta",str(delta_path),"--nas"],
                     stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=75)
    if p.returncode!=0:raise RuntimeError("LOCAL_LEARNING_INGEST_FAILED:"+(p.stderr or p.stdout)[-500:])
    x=json.loads(p.stdout)
    if x.get("status") not in {"RECORDED","DEDUPLICATED"}:raise RuntimeError("LOCAL_LEARNING_STATUS_INVALID")
    if (x.get("nas") or {}).get("status")!="PERSISTED":raise RuntimeError("LOCAL_LEARNING_NAS_NOT_PERSISTED")
    return x

def send_relay(delta_path:Path,relay_url:str,private_key:Path)->dict[str,Any]:
    if not private_key.is_file():raise RuntimeError("LEARNING_PRODUCER_PRIVATE_KEY_MISSING")
    delta=load(delta_path)
    packet={"schema":"chacha.dev/learning-uplink-packet/v2","algorithm":"Ed25519","key_id":key_id(private_key),
            "delta":delta,"signature":sign(private_key,ul.canonical(delta).encode())}
    body=json.dumps(packet,separators=(",",":"),ensure_ascii=False).encode()
    req=urllib.request.Request(relay_url.rstrip("/")+"/v1/learning-deltas",data=body,
                               headers={"Content-Type":"application/json","Accept":"application/json",
                                        "User-Agent":"ChaCha-DEV-Universal-Learning-Producer/1.0"},method="POST")
    try:
        with urllib.request.urlopen(req,timeout=25) as r:
            x=json.loads(r.read(1024*1024))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"LEARNING_RELAY_HTTP_{e.code}:"+e.read(2000).decode("utf-8","replace")) from e
    if x.get("status") not in {"RECORDED","DEDUPLICATED"}:raise RuntimeError("LEARNING_RELAY_STATUS_INVALID")
    return x

def flush(outbox:Path,sent:Path,transport:str,ingest:Path,db:Path,relay_url:str,private_key:Path|None,limit:int)->dict[str,Any]:
    outbox.mkdir(parents=True,exist_ok=True);sent.mkdir(parents=True,exist_ok=True)
    done=[];failed=[];blocked_streams=set()
    candidates=[]
    for p in outbox.glob("ld-*.json"):
        try:
            x=load(p)
            stream=(str(x.get("source_id") or ""),str(x.get("deployment_id") or ""))
            seq=int(x.get("sequence") or 0)
            candidates.append((stream,seq,str(x.get("observed_at") or ""),str(x.get("delta_id") or p.stem),p))
        except Exception as exc:
            failed.append({"delta_id":p.stem,"reason":"OUTBOX_DELTA_INVALID:"+type(exc).__name__+":"+str(exc)[:240]})
    candidates.sort(key=lambda row:(row[0][0],row[0][1],row[1],row[2],row[3]))
    for stream,seq,_,_,p in candidates[:limit]:
        if stream in blocked_streams:
            failed.append({"delta_id":p.stem,"reason":"DEFERRED_AFTER_PRIOR_STREAM_FAILURE"})
            continue
        try:
            result=send_local(p,ingest,db) if transport=="local" else send_relay(p,relay_url,private_key or Path("/nonexistent"))
            target=sent/p.name
            if target.exists():p.unlink()
            else:shutil.move(str(p),str(target))
            done.append({"delta_id":p.stem,"sequence":seq,"source_id":stream[0],"deployment_id":stream[1],"status":result.get("status")})
        except Exception as exc:
            blocked_streams.add(stream)
            failed.append({"delta_id":p.stem,"sequence":seq,"source_id":stream[0],"deployment_id":stream[1],
                           "reason":type(exc).__name__+":"+str(exc)[:300]})
    return {"schema":"chacha.dev/universal-learning-flush/v1","transport":transport,"ordering":"SOURCE_DEPLOYMENT_SEQUENCE_ASC",
            "sent":done,"failed":failed,"pending":len(list(outbox.glob("ld-*.json"))),"automatic_external_spend_eur":0}

def main()->int:
    ap=argparse.ArgumentParser()
    sub=ap.add_subparsers(dest="cmd",required=True)
    o=sub.add_parser("observe")
    o.add_argument("--project-id",required=True);o.add_argument("--source-id",required=True);o.add_argument("--source-kind",required=True)
    o.add_argument("--deployment-id",required=True);o.add_argument("--state",type=Path,required=True);o.add_argument("--anomaly",type=Path);o.add_argument("--lineage",type=Path)
    o.add_argument("--evidence-ref",action="append",default=[]);o.add_argument("--personal-data-class",default="none")
    o.add_argument("--outbox",type=Path,default=ul.DEFAULT_OUTBOX);o.add_argument("--state-root",type=Path,default=ul.DEFAULT_STATE)
    f=sub.add_parser("flush")
    f.add_argument("--transport",choices=["local","relay"],required=True);f.add_argument("--outbox",type=Path,default=ul.DEFAULT_OUTBOX)
    f.add_argument("--sent",type=Path,default=Path("/opt/chacha-dev/runtime/learning/sent"))
    f.add_argument("--ingest",type=Path,default=DEFAULT_INGEST);f.add_argument("--db",type=Path,default=DEFAULT_DB)
    f.add_argument("--relay-url",default=DEFAULT_RELAY);f.add_argument("--private-key",type=Path);f.add_argument("--limit",type=int,default=100)
    a=ap.parse_args()
    if a.cmd=="observe":
        anomaly=load(a.anomaly) if a.anomaly else None
        lineage=load(a.lineage) if a.lineage else None
        out=ul.observe(project_id=a.project_id,source_id=a.source_id,source_kind=a.source_kind,deployment_id=a.deployment_id,
                       state=load(a.state),anomaly=anomaly,evidence_refs=a.evidence_ref,lineage=lineage,
                       personal_data_class=a.personal_data_class,outbox_root=a.outbox,state_root=a.state_root)
    else:
        out=flush(a.outbox,a.sent,a.transport,a.ingest,a.db,a.relay_url,a.private_key,a.limit)
    print(json.dumps(out,indent=2,ensure_ascii=False))
    return 0 if not out.get("failed") else 1

if __name__=="__main__":
    raise SystemExit(main())
