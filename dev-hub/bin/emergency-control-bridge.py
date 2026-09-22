#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

COMMAND_SCHEMA = "chacha.dev/emergency-stop-command/v1"
STATE_SCHEMA = "chacha.dev/emergency-control-bridge-state/v1"
DEFAULT_COMMAND_URL = (
    "https://raw.githubusercontent.com/chachasan090375/WfGg/"
    "chacha-emergency-control/dev-hub/control/emergency-stop-command.json"
)
DEFAULT_STATE = Path("/opt/chacha-dev/runtime/control/emergency-control-bridge.json")
DEFAULT_EMERGENCY_STATE = Path("/opt/chacha-dev/runtime/control/emergency-stop.json")
DEFAULT_CONTROLLER = Path("/opt/chacha-dev/emergency-bridge/current/emergency-stop-controller.py")
MAX_COMMAND_BYTES = 16384
REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{3,128}$")


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def atomic_write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp-{os.getpid()}")
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def read_state(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(value, dict) and value.get("schema") == STATE_SCHEMA:
            return value
    except Exception:
        pass
    return {
        "schema": STATE_SCHEMA,
        "created_at": now_iso(),
        "last_seen_digest": None,
        "last_request_id": None,
        "last_action": None,
        "applied_request_ids": [],
    }


def fetch_command(command_url: str, command_file: Path | None) -> bytes:
    if command_file is not None:
        raw = command_file.read_bytes()
    else:
        sep = "&" if "?" in command_url else "?"
        url = f"{command_url}{sep}chacha_ts={time.time_ns()}"
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "ChaCha-DEV-Emergency-Control-Bridge/1.0",
                "Cache-Control": "no-cache",
                "Pragma": "no-cache",
            },
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=12) as response:
            raw = response.read(MAX_COMMAND_BYTES + 1)
    if len(raw) > MAX_COMMAND_BYTES:
        raise ValueError("COMMAND_TOO_LARGE")
    return raw


def validate_command(raw: bytes) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise ValueError(f"COMMAND_JSON_INVALID:{type(exc).__name__}") from exc
    if not isinstance(value, dict):
        raise ValueError("COMMAND_ROOT_NOT_OBJECT")
    if value.get("schema") != COMMAND_SCHEMA:
        raise ValueError("COMMAND_SCHEMA_INVALID")
    action = str(value.get("action") or "").upper()
    if action not in {"NOOP", "STOP"}:
        raise ValueError("REMOTE_ACTION_NOT_ALLOWED")
    request_id = str(value.get("request_id") or "")
    if not REQUEST_ID_RE.fullmatch(request_id):
        raise ValueError("REQUEST_ID_INVALID")
    reason = str(value.get("reason") or "").strip()
    if action == "STOP" and not reason:
        raise ValueError("STOP_REASON_REQUIRED")
    value["action"] = action
    value["request_id"] = request_id
    value["reason"] = reason[:240]
    return value


