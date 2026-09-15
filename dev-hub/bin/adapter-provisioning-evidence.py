#!/usr/bin/env python3
"""Bind a concrete provisioning receipt into adapter promotion evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

RECEIPT_SCHEMA = "chacha.dev/adapter-provisioning-receipt/v1"
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


def file_digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def canonical_digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def save(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Add concrete runtime provisioning proof to promotion evidence")
    parser.add_argument("--adapter", required=True)
    parser.add_argument("--base-evidence", required=True, type=Path)
    parser.add_argument("--receipt", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    base = load(args.base_evidence)
    receipt = load(args.receipt)
    if base.get("schema") != EVIDENCE_SCHEMA:
        raise SystemExit(f"EVIDENCE_SCHEMA_INVALID={base.get('schema')}")
    if receipt.get("schema") != RECEIPT_SCHEMA:
        raise SystemExit(f"RECEIPT_SCHEMA_INVALID={receipt.get('schema')}")
    if base.get("adapter") != args.adapter or receipt.get("adapter") != args.adapter:
        raise SystemExit("ADAPTER_IDENTITY_MISMATCH")

    executable = Path(str(receipt.get("executable_path") or ""))
    source_digest = receipt.get("source_digest")
    installed_digest = receipt.get("installed_digest")
    executable_digest = receipt.get("executable_digest")
    probe = receipt.get("probe") if isinstance(receipt.get("probe"), dict) else {}
    blockers: list[str] = []
    if receipt.get("applied") is not True:
        blockers.append("PROVISIONING_NOT_APPLIED")
    if not isinstance(executable_digest, str) or not executable_digest.startswith("sha256:"):
        blockers.append("EXECUTABLE_DIGEST_MISSING")
    if source_digest != installed_digest or installed_digest != executable_digest:
        blockers.append("PROVISIONING_DIGEST_CHAIN_MISMATCH")
    if not executable.is_absolute():
        blockers.append("EXECUTABLE_PATH_NOT_ABSOLUTE")
    elif not executable.is_file():
        blockers.append("EXECUTABLE_MISSING")
    elif file_digest(executable) != executable_digest:
        blockers.append("EXECUTABLE_DIGEST_DRIFT")
    if probe.get("status") != "PASS":
        blockers.append("PROVISIONING_PROBE_NOT_PASS")

    out = json.loads(json.dumps(base))
    out["observed_at"] = now_iso()
    evidence = out.setdefault("evidence", {})
    evidence["provisioning-pass"] = {
        "status": "PASS" if not blockers else "FAIL",
        "source": f"adapter-provisioning-receipt:{args.receipt}",
        "observed_at": now_iso(),
        "details": {
            "adapter": args.adapter,
            "version": receipt.get("version"),
            "executable_path": str(executable),
            "source_digest": source_digest,
            "installed_digest": installed_digest,
            "executable_digest": executable_digest,
            "receipt_digest": canonical_digest(receipt),
            "probe_status": probe.get("status"),
            "idempotent": bool(receipt.get("idempotent")),
            "blockers": blockers,
        },
    }
    notes = out.setdefault("notes", [])
    notes.append("Provisioning evidence cryptographically binds source, installed bytes, current executable, and runtime probe.")
    save(args.output, out)
    print(f"PROVISIONING_EVIDENCE={args.output}")
    print(f"PROVISIONING_EVIDENCE_STATUS={'PASS' if not blockers else 'FAIL'}")
    for blocker in blockers:
        print(f"BLOCKER={blocker}")
    return 0 if not blockers else 2


if __name__ == "__main__":
    raise SystemExit(main())
