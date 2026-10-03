from __future__ import annotations

import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


V01_AUDIT_SCHEMA = "chacha.dev/chacha-remote-operator-audit/v1"
V02_AUDIT_SCHEMA = "chacha.dev/chacha-remote-operator-audit/v2"


def append_audit(
    path: Path,
    tool: str,
    status: str,
    details: dict[str, Any] | None = None,
    *,
    schema: str = V01_AUDIT_SCHEMA,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    now_ns = time.time_ns()
    record = {
        "schema": schema,
        "event_id": "cro-audit-" + uuid.uuid4().hex,
        "timestamp_utc": datetime.fromtimestamp(now_ns / 1_000_000_000, tz=timezone.utc).isoformat(),
        "epoch": now_ns / 1_000_000_000,
        "epoch_ns": now_ns,
        "pid": os.getpid(),
        "tool": tool,
        "status": status,
        "details": details or {},
        "automatic_external_spend_eur": 0,
    }
    payload = (json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        written = os.write(fd, payload)
        if written != len(payload):
            raise OSError("AUDIT_APPEND_SHORT_WRITE")
        os.fsync(fd)
    finally:
        os.close(fd)
