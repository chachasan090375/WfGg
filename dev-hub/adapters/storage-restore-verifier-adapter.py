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
    action=str(cfg.get("action") or "")
    if action not in {"verify-master-anchor","verify-incremental-candidate"}:
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


def read_remote_json(path: str) -> dict[str,Any]:
    proc=run(ssh_base()+["cat",path],timeout=60)
    if proc.returncode!=0:
        raise RuntimeError("REMOTE_JSON_READ_FAILED")
    value=json.loads(proc.stdout.decode("utf-8","replace"))
    if not isinstance(value,dict):
        raise RuntimeError("REMOTE_JSON_INVALID")
    return value


def write_remote_json_immutable(path: str, document: dict[str,Any]) -> None:
    if run(ssh_base()+["test","-e",path],timeout=30).returncode==0:
        existing=read_remote_json(path)
        if existing==document:
            return
        raise RuntimeError("REMOTE_JSON_COLLISION")
    temp=path+f".incoming-{os.getpid()}"
    payload=(json.dumps(document,indent=2,ensure_ascii=False)+"\n").encode()
    remote_cmd=f"umask 077; cat > {shlex.quote(temp)}"
    proc=subprocess.Popen(
        ["/usr/bin/ssh","-o","BatchMode=yes","-o","ConnectTimeout=12",nas_host(),remote_cmd],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=False,
    )
    out,err=proc.communicate(payload,timeout=60)
    if proc.returncode!=0:
        run(ssh_base()+["rm","-f",temp],timeout=20)
        raise RuntimeError("REMOTE_JSON_UPLOAD_FAILED:"+err.decode("utf-8","replace")[:160])
    move=run(
        ssh_base()+[
            f"test ! -e {shlex.quote(path)} && mv {shlex.quote(temp)} {shlex.quote(path)}"
        ],
        timeout=30,
    )
    if move.returncode!=0:
        run(ssh_base()+["rm","-f",temp],timeout=20)
        raise RuntimeError("REMOTE_JSON_ATOMIC_PUBLISH_FAILED")


def canonical_digest(value: dict[str,Any]) -> str:
    return sha256_bytes(json.dumps(value,sort_keys=True,separators=(",",":")).encode())


def portable_verifier_path(cfg: dict[str,Any]) -> tuple[Path,str]:
    path=Path(os.environ.get("CHACHA_PORTABLE_RESTORE_VERIFIER","")).resolve()
    expected=str(cfg.get("portable_verifier_sha256") or "")
    if not path.is_file():
        raise RuntimeError("PORTABLE_RESTORE_VERIFIER_MISSING")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}",expected):
        raise RuntimeError("PORTABLE_RESTORE_VERIFIER_SHA_INVALID")
    actual="sha256:"+hashlib.sha256(path.read_bytes()).hexdigest()
    if actual!=expected:
        raise RuntimeError("PORTABLE_RESTORE_VERIFIER_LOCAL_SHA_MISMATCH")
    return path,expected


