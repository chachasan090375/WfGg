#!/usr/bin/env python3
"""ChaCha DEV HUB Storage Governor Adapter V1.

Policy-owned storage operations for WfGg. V1 supports:
- assess: read-only local/NAS capacity assessment through nas-ssh-adapter
- collector-incremental-discovery: schema-only discovery of safe incremental
  watermark candidates without exposing application row data
- collector-incremental-plan: classify every table into a deterministic
  cycle/time/full-table backup policy using schema and aggregate counts only
- collector-incremental-anchor: create exactly one immutable chain anchor
  bound to the validated MASTER and its baseline watermarks
- collector-incremental-package: prepare one immutable patch candidate per
  completed cycle after the anchor, without advancing committed chain state
- collector-incremental-commit: advance chain state only after an independent
  VERIFIED receipt matches both candidate and package digests
- collector-master-snapshot: create exactly one immutable, logical SQLite
  MASTER dump of the active Collector DB, gzip-streamed directly to the NAS.

The Collector database is opened read-only and held in a SQLite read
transaction for a coherent logical snapshot. No local full-size snapshot is
created, and the Collector service is never stopped.
"""
from __future__ import annotations

import gzip
import hashlib
import importlib.util
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
CHAIN_REL_ROOT=BACKUP_REL_ROOT+"/collector-chain"
CHAIN_HELPER_FILE="storage-governor-incremental-chain.py"
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
    if action in {"assess","collector-incremental-discovery","collector-incremental-plan"} and permission!="read":
        return None,"STORAGE_READ_ACTION_REQUIRES_READ"
    if action in {"collector-master-snapshot","collector-incremental-anchor","collector-incremental-package","collector-incremental-commit"} and permission!="workspace-write":
        return None,"STORAGE_WRITE_ACTION_REQUIRES_WORKSPACE_WRITE"
    if action not in {"assess","collector-incremental-discovery","collector-incremental-plan","collector-incremental-anchor","collector-incremental-package","collector-incremental-commit","collector-master-snapshot"}:
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
    rc=ssh.wait(timeout=1800)
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


def quote_ident(value: str) -> str:
    return '"' + value.replace('"','""') + '"'


def collector_incremental_discovery(request: dict[str,Any]) -> int:
    path=db_path()
    if not path.is_file():
        return blocked(request,"COLLECTOR_DB_MISSING")
    uri=f"file:{path}?mode=ro"
    conn=sqlite3.connect(uri,uri=True,timeout=15)
    inventory=[]
    try:
        tables=[
            str(row[0]) for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            ).fetchall()
        ]
        for table in tables:
            q=quote_ident(table)
            cols=[]
            candidates=[]
            for row in conn.execute(f"PRAGMA table_info({q})").fetchall():
                cid,name,ctype,notnull,default_value,pk=row
                name=str(name)
                ctype=str(ctype or "")
                lower=name.lower()
                normalized=lower.replace("_","")
                candidate_kind=None
                sample=None
                if "cycle" in normalized:
                    candidate_kind="cycle-watermark"
                elif lower in {"updated_at","observed_at","created_at","timestamp","ts"} or lower.endswith("_at"):
                    candidate_kind="time-watermark"
                elif int(pk or 0)>0 and lower in {"id","row_id","rowid","seq","sequence"}:
                    candidate_kind="monotonic-pk"
                if candidate_kind in {"cycle-watermark","time-watermark"}:
                    try:
                        max_value=conn.execute(
                            f"SELECT MAX({quote_ident(name)}) FROM {q}"
                        ).fetchone()[0]
                        if max_value is not None and isinstance(max_value,(int,float,str)):
                            sample={"max":str(max_value)[:128]}
                    except Exception:
                        sample=None
                col={
                    "name":name,
                    "type":ctype,
                    "notnull":bool(notnull),
                    "pk_order":int(pk or 0),
                }
                cols.append(col)
                if candidate_kind:
                    item={"column":name,"kind":candidate_kind}
                    if sample is not None:
                        item["aggregate"]=sample
                    candidates.append(item)
            indexes=[]
            try:
                for idx in conn.execute(f"PRAGMA index_list({q})").fetchall():
                    if len(idx)>=3:
                        indexes.append({"name":str(idx[1]),"unique":bool(idx[2])})
            except Exception:
                pass
            inventory.append({
                "table":table,
                "columns":cols,
                "indexes":indexes,
                "watermark_candidates":candidates,
            })
    finally:
        conn.close()

    safe={
        "source_db":str(path),
        "table_count":len(inventory),
        "tables":inventory,
        "raw_row_data_exposed":False,
    }
    digest=sha256_bytes(json.dumps(safe,sort_keys=True,separators=(",",":")).encode())
    candidate_tables=[
        {
            "table":x["table"],
            "watermark_candidates":x["watermark_candidates"],
        }
        for x in inventory if x["watermark_candidates"]
    ]
    evidence=[{
        "kind":"report",
        "source":"collector-schema://incremental-discovery",
        "digest":digest,
        "details":{
            "table_count":len(inventory),
            "candidate_table_count":len(candidate_tables),
            "candidate_tables":candidate_tables,
            "raw_row_data_exposed":False,
        },
    }]
    return emit(result(request,"OK","COLLECTOR_INCREMENTAL_DISCOVERY_OK",evidence,[{
        "type":"report",
        "id":"collector-incremental-schema",
        "status":"UNVERIFIED",
        "reason":"Schema-only discovery; incremental strategy still requires policy selection.",
    }]))


