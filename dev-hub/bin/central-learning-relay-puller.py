#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

DEFAULT_RELAY_URL="https://chacha-dev-learning-relay.chachasan090375.workers.dev"
DEFAULT_PRIVATE_KEY=Path("/opt/chacha-dev/runtime/secrets/central-learning-key.pem")
DEFAULT_INGEST=Path("/opt/chacha-dev/learning-relay/current/learning-delta-ingest.py")
DEFAULT_DB=Path("/opt/chacha-dev/runtime/knowledge/learning-deltas.db")
DEFAULT_ANOMALY_QUEUE=Path("/opt/chacha-dev/runtime/learning/anomaly-queue")
DEFAULT_EXPERIENCE_DB=Path("/opt/chacha-dev/runtime/knowledge/experience.db")
DEFAULT_GLOBAL_INDEXER=Path("/opt/chacha-dev/learning-relay/current/global-project-memory-index.py")
DEFAULT_GLOBAL_INDEX=Path("/opt/chacha-dev/runtime/knowledge/global-project-memory-index.json")
MAX_RESPONSE=2*1024*1024

def now_iso()->str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())

def derive_public_b64(private_key:Path)->str:
    p=subprocess.run(
        ["/usr/bin/openssl","pkey","-in",str(private_key),"-pubout","-outform","DER"],
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False,timeout=15
    )
    if p.returncode!=0:
        raise RuntimeError("CENTRAL_PRIVATE_KEY_READ_FAILED:"+p.stderr.decode(errors="replace")[-300:])
    return base64.b64encode(p.stdout).decode()

def derive_key_id(private_key:Path)->str:
    pub=derive_public_b64(private_key)
    return "central-"+hashlib.sha256(pub.encode()).hexdigest()[:16]

def sign(private_key:Path,message:bytes)->str:
    # OpenSSL Ed25519 is a one-shot operation and requires a seekable input
    # so it can determine the complete message size before signing.
    with tempfile.NamedTemporaryFile(prefix="chacha-ed25519-msg-",delete=True) as msg:
        msg.write(message); msg.flush()
        p=subprocess.run(
            ["/usr/bin/openssl","pkeyutl","-sign","-rawin","-inkey",str(private_key),"-in",msg.name],
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False,timeout=15
        )
    if p.returncode!=0:
        raise RuntimeError("CENTRAL_SIGN_FAILED:"+p.stderr.decode(errors="replace")[-300:])
    return base64.urlsafe_b64encode(p.stdout).decode().rstrip("=")

def request_message(method:str,url:str,timestamp:str,body:bytes=b"")->bytes:
    u=urllib.parse.urlsplit(url)
    path=u.path or "/"
    if u.query:
        path+="?"+u.query
    return (timestamp+"\n"+method.upper()+"\n"+path+"\n").encode()+body

def signed_request(method:str,url:str,private_key:Path,key_id:str,body:bytes=b"",content_type:str|None=None)->urllib.request.Request:
    ts=now_iso()
    headers={
        "User-Agent":"ChaCha-DEV-Central-Learning-Puller/1.0",
        "Accept":"application/json",
        "X-ChaCha-Key-Id":key_id,
        "X-ChaCha-Timestamp":ts,
        "X-ChaCha-Signature":sign(private_key,request_message(method,url,ts,body))
    }
    if content_type:
        headers["Content-Type"]=content_type
    return urllib.request.Request(url,data=(body if method.upper()!="GET" else None),headers=headers,method=method.upper())

def http_json(req:urllib.request.Request,timeout:int=25)->dict[str,Any]:
    try:
        with urllib.request.urlopen(req,timeout=timeout) as r:
            raw=r.read(MAX_RESPONSE+1)
            if len(raw)>MAX_RESPONSE:
                raise RuntimeError("RELAY_RESPONSE_TOO_LARGE")
            return json.loads(raw)
    except urllib.error.HTTPError as e:
        raw=e.read(8192).decode("utf-8","replace")
        raise RuntimeError(f"RELAY_HTTP_{e.code}:{raw[-1000:]}") from e

