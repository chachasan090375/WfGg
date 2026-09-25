#!/usr/bin/env python3
"""Independent health probe for collector-knowledge-runtime.

The probe never invokes collector-knowledge-adapter. It verifies the registered
adapter executable exists, the two local Knowledge Engine systemd services are
active, and the loopback-only read-only health endpoint returns JSON.
"""
from __future__ import annotations
import argparse,hashlib,json,os,subprocess,time,urllib.error,urllib.request
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlsplit,urlunsplit

SCHEMA="chacha.dev/provider-probe-result/v1"
PROVIDER="collector-knowledge-runtime"

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def sha256_file(path:Path)->str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""):h.update(chunk)
    return "sha256:"+h.hexdigest()

def safe_url(value:str)->str:
    p=urlsplit(value)
    return urlunsplit((p.scheme,p.netloc,p.path or "/","",""))

def systemctl_state(binary:Path,unit:str,timeout:float)->str:
    try:
        p=subprocess.run([str(binary),"is-active",unit],stdin=subprocess.DEVNULL,
                         stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                         timeout=max(1,min(timeout,15)),shell=False,check=False,text=True)
        return (p.stdout or "").strip() or "unknown"
    except Exception:
        return "unknown"

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--executable",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    ap.add_argument("--api-url",default="http://127.0.0.1:8791/knowledge/health")
    ap.add_argument("--systemctl-bin",type=Path,default=Path("/usr/bin/systemctl"))
    ap.add_argument("--worker-unit",default="wfgg-collector-knowledge-worker.service")
    ap.add_argument("--api-unit",default="wfgg-collector-knowledge-api.service")
    ap.add_argument("--timeout",type=float,default=5.0)
    a=ap.parse_args()

    blockers=[]
    parsed=urlsplit(a.api_url)
    if parsed.scheme!="http" or parsed.hostname not in {"127.0.0.1","localhost","::1"}:
        blockers.append("PROBE_TARGET_NOT_LOOPBACK_HTTP")

    executable_digest=None
    if not a.executable.is_absolute():
        blockers.append("EXECUTABLE_PATH_NOT_ABSOLUTE")
    elif not a.executable.is_file():
        blockers.append("EXECUTABLE_MISSING")
    elif not os.access(a.executable,os.X_OK):
        blockers.append("EXECUTABLE_NOT_EXECUTABLE")
    else:
        executable_digest=sha256_file(a.executable)

    if not a.systemctl_bin.is_absolute() or not a.systemctl_bin.is_file():
        blockers.append("SYSTEMCTL_MISSING")
        worker_state=api_state="unknown"
    else:
        worker_state=systemctl_state(a.systemctl_bin,a.worker_unit,a.timeout)
        api_state=systemctl_state(a.systemctl_bin,a.api_unit,a.timeout)
        if worker_state!="active":blockers.append("KNOWLEDGE_WORKER_NOT_ACTIVE:"+worker_state)
        if api_state!="active":blockers.append("KNOWLEDGE_API_NOT_ACTIVE:"+api_state)

    http_status=None;body_digest=None;json_valid=False;latency_ms=None
    if parsed.scheme=="http" and parsed.hostname in {"127.0.0.1","localhost","::1"}:
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        req=urllib.request.Request(a.api_url,method="GET",
                                   headers={"User-Agent":"ChaCha-DEV-CollectorKnowledge-Probe/1"})
        started=time.monotonic()
        try:
            with opener.open(req,timeout=max(.5,min(a.timeout,15))) as response:
                http_status=int(response.status)
                body=response.read(65537)
            if len(body)>65536:
                blockers.append("PROBE_RESPONSE_TOO_LARGE")
                body=body[:65536]
            body_digest="sha256:"+hashlib.sha256(body).hexdigest()
            try:
                value=json.loads(body.decode("utf-8"))
                json_valid=isinstance(value,dict)
            except Exception:
                json_valid=False
            if http_status!=200:blockers.append("KNOWLEDGE_API_HTTP_STATUS:"+str(http_status))
            if not json_valid:blockers.append("KNOWLEDGE_API_JSON_INVALID")
        except urllib.error.HTTPError as exc:
            http_status=int(exc.code)
            blockers.append("KNOWLEDGE_API_HTTP_STATUS:"+str(http_status))
        except Exception as exc:
            blockers.append("KNOWLEDGE_API_TRANSPORT:"+type(exc).__name__)
        latency_ms=round((time.monotonic()-started)*1000,3)

    state="HEALTHY" if not blockers else "UNAVAILABLE"
    checked=now_iso()
    basis={
      "provider":PROVIDER,"state":state,"target":safe_url(a.api_url),
      "worker_state":worker_state,"api_state":api_state,"http_status":http_status,
      "json_valid":json_valid,"executable_digest":executable_digest,"blockers":blockers
    }
    evidence_digest="sha256:"+hashlib.sha256(
        json.dumps(basis,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    out={
      "schema":SCHEMA,"provider":PROVIDER,"state":state,
      "source":"collector-knowledge-independent-local-probe",
      "checked_at":checked,"latency_ms":latency_ms,
      "reason":"healthy" if not blockers else ";".join(blockers),
      "details":{
        "target":safe_url(a.api_url),
        "worker_unit":a.worker_unit,"worker_state":worker_state,
        "api_unit":a.api_unit,"api_state":api_state,
        "http_status":http_status,"json_valid":json_valid,
        "body_digest":body_digest,
        "executable":str(a.executable),"executable_digest":executable_digest,
        "independent_from_adapter_execution":True,
        "loopback_only":True,
        "lastwar_connection":"NONE",
        "mutations":False,
        "blockers":blockers
      },
      "evidence_digest":evidence_digest
    }
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(out,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print("PROVIDER_PROBE_RESULT="+str(a.output))
    print("PROVIDER="+PROVIDER)
    print("STATE="+state)
    for b in blockers:print("BLOCKER="+b)
    return 0 if state=="HEALTHY" else 2

if __name__=="__main__":
    raise SystemExit(main())
