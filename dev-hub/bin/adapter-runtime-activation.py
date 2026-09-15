#!/usr/bin/env python3
"""ChaCha DEV HUB Adapter Runtime Activation V1.

Coordinates the local/VPS CONTRACT_OK -> PILOT boundary without directly
mutating the canonical provider-adapter registry. It provisions the exact
adapter bytes, verifies the install, binds the provisioning receipt into
promotion evidence, and asks the promotion engine for an eligibility plan.

The tool is deliberately fail-closed:
- explicit --apply is required for host mutation;
- a per-adapter activation lock prevents concurrent writers;
- the pre-existing `current` symlink is restored if provisioning/verification
  or promotion eligibility fails;
- the canonical adapter registry is never modified by this orchestrator;
- successful completion means READY_FOR_PROMOTION, not PILOT.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / "dev-hub/config/adapter-provisioning.v1.json"
REGISTRY_PATH = REPO_ROOT / "dev-hub/config/provider-adapters.v1.json"
CONTRACT_PATH = REPO_ROOT / "dev-hub/config/adapter-contract.v1.json"
PROMOTION_POLICY_PATH = REPO_ROOT / "dev-hub/config/adapter-promotion.v1.json"
ACTIVATION_SCHEMA = "chacha.dev/adapter-runtime-activation/v1"
EVIDENCE_SCHEMA = "chacha.dev/adapter-promotion-evidence/v1"


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


def canonical_digest(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def file_digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def run(argv: list[str], timeout: int = 60) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        cwd=str(REPO_ROOT),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout,
        check=False,
        shell=False,
        env=os.environ.copy(),
    )


def execution_kinds(registry: dict[str, Any], adapter: str) -> set[str]:
    out: set[str] = set()
    for item in (registry.get("providers") or {}).values():
        if isinstance(item, dict) and item.get("adapter") == adapter:
            value = item.get("execution")
            if isinstance(value, str) and value:
                out.add(value)
    return out


def provisioning_item(policy: dict[str, Any], adapter: str) -> dict[str, Any]:
    item = (policy.get("adapters") or {}).get(adapter)
    if not isinstance(item, dict):
        raise SystemExit(f"ADAPTER_NOT_PROVISIONABLE={adapter}")
    return item


def runtime_paths(policy: dict[str, Any], item: dict[str, Any], root_override: str | None) -> dict[str, Path]:
    root = Path(root_override or str(policy.get("target_root") or ""))
    if not root.is_absolute():
        raise SystemExit("TARGET_ROOT_MUST_BE_ABSOLUTE")
    if root_override and not bool(policy.get("sandbox_root_override_allowed", False)):
        raise SystemExit("TARGET_ROOT_OVERRIDE_FORBIDDEN")
    namespace = str(item.get("namespace") or "").strip("/.")
    version = str(item.get("version") or "").strip("/.")
    name = str(item.get("executable_name") or "").strip("/.")
    link_name = str(item.get("current_link_name") or "current").strip("/.")
    if not all((namespace, version, name, link_name)):
        raise SystemExit("PROVISIONING_PATH_COMPONENT_INVALID")
    namespace_root = root / namespace
    current = namespace_root / link_name
    return {
        "root": root,
        "namespace_root": namespace_root,
        "current_link": current,
        "executable": current / name,
        "version_dir": namespace_root / version,
    }


def evidence_ready(base: dict[str, Any], adapter: str) -> list[str]:
    blockers: list[str] = []
    if base.get("schema") != EVIDENCE_SCHEMA:
        blockers.append("BASE_EVIDENCE_SCHEMA_INVALID")
    if base.get("adapter") != adapter:
        blockers.append("BASE_EVIDENCE_ADAPTER_MISMATCH")
    items = base.get("evidence") if isinstance(base.get("evidence"), dict) else {}
    for key in ("runtime-contract-pass", "sandbox-only"):
        item = items.get(key)
        if not isinstance(item, dict):
            blockers.append(f"BASE_EVIDENCE_MISSING:{key}")
        elif item.get("status") != "PASS":
            blockers.append(f"BASE_EVIDENCE_NOT_PASS:{key}")
    return blockers


def capture_link(link: Path) -> dict[str, Any]:
    if link.is_symlink():
        return {"kind": "symlink", "target": os.readlink(link)}
    if link.exists():
        raise SystemExit("CURRENT_LINK_PATH_IS_NOT_SYMLINK")
    return {"kind": "absent", "target": None}


def restore_link(link: Path, previous: dict[str, Any]) -> None:
    link.parent.mkdir(parents=True, exist_ok=True)
    if previous.get("kind") == "absent":
        if link.is_symlink():
            link.unlink()
        elif link.exists():
            raise RuntimeError("ROLLBACK_LINK_REPLACED_BY_NON_SYMLINK")
        return
    target = previous.get("target")
    if not isinstance(target, str) or not target:
        raise RuntimeError("ROLLBACK_TARGET_INVALID")
    tmp = link.parent / f".{link.name}.rollback-{os.getpid()}"
    if tmp.exists() or tmp.is_symlink():
        tmp.unlink()
    os.symlink(target, tmp)
    os.replace(tmp, link)


def acquire_lock(root: Path, adapter: str) -> Path:
    lock_dir = root / ".activation-locks"
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock = lock_dir / f"{adapter}.lock"
    try:
        fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise SystemExit(f"ACTIVATION_LOCK_HELD={lock}")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(json.dumps({"pid": os.getpid(), "observed_at": now_iso()}) + "\n")
        fh.flush()
        os.fsync(fh.fileno())
    return lock


def release_lock(lock: Path) -> None:
    try:
        lock.unlink()
    except FileNotFoundError:
        pass


def truncate(value: str, limit: int = 4096) -> str:
    if len(value) <= limit:
        return value
    return value[:limit] + "...[truncated]"


def plan(adapter: str, base: dict[str, Any], root_override: str | None) -> dict[str, Any]:
    policy = load(POLICY_PATH)
    registry = load(REGISTRY_PATH)
    item = provisioning_item(policy, adapter)
    paths = runtime_paths(policy, item, root_override)
    entry = (registry.get("adapters") or {}).get(adapter)
    blockers = evidence_ready(base, adapter)
    if not isinstance(entry, dict):
        blockers.append("ADAPTER_NOT_REGISTERED")
        current_status = "UNKNOWN"
    else:
        current_status = str(entry.get("status") or "UNKNOWN")
        if current_status != "CONTRACT_OK":
            blockers.append(f"ADAPTER_STATUS_NOT_CONTRACT_OK:{current_status}")
    kinds = execution_kinds(registry, adapter)
    if "vps" not in kinds:
        blockers.append("ADAPTER_NOT_VPS_RUNTIME")
    return {
        "schema": ACTIVATION_SCHEMA,
        "adapter": adapter,
        "mode": "PLAN",
        "status": "READY" if not blockers else "BLOCKED",
        "current_status": current_status,
        "target_status": "PILOT",
        "execution_kinds": sorted(kinds),
        "target_root": str(paths["root"]),
        "current_link": str(paths["current_link"]),
        "executable_path": str(paths["executable"]),
        "version_dir": str(paths["version_dir"]),
        "blockers": sorted(set(blockers)),
        "observed_at": now_iso(),
    }


def activate(adapter: str, actor: str, base_evidence_path: Path, work_dir: Path,
             root_override: str | None) -> tuple[dict[str, Any], int]:
    base = load(base_evidence_path)
    initial = plan(adapter, base, root_override)
    if initial["blockers"]:
        initial["mode"] = "APPLY"
        initial["status"] = "BLOCKED"
        initial["actor"] = actor
        return initial, 2

    policy = load(POLICY_PATH)
    item = provisioning_item(policy, adapter)
    paths = runtime_paths(policy, item, root_override)
    work_dir.mkdir(parents=True, exist_ok=True)
    provision_receipt = work_dir / "provisioning-receipt.json"
    promotion_evidence = work_dir / "promotion-evidence.json"
    promotion_plan_file = work_dir / "promotion-plan.json"
    activation_receipt = work_dir / "activation-receipt.json"

    previous = capture_link(paths["current_link"])
    lock = acquire_lock(paths["root"], adapter)
    rollback_performed = False
    stage = "LOCKED"
    process_records: list[dict[str, Any]] = []
    try:
        provision_cmd = [
            "python3", "dev-hub/bin/adapter-provision.py",
        ]
        if root_override:
            provision_cmd += ["--root", root_override]
        provision_cmd += [
            "apply", "--adapter", adapter, "--actor", actor,
            "--receipt", str(provision_receipt), "--apply",
        ]
        proc = run(provision_cmd)
        process_records.append({
            "stage": "provision", "exit_code": proc.returncode,
            "stdout": truncate(proc.stdout), "stderr": truncate(proc.stderr),
        })
        if proc.returncode != 0:
            stage = "PROVISION_FAILED"
            restore_link(paths["current_link"], previous)
            rollback_performed = True
            raise RuntimeError("PROVISIONING_FAILED")
        stage = "PROVISIONED"

        verify_cmd = ["python3", "dev-hub/bin/adapter-provision.py"]
        if root_override:
            verify_cmd += ["--root", root_override]
        verify_cmd += [
            "verify", "--adapter", adapter, "--receipt", str(provision_receipt),
        ]
        proc = run(verify_cmd)
        process_records.append({
            "stage": "verify", "exit_code": proc.returncode,
            "stdout": truncate(proc.stdout), "stderr": truncate(proc.stderr),
        })
        if proc.returncode != 0:
            stage = "VERIFY_FAILED"
            restore_link(paths["current_link"], previous)
            rollback_performed = True
            raise RuntimeError("PROVISIONING_VERIFY_FAILED")
        stage = "VERIFIED"

        evidence_cmd = [
            "python3", "dev-hub/bin/adapter-provisioning-evidence.py",
            "--adapter", adapter,
            "--base-evidence", str(base_evidence_path),
            "--receipt", str(provision_receipt),
            "--output", str(promotion_evidence),
        ]
        proc = run(evidence_cmd)
        process_records.append({
            "stage": "evidence", "exit_code": proc.returncode,
            "stdout": truncate(proc.stdout), "stderr": truncate(proc.stderr),
        })
        if proc.returncode != 0:
            stage = "EVIDENCE_FAILED"
            restore_link(paths["current_link"], previous)
            rollback_performed = True
            raise RuntimeError("PROVISIONING_EVIDENCE_FAILED")
        stage = "EVIDENCE_BOUND"

        promotion_cmd = [
            "python3", "dev-hub/bin/adapter-promotion.py",
            "--evidence", str(promotion_evidence), "--json",
            "plan", "--adapter", adapter, "--target", "PILOT",
            "--executable", str(paths["executable"]),
        ]
        proc = run(promotion_cmd)
        process_records.append({
            "stage": "promotion-plan", "exit_code": proc.returncode,
            "stdout": truncate(proc.stdout), "stderr": truncate(proc.stderr),
        })
        try:
            promotion_plan = json.loads(proc.stdout)
        except json.JSONDecodeError:
            promotion_plan = {"eligible": False, "blockers": ["PROMOTION_PLAN_NOT_JSON"]}
        atomic_json(promotion_plan_file, promotion_plan)
        if proc.returncode != 0 or promotion_plan.get("eligible") is not True:
            stage = "PROMOTION_BLOCKED"
            restore_link(paths["current_link"], previous)
            rollback_performed = True
            blockers = promotion_plan.get("blockers") if isinstance(promotion_plan.get("blockers"), list) else []
            raise RuntimeError("PROMOTION_NOT_ELIGIBLE:" + ",".join(str(x) for x in blockers))
        stage = "READY_FOR_PROMOTION"

        provision = load(provision_receipt)
        evidence = load(promotion_evidence)
        receipt = {
            "schema": ACTIVATION_SCHEMA,
            "adapter": adapter,
            "mode": "APPLY",
            "status": "READY_FOR_PROMOTION",
            "actor": actor,
            "current_status": initial["current_status"],
            "target_status": "PILOT",
            "registry_mutated": False,
            "target_root": str(paths["root"]),
            "executable_path": str(paths["executable"]),
            "executable_digest": provision.get("executable_digest"),
            "provisioning_receipt": str(provision_receipt),
            "provisioning_receipt_digest": canonical_digest(provision),
            "promotion_evidence": str(promotion_evidence),
            "promotion_evidence_digest": canonical_digest(evidence),
            "promotion_plan": str(promotion_plan_file),
            "promotion_plan_digest": canonical_digest(promotion_plan),
            "rollback_performed": False,
            "previous_link": previous,
            "processes": process_records,
            "blockers": [],
            "observed_at": now_iso(),
        }
        if paths["executable"].is_file():
            receipt["observed_executable_digest"] = file_digest(paths["executable"])
        atomic_json(activation_receipt, receipt)
        return receipt, 0
    except Exception as exc:
        receipt = {
            "schema": ACTIVATION_SCHEMA,
            "adapter": adapter,
            "mode": "APPLY",
            "status": "FAILED",
            "actor": actor,
            "current_status": initial["current_status"],
            "target_status": "PILOT",
            "registry_mutated": False,
            "target_root": str(paths["root"]),
            "executable_path": str(paths["executable"]),
            "failed_stage": stage,
            "rollback_performed": rollback_performed,
            "previous_link": previous,
            "processes": process_records,
            "blockers": [str(exc)],
            "observed_at": now_iso(),
        }
        atomic_json(activation_receipt, receipt)
        return receipt, 2
    finally:
        release_lock(lock)


def main() -> int:
    parser = argparse.ArgumentParser(description="Provision and stage a VPS adapter for PILOT promotion")
    parser.add_argument("--adapter", required=True)
    parser.add_argument("--base-evidence", required=True, type=Path)
    parser.add_argument("--root", help="Sandbox-only target-root override")
    parser.add_argument("--json", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("plan")
    apply_cmd = sub.add_parser("apply")
    apply_cmd.add_argument("--actor", required=True)
    apply_cmd.add_argument("--work-dir", required=True, type=Path)
    apply_cmd.add_argument("--apply", action="store_true")

    args = parser.parse_args()
    base = load(args.base_evidence)

    if args.command == "plan":
        result = plan(args.adapter, base, args.root)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0 if not result["blockers"] else 2

    if not args.apply:
        result = plan(args.adapter, base, args.root)
        result.update({
            "mode": "APPLY",
            "status": "BLOCKED",
            "actor": args.actor,
            "blockers": sorted(set((result.get("blockers") or []) + ["EXPLICIT_APPLY_FLAG_REQUIRED"])),
        })
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 2

    result, rc = activate(args.adapter, args.actor, args.base_evidence, args.work_dir, args.root)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