def persist_delta(ingest:Path,db:Path,delta:dict[str,Any])->dict[str,Any]:
    with tempfile.TemporaryDirectory(prefix="chacha-central-pull-") as td:
        p=Path(td)/"delta.json"
        p.write_text(json.dumps(delta,ensure_ascii=False)+"\n",encoding="utf-8")
        proc=subprocess.run(
            ["/usr/bin/python3",str(ingest),"--db",str(db),"--delta",str(p),"--nas"],
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=70
        )
    if proc.returncode!=0:
        raise RuntimeError("LOCAL_DELTA_INGEST_FAILED:"+(proc.stderr.strip() or proc.stdout.strip())[-700:])
    try:
        out=json.loads(proc.stdout)
    except Exception as exc:
        raise RuntimeError("LOCAL_DELTA_INGEST_RESPONSE_INVALID") from exc
    if out.get("status") not in {"RECORDED","DEDUPLICATED"}:
        raise RuntimeError("LOCAL_DELTA_INGEST_STATUS_INVALID:"+str(out.get("status")))
    nas=out.get("nas") or {}
    if nas.get("status")!="PERSISTED":
        raise RuntimeError("LOCAL_DELTA_NAS_NOT_PERSISTED:"+str(nas.get("reason") or nas.get("status")))
    return out

