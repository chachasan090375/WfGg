#!/usr/bin/env python3
"""ChaCha DEV Collector incremental auto-watch V1.

One supervised iteration:
1. ask Storage Governor for the next completed-cycle candidate;
2. independently restore MASTER + committed patches + candidate;
3. require an immutable VERIFIED receipt;
4. commit the new chain state;
5. repeat sequentially up to a bounded catch-up limit.

The live Collector database is never written and the service is never stopped.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

INPUT_SCHEMA="chacha.dev/dispatch-envelope/v1"
GOVERNOR=Path(os.environ.get(
    "CHACHA_STORAGE_GOVERNOR",
    "/opt/chacha-dev/adapters/storage-governor/current/storage-governor-adapter",
))
RESTORE_VERIFIER=Path(os.environ.get(
    "CHACHA_STORAGE_RESTORE_VERIFIER",
    "/opt/chacha-dev/adapters/storage-restore-verifier/current/storage-restore-verifier-adapter",
))
PORTABLE_VERIFIER=Path(os.environ.get(
    "CHACHA_PORTABLE_RESTORE_VERIFIER",
    "/opt/chacha-dev/adapters/storage-restore-verifier/current/storage-restore-verifier-nas-linux-amd64",
))
NAS_ADAPTER=Path(os.environ.get(
    "CHACHA_NAS_ADAPTER",
    "/opt/chacha-dev/adapters/nas-ssh/current/nas-ssh-adapter",
))
COLLECTOR_DB=Path(os.environ.get("WFGG_COLLECTOR_DB","/opt/wfgg-collector/data/collector.db"))
NAS_HOST=os.environ.get("CHACHA_NAS_HOST","chachanas")
NAS_ROOT=os.environ.get("CHACHA_NAS_ROOT","/share/CACHEDEV1_DATA/ChaCha-DEV-HUB")
EVIDENCE=Path(os.environ.get(
    "CHACHA_INCREMENTAL_WATCH_EVIDENCE",
    "/opt/chacha-dev/evidence/collector-incremental-auto-watch-last.json",
))
LOCK=Path(os.environ.get(
    "CHACHA_INCREMENTAL_WATCH_LOCK",
    "/run/chacha-storage-incremental-watch.lock",
))
MAX_ADVANCE_PER_RUN=int(os.environ.get("WFGG_INCREMENTAL_MAX_ADVANCE","4"))


class WatchError(RuntimeError):
    pass


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def log(key: str, value: Any) -> None:
    print(f"{key}={value}",flush=True)


def atomic_json(path: Path, value: dict[str,Any]) -> None:
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+f".tmp-{os.getpid()}")
    temp.write_text(json.dumps(value,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    os.replace(temp,path)


def sha256_file(path: Path) -> str:
    h=hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda:fh.read(1024*1024),b""):
            h.update(chunk)
    return "sha256:"+h.hexdigest()


def service_state() -> tuple[str,str]:
    active=subprocess.run(
        ["systemctl","is-active","wfgg-collector"],
        stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
        text=True,check=False,
    ).stdout.strip()
    pid=subprocess.run(
        ["systemctl","show","-p","MainPID","--value","wfgg-collector"],
        stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
        text=True,check=False,
    ).stdout.strip()
    return active,pid


def require_runtime() -> None:
    for path,label in [
        (GOVERNOR,"STORAGE_GOVERNOR"),
        (RESTORE_VERIFIER,"RESTORE_VERIFIER"),
        (PORTABLE_VERIFIER,"PORTABLE_VERIFIER"),
        (NAS_ADAPTER,"NAS_ADAPTER"),
        (COLLECTOR_DB,"COLLECTOR_DB"),
    ]:
        if not path.is_file():
            raise WatchError(f"{label}_MISSING:{path}")
    if MAX_ADVANCE_PER_RUN<1 or MAX_ADVANCE_PER_RUN>16:
        raise WatchError("MAX_ADVANCE_OUT_OF_RANGE")


def envelope(
    *,
    run_id: str,
    task_id: str,
    provider: str,
    adapter: str,
    metadata_key: str,
    metadata_value: dict[str,Any],
    description: str,
) -> dict[str,Any]:
    return {
        "schema":INPUT_SCHEMA,
        "project":"wfgg-radar",
        "transition":task_id,
        "run_id":run_id,
        "wave":1,
        "task":{
            "id":task_id,
            "kind":"backup-store",
            "description":description,
            "owner_role":provider,
            "permission":"workspace-write",
            "outputs":[{"type":"artifact","id":task_id}],
            "verification":{"required":True,"mode":"machine"},
        },
        "bindings":[{
            "capability":"storage-governance",
            "provider":provider,
            "adapter":adapter,
            "fallback_used":False,
            "health_state":"pilot",
        }],
        "policy_context":{
            "resource_class":"heavy",
            "requires_storage_preflight":True,
            "human_approval_required":False,
            "approval_id":None,
            "timeout_seconds":1800,
        },
        "workspace":"/opt/chacha-dev",
        "metadata":{metadata_key:metadata_value},
    }


def invoke(path: Path, payload: dict[str,Any], timeout: int) -> dict[str,Any]:
    env=os.environ.copy()
    env.update({
        "WFGG_COLLECTOR_DB":str(COLLECTOR_DB),
        "CHACHA_NAS_ADAPTER":str(NAS_ADAPTER),
        "CHACHA_NAS_HOST":NAS_HOST,
        "CHACHA_NAS_ROOT":NAS_ROOT,
        "CHACHA_PORTABLE_RESTORE_VERIFIER":str(PORTABLE_VERIFIER),
    })
    proc=subprocess.run(
        [str(path)],
        input=json.dumps(payload,separators=(",",":")).encode(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        shell=False,
        check=False,
        env=env,
    )
    raw=proc.stdout.decode("utf-8","replace").strip()
    if not raw:
        raise WatchError(f"ADAPTER_EMPTY_RESULT:{path.name}:rc={proc.returncode}")
    try:
        value=json.loads(raw)
    except json.JSONDecodeError as exc:
        raise WatchError(f"ADAPTER_JSON_INVALID:{path.name}:{exc}") from exc
    if not isinstance(value,dict):
        raise WatchError(f"ADAPTER_RESULT_NOT_OBJECT:{path.name}")
    if proc.returncode!=0:
        raise WatchError(
            f"ADAPTER_NONZERO:{path.name}:rc={proc.returncode}:summary={value.get('summary')}"
        )
    return value


def candidate_path(value: dict[str,Any]) -> str:
    for item in value.get("outputs") or []:
        if not isinstance(item,dict):
            continue
        artifact=str(item.get("id") or "")
        if "collector-chain-candidate-" in artifact and artifact.endswith(".json"):
            return artifact
    raise WatchError("CANDIDATE_PATH_MISSING")


def package_next(run_id: str) -> dict[str,Any]:
    return invoke(
        GOVERNOR,
        envelope(
            run_id=run_id,
            task_id="collector-incremental-package",
            provider="storage-governor",
            adapter="storage-governor-adapter",
            metadata_key="storage_governor",
            metadata_value={"action":"collector-incremental-package"},
            description="Prepare exactly one completed-cycle incremental candidate.",
        ),
        timeout=1900,
    )


def verify_candidate(run_id: str, path: str, portable_sha: str) -> dict[str,Any]:
    return invoke(
        RESTORE_VERIFIER,
        envelope(
            run_id=run_id,
            task_id="collector-incremental-verify",
            provider="storage-restore-verifier",
            adapter="storage-restore-verifier-adapter",
            metadata_key="storage_restore_verifier",
            metadata_value={
                "action":"verify-incremental-candidate",
                "candidate_path":path,
                "portable_verifier_sha256":portable_sha,
            },
            description="Independently restore MASTER plus chain plus candidate and verify it.",
        ),
        timeout=2000,
    )


def commit_candidate(run_id: str) -> dict[str,Any]:
    return invoke(
        GOVERNOR,
        envelope(
            run_id=run_id,
            task_id="collector-incremental-commit",
            provider="storage-governor",
            adapter="storage-governor-adapter",
            metadata_key="storage_governor",
            metadata_value={"action":"collector-incremental-commit"},
            description="Commit only an independently VERIFIED incremental candidate.",
        ),
        timeout=180,
    )


def main() -> int:
    LOCK.parent.mkdir(parents=True,exist_ok=True)
    lock_handle=LOCK.open("w")
    try:
        fcntl.flock(lock_handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:
        log("COLLECTOR_INCREMENTAL_AUTO_WATCH","SKIP_LOCKED")
        return 0

    started=now_iso()
    run_id="incremental-auto-"+uuid.uuid4().hex[:16]
    record: dict[str,Any]={
        "schema":"chacha.dev/collector-incremental-auto-watch-run/v1",
        "run_id":run_id,
        "started_at":started,
        "status":"RUNNING",
        "advanced":0,
        "events":[],
        "production_data_mutation":False,
    }

    try:
        require_runtime()
        portable_sha=sha256_file(PORTABLE_VERIFIER)
        before_state,before_pid=service_state()
        if before_state!="active" or not before_pid or before_pid=="0":
            raise WatchError(f"COLLECTOR_NOT_ACTIVE:state={before_state}:pid={before_pid}")

        log("COLLECTOR_INCREMENTAL_AUTO_WATCH","START")
        log("COLLECTOR_PID_BEFORE",before_pid)
        log("PORTABLE_VERIFIER_SHA256",portable_sha)

        for iteration in range(1,MAX_ADVANCE_PER_RUN+1):
            cycle_run=f"{run_id}-{iteration}"
            package=package_next(cycle_run)
            psummary=str(package.get("summary") or "")
            log("INCREMENTAL_PACKAGE_RESULT",psummary)

            if package.get("status")!="OK":
                raise WatchError(f"PACKAGE_FAILED:{psummary}")

            if psummary=="COLLECTOR_INCREMENTAL_NOOP":
                record["events"].append({"iteration":iteration,"package":psummary})
                break

            if psummary not in {
                "COLLECTOR_INCREMENTAL_CANDIDATE_CREATED",
                "COLLECTOR_INCREMENTAL_CANDIDATE_EXISTS",
            }:
                raise WatchError(f"PACKAGE_UNEXPECTED:{psummary}")

            candidate=candidate_path(package)
            verified=verify_candidate(cycle_run,candidate,portable_sha)
            vsummary=str(verified.get("summary") or "")
            log("INCREMENTAL_VERIFY_RESULT",vsummary)
            if verified.get("status")!="OK" or vsummary not in {
                "COLLECTOR_INCREMENTAL_RESTORE_VERIFIED",
                "COLLECTOR_INCREMENTAL_ALREADY_VERIFIED",
            }:
                raise WatchError(f"VERIFY_FAILED:{vsummary}")

            committed=commit_candidate(cycle_run)
            csummary=str(committed.get("summary") or "")
            log("INCREMENTAL_COMMIT_RESULT",csummary)
            if committed.get("status")!="OK" or csummary not in {
                "COLLECTOR_INCREMENTAL_COMMITTED",
                "COLLECTOR_INCREMENTAL_ALREADY_COMMITTED",
            }:
                raise WatchError(f"COMMIT_FAILED:{csummary}")

            record["advanced"]+=1
            record["events"].append({
                "iteration":iteration,
                "candidate":candidate,
                "package":psummary,
                "verification":vsummary,
                "commit":csummary,
            })

        after_state,after_pid=service_state()
        if after_state!="active":
            raise WatchError(f"COLLECTOR_AFTER_NOT_ACTIVE:{after_state}")
        if after_pid!=before_pid:
            raise WatchError(f"COLLECTOR_PID_CHANGED:{before_pid}->{after_pid}")

        record["status"]="PASS"
        record["finished_at"]=now_iso()
        record["collector_pid_before"]=before_pid
        record["collector_pid_after"]=after_pid
        record["service_interruption"]=False
        record["portable_verifier_sha256"]=portable_sha
        atomic_json(EVIDENCE,record)

        log("COLLECTOR_INCREMENTAL_ADVANCED",record["advanced"])
        log("COLLECTOR_SERVICE_INTERRUPTION","NO")
        log("COLLECTOR_INCREMENTAL_PRODUCTION_MUTATION","NO")
        log("COLLECTOR_INCREMENTAL_AUTO_WATCH","PASS")
        return 0
    except Exception as exc:
        record["status"]="FAILED"
        record["finished_at"]=now_iso()
        record["error"]=f"{type(exc).__name__}:{str(exc)[:500]}"
        try:
            state,pid=service_state()
            record["collector_service_after"]=state
            record["collector_pid_after"]=pid
        except Exception:
            pass
        atomic_json(EVIDENCE,record)
        log("COLLECTOR_INCREMENTAL_AUTO_WATCH","FAILED")
        log("COLLECTOR_INCREMENTAL_ERROR",record["error"])
        return 1


if __name__=="__main__":
    raise SystemExit(main())
