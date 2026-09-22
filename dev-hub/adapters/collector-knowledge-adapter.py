#!/usr/bin/env python3
"""ChaCha DEV Collector Knowledge Runtime Adapter V1.

Dedicated adapter for the WfGg Collector Knowledge Engine.
It may install/probe the local Knowledge Engine pilot and query its localhost
read-only API. It never connects to Last War, never handles game credentials,
and never mutates the Radar Connector/runtime.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

INPUT_SCHEMA="chacha.dev/dispatch-envelope/v1"
OUTPUT_SCHEMA="chacha.dev/task-result/v1"
ADAPTER_ID="collector-knowledge-adapter"
PROVIDER_ID="collector-knowledge-runtime"
RAW_BASE="https://raw.githubusercontent.com/chachasan090375/WfGg"
REV_RE=re.compile(r"^[0-9a-f]{40}$")
INSTALLER_PATH="radar-vps/install-collector-knowledge-v1.sh"
PROBE_PATH="radar-vps/probe-collector-knowledge-v1-runtime.sh"
ABSOLUTE_MAX_TIMEOUT=300

RADAR_ROOT=Path("/opt/wfgg-radar")
RADAR_CONNECTOR=RADAR_ROOT/"bin/radar-connector"
RADAR_NATIVE=RADAR_ROOT/"bin/radar-native-template"
MESSENGER=RADAR_ROOT/"messenger/bin/wfgg-messenger-outbox"
KNOWLEDGE_APP=RADAR_ROOT/"collector-knowledge"
KNOWLEDGE_DB=RADAR_ROOT/"data/collector-knowledge/knowledge.db"
WORKER_UNIT="wfgg-collector-knowledge-worker.service"
API_UNIT="wfgg-collector-knowledge-api.service"
API_BASE="http://127.0.0.1:8791"

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def sha256_bytes(value: bytes) -> str:
    return "sha256:"+hashlib.sha256(value).hexdigest()

def sha256_file(path: Path) -> str|None:
    if not path.is_file(): return None
    h=hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""):
            h.update(chunk)
    return h.hexdigest()

def run(argv: list[str],timeout=30,env=None):
    return subprocess.run(argv,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                          timeout=timeout,shell=False,check=False,env=env or os.environ.copy())

def systemctl(*args: str,timeout=20):
    return run(["/usr/bin/systemctl",*args],timeout=timeout)

def state(unit: str) -> str:
    p=systemctl("is-active",unit)
    return p.stdout.decode("utf-8","replace").strip() or "unknown"

def enabled(unit: str) -> str:
    p=systemctl("is-enabled",unit)
    return p.stdout.decode("utf-8","replace").strip() or "unknown"

def result(request,status,summary,evidence=None,outputs=None):
    task=request.get("task") if isinstance(request.get("task"),dict) else {}
    return {
        "schema":OUTPUT_SCHEMA,
        "project":str(request.get("project") or "unknown"),
        "task_id":str(task.get("id") or "unknown"),
        "status":status,
        "producer":ADAPTER_ID,
        "observed_at":now_iso(),
        "summary":summary,
        "evidence":evidence or [],
        "verification":{
            "status":"UNVERIFIED","method":"none","verifier":"none","observed_at":now_iso(),
            "notes":"Collector Knowledge runtime results require independent verification."
        },
        "outputs":outputs or [],
    }

def emit(payload,code=0):
    sys.stdout.write(json.dumps(payload,ensure_ascii=False,separators=(",",":"))+"\n")
    return code

def blocked(request,reason):
    return emit(result(request,"BLOCKED",reason,[{
        "kind":"report","source":"collector-knowledge-adapter-policy",
        "digest":sha256_bytes(reason.encode()),"details":{"reason":reason}
    }]),2)

def timeout_from(request):
    p=request.get("policy_context") if isinstance(request.get("policy_context"),dict) else {}
    try:v=int(p.get("timeout_seconds") or 90)
    except Exception:v=90
    return max(1,min(v,ABSOLUTE_MAX_TIMEOUT))

def validate_request(request):
    if request.get("schema")!=INPUT_SCHEMA:return None,"INPUT_SCHEMA_INVALID"
    task=request.get("task")
    if not isinstance(task,dict) or not task.get("id"):return None,"TASK_ID_MISSING"
    bindings=request.get("bindings")
    if not isinstance(bindings,list) or not any(
        isinstance(x,dict) and x.get("provider")==PROVIDER_ID and x.get("adapter")==ADAPTER_ID for x in bindings
    ):
        return None,"COLLECTOR_KNOWLEDGE_BINDING_MISSING"
    meta=request.get("metadata")
    knowledge=meta.get("collector_knowledge") if isinstance(meta,dict) else None
    if not isinstance(knowledge,dict):return None,"COLLECTOR_KNOWLEDGE_METADATA_MISSING"
    action=str(knowledge.get("action") or "")
    expected={"status":"read","query":"read","pilot-install":"workspace-write","pilot-probe":"read"}.get(action)
    if expected is None:return None,"COLLECTOR_KNOWLEDGE_ACTION_NOT_ALLOWED"
    if str(task.get("permission") or "")!=expected:
        return None,f"COLLECTOR_KNOWLEDGE_PERMISSION_REQUIRED:{expected}"
    return knowledge,None

def production_snapshot():
    return {
        "radar_connector_state":state("wfgg-radar-connector"),
        "radar_sentinel_state":state("wfgg-radar-sentinel.timer"),
        "collector_sentinel_state":state("wfgg-collector-sentinel.timer"),
        "connector_sha256":sha256_file(RADAR_CONNECTOR),
        "native_sha256":sha256_file(RADAR_NATIVE),
        "messenger_sha256":sha256_file(MESSENGER),
    }

def production_unchanged(before,after):
    return before==after

def knowledge_snapshot():
    return {
        "worker_state":state(WORKER_UNIT),
        "worker_enabled":enabled(WORKER_UNIT),
        "api_state":state(API_UNIT),
        "api_enabled":enabled(API_UNIT),
        "app_exists":(KNOWLEDGE_APP/"knowledge_engine.py").is_file(),
        "refresh_exists":(KNOWLEDGE_APP/"source_refresh.py").is_file(),
        "database_exists":KNOWLEDGE_DB.is_file(),
    }

def get_json(path,timeout=10):
    url=API_BASE+path
    req=urllib.request.Request(url,headers={"User-Agent":"ChaCha-DEV-CollectorKnowledge/1"})
    with urllib.request.urlopen(req,timeout=timeout) as r:
        if r.status!=200:raise ValueError("COLLECTOR_KNOWLEDGE_HTTP_"+str(r.status))
        return json.load(r)

def download(revision,path,destination,timeout):
    if not REV_RE.fullmatch(revision):raise ValueError("COLLECTOR_KNOWLEDGE_REVISION_INVALID")
    if path not in {INSTALLER_PATH,PROBE_PATH}:raise ValueError("COLLECTOR_KNOWLEDGE_ASSET_PATH_INVALID")
    url=f"{RAW_BASE}/{revision}/{path}"
    req=urllib.request.Request(url,headers={"User-Agent":"ChaCha-DEV-CollectorKnowledge/1"})
    with urllib.request.urlopen(req,timeout=timeout) as r:
        body=r.read(1024*1024+1)
    if len(body)>1024*1024:raise ValueError("COLLECTOR_KNOWLEDGE_ASSET_TOO_LARGE")
    destination.write_bytes(body);destination.chmod(0o700)

def do_status(request,knowledge):
    snap=knowledge_snapshot()
    healthy=(snap["worker_state"]=="active" and snap["api_state"]=="active")
    details=dict(snap)
    if healthy:
        try:
            details["health"]=get_json("/knowledge/health")
            details["stats"]=get_json("/knowledge/stats")
        except Exception as exc:
            healthy=False;details["api_error"]=type(exc).__name__
    raw=json.dumps(details,sort_keys=True,separators=(",",":")).encode()
    return emit(result(request,"OK" if healthy else "BLOCKED",
        "COLLECTOR_KNOWLEDGE_STATUS_OK" if healthy else "COLLECTOR_KNOWLEDGE_STATUS_NOT_READY",
        [{"kind":"metric","source":"vps://localhost/collector-knowledge/status",
          "digest":sha256_bytes(raw),"details":details}],
        [{"type":"artifact","id":"collector-knowledge-status","status":"UNVERIFIED",
          "reason":"Local Knowledge Engine runtime snapshot."}]),0 if healthy else 2)

def do_query(request,knowledge):
    query=str(knowledge.get("q") or "").strip()
    if not query:return blocked(request,"COLLECTOR_KNOWLEDGE_QUERY_MISSING")
    if len(query)>500:return blocked(request,"COLLECTOR_KNOWLEDGE_QUERY_TOO_LONG")
    try:limit=max(1,min(int(knowledge.get("limit") or 25),100))
    except Exception:limit=25
    try:
        data=get_json("/knowledge/ask?"+urllib.parse.urlencode({"q":query,"limit":limit}),timeout=15)
    except Exception as exc:
        return emit(result(request,"FAILED",f"COLLECTOR_KNOWLEDGE_QUERY_FAILED:{type(exc).__name__}"))
    raw=json.dumps(data,sort_keys=True,separators=(",",":")).encode()
    return emit(result(request,"OK","COLLECTOR_KNOWLEDGE_QUERY_OK",[{
        "kind":"report","source":"vps://localhost/collector-knowledge/query",
        "digest":sha256_bytes(raw),"details":{"query":query,"resultCount":len(data.get("results") or [])}
    }],[{"type":"artifact","id":"collector-knowledge-query-result","status":"UNVERIFIED",
         "reason":json.dumps(data,ensure_ascii=False)[:6000]}]))

def do_install(request,knowledge):
    revision=str(knowledge.get("revision") or "").strip().lower()
    if not REV_RE.fullmatch(revision):return blocked(request,"COLLECTOR_KNOWLEDGE_REVISION_INVALID")
    before=production_snapshot()
    if before["radar_connector_state"]!="active":return blocked(request,"RADAR_PRODUCTION_SERVICE_NOT_ACTIVE")
    timeout=timeout_from(request)
    with tempfile.TemporaryDirectory(prefix="chacha-collector-knowledge-install-") as td:
        script=Path(td)/"install.sh"
        try:download(revision,INSTALLER_PATH,script,min(timeout,60))
        except Exception as exc:return emit(result(request,"FAILED",f"COLLECTOR_KNOWLEDGE_INSTALLER_DOWNLOAD_FAILED:{type(exc).__name__}"))
        env=os.environ.copy();env["WFGG_COLLECTOR_KNOWLEDGE_REV"]=revision
        proc=run(["/usr/bin/bash",str(script)],timeout=timeout,env=env)
    if proc.returncode!=0:
        digest=sha256_bytes(proc.stdout[:65536]+proc.stderr[:65536])
        return emit(result(request,"FAILED","COLLECTOR_KNOWLEDGE_PILOT_INSTALL_FAILED",[{
            "kind":"command","source":"local://collector-knowledge-installer","digest":digest,
            "details":{"returncode":proc.returncode,
                       "stdoutTail":proc.stdout.decode("utf-8","replace")[-1200:],
                       "stderrTail":proc.stderr.decode("utf-8","replace")[-1200:]}
        }]))
    after=production_snapshot()
    if not production_unchanged(before,after):
        return emit(result(request,"FAILED","COLLECTOR_KNOWLEDGE_PRODUCTION_RUNTIME_CHANGED",[{
            "kind":"metric","source":"vps://localhost/collector-knowledge/production-before",
            "digest":sha256_bytes(json.dumps(before,sort_keys=True).encode()),"details":before
        },{
            "kind":"metric","source":"vps://localhost/collector-knowledge/production-after",
            "digest":sha256_bytes(json.dumps(after,sort_keys=True).encode()),"details":after
        }]))
    snap=knowledge_snapshot()
    if snap["worker_state"]!="active" or snap["api_state"]!="active":
        return emit(result(request,"FAILED","COLLECTOR_KNOWLEDGE_RUNTIME_NOT_ACTIVE"))
    details={**snap,"production_runtime_unchanged":True,"lastwar_game_connection":"NONE",
             "lastwar_mutation":False,"token_persisted":False}
    return emit(result(request,"OK","COLLECTOR_KNOWLEDGE_PILOT_INSTALL_OK",[{
        "kind":"artifact","source":"vps://localhost/collector-knowledge/install",
        "digest":sha256_bytes(json.dumps(details,sort_keys=True).encode()),"details":details
    }],[{"type":"artifact","id":"collector-knowledge-engine-v1-pilot","status":"UNVERIFIED",
         "reason":"Knowledge Engine installed as isolated background services; probe required."}]))

def do_probe(request,knowledge):
    revision=str(knowledge.get("revision") or "").strip().lower()
    if not REV_RE.fullmatch(revision):return blocked(request,"COLLECTOR_KNOWLEDGE_REVISION_INVALID")
    before=production_snapshot()
    timeout=timeout_from(request)
    with tempfile.TemporaryDirectory(prefix="chacha-collector-knowledge-probe-") as td:
        script=Path(td)/"probe.sh"
        try:download(revision,PROBE_PATH,script,min(timeout,60))
        except Exception as exc:return emit(result(request,"FAILED",f"COLLECTOR_KNOWLEDGE_PROBE_DOWNLOAD_FAILED:{type(exc).__name__}"))
        proc=run(["/usr/bin/bash",str(script)],timeout=timeout)
    digest=sha256_bytes(proc.stdout[:65536]+proc.stderr[:65536])
    if proc.returncode!=0 or b"COLLECTOR_KNOWLEDGE_RUNTIME_PROBE=PASS" not in proc.stdout:
        return emit(result(request,"FAILED","COLLECTOR_KNOWLEDGE_PILOT_PROBE_FAILED",[{
            "kind":"command","source":"local://collector-knowledge-probe","digest":digest,
            "details":{"returncode":proc.returncode,
                       "stdoutTail":proc.stdout.decode("utf-8","replace")[-1600:],
                       "stderrTail":proc.stderr.decode("utf-8","replace")[-1600:]}
        }]))
    after=production_snapshot()
    if not production_unchanged(before,after):
        return emit(result(request,"FAILED","COLLECTOR_KNOWLEDGE_PROBE_CHANGED_PRODUCTION"))
    stats={}
    try:stats=get_json("/knowledge/stats")
    except Exception:pass
    details={"production_runtime_unchanged":True,"lastwar_game_connection":"NONE",
             "lastwar_mutation":False,"token_persisted":False,"stats":stats.get("stats",{})}
    return emit(result(request,"OK","COLLECTOR_KNOWLEDGE_PILOT_PROBE_OK",[{
        "kind":"command","source":"local://collector-knowledge-probe","digest":digest,"details":details
    }],[{"type":"gate","id":"collector-knowledge-v1-runtime-pilot","status":"UNVERIFIED",
         "reason":"Background worker and localhost read-only API probe passed."}]))

def main():
    try:request=json.load(sys.stdin)
    except Exception:return emit(result({},"BLOCKED","INPUT_JSON_INVALID"),2)
    knowledge,err=validate_request(request)
    if err:return blocked(request,err)
    action=str(knowledge.get("action"))
    if action=="status":return do_status(request,knowledge)
    if action=="query":return do_query(request,knowledge)
    if action=="pilot-install":return do_install(request,knowledge)
    if action=="pilot-probe":return do_probe(request,knowledge)
    return blocked(request,"COLLECTOR_KNOWLEDGE_ACTION_NOT_ALLOWED")

if __name__=="__main__":
    raise SystemExit(main())
