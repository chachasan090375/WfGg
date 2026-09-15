#!/usr/bin/env python3
"""ChaCha DEV HUB Adapter Runtime Provisioning V1.

Installs a configured local adapter into a versioned runtime directory, verifies
its SHA-256, atomically updates the current symlink, performs a non-destructive
structured probe, and writes a machine-readable receipt. It never changes the
provider-adapter registry or adapter lifecycle status.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

POLICY_SCHEMA = "chacha.dev/adapter-provisioning/v1"
RECEIPT_SCHEMA = "chacha.dev/adapter-provisioning-receipt/v1"
REPO_ROOT = Path(__file__).resolve().parents[2]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit(f"FILE_NOT_FOUND={path}")
    except json.JSONDecodeError as exc:
        raise SystemExit(f"JSON_INVALID={path}:{exc.lineno}:{exc.colno}:{exc.msg}")
    if not isinstance(value, dict):
        raise SystemExit(f"JSON_ROOT_NOT_OBJECT={path}")
    return value


def digest_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def digest_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(value, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def inside(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def config_for(policy: dict[str, Any], adapter: str) -> dict[str, Any]:
    item = (policy.get("adapters") or {}).get(adapter)
    if not isinstance(item, dict):
        raise SystemExit(f"ADAPTER_NOT_CONFIGURED={adapter}")
    return item


def resolve_paths(policy: dict[str, Any], item: dict[str, Any], root_override: str | None) -> dict[str, Path]:
    target_root = Path(root_override or str(policy.get("target_root") or ""))
    if not target_root.is_absolute():
        raise SystemExit("TARGET_ROOT_MUST_BE_ABSOLUTE")
    if root_override and not policy.get("sandbox_root_override_allowed", False):
        raise SystemExit("TARGET_ROOT_OVERRIDE_FORBIDDEN")

    source = (REPO_ROOT / str(item.get("source") or "")).resolve()
    if not inside(source, REPO_ROOT):
        raise SystemExit("SOURCE_OUTSIDE_REPOSITORY")
    namespace = str(item.get("namespace") or "").strip("/.")
    version = str(item.get("version") or "").strip("/.")
    executable_name = str(item.get("executable_name") or "").strip("/.")
    current_link_name = str(item.get("current_link_name") or "current").strip("/.")
    if not namespace or not version or not executable_name or not current_link_name:
        raise SystemExit("PROVISIONING_PATH_COMPONENT_INVALID")

    namespace_root = target_root / namespace
    version_dir = namespace_root / version
    installed = version_dir / executable_name
    current_link = namespace_root / current_link_name
    executable = current_link / executable_name
    for path in (version_dir, installed, current_link, executable):
        if not inside(path.parent if path.name == current_link_name else path, target_root):
            raise SystemExit("PROVISIONING_PATH_ESCAPE")
    return {
        "target_root": target_root,
        "source": source,
        "namespace_root": namespace_root,
        "version_dir": version_dir,
        "installed": installed,
        "current_link": current_link,
        "executable": executable,
    }


def probe(executable: Path, item: dict[str, Any], timeout: int) -> dict[str, Any]:
    cfg = item.get("probe") if isinstance(item.get("probe"), dict) else {}
    payload = cfg.get("input") if isinstance(cfg.get("input"), dict) else {}
    try:
        proc = subprocess.run(
            [str(executable)],
            input=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
            shell=False,
            env={**os.environ, "CHACHA_HTTP_SMOKE_ALLOWED_HOSTS": ""},
        )
        stdout, stderr = proc.stdout, proc.stderr
        try:
            result = json.loads(stdout.decode("utf-8"))
        except Exception:
            result = None
        expected_schema = cfg.get("expected_schema")
        expected_status = cfg.get("expected_status")
        expected_producer = cfg.get("expected_producer")
        expected_verification = cfg.get("expected_verification_status")
        verification = result.get("verification") if isinstance(result, dict) and isinstance(result.get("verification"), dict) else {}
        ok = bool(
            proc.returncode == 0
            and isinstance(result, dict)
            and result.get("schema") == expected_schema
            and result.get("status") == expected_status
            and result.get("producer") == expected_producer
            and verification.get("status") == expected_verification
        )
        return {
            "status": "PASS" if ok else "FAIL",
            "exit_code": proc.returncode,
            "result_schema": result.get("schema") if isinstance(result, dict) else None,
            "result_status": result.get("status") if isinstance(result, dict) else None,
            "producer": result.get("producer") if isinstance(result, dict) else None,
            "verification_status": verification.get("status") if isinstance(verification, dict) else None,
            "stdout_digest": digest_bytes(stdout),
            "stderr_digest": digest_bytes(stderr),
            "failure": None if ok else "STRUCTURED_PROBE_MISMATCH",
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "status": "FAIL",
            "exit_code": None,
            "result_schema": None,
            "result_status": None,
            "producer": None,
            "verification_status": None,
            "stdout_digest": digest_bytes(exc.stdout or b""),
            "stderr_digest": digest_bytes(exc.stderr or b""),
            "failure": "PROBE_TIMEOUT",
        }
    except OSError as exc:
        return {
            "status": "FAIL",
            "exit_code": None,
            "result_schema": None,
            "result_status": None,
            "producer": None,
            "verification_status": None,
            "stdout_digest": None,
            "stderr_digest": digest_bytes(str(exc).encode("utf-8")),
            "failure": "PROBE_START_FAILED",
        }


def plan(adapter: str, policy: dict[str, Any], item: dict[str, Any], paths: dict[str, Path]) -> dict[str, Any]:
    source = paths["source"]
    if not source.is_file():
        raise SystemExit(f"SOURCE_NOT_FOUND={source}")
    return {
        "schema": "chacha.dev/adapter-provisioning-plan/v1",
        "adapter": adapter,
        "version": item.get("version"),
        "source": str(source),
        "source_digest": digest_file(source),
        "target_root": str(paths["target_root"]),
        "installed_path": str(paths["installed"]),
        "current_link": str(paths["current_link"]),
        "executable_path": str(paths["executable"]),
        "applied": False,
        "observed_at": now_iso(),
    }


def install(adapter: str, actor: str, policy: dict[str, Any], item: dict[str, Any], paths: dict[str, Path]) -> dict[str, Any]:
    source = paths["source"]
    if not source.is_file():
        raise SystemExit(f"SOURCE_NOT_FOUND={source}")
    source_digest = digest_file(source)
    paths["namespace_root"].mkdir(parents=True, exist_ok=True)
    paths["version_dir"].mkdir(parents=True, exist_ok=True)
    installed = paths["installed"]
    idempotent = False

    if installed.exists():
        if not installed.is_file():
            raise SystemExit("VERSION_TARGET_NOT_FILE")
        existing_digest = digest_file(installed)
        if existing_digest != source_digest:
            raise SystemExit("VERSION_COLLISION_DIGEST_MISMATCH")
        idempotent = True
    else:
        fd, tmp_name = tempfile.mkstemp(prefix=installed.name + ".", suffix=".tmp", dir=str(paths["version_dir"]))
        try:
            with os.fdopen(fd, "wb") as fh, source.open("rb") as src:
                shutil.copyfileobj(src, fh)
                fh.flush()
                os.fsync(fh.fileno())
            os.chmod(tmp_name, int(str(item.get("mode") or "0755"), 8))
            os.replace(tmp_name, installed)
        finally:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)

    installed_digest = digest_file(installed)
    if installed_digest != source_digest:
        raise SystemExit("INSTALLED_DIGEST_MISMATCH")
    os.chmod(installed, int(str(item.get("mode") or "0755"), 8))
    mode = oct(stat.S_IMODE(installed.stat().st_mode))

    link = paths["current_link"]
    previous = os.readlink(link) if link.is_symlink() else None
    if link.exists() and not link.is_symlink():
        raise SystemExit("CURRENT_LINK_PATH_IS_NOT_SYMLINK")
    desired_target = str(paths["version_dir"].relative_to(paths["namespace_root"]))
    tmp_link = paths["namespace_root"] / (link.name + f".tmp-{os.getpid()}")
    try:
        if tmp_link.exists() or tmp_link.is_symlink():
            tmp_link.unlink()
        os.symlink(desired_target, tmp_link)
        os.replace(tmp_link, link)
    finally:
        if tmp_link.exists() or tmp_link.is_symlink():
            tmp_link.unlink()

    executable = paths["executable"]
    if not executable.is_file() or not os.access(executable, os.X_OK):
        raise SystemExit("PROVISIONED_EXECUTABLE_NOT_EXECUTABLE")
    executable_digest = digest_file(executable)
    if executable_digest != source_digest:
        raise SystemExit("CURRENT_EXECUTABLE_DIGEST_MISMATCH")

    probe_result = probe(executable, item, int(policy.get("probe_timeout_seconds") or 10))
    if probe_result.get("status") != "PASS":
        raise SystemExit(f"PROVISIONING_PROBE_FAILED:{probe_result.get('failure')}")

    return {
        "schema": RECEIPT_SCHEMA,
        "adapter": adapter,
        "version": str(item.get("version")),
        "actor": actor,
        "observed_at": now_iso(),
        "applied": True,
        "idempotent": idempotent,
        "target_root": str(paths["target_root"]),
        "source": str(source),
        "source_digest": source_digest,
        "installed_path": str(installed),
        "installed_digest": installed_digest,
        "executable_path": str(executable),
        "executable_digest": executable_digest,
        "mode": mode,
        "current_link": str(link),
        "current_target": desired_target,
        "previous_link_target": previous,
        "probe": probe_result,
    }


def verify_receipt(receipt: dict[str, Any], policy: dict[str, Any], item: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    if receipt.get("schema") != RECEIPT_SCHEMA:
        blockers.append("RECEIPT_SCHEMA_INVALID")
    installed = Path(str(receipt.get("installed_path") or ""))
    executable = Path(str(receipt.get("executable_path") or ""))
    current_link = Path(str(receipt.get("current_link") or ""))
    if not installed.is_file() or digest_file(installed) != receipt.get("installed_digest"):
        blockers.append("INSTALLED_DIGEST_INVALID")
    if not executable.is_file() or digest_file(executable) != receipt.get("executable_digest"):
        blockers.append("EXECUTABLE_DIGEST_INVALID")
    if not current_link.is_symlink() or os.readlink(current_link) != receipt.get("current_target"):
        blockers.append("CURRENT_LINK_INVALID")
    if not blockers:
        probe_result = probe(executable, item, int(policy.get("probe_timeout_seconds") or 10))
        if probe_result.get("status") != "PASS":
            blockers.append("PROVISIONING_PROBE_FAILED")
    return blockers


def main() -> int:
    parser = argparse.ArgumentParser(description="Provision local DEV HUB adapters")
    parser.add_argument("--policy", type=Path, default=Path("dev-hub/config/adapter-provisioning.v1.json"))
    parser.add_argument("--root")
    sub = parser.add_subparsers(dest="command", required=True)

    p_plan = sub.add_parser("plan")
    p_plan.add_argument("--adapter", required=True)

    p_apply = sub.add_parser("apply")
    p_apply.add_argument("--adapter", required=True)
    p_apply.add_argument("--actor", required=True)
    p_apply.add_argument("--receipt", required=True, type=Path)
    p_apply.add_argument("--apply", action="store_true")

    p_verify = sub.add_parser("verify")
    p_verify.add_argument("--adapter", required=True)
    p_verify.add_argument("--receipt", required=True, type=Path)

    args = parser.parse_args()
    policy = load(args.policy)
    if policy.get("schema") != POLICY_SCHEMA:
        raise SystemExit(f"POLICY_SCHEMA_INVALID={policy.get('schema')}")
    item = config_for(policy, args.adapter)
    paths = resolve_paths(policy, item, args.root)

    if args.command == "plan":
        print(json.dumps(plan(args.adapter, policy, item, paths), indent=2, ensure_ascii=False))
        return 0

    if args.command == "apply":
        if not args.apply:
            print("EXPLICIT_APPLY_FLAG_REQUIRED")
            return 2
        receipt = install(args.adapter, args.actor, policy, item, paths)
        atomic_json(args.receipt, receipt)
        print(f"ADAPTER_PROVISIONED={args.adapter}")
        print(f"EXECUTABLE={receipt['executable_path']}")
        print(f"DIGEST={receipt['executable_digest']}")
        print(f"RECEIPT={args.receipt}")
        print(f"IDEMPOTENT={'YES' if receipt.get('idempotent') else 'NO'}")
        return 0

    receipt = load(args.receipt)
    if receipt.get("adapter") != args.adapter:
        print("PROVISIONING_VERIFY=FAIL")
        print("BLOCKER=RECEIPT_ADAPTER_MISMATCH")
        return 2
    blockers = verify_receipt(receipt, policy, item)
    print(f"PROVISIONING_VERIFY={'PASS' if not blockers else 'FAIL'}")
    for blocker in blockers:
        print(f"BLOCKER={blocker}")
    return 0 if not blockers else 2


if __name__ == "__main__":
    raise SystemExit(main())