def table_schema(conn: sqlite3.Connection, table: str) -> dict[str,Any]:
    q=quote_ident(table)
    columns=[]
    pk=[]
    for row in conn.execute(f"PRAGMA table_info({q})").fetchall():
        cid,name,ctype,notnull,default_value,pk_order=row
        item={
            "name":str(name),
            "type":str(ctype or ""),
            "notnull":bool(notnull),
            "pk_order":int(pk_order or 0),
        }
        columns.append(item)
        if item["pk_order"]>0:
            pk.append((item["pk_order"],item["name"]))
    pk=[name for _,name in sorted(pk)]
    count=int(conn.execute(f"SELECT COUNT(*) FROM {q}").fetchone()[0])
    return {"table":table,"columns":columns,"pk":pk,"row_count":count}


def choose_incremental_policy(meta: dict[str,Any]) -> dict[str,Any]:
    table=meta["table"]
    names=[x["name"] for x in meta["columns"]]
    lower={x.lower():x for x in names}

    cycle_candidates=[
        x for x in names
        if "cycle" in x.lower().replace("_","")
    ]
    preferred_cycle=None
    for wanted in ("cycle_id","last_change_cycle"):
        if wanted in lower:
            preferred_cycle=lower[wanted]
            break
    if preferred_cycle is None and cycle_candidates:
        preferred_cycle=cycle_candidates[0]

    time_candidates=[
        x for x in names
        if x.lower() in {"updated_at","observed_at","created_at","changed_at","started_at","finished_at","timestamp","ts"}
        or x.lower().endswith("_at")
    ]

    if table=="cycles" and "id" in lower:
        return {
            "mode":"cycle-id",
            "watermark_columns":[lower["id"]],
            "reason":"cycles table uses monotonic primary cycle id",
        }
    if preferred_cycle:
        return {
            "mode":"cycle-watermark",
            "watermark_columns":[preferred_cycle],
            "reason":"table exposes an explicit cycle watermark",
        }
    if time_candidates:
        ordered=[]
        preferred=("observed_at","changed_at","updated_at","created_at","finished_at","started_at","timestamp","ts")
        for p in preferred:
            if p in lower and lower[p] in time_candidates and lower[p] not in ordered:
                ordered.append(lower[p])
        for x in time_candidates:
            if x not in ordered:
                ordered.append(x)
        tie=meta["pk"][0] if meta["pk"] else None
        cols=[ordered[0]]+([tie] if tie and tie!=ordered[0] else [])
        return {
            "mode":"time-watermark",
            "watermark_columns":cols,
            "reason":"table exposes a timestamp watermark"+(" with PK tie-breaker" if tie else ""),
        }
    # These are bounded current-state/dimension tables. They intentionally
    # carry no intrinsic change watermark, so a complete refresh inside each
    # incremental package is safer than inventing a synthetic watermark.
    # The explicit allowlist is schema-policy, not a generic size heuristic.
    dimension_full_refresh={"master_players","player_aliases","player_identity"}
    if table in dimension_full_refresh:
        return {
            "mode":"full-table-dimension",
            "watermark_columns":[],
            "reason":"current-state dimension table without safe intrinsic watermark; refresh atomically per incremental package",
        }
    if meta["row_count"]<=10000:
        return {
            "mode":"full-table-small",
            "watermark_columns":[],
            "reason":"no safe watermark; bounded aggregate row count allows full-table refresh",
        }
    return {
        "mode":"blocked-unclassified",
        "watermark_columns":[],
        "reason":"no safe watermark and table too large for blind full-table increments",
    }


