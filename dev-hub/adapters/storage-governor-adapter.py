#!/usr/bin/env python3
"""ChaCha DEV HUB Storage Governor Adapter V1.

Policy-owned storage operations for WfGg. V1 supports:
- assess: read-only local/NAS capacity assessment through nas-ssh-adapter
- collector-master-snapshot: create exactly one immutable, logical SQLite
  MASTER dump of the active Collector DB, gzip-streamed directly to the NAS.

The Collector database is opened read-only and held in a SQLite read
transaction for a coherent logical snapshot. No local full-size snapshot is
created, and the Collector service is never stopped.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

INPUT_SCHEMA="chacha.dev/dispatch-envelope/v1"
OUTPUT_SCHEMA="chacha.dev/task-result/v1"
ADAPTER_ID="storage-governor-adapter"
PROVIDER_ID="storage-governor"
NAS_PROVIDER_ID="nas"
NAS_ADAPTER_ID="nas-ssh-adapter"

DEFAULT_DB=Path("/opt/wfgg-collector/data/collector.db")
DEFAULT_NAS_ADAPTER=Path("/opt/chacha-dev/adapters/nas-ssh/current/nas-ssh-adapter")
DEFAULT_NAS_HOST="chachanas"
DEFAULT_NAS_ROOT="/share/CACHEDEV1_DATA/ChaCha-DEV-HUB"
BACKUP_REL_ROOT="projects/wfgg/backups"
SAFE_TOKEN=re.compile(r"^[A-Za-z0-9._/-]+$")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_bytes(value: bytes) -> str:
    return "sha256:"+hashlib.sha256(value).hexdigest()


def result(request: dict[str,Any], status: str, summary: str,
           evidence: list[dict[str,Any]]|None=None,
           outputs: list[dict[str,Any]]|None=None) -> dict[str,Any]:
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
            "status":"UNVERIFIED",
            "method":"none",
            "verifier":"pending-independent-verifier",
            "observed_at":now_iso(),
            "notes":"Storage Governor cannot self-verify its own snapshot."
        },
        "outputs":outputs or [],
    }


def emit(payload: dict[str,Any], code: int=0) -> int:
    sys.stdout.write(json.dumps(payload,ensure_ascii=False,separators=(",",":"))+"\n")
    return code


def blocked(request: dict[str,Any], reason: str) -> int:
    return emit(result(request,"BLOCKED",reason,[{
        "kind":"report",
        "source":"storage-governor-policy",
        "digest":sha256_bytes(reason.encode()),
        "details":{"reason":reason},
    }]))


def validate_request(request: dict[str,Any]) -> tuple[dict[str,Any]|None,str|None]:
    if request.get("schema")!=INPUT_SCHEMA:
        return None,"INPUT_SCHEMA_INVALID"
    task=request.get("task")
    if not isinstance(task,dict) or not task.get("id"):
        return None,"TASK_ID_MISSING"
    bindings=request.get("bindings")
    if not isinstance(bindings,list) or not any(
        isinstance(x,dict) and x.get("provider")==PROVIDER_ID and x.get("adapter")==ADAPTER_ID
        for x in bindings
    ):
        return None,"STORAGE_GOVERNOR_BINDING_MISSING"
    metadata=request.get("metadata")
    cfg=metadata.get("storage_governor") if isinstance(metadata,dict) else None
    if not isinstance(cfg,dict):
        return None,"STORAGE_GOVERNOR_METADATA_MISSING"
    action=str(cfg.get("action") or "")
    permission=str(task.get("permission") or "")
    if action=="assess" and permission!="read":
        return None,"STORAGE_ASSESS_REQUIRES_READ"
    if action=="collector-master-snapshot" and permission!="workspace-write":
        return None,"COLLECTOR_MASTER_REQUIRES_WORKSPACE_WRITE"
    if action not in {"assess","collector-master-snapshot"}:
        return None,"STORAGE_GOVERNOR_ACTION_NOT_ALLOWED"
    return cfg,None


def run(argv: list[str], timeout: int=30, stdin: bytes|None=None) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        argv,
        input=stdin,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        shell=False,
        check=False,
    )


def nas_host() -> str:
    host=os.environ.get("CHACHA_NAS_HOST",DEFAULT_NAS_HOST).strip()
    if not re.fullmatch(r"[A-Za-z0-9._-]+",host):
        raise ValueError("NAS_HOST_INVALID")
    return host


def nas_root() -> str:
    root=os.environ.get("CHACHA_NAS_ROOT",DEFAULT_NAS_ROOT).strip().rstrip("/")
    if not root.startswith("/") or ".." in Path(root).parts:
        raise ValueError("NAS_ROOT_INVALID")
    return root


def nas_adapter_path() -> Path:
    return Path(os.environ.get("CHACHA_NAS_ADAPTER",str(DEFAULT_NAS_ADAPTER))).resolve()


def db_path() -> Path:
    return Path(os.environ.get("WFGG_COLLECTOR_DB",str(DEFAULT_DB))).resolve()


def child_preflight(request: dict[str,Any], need_mb: float) -> dict[str,Any]:
    adapter=nas_adapter_path()
    if not adapter.is_file():
        raise RuntimeError("NAS_ADAPTER_RUNTIME_MISSING")
    envelope={
        "schema":INPUT_SCHEMA,
        "project":str(request.get("project") or "wfgg-radar"),
        "transition":"storage-governor-preflight",
        "run_id":str(request.get("run_id") or "storage-governor"),
        "wave":1,
        "task":{
            "id":"storage-governor-nas-preflight",
            "kind":"storage-preflight",
            "description":"Storage Governor delegated NAS preflight.",
            "owner_role":"storage-governor",
            "permission":"read",
            "outputs":[{"type":"gate","id":"storage-preflight"}],
            "verification":{"required":True,"mode":"machine"},
        },
        "bindings":[{
            "capability":"backup-store",
            "provider":NAS_PROVIDER_ID,
            "adapter":NAS_ADAPTER_ID,
            "fallback_used":False,
            "health_state":"pilot",
        }],
        "policy_context":{
            "resource_class":"heavy",
            "requires_storage_preflight":True,
            "human_approval_required":False,
            "approval_id":None,
            "timeout_seconds":30,
        },
        "workspace":str(db_path().parent),
        "metadata":{"nas_storage":{"action":"preflight","need_mb":need_mb,"reserve_mb":1024}},
    }
    proc=run([str(adapter)],timeout=40,stdin=json.dumps(envelope).encode())
    if proc.returncode!=0:
        raise RuntimeError("NAS_PREFLIGHT_ADAPTER_FAILED")
    value=json.loads(proc.stdout.decode())
    if value.get("status")!="OK" or value.get("summary")!="NAS_PREFLIGHT_OK":
        raise RuntimeError("NAS_PREFLIGHT_BLOCKED")
    return value


def ssh_base() -> list[str]:
    return ["/usr/bin/ssh","-o","BatchMode=yes","-o","ConnectTimeout=12",nas_host()]


def remote_exists(path: str) -> bool:
    proc=run(ssh_base()+["test","-e",path],timeout=20)
    return proc.returncode==0


def existing_master_files() -> list[str]:
    root=f"{nas_root()}/{BACKUP_REL_ROOT}"
    proc=run(
        ssh_base()+["find",root,"-maxdepth","1","-type","f","-name","collector-master-*.sql.gz","-print"],
        timeout=30,
    )
    if proc.returncode not in {0,1}:
        raise RuntimeError("NAS_MASTER_DISCOVERY_FAILED")
    return [x.strip() for x in proc.stdout.decode("utf-8","replace").splitlines() if x.strip()]


class HashingWriter:
    def __init__(self, raw):
        self.raw=raw
        self.hash=hashlib.sha256()
        self.count=0
    def write(self,data: bytes) -> int:
        self.hash.update(data)
        self.count+=len(data)
        self.raw.write(data)
        self.raw.flush()
        return len(data)
    def flush(self) -> None:
        self.raw.flush()


def sqlite_metadata(path: Path) -> dict[str,Any]:
    uri=f"file:{path}?mode=ro"
    conn=sqlite3.connect(uri,uri=True,timeout=10)
    try:
        journal=conn.execute("PRAGMA journal_mode").fetchone()[0]
        page_count=int(conn.execute("PRAGMA page_count").fetchone()[0])
        page_size=int(conn.execute("PRAGMA page_size").fetchone()[0])
        tables=int(conn.execute("SELECT count(*) FROM sqlite_master WHERE type='table'").fetchone()[0])
        user_version=int(conn.execute("PRAGMA user_version").fetchone()[0])
        return {
            "journal_mode":str(journal),
            "page_count":page_count,
            "page_size":page_size,
            "logical_bytes":page_count*page_size,
            "table_count":tables,
            "user_version":user_version,
        }
    finally:
        conn.close()


def stream_master_dump(path: Path, remote_temp: str) -> tuple[str,int,int]:
    # Fixed, policy-owned remote path. Local shell is never used.
    remote_cmd=f"umask 077; cat > '{remote_temp}'"
    ssh=subprocess.Popen(
        ["/usr/bin/ssh","-o","BatchMode=yes","-o","ConnectTimeout=12",nas_host(),remote_cmd],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=False,
    )
    if ssh.stdin is None:
        raise RuntimeError("NAS_STREAM_STDIN_MISSING")
    writer=HashingWriter(ssh.stdin)
    line_count=0
    uri=f"file:{path}?mode=ro"
    conn=sqlite3.connect(uri,uri=True,timeout=30,isolation_level=None)
    try:
        conn.execute("BEGIN")
        with gzip.GzipFile(fileobj=writer,mode="wb",compresslevel=6,mtime=0) as gz:
            for line in conn.iterdump():
                gz.write(line.encode("utf-8"))
                gz.write(b"\n")
                line_count+=1
        conn.execute("ROLLBACK")
    finally:
        conn.close()
        try:
            ssh.stdin.close()
        except Exception:
            pass
    rc=ssh.wait(timeout=300)
    if rc!=0:
        err=ssh.stderr.read(4096).decode("utf-8","replace") if ssh.stderr else ""
        raise RuntimeError("NAS_STREAM_FAILED:"+err[:120])
    return writer.hash.hexdigest(),writer.count,line_count


def write_manifest_via_nas_adapter(request: dict[str,Any], manifest: dict[str,Any], remote_rel: str) -> dict[str,Any]:
    adapter=nas_adapter_path()
    with tempfile.TemporaryDirectory(prefix="chacha-storage-governor-") as td:
        workspace=Path(td)
        local=workspace/"manifest.json"
        local.write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
        envelope={
            "schema":INPUT_SCHEMA,
            "project":str(request.get("project") or "wfgg-radar"),
            "transition":"collector-master-manifest",
            "run_id":str(request.get("run_id") or "storage-governor"),
            "wave":1,
            "task":{
                "id":"collector-master-manifest",
                "kind":"backup-manifest",
                "description":"Publish immutable Collector master manifest.",
                "owner_role":"storage-governor",
                "permission":"workspace-write",
                "outputs":[{"type":"artifact","id":remote_rel}],
                "verification":{"required":True,"mode":"machine"},
            },
            "bindings":[{
                "capability":"backup-store",
                "provider":NAS_PROVIDER_ID,
                "adapter":NAS_ADAPTER_ID,
                "fallback_used":False,
                "health_state":"pilot",
            }],
            "policy_context":{
                "resource_class":"light",
                "requires_storage_preflight":False,
                "human_approval_required":False,
                "approval_id":None,
                "timeout_seconds":30,
            },
            "workspace":str(workspace),
            "metadata":{"nas_storage":{
                "action":"put-file",
                "local_path":"manifest.json",
                "remote_path":remote_rel,
                "reserve_mb":1024,
            }},
        }
        proc=run([str(adapter)],timeout=40,stdin=json.dumps(envelope).encode())
        if proc.returncode!=0:
            raise RuntimeError("NAS_MANIFEST_ADAPTER_FAILED")
        value=json.loads(proc.stdout.decode())
        if value.get("status")!="OK":
            raise RuntimeError("NAS_MANIFEST_PUBLISH_FAILED")
        return value


def assess(request: dict[str,Any]) -> int:
    path=db_path()
    if not path.is_file():
        return blocked(request,"COLLECTOR_DB_MISSING")
    meta=sqlite_metadata(path)
    need_mb=max(path.stat().st_size/(1024*1024)*2,1024)
    preflight=child_preflight(request,need_mb)
    free=os.statvfs("/")
    free_mb=(free.f_bavail*free.f_frsize)/(1024*1024)
    evidence=[
        {
            "kind":"metric",
            "source":"vps://root",
            "digest":sha256_bytes(str(round(free_mb,2)).encode()),
            "details":{"free_mb":round(free_mb,2)},
        },
        {
            "kind":"file",
            "source":str(path),
            "digest":sha256_bytes(json.dumps(meta,sort_keys=True).encode()),
            "details":meta,
        },
    ]+list(preflight.get("evidence") or [])
    return emit(result(request,"OK","STORAGE_GOVERNOR_ASSESS_OK",evidence,[{
        "type":"gate","id":"collector-master-readiness","status":"OK",
        "reason":"Collector DB readable; NAS delegated preflight passed.",
    }]))


def collector_master(request: dict[str,Any]) -> int:
    path=db_path()
    if not path.is_file():
        return blocked(request,"COLLECTOR_DB_MISSING")
    if existing_master_files():
        return blocked(request,"COLLECTOR_MASTER_ALREADY_EXISTS")

    meta=sqlite_metadata(path)
    need_mb=max(path.stat().st_size/(1024*1024)*2,1024)
    child_preflight(request,need_mb)

    stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archive_name=f"collector-master-{stamp}.sql.gz"
    manifest_name=f"collector-master-{stamp}.manifest.json"
    archive_rel=f"{BACKUP_REL_ROOT}/{archive_name}"
    manifest_rel=f"{BACKUP_REL_ROOT}/{manifest_name}"
    final=f"{nas_root()}/{archive_rel}"
    temp=final+".incoming"

    if remote_exists(final) or remote_exists(temp):
        return blocked(request,"COLLECTOR_MASTER_DESTINATION_COLLISION")

    digest=""
    compressed_bytes=0
    line_count=0
    try:
        digest,compressed_bytes,line_count=stream_master_dump(path,temp)
        proc=run(ssh_base()+["sha256sum",temp],timeout=60)
        if proc.returncode!=0:
            raise RuntimeError("COLLECTOR_MASTER_REMOTE_HASH_FAILED")
        remote_hash=proc.stdout.decode("utf-8","replace").split()[0].strip()
        if remote_hash!=digest:
            raise RuntimeError("COLLECTOR_MASTER_SHA256_MISMATCH")
        move=run(ssh_base()+["mv",temp,final],timeout=30)
        if move.returncode!=0:
            raise RuntimeError("COLLECTOR_MASTER_ATOMIC_PUBLISH_FAILED")
    except Exception:
        run(ssh_base()+["rm","-f",temp],timeout=20)
        raise

    manifest={
        "schema":"chacha.dev/collector-master-snapshot/v1",
        "created_at":now_iso(),
        "source_db":str(path),
        "snapshot_kind":"MASTER",
        "immutable":True,
        "consistency":"sqlite-read-transaction-logical-dump",
        "collector_service_stopped":False,
        "archive":archive_rel,
        "archive_sha256":"sha256:"+digest,
        "compressed_bytes":compressed_bytes,
        "dump_lines":line_count,
        "db_metadata":meta,
        "restore_format":"gzip-compressed SQLite SQL dump",
        "incremental_chain_started":False,
        "notes":"MASTER baseline only. Incremental cycle-watermark backups are a later storage-governor stage.",
    }
    write_manifest_via_nas_adapter(request,manifest,manifest_rel)

    evidence=[{
        "kind":"file",
        "source":"nas://"+nas_host()+"/"+archive_rel,
        "digest":"sha256:"+digest,
        "details":{
            "snapshot_kind":"MASTER",
            "compressed_bytes":compressed_bytes,
            "dump_lines":line_count,
            "consistency":"sqlite-read-transaction",
            "service_stopped":False,
        },
    }]
    return emit(result(request,"OK","COLLECTOR_MASTER_SNAPSHOT_CREATED",evidence,[
        {"type":"artifact","id":archive_rel,"status":"UNVERIFIED","reason":"Awaiting independent restore/hash verifier."},
        {"type":"artifact","id":manifest_rel,"status":"UNVERIFIED","reason":"Published through nas-ssh-adapter."},
    ]))


def main() -> int:
    try:
        request=json.load(sys.stdin)
    except Exception as exc:
        minimal={"project":"unknown","task":{"id":"unknown"}}
        return emit(result(minimal,"BLOCKED",f"INPUT_JSON_INVALID:{type(exc).__name__}"),2)
    if not isinstance(request,dict):
        minimal={"project":"unknown","task":{"id":"unknown"}}
        return emit(result(minimal,"BLOCKED","INPUT_ROOT_NOT_OBJECT"),2)

    cfg,error=validate_request(request)
    if error:
        return blocked(request,error)
    assert cfg is not None

    try:
        if cfg.get("action")=="assess":
            return assess(request)
        return collector_master(request)
    except subprocess.TimeoutExpired:
        return emit(result(request,"FAILED","STORAGE_GOVERNOR_TIMEOUT"))
    except Exception as exc:
        reason=f"STORAGE_GOVERNOR_RUNTIME_FAILED:{type(exc).__name__}:{str(exc)[:160]}"
        return emit(result(request,"FAILED",reason))


if __name__=="__main__":
    raise SystemExit(main())
