#!/data/data/com.termux/files/usr/bin/python3
"""WfGg passive Last War teleport detector v6.3.7.

Reads the already-running Last War client's Android logcat through the local ADB
bridge. It never sends game requests, never stores a game token and never calls
Last War endpoints. A teleport is emitted only after a transition signal and a
stable late-window server candidate.
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

VERSION = "6.3.7"
PKG = "com.fun.lastwar.gp"
HOME = Path.home()
ROOT = HOME / ".wfgg" / "teleport-detector"
STATE = ROOT / "state.json"
EVENTS = ROOT / "events.jsonl"
HOOK = ROOT / "on-teleport.sh"
PIDFILE = ROOT / "detector.pid"

TRANSITION_RE = re.compile(
    r"disconnect|reconnect|\bEnterGame\b|lastwar-game-tcp[^\n]{0,80}\bconnect\b|gateway[^\n]{0,80}\bconnect\b",
    re.I,
)
EXPLICIT_PATTERNS = [
    (re.compile(r"\b(?:serverId|srcServer|currentServer|curServer|targetServer|dstServer|worldId)\s*[:=]\s*[\"']?(\d{1,5})", re.I), 6, "explicit"),
    (re.compile(r"\bserver\s*[:=]\s*[\"']?(\d{1,5})", re.I), 5, "server"),
    (re.compile(r"\bValue\s*=\s*s(\d{1,5})\b", re.I), 5, "zendesk-value"),
]
S_FIELD_RE = re.compile(r"(?<![A-Za-z0-9_])s\s*[:=]\s*(\d{1,5})(?!\d)", re.I)

RUNNING = True


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def log(stage: str, **fields) -> None:
    payload = " ".join(f"{k}={v}" for k, v in fields.items())
    print(f"WFGG_TELEPORT_V637 stage={stage}" + (f" {payload}" if payload else ""), flush=True)


def atomic_json(path: Path, obj: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def load_state(initial_server: int | None) -> dict:
    ROOT.mkdir(parents=True, exist_ok=True)
    if STATE.exists():
        try:
            state = json.loads(STATE.read_text(encoding="utf-8"))
        except Exception:
            state = {}
    else:
        state = {}
    state.setdefault("version", VERSION)
    state.setdefault("currentServer", initial_server)
    state.setdefault("previousServer", None)
    state.setdefault("lastTeleportAt", None)
    state.setdefault("teleports", 0)
    if state.get("currentServer") is None and initial_server is not None:
        state["currentServer"] = initial_server
    atomic_json(STATE, state)
    return state


def adb_serial() -> str | None:
    try:
        out = subprocess.check_output(["adb", "devices"], text=True, stderr=subprocess.DEVNULL)
    except Exception:
        return None
    for line in out.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "device":
            return parts[0]
    return None


def app_uid(serial: str) -> str | None:
    try:
        out = subprocess.check_output(
            ["adb", "-s", serial, "shell", "pm", "list", "packages", "-U"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        return None
    rx = re.compile(rf"^package:{re.escape(PKG)}\s+uid:(\d+)\s*$")
    for line in out.splitlines():
        m = rx.match(line.strip())
        if m:
            return m.group(1)
    return None


def candidates(line: str):
    seen = set()
    for rx, weight, source in EXPLICIT_PATTERNS:
        for raw in rx.findall(line):
            sid = int(raw)
            if 1 <= sid <= 9999 and sid not in seen:
                seen.add(sid)
                yield sid, weight, source
    if "zendesk" in line.lower() or "senddatatonative" in line.lower():
        for raw in S_FIELD_RE.findall(line):
            sid = int(raw)
            if 1 <= sid <= 9999 and sid not in seen:
                seen.add(sid)
                yield sid, 4, "zendesk-s"


def choose_stable(samples, now: float, current_server: int | None):
    late = [s for s in samples if now - s[0] <= 8.0]
    if not late:
        return None
    scores = collections.Counter()
    hits = collections.Counter()
    explicit_hits = collections.Counter()
    for _ts, sid, weight, source in late:
        scores[sid] += weight
        hits[sid] += 1
        if source in {"explicit", "server", "zendesk-value"}:
            explicit_hits[sid] += 1
    best, best_score = scores.most_common(1)[0]
    total_score = sum(scores.values())
    dominance = best_score / total_score if total_score else 0.0
    # Require repeated evidence. A strong explicit field may confirm with two hits;
    # otherwise demand three hits and clear dominance in the late stabilization window.
    strong = explicit_hits[best] >= 2 or (hits[best] >= 3 and dominance >= 0.70)
    if not strong:
        return None
    return {
        "server": best,
        "score": best_score,
        "hits": hits[best],
        "dominance": round(dominance, 3),
        "current": current_server,
    }


def emit_teleport(state: dict, detected: dict) -> None:
    previous = state.get("currentServer")
    current = detected["server"]
    if previous == current:
        return
    event = {
        "version": VERSION,
        "event": "TELEPORT_DETECTED",
        "at": now_iso(),
        "previousServer": previous,
        "currentServer": current,
        "confidence": detected["dominance"],
        "score": detected["score"],
        "hits": detected["hits"],
        "source": "PASSIVE_ANDROID_LOGCAT",
    }
    state["previousServer"] = previous
    state["currentServer"] = current
    state["lastTeleportAt"] = event["at"]
    state["teleports"] = int(state.get("teleports") or 0) + 1
    atomic_json(STATE, state)
    with EVENTS.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False) + "\n")
    log(
        "TELEPORT_DETECTED",
        previousServer=previous,
        currentServer=current,
        confidence=event["confidence"],
        hits=event["hits"],
    )
    if HOOK.exists() and os.access(HOOK, os.X_OK):
        env = os.environ.copy()
        env.update(
            WFGG_PREVIOUS_SERVER="" if previous is None else str(previous),
            WFGG_CURRENT_SERVER=str(current),
            WFGG_TELEPORT_AT=event["at"],
        )
        try:
            subprocess.Popen([str(HOOK)], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as exc:
            log("HOOK_ERROR", error=type(exc).__name__)


def stop_handler(_sig, _frame):
    global RUNNING
    RUNNING = False


def run(initial_server: int | None) -> int:
    signal.signal(signal.SIGTERM, stop_handler)
    signal.signal(signal.SIGINT, stop_handler)
    ROOT.mkdir(parents=True, exist_ok=True)
    PIDFILE.write_text(str(os.getpid()) + "\n", encoding="utf-8")
    state = load_state(initial_server)
    log("START", version=VERSION, currentServer=state.get("currentServer"), activeGameCalls="NO")

    transition_started = None
    samples = []
    last_trigger = 0.0

    while RUNNING:
        serial = adb_serial()
        if not serial:
            log("WAIT_ADB")
            time.sleep(3)
            continue
        uid = app_uid(serial)
        if not uid:
            log("WAIT_APP_UID", serial=serial)
            time.sleep(3)
            continue

        cmd = ["adb", "-s", serial, "logcat", f"--uid={uid}", "-v", "epoch"]
        log("ATTACH", serial=serial, appUid=uid)
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        except Exception:
            time.sleep(3)
            continue

        assert proc.stdout is not None
        for raw in proc.stdout:
            if not RUNNING:
                break
            line = raw.rstrip("\n")
            parts = line.split()
            try:
                ts = float(parts[0])
            except Exception:
                ts = time.time()

            if TRANSITION_RE.search(line) and transition_started is None and ts - last_trigger > 8:
                transition_started = ts
                samples = []
                last_trigger = ts
                log("TRANSITION_START", currentServer=state.get("currentServer"))

            if transition_started is not None:
                for sid, weight, source in candidates(line):
                    samples.append((ts, sid, weight, source))

                age = ts - transition_started
                if age >= 16:
                    detected = choose_stable(samples, ts, state.get("currentServer"))
                    if detected:
                        if state.get("currentServer") is None:
                            state["currentServer"] = detected["server"]
                            atomic_json(STATE, state)
                            log("BASELINE_SET", currentServer=detected["server"])
                        elif detected["server"] != state.get("currentServer"):
                            emit_teleport(state, detected)
                        elif age >= 20:
                            log("TRANSITION_NO_CHANGE", currentServer=state.get("currentServer"))
                        if detected["server"] == state.get("currentServer") or age >= 20:
                            transition_started = None
                            samples = []
                    elif age >= 32:
                        log("TRANSITION_UNRESOLVED", currentServer=state.get("currentServer"), samples=len(samples))
                        transition_started = None
                        samples = []

        try:
            proc.terminate()
        except Exception:
            pass
        if RUNNING:
            log("ADB_STREAM_RESTART")
            time.sleep(2)

    try:
        PIDFILE.unlink(missing_ok=True)
    except Exception:
        pass
    log("STOP")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--initial-server", type=int, default=None)
    args = parser.parse_args()
    return run(args.initial_server)


if __name__ == "__main__":
    raise SystemExit(main())
