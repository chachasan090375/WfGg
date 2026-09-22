#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

DEFAULT_BIND="127.0.0.1"
DEFAULT_PORT=8791
DEFAULT_KEYS=Path("/opt/chacha-dev/runtime/secrets/learning-ingress-keys.json")
DEFAULT_DELTA_DB=Path("/opt/chacha-dev/runtime/knowledge/learning-deltas.db")
DEFAULT_INGEST=Path("/opt/chacha-dev/platform/current/dev-hub/bin/learning-delta-ingest.py")
DEFAULT_ANOMALY_QUEUE=Path("/opt/chacha-dev/runtime/learning/anomaly-queue")
MAX_BODY=256*1024
PACKET_SCHEMA="chacha.dev/learning-uplink-packet/v1"
KEY_SCHEMA="chacha.dev/learning-ingress-keys/v1"
WRITE_LOCK=threading.Lock()

def now_iso()->str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())

def canonical_delta(delta:dict[str,Any])->bytes:
    return json.dumps(delta,sort_keys=True,ensure_ascii=False,separators=(",",":")).encode()

def load_registry(path:Path)->dict[str,Any]:
    raw=json.loads(path.read_text(encoding="utf-8"))
    if raw.get("schema")!=KEY_SCHEMA or not isinstance(raw.get("keys"),dict):
        raise RuntimeError("LEARNING_INGRESS_KEY_REGISTRY_INVALID")
    return raw

def authorize(packet:dict[str,Any],registry:dict[str,Any])->dict[str,Any]:
    if packet.get("schema")!=PACKET_SCHEMA:
        raise ValueError("UPLINK_PACKET_SCHEMA_INVALID")
    if packet.get("algorithm")!="HMAC-SHA256":
        raise ValueError("UPLINK_ALGORITHM_INVALID")
    key_id=str(packet.get("key_id") or "")
    key=(registry.get("keys") or {}).get(key_id)
    if not isinstance(key,dict) or key.get("status")!="ACTIVE":
        raise PermissionError("UPLINK_KEY_UNKNOWN_OR_INACTIVE")
    secret=str(key.get("secret") or "")
    if len(secret)<24:
        raise PermissionError("UPLINK_KEY_SECRET_INVALID")
    delta=packet.get("delta")
    if not isinstance(delta,dict):
        raise ValueError("UPLINK_DELTA_MISSING")
    provided=str(packet.get("signature") or "")
    expected=hmac.new(secret.encode(),canonical_delta(delta),hashlib.sha256).hexdigest()
    if not hmac.compare_digest(provided,expected):
        raise PermissionError("UPLINK_SIGNATURE_INVALID")
    project=str(delta.get("project_id") or "")
    deployment=str(delta.get("deployment_id") or "")
    allowed_projects=set(map(str,key.get("project_ids") or []))
    allowed_deployments=set(map(str,key.get("deployment_ids") or []))
    if allowed_projects and project not in allowed_projects:
        raise PermissionError("UPLINK_PROJECT_NOT_ALLOWED")
    if allowed_deployments and deployment not in allowed_deployments:
        raise PermissionError("UPLINK_DEPLOYMENT_NOT_ALLOWED")
    return delta

