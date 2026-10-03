from __future__ import annotations

import fcntl
import json
import os
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


class LeaseBusy(RuntimeError):
    pass


@contextmanager
def command_lease(runtime_root: Path, profile_id: str) -> Iterator[dict[str, object]]:
    root = runtime_root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    lock_path = root / "command.lock"
    state_path = root / "command-lease.json"
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise LeaseBusy("REMOTE_OPERATOR_COMMAND_LEASE_BUSY") from exc
        lease = {
            "schema": "chacha.dev/chacha-remote-operator-command-lease/v1",
            "lease_id": "cro-" + uuid.uuid4().hex,
            "profile_id": profile_id,
            "pid": os.getpid(),
            "acquired_epoch": time.time(),
            "single_writer": True,
        }
        tmp = state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(lease, sort_keys=True) + "\n", encoding="utf-8")
        os.chmod(tmp, 0o600)
        os.replace(tmp, state_path)
        yield lease
    finally:
        try:
            state_path.unlink(missing_ok=True)
        finally:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)