def collector_incremental_plan(request: dict[str,Any]) -> int:
    path=db_path()
    if not path.is_file():
        return blocked(request,"COLLECTOR_DB_MISSING")
    uri=f"file:{path}?mode=ro"
    conn=sqlite3.connect(uri,uri=True,timeout=20)
    try:
        tables=[
            str(row[0]) for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            ).fetchall()
        ]
        plans=[]
        for table in tables:
            meta=table_schema(conn,table)
            policy=choose_incremental_policy(meta)
            aggregates={}
            for col in policy["watermark_columns"]:
                try:
                    q=quote_ident(table)
                    value=conn.execute(f"SELECT MAX({quote_ident(col)}) FROM {q}").fetchone()[0]
                    if value is not None:
                        aggregates[col]=str(value)[:128]
                except Exception:
                    pass
            plans.append({
                "table":table,
                "row_count":meta["row_count"],
                "pk":meta["pk"],
                "mode":policy["mode"],
                "watermark_columns":policy["watermark_columns"],
                "current_max":aggregates,
                "reason":policy["reason"],
            })
    finally:
        conn.close()

    blocked_tables=[x["table"] for x in plans if x["mode"]=="blocked-unclassified"]
    summary={
        "source_db":str(path),
        "table_count":len(plans),
        "plans":plans,
        "blocked_tables":blocked_tables,
        "raw_row_data_exposed":False,
    }
    digest=sha256_bytes(json.dumps(summary,sort_keys=True,separators=(",",":")).encode())
    evidence=[{
        "kind":"report",
        "source":"collector-schema://incremental-plan",
        "digest":digest,
        "details":summary,
    }]
    status="OK" if not blocked_tables else "BLOCKED"
    label="COLLECTOR_INCREMENTAL_PLAN_OK" if status=="OK" else "COLLECTOR_INCREMENTAL_PLAN_REQUIRES_CLASSIFICATION"
    return emit(result(request,status,label,evidence,[{
        "type":"report",
        "id":"collector-incremental-plan",
        "status":"UNVERIFIED",
        "reason":"Schema/aggregate-only policy plan; no application rows exposed.",
    }]))


def load_chain_helper():
    path=Path(__file__).resolve().with_name(CHAIN_HELPER_FILE)
    if not path.is_file():
        raise RuntimeError("INCREMENTAL_CHAIN_HELPER_MISSING")
    spec=importlib.util.spec_from_file_location("storage_governor_incremental_chain",path)
    if spec is None or spec.loader is None:
        raise RuntimeError("INCREMENTAL_CHAIN_HELPER_LOAD_FAILED")
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def ensure_chain_dirs() -> None:
    root=f"{nas_root()}/{CHAIN_REL_ROOT}"
    proc=run(ssh_base()+["mkdir","-p",root,root+"/incrementals"],timeout=30)
    if proc.returncode!=0:
        raise RuntimeError("CHAIN_DIRECTORY_CREATE_FAILED")


def list_chain_state_files() -> list[str]:
    root=f"{nas_root()}/{CHAIN_REL_ROOT}"
    proc=run(
        ssh_base()+[
            "find",root,"-maxdepth","1","-type","f",
            "-name","collector-chain-state-*.json","-print"
        ],
        timeout=30,
    )
    if proc.returncode not in {0,1}:
        raise RuntimeError("CHAIN_STATE_DISCOVERY_FAILED")
    return sorted(x.strip() for x in proc.stdout.decode("utf-8","replace").splitlines() if x.strip())


