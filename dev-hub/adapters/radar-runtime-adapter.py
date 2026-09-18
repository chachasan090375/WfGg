#!/usr/bin/env python3
"""ChaCha DEV HUB WfGg Radar Runtime Adapter V1.

Narrow VPS runtime adapter for the WfGg Radar pilot lifecycle.

Supported actions:
- status            (read)
- pilot-open        (production-deploy)
- pilot-install     (production-deploy)
- pilot-probe       (read)
- pilot-close       (production-deploy)

The adapter accepts only structured dispatch envelopes, uses no shell
interpolation, never accepts arbitrary URLs or service names, requires a pinned
40-hex Git revision for downloaded pilot assets, and never returns secrets.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

INPUT_SCHEMA = "chacha.dev/dispatch-envelope/v1"
OUTPUT_SCHEMA = "chacha.dev/task-result/v1"
ADAPTER_ID = "radar-runtime-adapter"
PROVIDER_ID = "radar-vps-runtime"

RADAR_ROOT = Path(os.environ.get("CHACHA_RADAR_ROOT", "/opt/wfgg-radar"))
BIN_DIR = RADAR_ROOT / "bin"
CONNECTOR = BIN_DIR / "radar-connector"
NATIVE = BIN_DIR / "radar-native-template"
RADAR_SERVICE = "wfgg-radar-connector"
RADAR_SENTINEL_TIMER = "wfgg-radar-sentinel.timer"
RADAR_SENTINEL_SERVICE = "wfgg-radar-sentinel.service"
COLLECTOR_SENTINEL_TIMER = "wfgg-collector-sentinel.timer"
RAW_BASE = "https://raw.githubusercontent.com/chachasan090375/WfGg"
REV_RE = re.compile(r"^[0-9a-f]{40}$")
INSTALL_RE = re.compile(r"^radar-vps/install-v[0-9]+-pilot\.sh$")
PROBE_RE = re.compile(r"^radar-vps/probe-v[0-9]+-pilot-runtime\.sh$")
HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
ABSOLUTE_MAX_TIMEOUT = 180


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


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
            "status": "UNVERIFIED",
            "method": "none",
            "verifier": "none",
            "observed_at": now_iso(),
            "notes": "Radar runtime adapter results require independent verification.",
        },
        "outputs": outputs or [],
    }


def emit(payload: dict[str, Any], code: int = 0) -> int:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
    return code


def blocked(request: dict[str, Any], reason: str) -> int:
    return emit(result(request, "BLOCKED", reason, [{
        "kind": "report",
        "source": "radar-runtime-adapter-policy",
        "digest": sha256_bytes(reason.encode("utf-8")),
        "details": {"reason": reason},
    }]), 2)


def run(argv: list[str], timeout: int = 30,
        env: dict[str, str] | None = None) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        argv,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        shell=False,
        check=False,
        env=env or os.environ.copy(),
    )


def systemctl(*args: str, timeout: int = 20) -> subprocess.CompletedProcess[bytes]:
    return run(["/usr/bin/systemctl", *args], timeout=timeout)


def state(unit: str) -> str:
    p = systemctl("is-active", unit)
    return p.stdout.decode("utf-8", "replace").strip() or "unknown"


def enabled(unit: str) -> str:
    p = systemctl("is-enabled", unit)
    return p.stdout.decode("utf-8", "replace").strip() or "unknown"


def validate_request(request: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    if request.get("schema") != INPUT_SCHEMA:
        return None, "INPUT_SCHEMA_INVALID"
    task = request.get("task")
    if not isinstance(task, dict) or not task.get("id"):
        return None, "TASK_ID_MISSING"
    bindings = request.get("bindings")
    if not isinstance(bindings, list) or not any(
        isinstance(x, dict)
        and x.get("provider") == PROVIDER_ID
        and x.get("adapter") == ADAPTER_ID
        for x in bindings
    ):
        return None, "RADAR_RUNTIME_BINDING_MISSING"
    metadata = request.get("metadata")
    radar = metadata.get("radar_runtime") if isinstance(metadata, dict) else None
    if not isinstance(radar, dict):
        return None, "RADAR_RUNTIME_METADATA_MISSING"
    action = str(radar.get("action") or "")
    permission = str(task.get("permission") or "")
    expected_permission = {
        "status": "read",
        "pilot-open": "production-deploy",
        "pilot-install": "production-deploy",
        "pilot-probe": "read",
        "pilot-close": "production-deploy",
    }.get(action)
    if expected_permission is None:
        return None, "RADAR_RUNTIME_ACTION_NOT_ALLOWED"
    if permission != expected_permission:
        return None, f"RADAR_RUNTIME_PERMISSION_REQUIRED:{expected_permission}"
    return radar, None


def timeout_from(request: dict[str, Any]) -> int:
    policy = request.get("policy_context") if isinstance(request.get("policy_context"), dict) else {}
    try:
        value = int(policy.get("timeout_seconds") or 60)
    except Exception:
        value = 60
    return max(1, min(value, ABSOLUTE_MAX_TIMEOUT))


def approval_required(request: dict[str, Any]) -> str | None:
    policy = request.get("policy_context") if isinstance(request.get("policy_context"), dict) else {}
    if policy.get("human_approval_required") is not True:
        return "RADAR_PRODUCTION_APPROVAL_POLICY_MISSING"
    approval_id = str(policy.get("approval_id") or "").strip()
    if not approval_id:
        return "RADAR_PRODUCTION_APPROVAL_MISSING"
    return None


def status_snapshot() -> dict[str, Any]:
    out: dict[str, Any] = {
        "radar_service": state(RADAR_SERVICE),
        "radar_sentinel_timer": state(RADAR_SENTINEL_TIMER),
        "radar_sentinel_enabled": enabled(RADAR_SENTINEL_TIMER),
        "radar_sentinel_service": state(RADAR_SENTINEL_SERVICE),
        "collector_sentinel_timer": state(COLLECTOR_SENTINEL_TIMER),
    }
    out["connector_sha256"] = sha256_file(CONNECTOR) if CONNECTOR.is_file() else None
    out["native_sha256"] = sha256_file(NATIVE) if NATIVE.is_file() else None
    return out


def evidence_snapshot(kind: str, snap: dict[str, Any]) -> list[dict[str, Any]]:
    raw = json.dumps(snap, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return [{
        "kind": "metric",
        "source": f"vps://localhost/wfgg-radar/{kind}",
        "digest": sha256_bytes(raw),
        "details": snap,
    }]


def wait_inactive(unit: str, timeout: int) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if state(unit) != "active":
            return True
        time.sleep(1)
    return state(unit) != "active"


def download_asset(revision: str, path: str, destination: Path, timeout: int) -> None:
    url = f"{RAW_BASE}/{revision}/{path}"
    req = urllib.request.Request(url, headers={"User-Agent": "ChaCha-DEV-HUB-RadarRuntime/1"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        body = response.read(512 * 1024 + 1)
    if len(body) > 512 * 1024:
        raise ValueError("RADAR_ASSET_TOO_LARGE")
    destination.write_bytes(body)
    destination.chmod(0o700)


def validate_pilot_metadata(radar: dict[str, Any], need_probe: bool = False) -> tuple[str, str, str | None, str, str]:
    revision = str(radar.get("revision") or "").strip().lower()
    installer = str(radar.get("installer") or "").strip()
    probe = str(radar.get("probe") or "").strip() if need_probe else None
    connector_sha = str(radar.get("expected_connector_sha256") or "").strip().lower()
    native_sha = str(radar.get("expected_native_sha256") or "").strip().lower()
    if not REV_RE.fullmatch(revision):
        raise ValueError("RADAR_REVISION_INVALID")
    if not INSTALL_RE.fullmatch(installer):
        raise ValueError("RADAR_INSTALLER_PATH_INVALID")
    if need_probe and (probe is None or not PROBE_RE.fullmatch(probe)):
        raise ValueError("RADAR_PROBE_PATH_INVALID")
    if not HEX64_RE.fullmatch(connector_sha):
        raise ValueError("RADAR_EXPECTED_CONNECTOR_SHA_INVALID")
    if not HEX64_RE.fullmatch(native_sha):
        raise ValueError("RADAR_EXPECTED_NATIVE_SHA_INVALID")
    return revision, installer, probe, connector_sha, native_sha


def do_status(request: dict[str, Any]) -> int:
    snap = status_snapshot()
    return emit(result(request, "OK", "RADAR_RUNTIME_STATUS_OK", evidence_snapshot("status", snap), [{
        "type": "artifact", "id": "radar-runtime-status", "status": "UNVERIFIED",
        "reason": "Observed locally; independent verification required.",
    }]))


def do_open(request: dict[str, Any]) -> int:
    approval_error = approval_required(request)
    if approval_error:
        return blocked(request, approval_error)
    before = status_snapshot()
    p = systemctl("stop", RADAR_SENTINEL_TIMER)
    if p.returncode != 0:
        return emit(result(request, "FAILED", "RADAR_SENTINEL_STOP_FAILED"))
    if not wait_inactive(RADAR_SENTINEL_SERVICE, 30):
        systemctl("start", RADAR_SENTINEL_TIMER)
        return emit(result(request, "FAILED", "RADAR_SENTINEL_SERVICE_BUSY"))
    after = status_snapshot()
    if after["radar_sentinel_timer"] != "inactive" or after["radar_sentinel_enabled"] != "enabled":
        systemctl("start", RADAR_SENTINEL_TIMER)
        return emit(result(request, "FAILED", "RADAR_PILOT_WINDOW_OPEN_INVARIANT_FAILED"))
    if after["collector_sentinel_timer"] != "active":
        systemctl("start", RADAR_SENTINEL_TIMER)
        return emit(result(request, "FAILED", "COLLECTOR_SENTINEL_NOT_ACTIVE"))
    ev = evidence_snapshot("pilot-open-before", before) + evidence_snapshot("pilot-open-after", after)
    return emit(result(request, "OK", "RADAR_PILOT_WINDOW_OPEN", ev, [{
        "type": "gate", "id": "radar-pilot-window", "status": "UNVERIFIED",
        "reason": "Radar Sentinel paused; Collector Sentinel remains active.",
    }]))


def do_install(request: dict[str, Any], radar: dict[str, Any]) -> int:
    approval_error = approval_required(request)
    if approval_error:
        return blocked(request, approval_error)
    try:
        revision, installer, _probe, expected_connector, expected_native = validate_pilot_metadata(radar, False)
    except ValueError as exc:
        return blocked(request, str(exc))
    snap = status_snapshot()
    if snap["radar_sentinel_timer"] != "inactive":
        return blocked(request, "RADAR_PILOT_WINDOW_NOT_OPEN")
    if snap["collector_sentinel_timer"] != "active":
        return blocked(request, "COLLECTOR_SENTINEL_NOT_ACTIVE")
    timeout = timeout_from(request)
    with tempfile.TemporaryDirectory(prefix="chacha-radar-pilot-") as td:
        script = Path(td) / "installer.sh"
        try:
            download_asset(revision, installer, script, min(timeout, 60))
        except Exception as exc:
            return emit(result(request, "FAILED", f"RADAR_INSTALLER_DOWNLOAD_FAILED:{type(exc).__name__}"))
        env = os.environ.copy()
        env["WFGG_RADAR_V6191_REV"] = revision
        proc = run(["/usr/bin/bash", str(script)], timeout=timeout, env=env)
    if proc.returncode != 0:
        digest = sha256_bytes(proc.stderr[:65536] + proc.stdout[:65536])
        return emit(result(request, "FAILED", "RADAR_PILOT_INSTALL_FAILED", [{
            "kind": "command", "source": "local://radar-pilot-installer", "digest": digest,
            "details": {"returncode": proc.returncode},
        }]))
    after = status_snapshot()
    if after["connector_sha256"] != expected_connector or after["native_sha256"] != expected_native:
        return emit(result(request, "FAILED", "RADAR_PILOT_SHA_MISMATCH", evidence_snapshot("pilot-install-after", after)))
    if after["radar_service"] != "active":
        return emit(result(request, "FAILED", "RADAR_SERVICE_NOT_ACTIVE", evidence_snapshot("pilot-install-after", after)))
    return emit(result(request, "OK", "RADAR_PILOT_INSTALL_OK", evidence_snapshot("pilot-install-after", after), [{
        "type": "artifact", "id": revision, "status": "UNVERIFIED",
        "reason": "Pinned pilot runtime installed and SHA-matched.",
    }]))


def do_probe(request: dict[str, Any], radar: dict[str, Any]) -> int:
    try:
        revision, installer, probe, expected_connector, expected_native = validate_pilot_metadata(radar, True)
    except ValueError as exc:
        return blocked(request, str(exc))
    _ = installer
    snap = status_snapshot()
    if snap["connector_sha256"] != expected_connector or snap["native_sha256"] != expected_native:
        return emit(result(request, "FAILED", "RADAR_PILOT_NOT_LOADED", evidence_snapshot("pilot-probe-pre", snap)))
    timeout = timeout_from(request)
    with tempfile.TemporaryDirectory(prefix="chacha-radar-probe-") as td:
        script = Path(td) / "probe.sh"
        try:
            assert probe is not None
            download_asset(revision, probe, script, min(timeout, 60))
        except Exception as exc:
            return emit(result(request, "FAILED", f"RADAR_PROBE_DOWNLOAD_FAILED:{type(exc).__name__}"))
        proc = run(["/usr/bin/bash", str(script)], timeout=timeout)
    digest = sha256_bytes(proc.stdout[:65536] + proc.stderr[:65536])
    if proc.returncode != 0 or b"RUNTIME_PROBE=PASS" not in proc.stdout:
        return emit(result(request, "FAILED", "RADAR_PILOT_PROBE_FAILED", [{
            "kind": "command", "source": "local://radar-pilot-probe", "digest": digest,
            "details": {"returncode": proc.returncode},
        }]))
    return emit(result(request, "OK", "RADAR_PILOT_PROBE_OK", [{
        "kind": "command", "source": "local://radar-pilot-probe", "digest": digest,
        "details": {"returncode": proc.returncode, "pass_marker": True},
    }], [{
        "type": "gate", "id": "radar-pilot-runtime", "status": "UNVERIFIED",
        "reason": "Runtime probe passed; independent verification required.",
    }]))


def do_close(request: dict[str, Any]) -> int:
    approval_error = approval_required(request)
    if approval_error:
        return blocked(request, approval_error)
    systemctl("start", RADAR_SENTINEL_TIMER)
    systemctl("start", RADAR_SENTINEL_SERVICE)
    if not wait_inactive(RADAR_SENTINEL_SERVICE, 60):
        return emit(result(request, "FAILED", "RADAR_SENTINEL_RECONCILE_TIMEOUT"))
    after = status_snapshot()
    if after["radar_sentinel_timer"] != "active" or after["radar_sentinel_enabled"] != "enabled":
        return emit(result(request, "FAILED", "RADAR_SENTINEL_RESTORE_FAILED", evidence_snapshot("pilot-close", after)))
    if after["collector_sentinel_timer"] != "active":
        return emit(result(request, "FAILED", "COLLECTOR_SENTINEL_NOT_ACTIVE", evidence_snapshot("pilot-close", after)))
    return emit(result(request, "OK", "RADAR_PILOT_WINDOW_CLOSED", evidence_snapshot("pilot-close", after), [{
        "type": "gate", "id": "radar-sentinel-protection", "status": "UNVERIFIED",
        "reason": "Radar Sentinel timer active and reconciler completed.",
    }]))


def main() -> int:
    try:
        request = json.load(sys.stdin)
    except Exception as exc:
        minimal = {"project": "unknown", "task": {"id": "unknown"}}
        return emit(result(minimal, "BLOCKED", f"INPUT_JSON_INVALID:{type(exc).__name__}"), 2)
    if not isinstance(request, dict):
        minimal = {"project": "unknown", "task": {"id": "unknown"}}
        return emit(result(minimal, "BLOCKED", "INPUT_ROOT_NOT_OBJECT"), 2)

    radar, error = validate_request(request)
    if error:
        return blocked(request, error)
    assert radar is not None
    action = str(radar.get("action"))
    try:
        if action == "status":
            return do_status(request)
        if action == "pilot-open":
            return do_open(request)
        if action == "pilot-install":
            return do_install(request, radar)
        if action == "pilot-probe":
            return do_probe(request, radar)
        return do_close(request)
    except subprocess.TimeoutExpired:
        return emit(result(request, "FAILED", "RADAR_RUNTIME_COMMAND_TIMEOUT"))
    except (OSError, ValueError) as exc:
        return emit(result(request, "FAILED", f"RADAR_RUNTIME_ERROR:{type(exc).__name__}"))


if __name__ == "__main__":
    raise SystemExit(main())
