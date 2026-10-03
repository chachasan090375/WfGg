"""Read-only NAS readback adapter for Cognitive Memory Fabric shadow use."""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

INPUT_SCHEMA = "chacha.dev/dispatch-envelope/v1"
OUTPUT_SCHEMA = "chacha.dev/task-result/v1"
POLICY_SCHEMA = "chacha.dev/nas-readback-adapter-policy/v1"
PROVIDER_ID = "nas-readback"
ADAPTER_ID = "nas-readback-adapter"
SAFE_REL = re.compile(r"^[A-Za-z0-9._/-]+$")
POLICY_PATH = Path(__file__).resolve().parents[1] / "config/nas-readback-adapter.v1.json"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()

def load_policy() -> dict[str, Any]:
    value = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema") != POLICY_SCHEMA:
        raise RuntimeError("NAS_READBACK_POLICY_INVALID")
    return value


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
            "status": "VERIFIED" if status == "OK" else "FAILED",
            "method": "remote-and-local-sha256",
            "verifier": ADAPTER_ID,
            "observed_at": now_iso(),
        },
        "outputs": outputs or [],
    }


def emit(payload: dict[str, Any], code: int = 0) -> int:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
    return code


def blocked(request: dict[str, Any], reason: str) -> int:
    return emit(result(request, "BLOCKED", reason), 2)

def safe_relative(value: str) -> str:
    value = value.strip().lstrip("/")
    if not value or not SAFE_REL.fullmatch(value):
        raise ValueError("NAS_READBACK_RELATIVE_PATH_INVALID")
    parts = PurePosixPath(value).parts
    if any(p in {"", ".", ".."} for p in parts):
        raise ValueError("NAS_READBACK_RELATIVE_PATH_INVALID")
    return "/".join(parts)


def is_under(path: Path, roots: list[Path]) -> bool:
    for root in roots:
        try:
            path.relative_to(root)
            return True
        except ValueError:
            continue
    return False


def validate_request(request: dict[str, Any], policy: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    if request.get("schema") != INPUT_SCHEMA:
        return None, "INPUT_SCHEMA_INVALID"
    task = request.get("task")
    if not isinstance(task, dict) or not task.get("id"):
        return None, "TASK_ID_MISSING"
    if str(task.get("permission") or "") != "workspace-write":
        return None, "NAS_READBACK_REQUIRES_WORKSPACE_WRITE"
    bindings = request.get("bindings")
    if not isinstance(bindings, list) or not any(
        isinstance(x, dict) and x.get("provider") == PROVIDER_ID and x.get("adapter") == ADAPTER_ID
        for x in bindings
    ):
        return None, "NAS_READBACK_BINDING_MISSING"
    metadata = request.get("metadata")
    cfg = metadata.get("nas_readback") if isinstance(metadata, dict) else None
    if not isinstance(cfg, dict) or cfg.get("action") != "read-file":
        return None, "NAS_READBACK_METADATA_INVALID"
    return cfg, None

def resolve_paths(request: dict[str, Any], cfg: dict[str, Any], policy: dict[str, Any]) -> tuple[str, Path, str]:
    remote = safe_relative(str(cfg.get("remote_path") or ""))
    prefixes = [str(x) for x in policy["nas"]["allowed_prefixes"]]
    if not any(remote.startswith(prefix) for prefix in prefixes):
        raise ValueError("NAS_READBACK_REMOTE_PATH_NOT_ALLOWLISTED")
    expected = str(cfg.get("expected_sha256") or "")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", expected):
        raise ValueError("NAS_READBACK_EXPECTED_SHA256_REQUIRED")
    workspace_raw = str(request.get("workspace") or "")
    if not workspace_raw:
        raise ValueError("NAS_READBACK_WORKSPACE_REQUIRED")
    workspace = Path(workspace_raw).resolve(strict=True)
    if not workspace.is_dir():
        raise ValueError("NAS_READBACK_WORKSPACE_INVALID")
    roots = [Path(x).resolve() for x in policy["workspace"]["allowed_roots"]]
    if not is_under(workspace, roots):
        raise ValueError("NAS_READBACK_WORKSPACE_NOT_ALLOWLISTED")
    local_rel = safe_relative(str(cfg.get("local_path") or ""))
    destination = (workspace / local_rel).resolve()
    try:
        destination.relative_to(workspace)
    except ValueError as exc:
        raise ValueError("NAS_READBACK_LOCAL_PATH_OUTSIDE_WORKSPACE") from exc
    if destination.exists():
        raise ValueError("NAS_READBACK_LOCAL_DESTINATION_EXISTS")
    return remote, destination, expected


def run(argv: list[str], timeout: int = 60) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        argv,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        shell=False,
        check=False,
    )

def ssh_base(policy: dict[str, Any]) -> list[str]:
    host = str(policy["nas"]["host"])
    if not re.fullmatch(r"[A-Za-z0-9._-]+", host):
        raise ValueError("NAS_READBACK_POLICY_HOST_INVALID")
    return ["/usr/bin/ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", host]