def read_remote_json(path: str) -> dict[str,Any]:
    proc=run(ssh_base()+["cat",path],timeout=30)
    if proc.returncode!=0:
        raise RuntimeError("CHAIN_STATE_READ_FAILED")
    value=json.loads(proc.stdout.decode("utf-8"))
    if not isinstance(value,dict):
        raise RuntimeError("CHAIN_STATE_INVALID")
    return value


def write_json_via_nas_adapter(
    request: dict[str,Any],
    document: dict[str,Any],
    remote_rel: str,
    task_id: str,
    description: str,
) -> dict[str,Any]:
    adapter=nas_adapter_path()
    with tempfile.TemporaryDirectory(prefix="chacha-storage-governor-json-") as td:
        workspace=Path(td)
        local=workspace/"document.json"
        local.write_text(json.dumps(document,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
        envelope={
            "schema":INPUT_SCHEMA,
            "project":str(request.get("project") or "wfgg-radar"),
            "transition":task_id,
            "run_id":str(request.get("run_id") or "storage-governor"),
            "wave":1,
            "task":{
                "id":task_id,
                "kind":"backup-manifest",
                "description":description,
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
                "local_path":"document.json",
                "remote_path":remote_rel,
                "reserve_mb":1024,
            }},
        }
        proc=run([str(adapter)],timeout=40,stdin=json.dumps(envelope).encode())
        if proc.returncode!=0:
            raise RuntimeError("NAS_JSON_ADAPTER_FAILED")
        value=json.loads(proc.stdout.decode())
        if value.get("status")!="OK":
            raise RuntimeError("NAS_JSON_PUBLISH_FAILED:"+str(value.get("summary")))
        return value


def collector_incremental_anchor(request: dict[str,Any], cfg: dict[str,Any]) -> int:
    helper=load_chain_helper()
    ensure_chain_dirs()
    existing=list_chain_state_files()
    if existing:
        return blocked(request,"COLLECTOR_INCREMENTAL_CHAIN_ALREADY_ANCHORED")

    master_archive=str(cfg.get("master_archive") or "")
    master_sha=str(cfg.get("master_sha256") or "")
    master_created_at=str(cfg.get("master_created_at") or "")
    baseline_cycle=int(cfg.get("baseline_cycle") or 0)
    obs=dict(cfg.get("observations_watermark") or {})
    masters=dict(cfg.get("masters_watermark") or {})
    plan_digest=str(cfg.get("plan_digest") or "")

    if not master_archive.startswith(BACKUP_REL_ROOT+"/collector-master-"):
        return blocked(request,"CHAIN_MASTER_ARCHIVE_INVALID")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}",master_sha):
        return blocked(request,"CHAIN_MASTER_SHA_INVALID")
    if baseline_cycle<=0 or not master_created_at:
        return blocked(request,"CHAIN_BASELINE_INVALID")
    if not plan_digest.startswith("sha256:"):
        return blocked(request,"CHAIN_PLAN_DIGEST_INVALID")

    remote_master=f"{nas_root()}/{master_archive}"
    proc=run(ssh_base()+["sha256sum",remote_master],timeout=120)
    if proc.returncode!=0:
        return blocked(request,"CHAIN_MASTER_REMOTE_HASH_FAILED")
    remote_hash=proc.stdout.decode("utf-8","replace").split()[0].strip()
    if "sha256:"+remote_hash != master_sha:
        return blocked(request,"CHAIN_MASTER_SHA_MISMATCH")

    state=helper.make_anchor_state(
        master_archive=master_archive,
        master_sha256=master_sha,
        master_created_at=master_created_at,
        baseline_cycle=baseline_cycle,
        observations_watermark=obs,
        masters_watermark=masters,
        plan_digest=plan_digest,
    )
    remote_rel=f"{CHAIN_REL_ROOT}/collector-chain-state-000000.json"
    write_json_via_nas_adapter(
        request,state,remote_rel,
        "collector-incremental-anchor",
        "Publish immutable Collector incremental chain anchor.",
    )
    digest=sha256_bytes(json.dumps(state,sort_keys=True,separators=(",",":")).encode())
    evidence=[{
        "kind":"file",
        "source":"nas://"+nas_host()+"/"+remote_rel,
        "digest":digest,
        "details":{
            "sequence":0,
            "baseline_cycle":baseline_cycle,
            "master_archive":master_archive,
            "master_sha256":master_sha,
            "raw_row_data_exposed":False,
        },
    }]
    return emit(result(request,"OK","COLLECTOR_INCREMENTAL_CHAIN_ANCHORED",evidence,[{
        "type":"artifact","id":remote_rel,"status":"UNVERIFIED",
        "reason":"Immutable anchor published; independent chain verifier pending.",
    }]))