def upload_portable_verifier(local_path: Path, remote_path: str, expected_sha: str) -> None:
    scp=subprocess.run(
        [
            "/usr/bin/scp","-q",
            "-o","BatchMode=yes",
            "-o","ConnectTimeout=12",
            str(local_path),
            f"{nas_host()}:{remote_path}",
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
        f"chmod 0700 {shlex.quote(remote_path)}; "
        f"test \"sha256:$(sha256sum {shlex.quote(remote_path)} | awk '{{print $1}}')\" = "
        f"{shlex.quote(expected_sha)}",
        timeout=60,
    )


def run_portable_restore(
    *,
    local_portable: Path,
    portable_sha: str,
    master_abs: str,
    patch_abs: list[str],
    sandbox: str,
    expected_doc: dict[str,Any],
) -> tuple[dict[str,Any]|None,subprocess.CompletedProcess[bytes],str,str]:
    restored=f"{sandbox}/collector-restore.db"
    remote_bin=f"{sandbox}/storage-restore-verifier"
    remote_result=f"{sandbox}/result.json"
    expected_b64=base64.b64encode(
        json.dumps(expected_doc,separators=(",",":"),sort_keys=True).encode()
    ).decode()

    remote_exec(
        f"umask 077; mkdir -p {shlex.quote(sandbox)}; "
        f"test ! -e {shlex.quote(restored)}; "
        f"test ! -e {shlex.quote(remote_bin)}",
        timeout=30,
    )
    upload_portable_verifier(local_portable,remote_bin,portable_sha)

    patch_args="".join(
        f" --patch {shlex.quote(path)}"
        for path in patch_abs
    )
    verifier_cmd=(
        f"{shlex.quote(remote_bin)} "
        f"--master {shlex.quote(master_abs)}"
        f"{patch_args} "
        f"--restore {shlex.quote(restored)} "
        f"--expected-b64 {shlex.quote(expected_b64)} "
        f"--result {shlex.quote(remote_result)}"
    )
    verifier_proc=run(ssh_base()+[verifier_cmd],timeout=1800)
    probe=None
    probe_proc=run(
        ssh_base()+[
            f"test -s {shlex.quote(remote_result)} && cat {shlex.quote(remote_result)}"
        ],
        timeout=60,
    )
    if probe_proc.returncode==0 and probe_proc.stdout.strip():
        try:
            probe=json.loads(probe_proc.stdout.decode("utf-8","replace"))
        except Exception:
            probe=None
    return probe,verifier_proc,restored,remote_result


def cleanup_restore_sandbox(sandbox: str, restored: str, remote_result: str) -> None:
    remote_bin=f"{sandbox}/storage-restore-verifier"
    try:
        remote_exec(
            f"rm -f {shlex.quote(restored)} "
            f"{shlex.quote(restored+'-journal')} "
            f"{shlex.quote(restored+'-wal')} "
            f"{shlex.quote(restored+'-shm')} "
            f"{shlex.quote(remote_result)} "
            f"{shlex.quote(remote_bin)}; "
            f"rmdir {shlex.quote(sandbox)} 2>/dev/null || true",
            timeout=60,
        )
    except Exception:
        pass


def verify_incremental_candidate(request: dict[str,Any], cfg: dict[str,Any]) -> int:
    run_id=str(request.get("run_id") or "incremental-restore-verifier")
    if not SAFE_RUN.fullmatch(run_id):
        return blocked(request,"RESTORE_VERIFIER_RUN_ID_INVALID")

    root=nas_root()
    candidate_rel=safe_rel(
        str(cfg.get("candidate_path") or ""),
        "projects/wfgg/backups/collector-chain/",
    )
    candidate_abs=f"{root}/{candidate_rel}"
    candidate=read_remote_json(candidate_abs)
    if candidate.get("schema")!="chacha.dev/collector-incremental-candidate/v1":
        return blocked(request,"INCREMENTAL_CANDIDATE_SCHEMA_INVALID")
    if candidate.get("status")!="PENDING_VERIFICATION":
        return blocked(request,"INCREMENTAL_CANDIDATE_STATUS_INVALID")

    sequence=int(candidate.get("sequence") or 0)
    if sequence<=0:
        return blocked(request,"INCREMENTAL_CANDIDATE_SEQUENCE_INVALID")
    expected_name=f"collector-chain-candidate-{sequence:06d}.json"
    if not candidate_rel.endswith("/"+expected_name):
        return blocked(request,"INCREMENTAL_CANDIDATE_PATH_SEQUENCE_MISMATCH")

    candidate_sha=canonical_digest(candidate)
    incremental=dict(candidate.get("incremental") or {})
    package_rel=safe_rel(
        str(incremental.get("archive") or ""),
        "projects/wfgg/backups/collector-chain/incrementals/",
    )
    package_sha=str(incremental.get("sha256") or "")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}",package_sha):
        return blocked(request,"INCREMENTAL_PACKAGE_SHA_INVALID")
    package_abs=f"{root}/{package_rel}"
    if "sha256:"+remote_sha256(package_abs)!=package_sha:
        return blocked(request,"INCREMENTAL_PACKAGE_SHA_MISMATCH")

    receipt_rel=(
        "projects/wfgg/backups/collector-chain/"
        f"collector-chain-verification-{sequence:06d}.json"
    )
    receipt_abs=f"{root}/{receipt_rel}"
    if run(ssh_base()+["test","-e",receipt_abs],timeout=30).returncode==0:
        receipt=read_remote_json(receipt_abs)
        if (
            receipt.get("schema")=="chacha.dev/collector-incremental-verification/v1"
            and receipt.get("status")=="VERIFIED"
            and int(receipt.get("sequence") or -1)==sequence
            and receipt.get("candidate_sha256")==candidate_sha
            and receipt.get("package_sha256")==package_sha
        ):
            return emit(result(
                request,"OK","COLLECTOR_INCREMENTAL_ALREADY_VERIFIED",
                [{
                    "kind":"report",
                    "source":"nas://"+nas_host()+"/"+receipt_rel,
                    "digest":canonical_digest(receipt),
                    "details":{
                        "sequence":sequence,
                        "candidate_sha256":candidate_sha,
                        "package_sha256":package_sha,
                        "receipt_reused":True,
                    },
                }],
                [{
                    "type":"artifact","id":receipt_rel,"status":"VERIFIED",
                    "reason":"Existing immutable verification receipt matches candidate and package."
                }]
            ))
        return blocked(request,"INCREMENTAL_VERIFICATION_RECEIPT_COLLISION")

    previous_rel=safe_rel(
        str(candidate.get("previous_state_path") or ""),
        "projects/wfgg/backups/collector-chain/",
    )
    previous_abs=f"{root}/{previous_rel}"
    previous=read_remote_json(previous_abs)
    previous_sha=canonical_digest(previous)
    if previous_sha!=str(candidate.get("previous_state_sha256") or ""):
        return blocked(request,"INCREMENTAL_PREVIOUS_STATE_SHA_MISMATCH")
    if int(previous.get("sequence") or -1)!=sequence-1:
        return blocked(request,"INCREMENTAL_PREVIOUS_STATE_SEQUENCE_MISMATCH")

    master=dict(candidate.get("master") or {})
    master_rel=safe_rel(
        str(master.get("archive") or ""),
        "projects/wfgg/backups/",
    )
    master_sha=str(master.get("sha256") or "")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}",master_sha):
        return blocked(request,"INCREMENTAL_MASTER_SHA_INVALID")
    master_abs=f"{root}/{master_rel}"
    if "sha256:"+remote_sha256(master_abs)!=master_sha:
        return blocked(request,"INCREMENTAL_MASTER_SHA_MISMATCH")

    # Replay every committed package in strict sequence before the candidate.
    patch_abs=[]
    for index in range(1,sequence):
        state_rel=(
            "projects/wfgg/backups/collector-chain/"
            f"collector-chain-state-{index:06d}.json"
        )
        state=read_remote_json(f"{root}/{state_rel}")
        if int(state.get("sequence") or -1)!=index:
            return blocked(request,"INCREMENTAL_COMMITTED_STATE_SEQUENCE_MISMATCH")
        inc=dict(state.get("incremental") or {})
        rel=safe_rel(
            str(inc.get("archive") or ""),
            "projects/wfgg/backups/collector-chain/incrementals/",
        )
        digest=str(inc.get("sha256") or "")
        if not re.fullmatch(r"sha256:[0-9a-f]{64}",digest):
            return blocked(request,"INCREMENTAL_COMMITTED_PACKAGE_SHA_INVALID")
        absolute=f"{root}/{rel}"
        if "sha256:"+remote_sha256(absolute)!=digest:
            return blocked(request,"INCREMENTAL_COMMITTED_PACKAGE_SHA_MISMATCH")
        patch_abs.append(absolute)
    patch_abs.append(package_abs)

    expectations=dict(candidate.get("verification_expectations") or {})
    restored_rows=dict(expectations.get("restored_row_counts") or {})
    result_wm=dict(expectations.get("result_watermarks") or {})
    if sorted(restored_rows)!=sorted(EXPECTED_TABLES):
        return blocked(request,"INCREMENTAL_RESTORED_ROW_COUNTS_INCOMPLETE")
    expected_doc={
        "row_counts":{k:int(v) for k,v in restored_rows.items()},
        "baseline_cycle":int(incremental.get("to_cycle") or 0),
        "observations_watermark":dict(result_wm.get("observations") or {}),
        "masters_watermark":dict(result_wm.get("masters") or {}),
    }

    local_portable,portable_sha=portable_verifier_path(cfg)
    arch=remote_exec("uname -m",timeout=30).strip()
    if arch not in {"x86_64","amd64"}:
        return blocked(request,"NAS_ARCH_UNSUPPORTED:"+arch)

    sandbox=f"{root}/artifacts/restore-verification/{run_id}"
    restored=remote_result=""
    try:
        probe,proc,restored,remote_result=run_portable_restore(
            local_portable=local_portable,
            portable_sha=portable_sha,
            master_abs=master_abs,
            patch_abs=patch_abs,
            sandbox=sandbox,
            expected_doc=expected_doc,
        )
        if proc.returncode!=0 or not isinstance(probe,dict) or probe.get("status")!="PASS":
            details={
                "remote_returncode":proc.returncode,
                "remote_stderr":proc.stderr.decode("utf-8","replace")[:500],
                "result_json_present":isinstance(probe,dict),
            }
            if isinstance(probe,dict):
                details.update({
                    "portable_status":probe.get("status"),
                    "portable_errors":list(probe.get("errors") or []),
                    "statements_executed":probe.get("statements_executed"),
                    "patch_count":probe.get("patch_count"),
                    "integrity":probe.get("integrity"),
                    "table_count":len(probe.get("tables") or []),
                    "row_counts":dict(probe.get("row_counts") or {}),
                    "baseline_cycle":probe.get("baseline_cycle"),
                })
            return emit(result(
                request,"FAILED","COLLECTOR_INCREMENTAL_RESTORE_VERIFICATION_FAILED",
                [{
                    "kind":"report",
                    "source":"nas://"+nas_host()+"/restore-verification",
                    "digest":sha256_bytes(json.dumps(details,sort_keys=True).encode()),
                    "details":details,
                }]
            ))

        receipt={
            "schema":"chacha.dev/collector-incremental-verification/v1",
            "status":"VERIFIED",
            "sequence":sequence,
            "verified_at":now_iso(),
            "verifier":ADAPTER_ID,
            "candidate_path":candidate_rel,
            "candidate_sha256":candidate_sha,
            "package_sha256":package_sha,
            "master_sha256":master_sha,
            "portable_verifier_sha256":portable_sha,
            "patch_count":len(patch_abs),
            "restored":{
                "integrity":probe.get("integrity"),
                "table_count":len(probe.get("tables") or []),
                "row_counts":dict(probe.get("row_counts") or {}),
                "baseline_cycle":int(probe.get("baseline_cycle") or 0),
                "observations_watermark":dict(probe.get("observations_watermark") or {}),
                "masters_watermark":dict(probe.get("masters_watermark") or {}),
            },
            "production_data_mutation":False,
            "immutable":True,
        }
        write_remote_json_immutable(f"{root}/{receipt_rel}",receipt)
        evidence=[{
            "kind":"report",
            "source":"nas://"+nas_host()+"/"+receipt_rel,
            "digest":canonical_digest(receipt),
            "details":{
                "sequence":sequence,
                "candidate_sha256":candidate_sha,
                "package_sha256":package_sha,
                "patch_count":len(patch_abs),
                "integrity":"ok",
                "baseline_cycle":receipt["restored"]["baseline_cycle"],
                "production_data_mutation":False,
            },
        }]
        return emit(result(
            request,"OK","COLLECTOR_INCREMENTAL_RESTORE_VERIFIED",
            evidence,
            [{
                "type":"artifact","id":receipt_rel,"status":"VERIFIED",
                "reason":"MASTER plus committed chain plus candidate restored independently."
            }]
        ))
    finally:
        if restored and remote_result:
            cleanup_restore_sandbox(sandbox,restored,remote_result)


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

        verifier_cmd=(
            f"{shlex.quote(remote_bin)} "
            f"--master {shlex.quote(master_abs)} "
            f"--restore {shlex.quote(restored)} "
            f"--expected-b64 {shlex.quote(expected_b64)} "
            f"--result {shlex.quote(remote_result)}"
        )
        verifier_proc=run(ssh_base()+[verifier_cmd],timeout=1800)

        probe=None
        probe_proc=run(
            ssh_base()+[
                f"test -s {shlex.quote(remote_result)} && "
                f"cat {shlex.quote(remote_result)}"
            ],
            timeout=60,
        )
        if probe_proc.returncode==0 and probe_proc.stdout.strip():
            try:
                probe=json.loads(probe_proc.stdout.decode("utf-8","replace"))
            except Exception:
                probe=None

        if verifier_proc.returncode!=0:
            details={
                "remote_returncode":verifier_proc.returncode,
                "remote_stderr":verifier_proc.stderr.decode("utf-8","replace")[:500],
                "result_json_present":probe is not None,
            }
            if isinstance(probe,dict):
                details.update({
                    "portable_status":probe.get("status"),
                    "portable_errors":list(probe.get("errors") or []),
                    "statements_executed":probe.get("statements_executed"),
                    "integrity":probe.get("integrity"),
                    "table_count":len(probe.get("tables") or []),
                    "row_counts":dict(probe.get("row_counts") or {}),
                    "baseline_cycle":probe.get("baseline_cycle"),
                })
            return emit(result(
                request,
                "FAILED",
                "COLLECTOR_RESTORE_PORTABLE_VERIFIER_FAILED",
                [{
                    "kind":"report",
                    "source":"nas://"+nas_host()+"/restore-verification",
                    "digest":sha256_bytes(json.dumps(details,sort_keys=True).encode()),
                    "details":details,
                }]
            ))

        if not isinstance(probe,dict):
            return emit(result(
                request,
                "FAILED",
                "COLLECTOR_RESTORE_RESULT_MISSING",
                [{
                    "kind":"report",
                    "source":"nas://"+nas_host()+"/restore-verification",
                    "digest":sha256_bytes(b"result-missing"),
                    "details":{"remote_returncode":verifier_proc.returncode},
                }]
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
                    "statements_executed":probe.get("statements_executed"),
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
                    f"rm -f {shlex.quote(restored)} "
                    f"{shlex.quote(restored+'-journal')} "
                    f"{shlex.quote(restored+'-wal')} "
                    f"{shlex.quote(restored+'-shm')} "
                    f"{shlex.quote(remote_result)} "
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
        if cfg.get("action")=="verify-incremental-candidate":
            return verify_incremental_candidate(request,cfg)
        return verify_master_anchor(request,cfg)
    except subprocess.TimeoutExpired:
        return emit(result(request,"FAILED","RESTORE_VERIFIER_TIMEOUT"))
    except Exception as exc:
        return emit(result(request,"FAILED",f"RESTORE_VERIFIER_RUNTIME_FAILED:{type(exc).__name__}:{str(exc)[:160]}"))


if __name__=="__main__":
    raise SystemExit(main())