def remote_absolute(policy: dict[str, Any], relative: str) -> str:
    root = str(policy["nas"]["root"]).rstrip("/")
    if not root.startswith("/") or ".." in PurePosixPath(root).parts:
        raise ValueError("NAS_READBACK_POLICY_ROOT_INVALID")
    return root + "/" + relative


def remote_size(policy: dict[str, Any], remote: str) -> int:
    proc = run(ssh_base(policy) + ["stat", "-c", "%s", remote], timeout=30)
    if proc.returncode != 0:
        raise RuntimeError("NAS_READBACK_REMOTE_STAT_FAILED")
    try:
        value = int(proc.stdout.decode("utf-8", "replace").strip())
    except Exception as exc:
        raise RuntimeError("NAS_READBACK_REMOTE_SIZE_INVALID") from exc
    if value < 0:
        raise RuntimeError("NAS_READBACK_REMOTE_SIZE_INVALID")
    return value


def remote_sha256(policy: dict[str, Any], remote: str) -> str:
    proc = run(ssh_base(policy) + ["sha256sum", remote], timeout=60)
    if proc.returncode != 0:
        raise RuntimeError("NAS_READBACK_REMOTE_SHA256_FAILED")
    value = proc.stdout.decode("utf-8", "replace").split()[0].strip()
    if not re.fullmatch(r"[0-9a-f]{64}", value):
        raise RuntimeError("NAS_READBACK_REMOTE_SHA256_INVALID")
    return "sha256:" + value

def readback(request: dict[str, Any], cfg: dict[str, Any], policy: dict[str, Any]) -> int:
    remote_rel, destination, expected = resolve_paths(request, cfg, policy)
    remote = remote_absolute(policy, remote_rel)
    size = remote_size(policy, remote)
    maximum = int(policy["integrity"]["maximum_bytes"])
    if size > maximum:
        return blocked(request, "NAS_READBACK_REMOTE_FILE_TOO_LARGE")
    remote_digest = remote_sha256(policy, remote)
    if remote_digest != expected:
        return blocked(request, "NAS_READBACK_REMOTE_SHA256_MISMATCH")

    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_name(destination.name + f".incoming-{os.getpid()}")
    if temp.exists():
        temp.unlink()
    host = str(policy["nas"]["host"])
    copy = run(["/usr/bin/scp", "-q", "--", f"{host}:{remote}", str(temp)], timeout=90)
    if copy.returncode != 0:
        if temp.exists():
            temp.unlink()
        return emit(result(request, "FAILED", "NAS_READBACK_COPY_FAILED"), 3)
    local_digest = sha256_file(temp)
    if local_digest != expected:
        temp.unlink(missing_ok=True)
        return emit(result(request, "FAILED", "NAS_READBACK_LOCAL_SHA256_MISMATCH"), 3)
    if temp.stat().st_size != size:
        temp.unlink(missing_ok=True)
        return emit(result(request, "FAILED", "NAS_READBACK_SIZE_MISMATCH"), 3)
    try:
        os.link(temp, destination)
    except FileExistsError:
        temp.unlink(missing_ok=True)
        return blocked(request, "NAS_READBACK_LOCAL_DESTINATION_EXISTS")
    except OSError:
        temp.unlink(missing_ok=True)
        return emit(result(request, "FAILED", "NAS_READBACK_ATOMIC_LOCAL_PUBLISH_FAILED"), 3)
    temp.unlink(missing_ok=True)

    evidence = [{
        "kind": "file",
        "source": f"nas-readback://{remote_rel}",
        "digest": expected,
        "details": {
            "bytes": size,
            "remote_sha256_verified": True,
            "local_sha256_verified": True,
            "remote_write_performed": False,
        },
    }]
    outputs = [{
        "type": "artifact",
        "id": str(destination),
        "status": "VERIFIED",
        "reason": "Read-only NAS copy verified by remote and local SHA-256.",
    }]
    return emit(result(request, "OK", "NAS_READBACK_OK", evidence, outputs))


def main() -> int:
    try:
        request = json.load(sys.stdin)
    except Exception as exc:
        minimal = {"project": "unknown", "task": {"id": "unknown"}}
        return emit(result(minimal, "BLOCKED", f"INPUT_JSON_INVALID:{type(exc).__name__}"), 2)
    if not isinstance(request, dict):
        minimal = {"project": "unknown", "task": {"id": "unknown"}}
        return emit(result(minimal, "BLOCKED", "INPUT_ROOT_NOT_OBJECT"), 2)
    try:
        policy = load_policy()
        cfg, error = validate_request(request, policy)
        if error:
            return blocked(request, error)
        assert cfg is not None
        return readback(request, cfg, policy)
    except subprocess.TimeoutExpired:
        return emit(result(request, "FAILED", "NAS_READBACK_COMMAND_TIMEOUT"), 3)
    except (OSError, RuntimeError, ValueError, KeyError) as exc:
        return emit(result(request, "BLOCKED", str(exc)), 2)


if __name__ == "__main__":
    raise SystemExit(main())
