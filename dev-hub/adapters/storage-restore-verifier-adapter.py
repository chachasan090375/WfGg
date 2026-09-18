#!/usr/bin/env python3
"""Independent ChaCha DEV storage restore verifier V1.

This verifier is intentionally separate from storage-governor-adapter.
It restores the immutable Collector MASTER into a disposable NAS sandbox,
checks SQLite integrity and baseline aggregates, verifies the chain anchor,
then removes only the disposable restore database it created.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

INPUT_SCHEMA="chacha.dev/dispatch-envelope/v1"
OUTPUT_SCHEMA="chacha.dev/task-result/v1"
ADAPTER_ID="storage-restore-verifier-adapter"
PROVIDER_ID="storage-restore-verifier"
DEFAULT_NAS_HOST="chachanas"
DEFAULT_NAS_ROOT="/share/CACHEDEV1_DATA/ChaCha-DEV-HUB"
SAFE_RUN=re.compile(r"^[A-Za-z0-9._-]+$")
EXPECTED_TABLES=[
    "cycle_baseline","cycle_changes","cycle_seen","cycles","identity_coverage",
    "master_players","masters","observations","player_aliases","player_identity","players",
]


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
            "status":"VERIFIED" if status=="OK" else "FAILED",
            "method":"independent-restore",
            "verifier":ADAPTER_ID,
            "observed_at":now_iso(),
            "notes":"Verifier code is independent from Storage Governor producer code."
        },
        "outputs":outputs or [],
    }


def emit(payload: dict[str,Any], code: int=0) -> int:
    sys.stdout.write(json.dumps(payload,ensure_ascii=False,separators=(",",":"))+"\n")
    return code


def blocked(request: dict[str,Any], reason: str) -> int:
    return emit(result(request,"BLOCKED",reason,[{
        "kind":"report",
        "source":"storage-restore-verifier-policy",
        "digest":sha256_bytes(reason.encode()),
        "details":{"reason":reason},
    }]))


def validate_request(request: dict[str,Any]) -> tuple[dict[str,Any]|None,str|None]:
    if request.get("schema")!=INPUT_SCHEMA:
        return None,"INPUT_SCHEMA_INVALID"
    task=request.get("task")
    if not isinstance(task,dict) or not task.get("id"):
        return None,"TASK_ID_MISSING"
    if str(task.get("permission") or "")!="workspace-write":
        return None,"RESTORE_VERIFIER_REQUIRES_WORKSPACE_WRITE"
    bindings=request.get("bindings")
    if not isinstance(bindings,list) or not any(
        isinstance(x,dict)
        and x.get("provider")==PROVIDER_ID
        and x.get("adapter")==ADAPTER_ID
        for x in bindings
    ):
        return None,"RESTORE_VERIFIER_BINDING_MISSING"
    metadata=request.get("metadata")
    cfg=metadata.get("storage_restore_verifier") if isinstance(metadata,dict) else None
    if not isinstance(cfg,dict):
        return None,"RESTORE_VERIFIER_METADATA_MISSING"
    if str(cfg.get("action") or "")!="verify-master-anchor":
        return None,"RESTORE_VERIFIER_ACTION_NOT_ALLOWED"
    return cfg,None


def nas_host() -> str:
    host=os.environ.get("CHACHA_NAS_HOST",DEFAULT_NAS_HOST).strip()
    if not re.fullmatch(r"[A-Za-z0-9._-]+",host):
        raise ValueError("NAS_HOST_INVALID")
    return host


def nas_root() -> str:
    root=os.environ.get("CHACHA_NAS_ROOT",DEFAULT_NAS_ROOT).strip().rstrip("/")
    if not root.startswith("/"):
        raise ValueError("NAS_ROOT_INVALID")
    return root


def run(argv: list[str], timeout: int=60) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        argv,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        shell=False,
        check=False,
    )


def ssh_base() -> list[str]:
    return ["/usr/bin/ssh","-o","BatchMode=yes","-o","ConnectTimeout=12",nas_host()]


def remote_sha256(path: str) -> str:
    proc=run(ssh_base()+["sha256sum",path],timeout=120)
    if proc.returncode!=0:
        raise RuntimeError("REMOTE_SHA256_FAILED")
    value=proc.stdout.decode("utf-8","replace").split()[0].strip()
    if not re.fullmatch(r"[0-9a-f]{64}",value):
        raise RuntimeError("REMOTE_SHA256_INVALID")
    return value


def remote_exec(command: str, timeout: int=120) -> str:
    proc=run(ssh_base()+[command],timeout=timeout)
    if proc.returncode!=0:
        err=proc.stderr.decode("utf-8","replace")[:200]
        raise RuntimeError("REMOTE_COMMAND_FAILED:"+err)
    return proc.stdout.decode("utf-8","replace")


def safe_rel(value: str, prefix: str) -> str:
    value=value.strip().lstrip("/")
    if not value.startswith(prefix) or ".." in Path(value).parts:
        raise ValueError("REMOTE_PATH_INVALID")
    if not re.fullmatch(r"[A-Za-z0-9._/-]+",value):
        raise ValueError("REMOTE_PATH_INVALID")
    return value


def parse_expected_rows(value: Any) -> dict[str,int]:
    if not isinstance(value,dict):
        raise ValueError("EXPECTED_ROWS_INVALID")
    out={}
    for table in EXPECTED_TABLES:
        if table not in value:
            raise ValueError("EXPECTED_ROWS_INCOMPLETE")
        count=int(value[table])
        if count<0:
            raise ValueError("EXPECTED_ROWS_INVALID")
        out[table]=count
    extra=set(value)-set(EXPECTED_TABLES)
    if extra:
        raise ValueError("EXPECTED_ROWS_UNKNOWN_TABLE")
    return out


def verify_probe(probe: dict[str,Any], expected_rows: dict[str,int], expected: dict[str,Any]) -> list[str]:
    errors=[]
    if probe.get("integrity")!="ok":
        errors.append("SQLITE_INTEGRITY_FAILED")
    if probe.get("tables")!=EXPECTED_TABLES:
        errors.append("TABLE_SET_MISMATCH")
    if probe.get("row_counts")!=expected_rows:
        errors.append("ROW_COUNTS_MISMATCH")
    if int(probe.get("max_cycle") or -1)!=int(expected["baseline_cycle"]):
        errors.append("BASELINE_CYCLE_MISMATCH")
    obs=probe.get("observations") or {}
    if str(obs.get("observed_at") or "")!=str(expected["observations"]["observed_at"]):
        errors.append("OBSERVED_AT_WATERMARK_MISMATCH")
    if int(obs.get("id") or -1)!=int(expected["observations"]["id"]):
        errors.append("OBSERVATION_ID_WATERMARK_MISMATCH")
    masters=probe.get("masters") or {}
    if str(masters.get("created_at") or "")!=str(expected["masters"]["created_at"]):
        errors.append("MASTER_TIME_WATERMARK_MISMATCH")
    if int(masters.get("id") or -1)!=int(expected["masters"]["id"]):
        errors.append("MASTER_ID_WATERMARK_MISMATCH")
    return errors


def verify_master_anchor(request: dict[str,Any], cfg: dict[str,Any]) -> int:
    run_id=str(request.get("run_id") or "restore-verifier")
    if not SAFE_RUN.fullmatch(run_id):
        return blocked(request,"RESTORE_VERIFIER_RUN_ID_INVALID")

    master_rel=safe_rel(str(cfg.get("master_archive") or ""),"projects/wfgg/backups/")
    anchor_rel=safe_rel(str(cfg.get("anchor_path") or ""),"projects/wfgg/backups/collector-chain/")
    expected_master=str(cfg.get("master_sha256") or "")
    expected_anchor=str(cfg.get("anchor_sha256") or "")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}",expected_master):
        return blocked(request,"RESTORE_MASTER_SHA_INVALID")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}",expected_anchor):
        return blocked(request,"RESTORE_ANCHOR_SHA_INVALID")

    expected_rows=parse_expected_rows(cfg.get("expected_rows"))
    expected={
        "baseline_cycle":int(cfg.get("baseline_cycle") or 0),
        "observations":dict(cfg.get("observations_watermark") or {}),
        "masters":dict(cfg.get("masters_watermark") or {}),
    }

    root=nas_root()
    master_abs=f"{root}/{master_rel}"
    anchor_abs=f"{root}/{anchor_rel}"

    if "sha256:"+remote_sha256(master_abs)!=expected_master:
        return blocked(request,"RESTORE_MASTER_SHA_MISMATCH")
    if "sha256:"+remote_sha256(anchor_abs)!=expected_anchor:
        return blocked(request,"RESTORE_ANCHOR_SHA_MISMATCH")

    portable_path=Path(
        os.environ.get("CHACHA_PORTABLE_RESTORE_VERIFIER","")
    ).resolve()
    portable_expected=str(cfg.get("portable_verifier_sha256") or "")
    if not portable_path.is_file():
        return blocked(request,"PORTABLE_RESTORE_VERIFIER_MISSING")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}",portable_expected):
        return blocked(request,"PORTABLE_RESTORE_VERIFIER_SHA_INVALID")
    local_portable_sha="sha256:"+hashlib.sha256(portable_path.read_bytes()).hexdigest()
    if local_portable_sha!=portable_expected:
        return blocked(request,"PORTABLE_RESTORE_VERIFIER_LOCAL_SHA_MISMATCH")

    arch=remote_exec("uname -m",timeout=30).strip()
    if arch not in {"x86_64","amd64"}:
        return blocked(request,"NAS_ARCH_UNSUPPORTED:"+arch)

    sandbox=f"{root}/artifacts/restore-verification/{run_id}"
    restored=f"{sandbox}/collector-restore.db"
    remote_bin=f"{sandbox}/storage-restore-verifier"
    remote_result=f"{sandbox}/result.json"

    expected_doc={
        "row_counts":expected_rows,
        "baseline_cycle":expected["baseline_cycle"],
        "observations_watermark":expected["observations"],
        "masters_watermark":expected["masters"],
    }
    expected_b64=base64.b64encode(
        json.dumps(expected_doc,separators=(",",":"),sort_keys=True).encode()
    ).decode()

    # The sandbox path is policy-owned and unique to this run.
    remote_exec(
        f"umask 077; mkdir -p {shlex.quote(sandbox)}; "
        f"test ! -e {shlex.quote(restored)}; "
        f"test ! -e {shlex.quote(remote_bin)}",
        timeout=30,
    )
    cleanup_needed=True
    try:
        scp=subprocess.run(
            [
                "/usr/bin/scp","-q",
                "-o","BatchMode=yes",
                "-o","ConnectTimeout=12",
                str(portable_path),
                f"{nas_host()}:{remote_bin}",
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=120,
            shell=False,
            check=False,
        )
        if scp.returncode!=0:
            raise RuntimeError(
                "PORTABLE_RESTORE_VERIFIER_UPLOAD_FAILED:"+
                scp.stderr.decode("utf-8","replace")[:160]
            )

        remote_exec(
            f"chmod 0700 {shlex.quote(remote_bin)}; "
            f"test \"sha256:$(sha256sum {shlex.quote(remote_bin)} | awk '{{print $1}}')\" = "
            f"{shlex.quote(portable_expected)}",
            timeout=60,
        )

        remote_exec(
            f"{shlex.quote(remote_bin)} "
            f"--master {shlex.quote(master_abs)} "
            f"--restore {shlex.quote(restored)} "
            f"--expected-b64 {shlex.quote(expected_b64)} "
            f"--result {shlex.quote(remote_result)}",
            timeout=1800,
        )

        probe=json.loads(remote_exec(
            f"cat {shlex.quote(remote_result)}",timeout=60
        ))
        if probe.get("status")!="PASS":
            return emit(result(request,"FAILED","COLLECTOR_RESTORE_VERIFICATION_FAILED",[{
                "kind":"report",
                "source":"nas://"+nas_host()+"/restore-verification",
                "digest":sha256_bytes(json.dumps(probe,sort_keys=True).encode()),
                "details":{
                    "errors":list(probe.get("errors") or []),
                    "integrity":probe.get("integrity"),
                    "table_count":len(probe.get("tables") or []),
                    "row_counts":dict(probe.get("row_counts") or {}),
                    "max_cycle":probe.get("baseline_cycle"),
                },
            }]))

        translated={
            "integrity":probe.get("integrity"),
            "tables":list(probe.get("tables") or []),
            "row_counts":dict(probe.get("row_counts") or {}),
            "max_cycle":int(probe.get("baseline_cycle") or 0),
            "observations":{
                "observed_at":str((probe.get("observations_watermark") or {}).get("observed_at") or ""),
                "id":int((probe.get("observations_watermark") or {}).get("id") or 0),
            },
            "masters":{
                "created_at":str((probe.get("masters_watermark") or {}).get("created_at") or ""),
                "id":int((probe.get("masters_watermark") or {}).get("id") or 0),
            },
        }
        errors=verify_probe(translated,expected_rows,expected)
        if errors:
            return emit(result(request,"FAILED","COLLECTOR_RESTORE_VERIFICATION_FAILED",[{
                "kind":"report",
                "source":"nas://"+nas_host()+"/restore-verification",
                "digest":sha256_bytes(json.dumps(translated,sort_keys=True).encode()),
                "details":{
                    "errors":errors,
                    "integrity":translated["integrity"],
                    "table_count":len(translated["tables"]),
                    "row_counts":translated["row_counts"],
                    "max_cycle":translated["max_cycle"],
                },
            }]))

        evidence=[{
            "kind":"report",
            "source":"nas://"+nas_host()+"/restore-verification",
            "digest":sha256_bytes(json.dumps(translated,sort_keys=True).encode()),
            "details":{
                "master_sha256":expected_master,
                "anchor_sha256":expected_anchor,
                "portable_verifier_sha256":portable_expected,
                "portable_verifier_arch":arch,
                "integrity":"ok",
                "table_count":len(translated["tables"]),
                "row_counts":translated["row_counts"],
                "baseline_cycle":translated["max_cycle"],
                "observations_watermark":translated["observations"],
                "masters_watermark":translated["masters"],
                "sandbox_deleted_after_verification":True,
                "production_data_mutation":False,
            },
        }]
        return emit(result(request,"OK","COLLECTOR_MASTER_RESTORE_VERIFIED",evidence,[{
            "type":"gate","id":"collector-restore-proof","status":"VERIFIED",
            "reason":"MASTER restored independently with portable SQLite verifier and matched anchor baseline."
        }]))
    finally:
        if cleanup_needed:
            # Delete only verifier-owned sandbox files and then its empty directory.
            try:
                remote_exec(
                    f"rm -f {shlex.quote(restored)} {shlex.quote(remote_result)} "
                    f"{shlex.quote(remote_bin)}; "
                    f"rmdir {shlex.quote(sandbox)} 2>/dev/null || true",
                    timeout=60,
                )
            except Exception:
                pass


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
        return verify_master_anchor(request,cfg)
    except subprocess.TimeoutExpired:
        return emit(result(request,"FAILED","RESTORE_VERIFIER_TIMEOUT"))
    except Exception as exc:
        return emit(result(request,"FAILED",f"RESTORE_VERIFIER_RUNTIME_FAILED:{type(exc).__name__}:{str(exc)[:160]}"))


if __name__=="__main__":
    raise SystemExit(main())
