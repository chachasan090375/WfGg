from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any


def append_audit(path: Path, tool: str, status: str, details: dict[str, Any] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "schema": "chacha.dev/chacha-remote-operator-audit/v1",
        "epoch": time.time(),
        "tool": tool,
        "status": status,
        "details": details or {},
        "automatic_external_spend_eur": 0,
    }
    payload = (json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        os.write(fd, payload)
        os.fsync(fd)
    finally:
        os.close(fd)