class LineHashingGzipWriter:
    def __init__(self, raw):
        self.raw=raw
        self.hash=hashlib.sha256()
        self.compressed_bytes=0
        self.lines=0
        self._hashing=HashingWriter(raw)
        self.gz=gzip.GzipFile(fileobj=self._hashing,mode="wb",compresslevel=6,mtime=0)
    def line(self,value: str) -> None:
        data=(value+"\n").encode("utf-8")
        self.gz.write(data)
        self.lines+=1
    def close(self) -> None:
        self.gz.close()
        self.compressed_bytes=self._hashing.count
        self.hash=self._hashing.hash


def latest_chain_state() -> tuple[str,dict[str,Any]]:
    files=list_chain_state_files()
    if not files:
        raise RuntimeError("COLLECTOR_INCREMENTAL_CHAIN_NOT_ANCHORED")
    path=files[-1]
    return path,read_remote_json(path)


def incremental_candidate_rel(sequence: int) -> str:
    return f"{CHAIN_REL_ROOT}/collector-chain-candidate-{sequence:06d}.json"


def incremental_verification_rel(sequence: int) -> str:
    return f"{CHAIN_REL_ROOT}/collector-chain-verification-{sequence:06d}.json"


def collector_incremental_package(request: dict[str,Any]) -> int:
    helper=load_chain_helper()
    ensure_chain_dirs()
    state_path,state=latest_chain_state()
    if state.get("schema")!=helper.CHAIN_SCHEMA:
        return blocked(request,"CHAIN_STATE_SCHEMA_INVALID")

    sequence=int(state.get("sequence") or 0)
    expected_name=f"collector-chain-state-{sequence:06d}.json"
    if not state_path.endswith("/"+expected_name):
        return blocked(request,"CHAIN_STATE_SEQUENCE_MISMATCH")

    next_seq=sequence+1
    candidate_rel=incremental_candidate_rel(next_seq)
    candidate_abs=f"{nas_root()}/{candidate_rel}"
    if remote_exists(candidate_abs):
        candidate=read_remote_json(candidate_abs)
        evidence=[{
            "kind":"file",
            "source":"nas://"+nas_host()+"/"+candidate_rel,
            "digest":sha256_bytes(json.dumps(candidate,sort_keys=True,separators=(",",":")).encode()),
            "details":{
                "sequence":next_seq,
                "status":candidate.get("status"),
                "candidate_reused":True,
            },
        }]
        return emit(result(request,"OK","COLLECTOR_INCREMENTAL_CANDIDATE_EXISTS",evidence,[{
            "type":"artifact","id":candidate_rel,"status":"UNVERIFIED",
            "reason":"Existing immutable candidate awaits independent verification.",
        }]))

    child_preflight(request,512)
    path=db_path()
    if not path.is_file():
        return blocked(request,"COLLECTOR_DB_MISSING")

    uri=f"file:{path}?mode=ro"
    conn=sqlite3.connect(uri,uri=True,timeout=30,isolation_level=None)
    try:
        conn.execute("BEGIN")
        from_cycle=int((state.get("watermarks") or {}).get("cycle") or 0)
        target=helper.next_completed_cycle(conn,from_cycle)
        if target is None:
            conn.execute("ROLLBACK")
            evidence=[{
                "kind":"report",
                "source":"collector://incremental-chain",
                "digest":sha256_bytes(f"noop:{sequence}:{from_cycle}".encode()),
                "details":{
                    "sequence":sequence,
                    "baseline_cycle":from_cycle,
                    "next_completed_cycle":None,
                    "nas_mutation":False,
                    "raw_row_data_exposed":False,
                },
            }]
            return emit(result(request,"OK","COLLECTOR_INCREMENTAL_NOOP",evidence,[{
                "type":"gate","id":"collector-incremental-next","status":"OK",
                "reason":"No completed cycle exists beyond current chain watermark.",
            }]))

        to_cycle=int(target["cycle"])
        archive_rel=(
            f"{CHAIN_REL_ROOT}/incrementals/"
            f"collector-incremental-{next_seq:06d}-cycle-{to_cycle:06d}.sql.gz"
        )
        final=f"{nas_root()}/{archive_rel}"
        temp=final+".incoming"
        if remote_exists(final):
            conn.execute("ROLLBACK")
            return blocked(request,"COLLECTOR_INCREMENTAL_ORPHAN_ARCHIVE")
        if remote_exists(temp):
            conn.execute("ROLLBACK")
            return blocked(request,"COLLECTOR_INCREMENTAL_TEMP_COLLISION")

        remote_cmd=f"umask 077; cat > '{temp}'"
        ssh=subprocess.Popen(
            ["/usr/bin/ssh","-o","BatchMode=yes","-o","ConnectTimeout=12",nas_host(),remote_cmd],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
        )
        if ssh.stdin is None:
            conn.execute("ROLLBACK")
            raise RuntimeError("INCREMENTAL_STREAM_STDIN_MISSING")

        writer=LineHashingGzipWriter(ssh.stdin)
        package=None
        try:
            package=helper.generate_incremental_sql(conn,state,writer.line)
            if package is None:
                raise RuntimeError("INCREMENTAL_TARGET_DISAPPEARED")
            restored_row_counts={
                table:int(conn.execute(
                    f'SELECT COUNT(*) FROM "{table}"'
                ).fetchone()[0])
                for table in helper.TABLE_ORDER
            }
            writer.close()
            ssh.stdin.close()
            rc=ssh.wait(timeout=1800)
            if rc!=0:
                err=ssh.stderr.read(4096).decode("utf-8","replace") if ssh.stderr else ""
                raise RuntimeError("INCREMENTAL_STREAM_FAILED:"+err[:120])
            conn.execute("ROLLBACK")
        except Exception:
            try:
                writer.close()
            except Exception:
                pass
            try:
                ssh.stdin.close()
            except Exception:
                pass
            try:
                ssh.kill()
            except Exception:
                pass
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            run(ssh_base()+["rm","-f",temp],timeout=20)
            raise
    finally:
        conn.close()

    local_hash=writer.hash.hexdigest()
    proc=run(ssh_base()+["sha256sum",temp],timeout=120)
    if proc.returncode!=0:
        run(ssh_base()+["rm","-f",temp],timeout=20)
        raise RuntimeError("INCREMENTAL_REMOTE_HASH_FAILED")
    remote_hash=proc.stdout.decode("utf-8","replace").split()[0].strip()
    if remote_hash!=local_hash:
        run(ssh_base()+["rm","-f",temp],timeout=20)
        raise RuntimeError("INCREMENTAL_SHA256_MISMATCH")

    move=run(ssh_base()+["mv",temp,final],timeout=30)
    if move.returncode!=0:
        run(ssh_base()+["rm","-f",temp],timeout=20)
        raise RuntimeError("INCREMENTAL_ATOMIC_PUBLISH_FAILED")

    previous_digest=sha256_bytes(json.dumps(state,sort_keys=True,separators=(",",":")).encode())
    candidate={
        "schema":"chacha.dev/collector-incremental-candidate/v1",
        "status":"PENDING_VERIFICATION",
        "sequence":int(package["sequence"]),
        "created_at":now_iso(),
        "master":state["master"],
        "watermarks":package["watermarks"],
        "plan_digest":state.get("plan_digest"),
        "package_format":state.get("package_format"),
        "previous_state_path":state_path.replace(nas_root()+"/",""),
        "previous_state_sha256":previous_digest,
        "incremental":{
            "archive":archive_rel,
            "sha256":"sha256:"+local_hash,
            "from_cycle":int(package["from_cycle"]),
            "to_cycle":int(package["to_cycle"]),
            "target_finished_at":package["target_finished_at"],
            "row_counts":package["row_counts"],
            "compressed_bytes":writer.compressed_bytes,
            "sql_lines":writer.lines,
        },
        "verification_expectations":{
            "table_names":[
                "cycle_baseline","cycle_changes","cycle_seen","cycles",
                "identity_coverage","master_players","masters","observations",
                "player_aliases","player_identity","players"
            ],
            "full_refresh_tables":[
                "identity_coverage","master_players","player_aliases","player_identity"
            ],
            "cycle_watermarks":{
                "cycle_baseline":"cycle_id",
                "cycle_changes":"cycle_id",
                "cycle_seen":"cycle_id",
                "players":"last_change_cycle"
            },
            "previous_watermarks":{
                "observations":dict((state.get("watermarks") or {}).get("observations") or {}),
                "masters":dict((state.get("watermarks") or {}).get("masters") or {}),
            },
            "target_finished_at":package["target_finished_at"],
            "target_cycle":int(package["to_cycle"]),
            "patch_row_counts":package["row_counts"],
            "restored_row_counts":restored_row_counts,
            "result_watermarks":package["watermarks"],
        },
        "immutable":True,
    }
    write_json_via_nas_adapter(
        request,candidate,candidate_rel,
        "collector-incremental-candidate",
        "Publish immutable Collector incremental candidate awaiting independent verification.",
    )

    candidate_digest=sha256_bytes(json.dumps(candidate,sort_keys=True,separators=(",",":")).encode())
    evidence=[{
        "kind":"file",
        "source":"nas://"+nas_host()+"/"+archive_rel,
        "digest":"sha256:"+local_hash,
        "details":{
            "sequence":int(package["sequence"]),
            "from_cycle":int(package["from_cycle"]),
            "to_cycle":int(package["to_cycle"]),
            "compressed_bytes":writer.compressed_bytes,
            "sql_lines":writer.lines,
            "row_counts":package["row_counts"],
            "candidate_sha256":candidate_digest,
            "chain_state_advanced":False,
            "raw_row_data_exposed":False,
            "collector_service_stopped":False,
        },
    }]
    return emit(result(request,"OK","COLLECTOR_INCREMENTAL_CANDIDATE_CREATED",evidence,[
        {"type":"artifact","id":archive_rel,"status":"UNVERIFIED","reason":"Awaiting independent candidate verifier."},
        {"type":"artifact","id":candidate_rel,"status":"UNVERIFIED","reason":"Committed chain state is unchanged until VERIFIED receipt."},
    ]))


