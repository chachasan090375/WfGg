#!/usr/bin/env python3
"""ChaCha DEV HUB NAS SSH Adapter V1.

Structured storage adapter for a private NAS reached from the VPS through a
preconfigured SSH host alias. It supports:
- preflight: read-only capacity/health check
- put-file: create-only atomic file publication under an allowlisted NAS root

The adapter never invokes a local shell, never accepts an arbitrary host or
absolute remote path from the task, never overwrites an existing destination,
and never deletes persistent NAS content.
"""
from __future__ import annotations

import hashlib
import json
import os
import posixpath
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

INPUT_SCHEMA = "chacha.dev/dispatch-envelope/v1"
OUTPUT_SCHEMA = "chacha.dev/task-result/v1"
ADAPTER_ID = "nas-ssh-adapter"
PROVIDER_ID = "nas"
SAFE_REL = re.compile(r"^[A-Za-z0-9._/-]+$")
DEFAULT_HOST = "chachanas"
DEFAULT_ROOT = "/share/CACHEDEV1_DATA/ChaCha-DEV-HUB"
DEFAULT_TIMEOUT = 20
DEFAULT_RESERVE_MB = 1024


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def result(request: dict[str, Any], status: str, summary: str,
           evidence: list[dict[str, Any]] | None = None,
           outputs: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    task = request.get("task") if isinstance(request.get("task"), dict) else {}
    return {
        "schema": OUTPUT_SCHEMA,
        "project": str(request.get("project") or "unknown"),
        "task_id": str(task.get("id") or "unknown"),
        "status": status,
        "producer": ADAPTER_ID,
        "observed_at": now_iso(),
        "summary": summary,
        "evidence": evidence or [],
        "verification": {
            "status": "UNVERIFIED",
            "method": "none",
            "verifier": "none",
            "observed_at": now_iso(),
            "notes": "Storage adapter output requires independent verification."
        },
        "outputs": outputs or [],
    }


def emit(payload: dict[str, Any], code: int = 0) -> int:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
    return code


def blocked(request: dict[str, Any], reason: str) -> int:
    evidence = [{
        "kind": "report",
        "source": "nas-ssh-adapter-policy",
        "digest": sha256_bytes(reason.encode()),
        "details": {"reason": reason},
    }]
    return emit(result(request, "BLOCKED", reason, evidence))


def validate_request(request: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    if request.get("schema") != INPUT_SCHEMA:
        return None, "INPUT_SCHEMA_INVALID"
    task = request.get("task")
    if not isinstance(task, dict) or not task.get("id"):
        return None, "TASK_ID_MISSING"
    bindings = request.get("bindings")
    if not isinstance(bindings, list) or not any(
        isinstance(x, dict)
        and x.get("provider") == PROVIDER_ID
        and x.get("adapter") == ADAPTER_ID
        for x in bindings
    ):
        return None, "NAS_BINDING_MISSING"
    metadata = request.get("metadata")
    storage = metadata.get("nas_storage") if isinstance(metadata, dict) else None
    if not isinstance(storage, dict):
        return None, "NAS_STORAGE_METADATA_MISSING"
    action = str(storage.get("action") or "")
    permission = str(task.get("permission") or "")
    if action == "preflight" and permission != "read":
        return None, "NAS_PREFLIGHT_REQUIRES_READ"
    if action == "put-file" and permission != "workspace-write":
        return None, "NAS_PUT_FILE_REQUIRES_WORKSPACE_WRITE"
    if action not in {"preflight", "put-file"}:
        return None, "NAS_ACTION_NOT_ALLOWED"
    return storage, None


def command_timeout(request: dict[str, Any]) -> int:
    policy = request.get("policy_context") if isinstance(request.get("policy_context"), dict) else {}
    try:
        value = int(policy.get("timeout_seconds") or DEFAULT_TIMEOUT)
    except Exception:
        value = DEFAULT_TIMEOUT
    return max(1, min(value, 60))


def ssh_bin() -> str:
    value = os.environ.get("CHACHA_NAS_SSH_BIN", "/usr/bin/ssh")
    if not value.startswith("/"):
        raise ValueError("SSH_BIN_MUST_BE_ABSOLUTE")
    return value


def scp_bin() -> str:
    value = os.environ.get("CHACHA_NAS_SCP_BIN", "/usr/bin/scp")
    if not value.startswith("/"):
        raise ValueError("SCP_BIN_MUST_BE_ABSOLUTE")
    return value


def nas_host() -> str:
    host = os.environ.get("CHACHA_NAS_HOST", DEFAULT_HOST).strip()
    if not re.fullmatch(r"[A-Za-z0-9._-]+", host):
        raise ValueError("NAS_HOST_INVALID")
    return host


def nas_root() -> str:
    root = os.environ.get("CHACHA_NAS_ROOT", DEFAULT_ROOT).strip()
    if not root.startswith("/") or ".." in PurePosixPath(root).parts:
        raise ValueError("NAS_ROOT_INVALID")
    return root.rstrip("/")


def safe_relative(value: str) -> str:
    value = value.strip().lstrip("/")
    if not value or not SAFE_REL.fullmatch(value):
        raise ValueError("NAS_RELATIVE_PATH_INVALID")
    parts = PurePosixPath(value).parts
    if any(p in {"", ".", ".."} for p in parts):
        raise ValueError("NAS_RELATIVE_PATH_INVALID")
    return "/".join(parts)


def run(argv: list[str], timeout: int) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        argv,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        shell=False,
        check=False,
    )


def ssh_args(host: str) -> list[str]:
    return [ssh_bin(), "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", host]


def preflight(request: dict[str, Any], storage: dict[str, Any]) -> int:
    host, root, timeout = nas_host(), nas_root(), command_timeout(request)
    proc = run(ssh_args(host) + ["df", "-Pk", root], timeout)
    if proc.returncode != 0:
        return emit(result(request, "FAILED", "NAS_PREFLIGHT_SSH_FAILED", [{
            "kind": "metric",
            "source": f"nas://{host}",
            "digest": sha256_bytes(proc.stderr[:4096]),
            "details": {"returncode": proc.returncode},
        }]))
    lines = [x for x in proc.stdout.decode("utf-8", "replace").splitlines() if x.strip()]
    if len(lines) < 2:
        return emit(result(request, "FAILED", "NAS_PREFLIGHT_DF_INVALID"))
    fields = lines[-1].split()
    if len(fields) < 4:
        return emit(result(request, "FAILED", "NAS_PREFLIGHT_DF_INVALID"))
    try:
        total_kb, used_kb, free_kb = int(fields[1]), int(fields[2]), int(fields[3])
    except Exception:
        return emit(result(request, "FAILED", "NAS_PREFLIGHT_DF_INVALID"))
    free_mb = free_kb / 1024
    used_pct = (used_kb / total_kb * 100) if total_kb else 100.0
    need_mb = float(storage.get("need_mb") or 0)
    reserve_mb = float(storage.get("reserve_mb") or DEFAULT_RESERVE_MB)
    required = need_mb + reserve_mb
    status = "OK" if free_mb >= required else "BLOCKED"
    summary = "NAS_PREFLIGHT_OK" if status == "OK" else "NAS_PREFLIGHT_INSUFFICIENT_SPACE"
    evidence = [{
        "kind": "metric",
        "source": f"nas://{host}{root}",
        "digest": sha256_bytes(proc.stdout),
        "details": {
            "free_mb": round(free_mb, 2),
            "used_percent": round(used_pct, 2),
            "need_mb": need_mb,
            "reserve_mb": reserve_mb,
            "required_free_mb": required,
        },
    }]
    return emit(result(request, status, summary, evidence, [{
        "type": "gate", "id": "storage-preflight",
        "status": "OK" if status == "OK" else "MISSING",
        "reason": summary,
    }]))


def put_file(request: dict[str, Any], storage: dict[str, Any]) -> int:
    policy = request.get("policy_context") if isinstance(request.get("policy_context"), dict) else {}
    if policy.get("human_approval_required") is True and not policy.get("approval_id"):
        return blocked(request, "NAS_WRITE_APPROVAL_MISSING")

    workspace = Path(str(request.get("workspace") or "")).resolve()
    local_raw = str(storage.get("local_path") or "")
    if not local_raw or not workspace.is_absolute():
        return blocked(request, "NAS_LOCAL_PATH_INVALID")
    local = Path(local_raw)
    if not local.is_absolute():
        local = workspace / local
    local = local.resolve()
    try:
        local.relative_to(workspace)
    except ValueError:
        return blocked(request, "NAS_LOCAL_PATH_OUTSIDE_WORKSPACE")
    if not local.is_file():
        return blocked(request, "NAS_LOCAL_FILE_MISSING")

    try:
        relative = safe_relative(str(storage.get("remote_path") or ""))
    except ValueError as exc:
        return blocked(request, str(exc))

    host, root, timeout = nas_host(), nas_root(), command_timeout(request)
    final = posixpath.join(root, relative)
    run_id = re.sub(r"[^A-Za-z0-9._-]", "_", str(request.get("run_id") or "run"))[:64]
    temp = final + ".incoming-" + run_id

    exists = run(ssh_args(host) + ["test", "!", "-e", final], timeout)
    if exists.returncode != 0:
        return blocked(request, "NAS_DESTINATION_ALREADY_EXISTS")

    size_mb = local.stat().st_size / (1024 * 1024)
    pre = run(ssh_args(host) + ["df", "-Pk", root], timeout)
    if pre.returncode != 0:
        return emit(result(request, "FAILED", "NAS_PREFLIGHT_SSH_FAILED"))
    fields = pre.stdout.decode("utf-8", "replace").splitlines()[-1].split()
    try:
        free_mb = int(fields[3]) / 1024
    except Exception:
        return emit(result(request, "FAILED", "NAS_PREFLIGHT_DF_INVALID"))
    reserve_mb = float(storage.get("reserve_mb") or DEFAULT_RESERVE_MB)
    if free_mb < size_mb + reserve_mb:
        return blocked(request, "NAS_PREFLIGHT_INSUFFICIENT_SPACE")

    # The destination may be several levels below the NAS root. The original
    # V1 pilot prepared its parent directory out-of-band, which made later
    # immutable Experience Ledger writes fail with NAS_COPY_FAILED. Directory
    # preparation belongs inside the storage adapter so every create-only put
    # is self-contained and still constrained to the validated allowlisted path.
    parent = posixpath.dirname(final)
    prepare = run(ssh_args(host) + ["mkdir", "-p", parent], timeout)
    if prepare.returncode != 0:
        return emit(result(request, "FAILED", "NAS_PARENT_PREPARE_FAILED", [{
            "kind": "report",
            "source": f"nas://{host}{root}",
            "digest": sha256_bytes(prepare.stderr[:4096]),
            "details": {"returncode": prepare.returncode},
        }]))

    copy = run([scp_bin(), "-q", "--", str(local), f"{host}:{temp}"], timeout)
    if copy.returncode != 0:
        return emit(result(request, "FAILED", "NAS_COPY_FAILED", [{
            "kind": "report",
            "source": f"nas://{host}{root}",
            "digest": sha256_bytes(copy.stderr[:4096]),
            "details": {"returncode": copy.returncode},
        }]))

    local_hash = sha256_file(local)
    remote_hash_proc = run(ssh_args(host) + ["sha256sum", temp], timeout)
    if remote_hash_proc.returncode != 0:
        return emit(result(request, "FAILED", "NAS_REMOTE_HASH_FAILED"))
    remote_hash = remote_hash_proc.stdout.decode("utf-8", "replace").split()[0].strip()
    if local_hash != remote_hash:
        return emit(result(request, "FAILED", "NAS_HASH_MISMATCH"))

    move = run(ssh_args(host) + ["mv", temp, final], timeout)
    if move.returncode != 0:
        return emit(result(request, "FAILED", "NAS_ATOMIC_PUBLISH_FAILED"))

    evidence = [{
        "kind": "file",
        "source": f"nas://{host}/{relative}",
        "digest": "sha256:" + local_hash,
        "details": {"bytes": local.stat().st_size, "mode": "create-only-atomic"},
    }]
    return emit(result(request, "OK", "NAS_PUT_FILE_OK", evidence, [{
        "type": "artifact", "id": relative, "status": "UNVERIFIED",
        "reason": "Copied and SHA256-matched; independent verification still required.",
    }]))


def main() -> int:
    try:
        request = json.load(sys.stdin)
    except Exception as exc:
        minimal = {"project": "unknown", "task": {"id": "unknown"}}
        return emit(result(minimal, "BLOCKED", f"INPUT_JSON_INVALID:{type(exc).__name__}"), 2)
    if not isinstance(request, dict):
        minimal = {"project": "unknown", "task": {"id": "unknown"}}
        return emit(result(minimal, "BLOCKED", "INPUT_ROOT_NOT_OBJECT"), 2)

    storage, error = validate_request(request)
    if error:
        return blocked(request, error)
    assert storage is not None

    try:
        if storage.get("action") == "preflight":
            return preflight(request, storage)
        return put_file(request, storage)
    except subprocess.TimeoutExpired:
        return emit(result(request, "FAILED", "NAS_COMMAND_TIMEOUT"))
    except (OSError, ValueError) as exc:
        return emit(result(request, "FAILED", f"NAS_RUNTIME_ERROR:{type(exc).__name__}"))


if __name__ == "__main__":
    raise SystemExit(main())