def queue_anomaly(root:Path,delta:dict[str,Any])->str|None:
    anomaly=delta.get("anomaly") or {}
    severity=str(anomaly.get("severity") or "").lower()
    if severity not in {"high","critical"}:
        return None
    root.mkdir(parents=True,exist_ok=True)
    delta_id=str(delta.get("delta_id") or "")
    if not delta_id:
        return None
    target=root/(delta_id+".json")
    if target.exists():
        return str(target)
    payload={
        "schema":"chacha.dev/anomaly-remediation-candidate/v1",
        "queued_at":now_iso(),
        "project_id":delta.get("project_id"),
        "source_id":delta.get("source_id"),
        "deployment_id":delta.get("deployment_id"),
        "delta_id":delta_id,
        "severity":severity,
        "anomaly":anomaly,
        "evidence_refs":delta.get("evidence_refs") or [],
        "automatic_apply_authorized":False,
        "status":"CANDIDATE"
    }
    tmp=target.with_name(target.name+f".tmp-{os.getpid()}")
    tmp.write_text(json.dumps(payload,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    os.replace(tmp,target)
    return str(target)

def rebuild_global_index(indexer:Path,experience_db:Path,delta_db:Path,output:Path)->None:
    if not indexer.is_file():
        raise RuntimeError("GLOBAL_PROJECT_MEMORY_INDEXER_MISSING")
    proc=subprocess.run(
        ["/usr/bin/python3",str(indexer),"--experience-db",str(experience_db),"--delta-db",str(delta_db),"--output",str(output)],
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=45
    )
    if proc.returncode!=0 or "CHACHA_DEV_GLOBAL_PROJECT_MEMORY_INDEX=PASS" not in proc.stdout:
        raise RuntimeError("GLOBAL_PROJECT_MEMORY_INDEX_REBUILD_FAILED:"+(proc.stderr.strip() or proc.stdout.strip())[-700:])


def run_once(relay_url:str,private_key:Path,ingest:Path,db:Path,anomaly_queue:Path,batch_limit:int,indexer:Path,experience_db:Path,global_index:Path)->dict[str,Any]:
    if not private_key.is_file():
        raise RuntimeError("CENTRAL_PRIVATE_KEY_MISSING")
    if not ingest.is_file():
        raise RuntimeError("LEARNING_DELTA_INGEST_MISSING")
    key_id=derive_key_id(private_key)
    pull_url=relay_url.rstrip("/")+"/v1/central/pull?limit="+str(batch_limit)
    batch=http_json(signed_request("GET",pull_url,private_key,key_id))
    if batch.get("schema")!="chacha.dev/learning-relay-batch/v1":
        raise RuntimeError("RELAY_BATCH_SCHEMA_INVALID")
    items=batch.get("items") or []
    if not isinstance(items,list):
        raise RuntimeError("RELAY_BATCH_ITEMS_INVALID")
    ack_ids=[]
    anomalies=0
    for item in items:
        if not isinstance(item,dict) or not isinstance(item.get("delta"),dict):
            raise RuntimeError("RELAY_BATCH_ITEM_INVALID")
        delta=item["delta"]
        if str(item.get("delta_id") or "")!=str(delta.get("delta_id") or ""):
            raise RuntimeError("RELAY_BATCH_DELTA_ID_MISMATCH")
        persist_delta(ingest,db,delta)
        if queue_anomaly(anomaly_queue,delta):
            anomalies+=1
        ack_ids.append(str(item["delta_id"]))
    global_index_updated=False
    if ack_ids:
        # ACK is deliberately held until durable NAS persistence and the
        # central cross-project memory index have both been refreshed.
        rebuild_global_index(indexer,experience_db,db,global_index)
        global_index_updated=True
        body=json.dumps({"delta_ids":ack_ids},separators=(",",":")).encode()
        ack_url=relay_url.rstrip("/")+"/v1/central/ack"
        ack=http_json(signed_request("POST",ack_url,private_key,key_id,body,"application/json"))
        if ack.get("status")!="ACKED":
            raise RuntimeError("RELAY_ACK_STATUS_INVALID")
    return {
        "schema":"chacha.dev/central-learning-pull-result/v1",
        "status":"PASS",
        "key_id":key_id,
        "pulled":len(items),
        "persisted":len(ack_ids),
        "acked":len(ack_ids),
        "anomaly_candidates":anomalies,
        "nas_required":True,
        "global_project_memory_index_updated":global_index_updated,
        "relay_url":relay_url
    }

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--relay-url",default=DEFAULT_RELAY_URL)
    ap.add_argument("--private-key",type=Path,default=DEFAULT_PRIVATE_KEY)
    ap.add_argument("--ingest",type=Path,default=DEFAULT_INGEST)
    ap.add_argument("--db",type=Path,default=DEFAULT_DB)
    ap.add_argument("--anomaly-queue",type=Path,default=DEFAULT_ANOMALY_QUEUE)
    ap.add_argument("--batch-limit",type=int,default=25)
    ap.add_argument("--experience-db",type=Path,default=DEFAULT_EXPERIENCE_DB)
    ap.add_argument("--global-indexer",type=Path,default=DEFAULT_GLOBAL_INDEXER)
    ap.add_argument("--global-index",type=Path,default=DEFAULT_GLOBAL_INDEX)
    ap.add_argument("--print-identity",action="store_true")
    a=ap.parse_args()
    if not a.relay_url.startswith("https://"):
        raise SystemExit("CENTRAL_RELAY_HTTPS_REQUIRED")
    if not 1<=a.batch_limit<=100:
        raise SystemExit("CENTRAL_RELAY_BATCH_LIMIT_INVALID")
    if a.print_identity:
        print(json.dumps({
            "schema":"chacha.dev/central-learning-public-key/v1",
            "key_id":derive_key_id(a.private_key),
            "algorithm":"Ed25519",
            "public_key_spki_b64":derive_public_b64(a.private_key),
            "private_key_exported":False
        },indent=2))
        return 0
    out=run_once(a.relay_url,a.private_key,a.ingest,a.db,a.anomaly_queue,a.batch_limit,a.global_indexer,a.experience_db,a.global_index)
    print(json.dumps(out,indent=2,ensure_ascii=False))
    print("CHACHA_DEV_V69_CENTRAL_PULL=PASS")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
