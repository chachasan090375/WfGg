#!/usr/bin/env python3
"""ChaCha DEV Collector incremental auto-watch V1.

One bounded iteration:
1. ask Storage Governor for the next completed-cycle candidate;
2. independently restore MASTER + committed chain + candidate;
3. only after VERIFIED receipt, commit the next chain state;
4. stop. A systemd timer schedules the next bounded iteration.

No Collector stop/restart is performed here.
"""
from __future__ import annotations

import fcntl
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

INPUT_SCHEMA="chacha.dev/dispatch-envelope/v1"
GOVERNOR=Path(os.environ.get(
    "CHACHA_STORAGE_GOVERNOR",
    "/opt/chacha-dev/adapters/storage-governor/current/storage-governor-adapter",
))
VERIFIER=Path(os.environ.get(
    "CHACHA_STORAGE_RESTORE_VERIFIER",
    "/opt/chacha-dev/adapters/storage-restore-verifier/current/storage-restore-verifier-adapter",
))
PORTABLE=Path(os.environ.get(
    "CHACHA_PORTABLE_RESTORE_VERIFIER",
    "/opt/chacha-dev/adapters/storage-restore-verifier/current/storage-restore-verifier-nas-linux-amd64",
))
PORTABLE_SHA=os.environ.get(
    "CHACHA_PORTABLE_RESTORE_VERIFIER_SHA256",
    "sha256:db0da08a11c2b2cbdddb5f1ac6b89aba228acac624815079e48e2fd13148eec3",
)
NAS_HOST=os.environ.get("CHACHA_NAS_HOST","chachanas")
NAS_ROOT=os.environ.get(
    "CHACHA_NAS_ROOT",
    "/share/CACHEDEV1_DATA/ChaCha-DEV-HUB",
)
DB_PATH=os.environ.get(
    "WFGG_COLLECTOR_DB",
    "/opt/wfgg-collector/data/collector.db",
)
LOCK=Path("/run/chacha-storage-incremental-watch.lock")
EVIDENCE=Path("/opt/chacha-dev/evidence")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_adapter(path: Path, envelope: dict[str,Any], timeout: int) -> dict[str,Any]:
    if not path.is_file():
        raise RuntimeError(f"ADAPTER_MISSING:{path}")
    proc=subprocess.run(
        [str(path)],
        input=json.dumps(envelope,separators=(",",":")).encode(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        shell=False,
        check=False,
        env={
            **os.environ,
            "CHACHA_NAS_HOST":NAS_HOST,
            "CHACHA_NAS_ROOT":NAS_ROOT,
            "CHACHA_PORTABLE_RESTORE_VERIFIER":str(PORTABLE),
            "WFGG_COLLECTOR_DB":DB_PATH,
        },
    )
    if not proc.stdout.strip():
        raise RuntimeError(
            f"ADAPTER_NO_RESULT:{path.name}:rc={proc.returncode}:"
            +proc.stderr.decode("utf-8","replace")[:160]
        )
    try:
        value=json.loads(proc.stdout.decode("utf-8"))
    except Exception as exc:
        raise RuntimeError(
            f"ADAPTER_RESULT_INVALID:{path.name}:{type(exc).__name__}:"
            +proc.stdout.decode("utf-8","replace")[:160]
        )
    if not isinstance(value,dict) or value.get("schema")!="chacha.dev/task-result/v1":
        raise RuntimeError(f"ADAPTER_RESULT_SCHEMA_INVALID:{path.name}")
    return value


def envelope(
    *,
    task_id: str,
    provider: str,
    adapter: str,
    action_key: str,
    action_cfg: dict[str,Any],
    resource_class: str="heavy",
    timeout_seconds: int=1800,
) -> dict[str,Any]:
    run_id="incremental-watch-"+datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return {
        "schema":INPUT_SCHEMA,
        "project":"wfgg-radar",
        "transition":task_id,
        "run_id":run_id,
        "wave":1,
        "task":{
            "id":task_id,
            "kind":"storage-governance",
            "description":"ChaCha DEV automatic Collector incremental chain iteration.",
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
            "resource_class":resource_class,
            "requires_storage_preflight":provider=="storage-governor",
            "human_approval_required":False,
            "approval_id":None,
            "timeout_seconds":timeout_seconds,
        },
        "workspace":"/opt/chacha-dev",
        "metadata":{action_key:action_cfg},
    }


def artifact_id(result: dict[str,Any], contains: str) -> str|None:
    for item in result.get("outputs") or []:
        if not isinstance(item,dict):
            continue
        value=str(item.get("id") or "")
        if contains in value:
            return value
    return None


def save_evidence(doc: dict[str,Any]) -> Path:
    EVIDENCE.mkdir(parents=True,exist_ok=True)
    stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path=EVIDENCE/f"storage-incremental-watch-{stamp}.json"
    tmp=path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(doc,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    os.chmod(tmp,0o600)
    os.replace(tmp,path)
    return path


def main() -> int:
    LOCK.parent.mkdir(parents=True,exist_ok=True)
    with LOCK.open("w") as lock:
        try:
            fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            print("STORAGE_INCREMENTAL_WATCH=SKIP reason=already_running")
            return 0

        started=now_iso()
        evidence={
            "schema":"chacha.dev/storage-incremental-watch-run/v1",
            "started_at":started,
            "status":"RUNNING",
            "collector_service_mutation":False,
            "production_data_mutation":False,
            "steps":[],
        }
        try:
            package_req=envelope(
                task_id="collector-incremental-candidate",
                provider="storage-governor",
                adapter="storage-governor-adapter",
                action_key="storage_governor",
                action_cfg={"action":"collector-incremental-package"},
            )
            package=run_adapter(GOVERNOR,package_req,1900)
            evidence["steps"].append({
                "step":"candidate",
                "status":package.get("status"),
                "summary":package.get("summary"),
            })

            if package.get("status")!="OK":
                raise RuntimeError(
                    "CANDIDATE_FAILED:"+str(package.get("summary"))
                )
            if package.get("summary")=="COLLECTOR_INCREMENTAL_NOOP":
                evidence["status"]="NOOP"
                evidence["completed_at"]=now_iso()
                path=save_evidence(evidence)
                print("STORAGE_INCREMENTAL_WATCH=NOOP")
                print(f"STORAGE_INCREMENTAL_WATCH_EVIDENCE={path}")
                return 0

            if package.get("summary") not in {
                "COLLECTOR_INCREMENTAL_CANDIDATE_CREATED",
                "COLLECTOR_INCREMENTAL_CANDIDATE_EXISTS",
            }:
                raise RuntimeError(
                    "CANDIDATE_RESULT_UNEXPECTED:"+str(package.get("summary"))
                )

            candidate=artifact_id(package,"collector-chain-candidate-")
            if not candidate:
                raise RuntimeError("CANDIDATE_PATH_MISSING")

            verify_req=envelope(
                task_id="collector-incremental-independent-verify",
                provider="storage-restore-verifier",
                adapter="storage-restore-verifier-adapter",
                action_key="storage_restore_verifier",
                action_cfg={
                    "action":"verify-incremental-candidate",
                    "candidate_path":candidate,
                    "portable_verifier_sha256":PORTABLE_SHA,
                },
            )
            verified=run_adapter(VERIFIER,verify_req,2200)
            evidence["steps"].append({
                "step":"independent-verify",
                "status":verified.get("status"),
                "summary":verified.get("summary"),
                "candidate":candidate,
            })
            if (
                verified.get("status")!="OK"
                or verified.get("summary")!="COLLECTOR_INCREMENTAL_RESTORE_VERIFIED"
                or (verified.get("verification") or {}).get("status")!="VERIFIED"
            ):
                raise RuntimeError(
                    "INDEPENDENT_VERIFICATION_FAILED:"+
                    str(verified.get("summary"))
                )

            commit_req=envelope(
                task_id="collector-incremental-commit",
                provider="storage-governor",
                adapter="storage-governor-adapter",
                action_key="storage_governor",
                action_cfg={"action":"collector-incremental-commit"},
                resource_class="light",
                timeout_seconds=300,
            )
            committed=run_adapter(GOVERNOR,commit_req,360)
            evidence["steps"].append({
                "step":"commit",
                "status":committed.get("status"),
                "summary":committed.get("summary"),
            })
            if (
                committed.get("status")!="OK"
                or committed.get("summary") not in {
                    "COLLECTOR_INCREMENTAL_COMMITTED",
                    "COLLECTOR_INCREMENTAL_ALREADY_COMMITTED",
                }
            ):
                raise RuntimeError(
                    "COMMIT_FAILED:"+str(committed.get("summary"))
                )

            evidence["status"]="PASS"
            evidence["completed_at"]=now_iso()
            evidence["candidate_path"]=candidate
            state=artifact_id(committed,"collector-chain-state-")
            if state:
                evidence["committed_state"]=state
            path=save_evidence(evidence)
            print("STORAGE_INCREMENTAL_WATCH=PASS")
            print(f"STORAGE_INCREMENTAL_WATCH_CANDIDATE={candidate}")
            if state:
                print(f"STORAGE_INCREMENTAL_WATCH_STATE={state}")
            print(f"STORAGE_INCREMENTAL_WATCH_EVIDENCE={path}")
            return 0
        except Exception as exc:
            evidence["status"]="FAILED"
            evidence["completed_at"]=now_iso()
            evidence["error"]=f"{type(exc).__name__}:{str(exc)[:300]}"
            path=save_evidence(evidence)
            print("STORAGE_INCREMENTAL_WATCH=FAILED")
            print(f"STORAGE_INCREMENTAL_WATCH_ERROR={evidence['error']}")
            print(f"STORAGE_INCREMENTAL_WATCH_EVIDENCE={path}")
            return 1


if __name__=="__main__":
    raise SystemExit(main())
