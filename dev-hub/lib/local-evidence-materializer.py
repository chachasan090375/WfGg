#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from pathlib import Path
from typing import Any

DEFAULT_ROOT = Path("/opt/chacha-dev/runtime/evidence")
SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def _safe(value: str, fallback: str) -> str:
    cleaned = SAFE.sub("_", value).strip("._")
    return cleaned or fallback


def _canonical_bytes(payload: Any) -> bytes:
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def materialize(
    *,
    project: str,
    task_id: str,
    producer: str,
    kind: str,
    payload: Any,
    evidence_root: Path | None = None,
) -> dict[str, Any]:
    root = (evidence_root or Path(os.environ.get("CHACHA_DEV_EVIDENCE_ROOT", str(DEFAULT_ROOT)))).resolve()
    out_dir = root / _safe(project, "unknown-project") / _safe(task_id, "unknown-task") / _safe(producer, "unknown-producer")
    out_dir.mkdir(parents=True, exist_ok=True)

    body = _canonical_bytes(payload)
    digest = "sha256:" + hashlib.sha256(body).hexdigest()
    name = _safe(kind, "evidence") + "-" + digest.split(":", 1)[1][:16] + ".json"
    target = out_dir / name

    if not target.exists():
        tmp = target.with_name(target.name + f".tmp-{os.getpid()}-{uuid.uuid4().hex[:8]}")
        with tmp.open("wb") as fh:
            fh.write(body + b"\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp, 0o640)
        os.replace(tmp, target)

    return {"path": str(target), "digest": digest}