def collector_incremental_commit(request: dict[str,Any]) -> int:
    helper=load_chain_helper()
    ensure_chain_dirs()
    state_path,state=latest_chain_state()
    sequence=int(state.get("sequence") or 0)
    next_seq=sequence+1
    candidate_rel=incremental_candidate_rel(next_seq)
    verification_rel=incremental_verification_rel(next_seq)
    candidate_abs=f"{nas_root()}/{candidate_rel}"
    verification_abs=f"{nas_root()}/{verification_rel}"
    if not remote_exists(candidate_abs):
        return blocked(request,"COLLECTOR_INCREMENTAL_CANDIDATE_MISSING")
    if not remote_exists(verification_abs):
        return blocked(request,"COLLECTOR_INCREMENTAL_VERIFICATION_MISSING")

    candidate=read_remote_json(candidate_abs)
    receipt=read_remote_json(verification_abs)
    if candidate.get("schema")!="chacha.dev/collector-incremental-candidate/v1":
        return blocked(request,"COLLECTOR_INCREMENTAL_CANDIDATE_SCHEMA_INVALID")
    if candidate.get("status")!="PENDING_VERIFICATION":
        return blocked(request,"COLLECTOR_INCREMENTAL_CANDIDATE_STATUS_INVALID")
    if int(candidate.get("sequence") or -1)!=next_seq:
        return blocked(request,"COLLECTOR_INCREMENTAL_CANDIDATE_SEQUENCE_INVALID")

    candidate_digest=sha256_bytes(json.dumps(candidate,sort_keys=True,separators=(",",":")).encode())
    incremental=dict(candidate.get("incremental") or {})
    package_sha=str(incremental.get("sha256") or "")
    if receipt.get("schema")!="chacha.dev/collector-incremental-verification/v1":
        return blocked(request,"COLLECTOR_INCREMENTAL_VERIFICATION_SCHEMA_INVALID")
    if receipt.get("status")!="VERIFIED":
        return blocked(request,"COLLECTOR_INCREMENTAL_VERIFICATION_NOT_VERIFIED")
    if int(receipt.get("sequence") or -1)!=next_seq:
        return blocked(request,"COLLECTOR_INCREMENTAL_VERIFICATION_SEQUENCE_INVALID")
    if receipt.get("candidate_sha256")!=candidate_digest:
        return blocked(request,"COLLECTOR_INCREMENTAL_VERIFICATION_CANDIDATE_MISMATCH")
    if receipt.get("package_sha256")!=package_sha:
        return blocked(request,"COLLECTOR_INCREMENTAL_VERIFICATION_PACKAGE_MISMATCH")

    previous_digest=sha256_bytes(json.dumps(state,sort_keys=True,separators=(",",":")).encode())
    if candidate.get("previous_state_sha256")!=previous_digest:
        return blocked(request,"COLLECTOR_INCREMENTAL_PREVIOUS_STATE_MISMATCH")

    final_state={
        "schema":helper.CHAIN_SCHEMA,
        "sequence":next_seq,
        "created_at":now_iso(),
        "master":candidate["master"],
        "watermarks":candidate["watermarks"],
        "plan_digest":candidate.get("plan_digest"),
        "package_format":candidate.get("package_format"),
        "next_sequence":next_seq+1,
        "immutable":True,
        "previous_state_sha256":previous_digest,
        "incremental":incremental,
        "verification":{
            "receipt":verification_rel,
            "receipt_sha256":sha256_bytes(json.dumps(receipt,sort_keys=True,separators=(",",":")).encode()),
            "status":"VERIFIED",
            "verifier":receipt.get("verifier"),
            "verified_at":receipt.get("verified_at"),
        },
    }
    state_rel=f"{CHAIN_REL_ROOT}/collector-chain-state-{next_seq:06d}.json"
    state_abs=f"{nas_root()}/{state_rel}"
    if remote_exists(state_abs):
        existing=read_remote_json(state_abs)
        existing_digest=sha256_bytes(json.dumps(existing,sort_keys=True,separators=(",",":")).encode())
        desired_digest=sha256_bytes(json.dumps(final_state,sort_keys=True,separators=(",",":")).encode())
        if existing_digest==desired_digest:
            return emit(result(request,"OK","COLLECTOR_INCREMENTAL_ALREADY_COMMITTED",[],[{
                "type":"artifact","id":state_rel,"status":"VERIFIED","reason":"Existing committed state matches verified candidate.",
            }]))
        return blocked(request,"COLLECTOR_INCREMENTAL_STATE_COLLISION")

    write_json_via_nas_adapter(
        request,final_state,state_rel,
        "collector-incremental-commit",
        "Commit independently verified Collector incremental chain state.",
    )
    evidence=[{
        "kind":"file",
        "source":"nas://"+nas_host()+"/"+state_rel,
        "digest":sha256_bytes(json.dumps(final_state,sort_keys=True,separators=(",",":")).encode()),
        "details":{
            "sequence":next_seq,
            "to_cycle":incremental.get("to_cycle"),
            "verification_status":"VERIFIED",
            "candidate_sha256":candidate_digest,
            "package_sha256":package_sha,
        },
    }]
    return emit(result(request,"OK","COLLECTOR_INCREMENTAL_COMMITTED",evidence,[{
        "type":"artifact","id":state_rel,"status":"VERIFIED",
        "reason":"Chain advanced only after independent VERIFIED receipt.",
    }]))


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
        if cfg.get("action")=="collector-incremental-discovery":
            return collector_incremental_discovery(request)
        if cfg.get("action")=="collector-incremental-plan":
            return collector_incremental_plan(request)
        if cfg.get("action")=="collector-incremental-anchor":
            return collector_incremental_anchor(request,cfg)
        if cfg.get("action")=="collector-incremental-package":
            return collector_incremental_package(request)
        if cfg.get("action")=="collector-incremental-commit":
            return collector_incremental_commit(request)
        return collector_master(request)
    except subprocess.TimeoutExpired:
        return emit(result(request,"FAILED","STORAGE_GOVERNOR_TIMEOUT"))
    except Exception as exc:
        reason=f"STORAGE_GOVERNOR_RUNTIME_FAILED:{type(exc).__name__}:{str(exc)[:160]}"
        return emit(result(request,"FAILED",reason))


if __name__=="__main__":
    raise SystemExit(main())