def invoke_stop(
    controller: Path,
    emergency_state: Path,
    command: dict[str, Any],
) -> dict[str, Any]:
    request_id = command["request_id"]
    reason = command.get("reason") or "remote-emergency-stop"
    proc = subprocess.run(
        [
            "/usr/bin/python3",
            str(controller),
            "--state",
            str(emergency_state),
            "activate",
            "--reason",
            f"remote:{request_id}:{reason}"[:320],
            "--actor",
            "chatgpt-emergency-control-bridge",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        shell=False,
        check=False,
        timeout=45,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            "EMERGENCY_CONTROLLER_FAILED:"
            + (proc.stderr.strip() or proc.stdout.strip())[-500:]
        )
    try:
        result = json.loads(proc.stdout)
    except Exception as exc:
        raise RuntimeError("EMERGENCY_CONTROLLER_RESPONSE_INVALID") from exc
    if result.get("active") is not True:
        raise RuntimeError("EMERGENCY_CONTROLLER_DID_NOT_LATCH")
    return result


def baseline(
    state_path: Path,
    command_url: str,
    command_file: Path | None,
) -> dict[str, Any]:
    raw = fetch_command(command_url, command_file)
    command = validate_command(raw)
    if command["action"] != "NOOP":
        raise RuntimeError("BASELINE_REQUIRES_NEUTRAL_COMMAND")
    state = read_state(state_path)
    state.update(
        {
            "baseline_at": now_iso(),
            "last_seen_digest": digest(raw),
            "last_request_id": command["request_id"],
            "last_action": command["action"],
        }
    )
    atomic_write(state_path, state)
    return state


def process_once(
    state_path: Path,
    command_url: str,
    command_file: Path | None,
    controller: Path,
    emergency_state: Path,
) -> str:
    raw = fetch_command(command_url, command_file)
    command = validate_command(raw)
    d = digest(raw)
    state = read_state(state_path)

    if state.get("last_seen_digest") == d:
        return "UNCHANGED"

    applied = list(state.get("applied_request_ids") or [])
    request_id = command["request_id"]

    if request_id in applied:
        state.update(
            {
                "last_seen_digest": d,
                "last_request_id": request_id,
                "last_action": "REPLAY_IGNORED",
                "last_seen_at": now_iso(),
            }
        )
        atomic_write(state_path, state)
        return "REPLAY_IGNORED"

    if command["action"] == "NOOP":
        state.update(
            {
                "last_seen_digest": d,
                "last_request_id": request_id,
                "last_action": "NOOP",
                "last_seen_at": now_iso(),
            }
        )
        atomic_write(state_path, state)
        return "NOOP"

    result = invoke_stop(controller, emergency_state, command)
    applied.append(request_id)
    state.update(
        {
            "last_seen_digest": d,
            "last_request_id": request_id,
            "last_action": "STOP",
            "last_seen_at": now_iso(),
            "last_activation_at": result.get("activated_at") or now_iso(),
            "applied_request_ids": applied[-100:],
        }
    )
    atomic_write(state_path, state)
    return "STOP_APPLIED"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--command-url", default=DEFAULT_COMMAND_URL)
    ap.add_argument("--command-file", type=Path)
    ap.add_argument("--state", type=Path, default=DEFAULT_STATE)
    ap.add_argument("--emergency-state", type=Path, default=DEFAULT_EMERGENCY_STATE)
    ap.add_argument("--controller", type=Path, default=DEFAULT_CONTROLLER)
    ap.add_argument("--poll-seconds", type=float, default=10.0)
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--baseline", action="store_true")
    mode.add_argument("--once", action="store_true")
    args = ap.parse_args()

    if args.poll_seconds < 2:
        raise SystemExit("POLL_INTERVAL_TOO_LOW")

    if args.baseline:
        baseline(args.state, args.command_url, args.command_file)
        print("CHACHA_DEV_EMERGENCY_BRIDGE_BASELINE=PASS")
        return 0

    if args.once:
        outcome = process_once(
            args.state,
            args.command_url,
            args.command_file,
            args.controller,
            args.emergency_state,
        )
        print(f"CHACHA_DEV_EMERGENCY_BRIDGE_ONCE={outcome}")
        return 0

    print(
        f"CHACHA_DEV_EMERGENCY_BRIDGE=READY poll_seconds={args.poll_seconds:g}",
        flush=True,
    )
    while True:
        try:
            outcome = process_once(
                args.state,
                args.command_url,
                args.command_file,
                args.controller,
                args.emergency_state,
            )
            if outcome != "UNCHANGED":
                print(
                    f"CHACHA_DEV_EMERGENCY_BRIDGE_EVENT={outcome} at={now_iso()}",
                    flush=True,
                )
        except (OSError, ValueError, RuntimeError, urllib.error.URLError) as exc:
            print(
                f"CHACHA_DEV_EMERGENCY_BRIDGE_ERROR={type(exc).__name__}:{exc}",
                file=sys.stderr,
                flush=True,
            )
        time.sleep(args.poll_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