def queue_anomaly(queue_root:Path,delta:dict[str,Any],ingest_result:dict[str,Any])->str|None:
    anomaly=delta.get("anomaly") or {}
    severity=str(anomaly.get("severity") or "").lower()
    if severity not in {"high","critical"} and not ingest_result.get("remediation_candidate"):
        return None
    queue_root.mkdir(parents=True,exist_ok=True)
    delta_id=str(delta.get("delta_id"))
    payload={
        "schema":"chacha.dev/anomaly-remediation-candidate/v1",
        "queued_at":now_iso(),
        "project_id":delta.get("project_id"),
        "source_id":delta.get("source_id"),
        "deployment_id":delta.get("deployment_id"),
        "delta_id":delta_id,
        "severity":severity or "unspecified",
        "anomaly":anomaly,
        "evidence_refs":delta.get("evidence_refs") or [],
        "automatic_apply_authorized":False,
        "status":"CANDIDATE"
    }
    target=queue_root/(delta_id+".json")
    if target.exists():
        return str(target)
    tmp=target.with_name(target.name+f".tmp-{os.getpid()}-{threading.get_ident()}")
    tmp.write_text(json.dumps(payload,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    os.replace(tmp,target)
    return str(target)

def ingest_delta(ingest:Path,db:Path,delta:dict[str,Any],use_nas:bool)->dict[str,Any]:
    import tempfile
    with tempfile.TemporaryDirectory(prefix="chacha-learning-ingress-") as td:
        p=Path(td)/"delta.json"
        p.write_text(json.dumps(delta,ensure_ascii=False)+"\n",encoding="utf-8")
        cmd=["/usr/bin/python3",str(ingest),"--db",str(db),"--delta",str(p)]
        if use_nas:
            cmd.append("--nas")
        proc=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=55)
    if proc.returncode!=0:
        raise RuntimeError("LEARNING_DELTA_INGEST_FAILED:"+(proc.stderr.strip() or proc.stdout.strip())[-700:])
    try:
        result=json.loads(proc.stdout)
    except Exception as exc:
        raise RuntimeError("LEARNING_DELTA_INGEST_RESPONSE_INVALID") from exc
    nas=result.get("nas")
    if use_nas and isinstance(nas,dict) and nas.get("status")!="PERSISTED":
        raise RuntimeError("LEARNING_DELTA_NAS_PERSISTENCE_NOT_CONFIRMED:"+str(nas.get("reason") or nas.get("status")))
    return result

class Server(ThreadingHTTPServer):
    daemon_threads=True
    allow_reuse_address=False

class Handler(BaseHTTPRequestHandler):
    server_version="ChaChaCentralLearningIngress/1.0"
    def json_out(self,code:int,obj:dict[str,Any]):
        raw=json.dumps(obj,ensure_ascii=False,separators=(",",":")).encode()
        self.send_response(code)
        self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Cache-Control","no-store")
        self.send_header("Content-Length",str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)
    def do_GET(self):
        if self.path=="/healthz":
            self.json_out(200,{"status":"ok","service":"chacha-central-learning-ingress","time":now_iso()})
            return
        self.json_out(404,{"error":"not_found"})
    def do_POST(self):
        if self.path!="/v1/learning-deltas":
            self.json_out(404,{"error":"not_found"});return
        try:
            n=int(self.headers.get("Content-Length","0") or 0)
        except Exception:
            n=0
        if n<=0 or n>MAX_BODY:
            self.json_out(413,{"error":"payload_size_invalid"});return
        try:
            packet=json.loads(self.rfile.read(n))
            if not isinstance(packet,dict): raise ValueError("PACKET_ROOT_NOT_OBJECT")
            registry=load_registry(self.server.key_registry)
            delta=authorize(packet,registry)
            result=ingest_delta(self.server.ingest,self.server.delta_db,delta,self.server.use_nas)
            with WRITE_LOCK:
                queued=queue_anomaly(self.server.anomaly_queue,delta,result)
            self.json_out(202 if result.get("status")=="RECORDED" else 200,{
                "schema":"chacha.dev/learning-ingress-ack/v1",
                "status":result.get("status"),
                "delta_id":result.get("delta_id") or delta.get("delta_id"),
                "digest":result.get("digest"),
                "nas":result.get("nas"),
                "remediation_candidate":bool(result.get("remediation_candidate")),
                "remediation_queue":queued,
                "received_at":now_iso()
            })
        except PermissionError as exc:
            self.json_out(403,{"error":str(exc)})
        except (ValueError,json.JSONDecodeError) as exc:
            self.json_out(400,{"error":str(exc)})
        except Exception as exc:
            self.json_out(500,{"error":str(exc)[:800]})
    def log_message(self,fmt,*args):
        return

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--bind",default=DEFAULT_BIND)
    ap.add_argument("--port",type=int,default=DEFAULT_PORT)
    ap.add_argument("--key-registry",type=Path,default=DEFAULT_KEYS)
    ap.add_argument("--delta-db",type=Path,default=DEFAULT_DELTA_DB)
    ap.add_argument("--ingest",type=Path,default=DEFAULT_INGEST)
    ap.add_argument("--anomaly-queue",type=Path,default=DEFAULT_ANOMALY_QUEUE)
    ap.add_argument("--nas",action="store_true")
    a=ap.parse_args()
    if a.bind not in {"127.0.0.1","::1","localhost"}:
        raise SystemExit("CENTRAL_LEARNING_INGRESS_BIND_MUST_BE_LOOPBACK")
    if not a.key_registry.is_file():
        raise SystemExit("CENTRAL_LEARNING_INGRESS_KEY_REGISTRY_MISSING")
    srv=Server((a.bind,a.port),Handler)
    srv.key_registry=a.key_registry;srv.delta_db=a.delta_db;srv.ingest=a.ingest
    srv.anomaly_queue=a.anomaly_queue;srv.use_nas=a.nas
    print(f"CHACHA_DEV_CENTRAL_LEARNING_INGRESS=READY bind={a.bind} port={srv.server_address[1]} nas={str(a.nas).upper()}",flush=True)
    srv.serve_forever()

if __name__=="__main__":
    main()
