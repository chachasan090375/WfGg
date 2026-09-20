#!/usr/bin/env python3
"""ChaCha DEV HUB WfGg Radar Runtime Adapter V1.

Narrow VPS runtime adapter for the WfGg Radar pilot lifecycle.

Supported actions:
- status                     (read)
- cluster-quality-diagnostic (read)
- cluster-catalog-probe      (read)
- history-performance-diagnostic (read)
- census-frontier-diagnostic  (read)
- seed-scout-route-diagnostic (read)
- pilot-open                 (production-deploy)
- pilot-install     (production-deploy)
- pilot-probe       (read)
- pilot-close       (production-deploy)

The adapter accepts only structured dispatch envelopes, uses no shell
interpolation, never accepts arbitrary URLs or service names, requires a pinned
40-hex Git revision for downloaded pilot assets, and never returns secrets.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
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
COLLECTOR_DB_DEFAULT = Path("/opt/wfgg-collector/data/collector.db")
QUALITY_REQUIRED_COLUMNS = {"id", "status", "error", "query"}


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
        "cluster-quality-diagnostic": "read",
        "cluster-catalog-probe": "read",
        "history-performance-diagnostic": "read",
        "census-frontier-diagnostic": "read",
        "seed-scout-route-diagnostic": "read",
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


def collector_db_path() -> Path:
    raw = str(os.environ.get("WFGG_COLLECTOR_DB") or "").strip()
    return Path(raw) if raw else COLLECTOR_DB_DEFAULT


def cluster_quality_snapshot() -> dict[str, Any]:
    db_path = collector_db_path()
    snap: dict[str, Any] = {
        "db_path": str(db_path),
        "db_path_source": "environment" if str(os.environ.get("WFGG_COLLECTOR_DB") or "").strip() else "default",
        "db_exists": db_path.is_file(),
        "db_readable": os.access(db_path, os.R_OK) if db_path.exists() else False,
        "python3_path": shutil.which("python3"),
        "cycles_table_present": False,
        "cycles_columns": [],
        "required_columns": sorted(QUALITY_REQUIRED_COLUMNS),
        "missing_columns": sorted(QUALITY_REQUIRED_COLUMNS),
        "cycle_count": 0,
        "status_counts": {},
        "cycles_with_error": 0,
        "federated_cycles": 0,
        "quality_gate_ready": False,
        "failure_class": None,
    }
    if not snap["db_exists"]:
        snap["failure_class"] = "COLLECTOR_DB_NOT_FOUND"
        return snap
    if not snap["db_readable"]:
        snap["failure_class"] = "COLLECTOR_DB_NOT_READABLE"
        return snap
    if not snap["python3_path"]:
        snap["failure_class"] = "COLLECTOR_QUALITY_PYTHON3_MISSING"
        return snap

    try:
        uri = "file:" + str(db_path) + "?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
        try:
            tables = {str(r[0]) for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            snap["cycles_table_present"] = "cycles" in tables
            if "cycles" not in tables:
                snap["failure_class"] = "CYCLES_TABLE_MISSING"
                return snap
            columns = [str(r[1]) for r in conn.execute("PRAGMA table_info(cycles)")]
            snap["cycles_columns"] = sorted(columns)
            missing = sorted(QUALITY_REQUIRED_COLUMNS.difference(columns))
            snap["missing_columns"] = missing
            if missing:
                snap["failure_class"] = "CYCLES_REQUIRED_COLUMNS_MISSING"
                return snap

            snap["cycle_count"] = int(conn.execute("SELECT COUNT(*) FROM cycles").fetchone()[0])
            snap["status_counts"] = {
                str(status or ""): int(count)
                for status, count in conn.execute(
                    "SELECT COALESCE(status,''), COUNT(*) FROM cycles GROUP BY COALESCE(status,'') ORDER BY 1"
                )
            }
            snap["cycles_with_error"] = int(
                conn.execute("SELECT COUNT(*) FROM cycles WHERE TRIM(COALESCE(error,'')) <> ''").fetchone()[0]
            )
            snap["federated_cycles"] = int(
                conn.execute(
                    "SELECT COUNT(*) FROM cycles WHERE LOWER(TRIM(COALESCE(query,''))) LIKE '@federated:%'"
                ).fetchone()[0]
            )
        finally:
            conn.close()
    except sqlite3.Error as exc:
        snap["failure_class"] = "SQLITE_READ_FAILED"
        snap["sqlite_error_class"] = type(exc).__name__
        return snap

    snap["quality_gate_ready"] = True
    return snap


def do_cluster_quality_diagnostic(request: dict[str, Any]) -> int:
    snap = cluster_quality_snapshot()
    raw = json.dumps(snap, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return emit(result(request, "OK", "RADAR_CLUSTER_QUALITY_DIAGNOSTIC_OK", [{
        "kind": "diagnostic",
        "source": "vps://localhost/wfgg-collector/cycle-quality-v617",
        "digest": sha256_bytes(raw),
        "details": snap,
    }], [{
        "type": "artifact",
        "id": "radar-cluster-quality-diagnostic",
        "status": "UNVERIFIED",
        "reason": "Read-only Collector schema/quality-gate diagnostic; independent verification required.",
    }]))


def connector_shared_key() -> str:
    proc = systemctl("show", "-p", "MainPID", "--value", RADAR_SERVICE)
    if proc.returncode != 0:
        raise RuntimeError("RADAR_CONNECTOR_MAINPID_UNAVAILABLE")
    pid = proc.stdout.decode("utf-8", "replace").strip()
    if not pid.isdigit() or pid == "0":
        raise RuntimeError("RADAR_CONNECTOR_NOT_RUNNING")
    try:
        raw = Path(f"/proc/{pid}/environ").read_bytes()
    except OSError as exc:
        raise RuntimeError("RADAR_CONNECTOR_ENV_UNAVAILABLE") from exc
    for item in raw.split(b"\x00"):
        if item.startswith(b"RADAR_CONNECTOR_SHARED_KEY="):
            value = item.split(b"=", 1)[1].decode("utf-8", "replace")
            if len(value) >= 32:
                return value
    raise RuntimeError("RADAR_CONNECTOR_SHARED_KEY_UNAVAILABLE")


def radar_signature(method: str, path: str, timestamp: str, nonce: str, body: bytes, secret: str) -> str:
    body_hash = hashlib.sha256(body).hexdigest()
    canonical = "\n".join([method.upper(), path, timestamp, nonce, body_hash])
    return hmac.new(secret.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256).hexdigest()


def cluster_catalog_probe_snapshot() -> dict[str, Any]:
    path = "/v1/collector/server-cluster-catalog"
    secret = connector_shared_key()
    timestamp = str(int(time.time()))
    nonce = os.urandom(16).hex()
    body = b""
    signature = radar_signature("GET", path, timestamp, nonce, body, secret)
    req = urllib.request.Request(
        "http://127.0.0.1:8788" + path,
        method="GET",
        headers={
            "Accept": "application/json",
            "X-Radar-Timestamp": timestamp,
            "X-Radar-Nonce": nonce,
            "X-Radar-Signature": signature,
        },
    )
    started = time.monotonic()
    status = 0
    raw = b""
    try:
        with urllib.request.urlopen(req, timeout=45) as response:
            status = int(response.status)
            raw = response.read(65537)
    except urllib.error.HTTPError as exc:
        status = int(exc.code)
        raw = exc.read(65537)
    elapsed_ms = int(round((time.monotonic() - started) * 1000))
    if len(raw) > 65536:
        raise RuntimeError("RADAR_CATALOG_RESPONSE_TOO_LARGE")
    try:
        payload = json.loads(raw.decode("utf-8", "strict"))
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    seed = payload.get("recommendedSeed") if isinstance(payload.get("recommendedSeed"), dict) else {}
    return {
        "http_status": status,
        "elapsed_ms": elapsed_ms,
        "ok": payload.get("ok"),
        "readonly": payload.get("readonly"),
        "catalog_version": payload.get("catalogVersion"),
        "error": payload.get("error"),
        "confirmed_cluster_count": payload.get("confirmedClusterCount"),
        "confirmed_server_count": payload.get("confirmedServerCount"),
        "frontier_count": payload.get("frontierCount"),
        "noise_count": payload.get("noiseCount"),
        "recommended_seed": {
            "serverId": seed.get("serverId"),
            "command": seed.get("command"),
            "players": seed.get("players"),
        } if seed else None,
        "near_handler_deadline_30s": 28500 <= elapsed_ms <= 33000,
    }


def do_cluster_catalog_probe(request: dict[str, Any]) -> int:
    try:
        snap = cluster_catalog_probe_snapshot()
    except RuntimeError as exc:
        return emit(result(request, "FAILED", str(exc)))
    raw = json.dumps(snap, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return emit(result(request, "OK", "RADAR_CLUSTER_CATALOG_PROBE_OK", [{
        "kind": "diagnostic",
        "source": "http://127.0.0.1:8788/v1/collector/server-cluster-catalog",
        "digest": sha256_bytes(raw),
        "details": snap,
    }], [{
        "type": "artifact",
        "id": "radar-cluster-catalog-probe",
        "status": "UNVERIFIED",
        "reason": "Signed localhost read-only probe; independent verification required.",
    }]))


def history_performance_snapshot() -> dict[str, Any]:
    db_path = collector_db_path()
    started = time.monotonic()
    snap: dict[str, Any] = {
        "db_exists": db_path.is_file(),
        "db_readable": os.access(db_path, os.R_OK) if db_path.exists() else False,
        "required_tables_present": False,
        "cycle_count": 0,
        "seen_rows": 0,
        "hash_matched": 0,
        "hash_mismatched": 0,
        "unresolved": 0,
        "elapsed_ms": None,
        "slowest_cycles": [],
        "indexes": {},
        "failure_class": None,
    }
    if not snap["db_exists"]:
        snap["failure_class"] = "COLLECTOR_DB_NOT_FOUND"
        return snap
    if not snap["db_readable"]:
        snap["failure_class"] = "COLLECTOR_DB_NOT_READABLE"
        return snap

    required = {"cycle_seen", "cycle_baseline", "cycle_changes"}
    try:
        conn = sqlite3.connect("file:" + str(db_path) + "?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        try:
            tables = {str(r[0]) for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            snap["required_tables_present"] = required.issubset(tables)
            if not snap["required_tables_present"]:
                snap["failure_class"] = "HISTORICAL_SCHEMA_MISSING"
                return snap

            for table in sorted(required):
                idxs = []
                for row in conn.execute(f"PRAGMA index_list({table})"):
                    idx_name = str(row[1])
                    cols = [str(x[2]) for x in conn.execute(f"PRAGMA index_info({idx_name})")]
                    idxs.append({"name": idx_name, "columns": cols})
                snap["indexes"][table] = idxs

            cycle_ids = [int(r[0]) for r in conn.execute(
                "SELECT DISTINCT cycle_id FROM cycle_seen ORDER BY cycle_id"
            )]
            snap["cycle_count"] = len(cycle_ids)
            timings = []
            for cid in cycle_ids:
                cstart = time.monotonic()
                baseline = {
                    str(r["game_uid"]): str(r["state_json"] or "")
                    for r in conn.execute(
                        "SELECT game_uid,state_json FROM cycle_baseline WHERE cycle_id=?", (cid,)
                    )
                }
                changes: dict[str, str] = {}
                for r in conn.execute(
                    "SELECT game_uid,after_json FROM cycle_changes WHERE cycle_id=? ORDER BY id", (cid,)
                ):
                    if r["after_json"]:
                        changes[str(r["game_uid"])] = str(r["after_json"])

                seen = matched = mismatched = unresolved = 0
                for r in conn.execute(
                    "SELECT game_uid,state_hash FROM cycle_seen WHERE cycle_id=?", (cid,)
                ):
                    seen += 1
                    uid = str(r["game_uid"])
                    expected = str(r["state_hash"] or "").strip().lower()
                    raw = changes.get(uid) or baseline.get(uid) or ""
                    if not raw or not expected:
                        unresolved += 1
                        continue
                    actual = hashlib.sha256(raw.encode("utf-8")).hexdigest()
                    if actual != expected:
                        mismatched += 1
                        continue
                    try:
                        obj = json.loads(raw)
                    except Exception:
                        unresolved += 1
                        continue
                    sid = obj.get("server_id") if isinstance(obj, dict) else None
                    if sid is None or not str(sid).strip():
                        unresolved += 1
                        continue
                    matched += 1

                snap["seen_rows"] += seen
                snap["hash_matched"] += matched
                snap["hash_mismatched"] += mismatched
                snap["unresolved"] += unresolved
                timings.append({
                    "cycle_id": cid,
                    "elapsed_ms": int(round((time.monotonic() - cstart) * 1000)),
                    "seen_rows": seen,
                })
        finally:
            conn.close()
    except sqlite3.Error as exc:
        snap["failure_class"] = "SQLITE_READ_FAILED"
        snap["sqlite_error_class"] = type(exc).__name__
        return snap

    snap["elapsed_ms"] = int(round((time.monotonic() - started) * 1000))
    snap["slowest_cycles"] = sorted(
        timings, key=lambda x: (x["elapsed_ms"], x["seen_rows"]), reverse=True
    )[:8]
    snap["exceeds_catalog_budget_30s"] = bool((snap["elapsed_ms"] or 0) >= 30000)
    return snap


def do_history_performance_diagnostic(request: dict[str, Any]) -> int:
    snap = history_performance_snapshot()
    raw = json.dumps(snap, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return emit(result(request, "OK", "RADAR_HISTORY_PERFORMANCE_DIAGNOSTIC_OK", [{
        "kind": "diagnostic",
        "source": "vps://localhost/wfgg-collector/server-cycle-history-v614",
        "digest": sha256_bytes(raw),
        "details": snap,
    }], [{
        "type": "artifact",
        "id": "radar-history-performance-diagnostic",
        "status": "UNVERIFIED",
        "reason": "Read-only reconstruction timing with aggregate-only output; independent verification required.",
    }]))


def signed_json_get(path: str, timeout_seconds: int = 45) -> tuple[int, dict[str, Any], int]:
    secret = connector_shared_key()
    timestamp = str(int(time.time()))
    nonce = os.urandom(16).hex()
    body = b""
    signature = radar_signature("GET", path, timestamp, nonce, body, secret)
    req = urllib.request.Request(
        "http://127.0.0.1:8788" + path,
        method="GET",
        headers={
            "Accept": "application/json",
            "X-Radar-Timestamp": timestamp,
            "X-Radar-Nonce": nonce,
            "X-Radar-Signature": signature,
        },
    )
    started = time.monotonic()
    status = 0
    raw = b""
    try:
        with urllib.request.urlopen(req, timeout=timeout_seconds) as response:
            status = int(response.status)
            raw = response.read(262145)
    except urllib.error.HTTPError as exc:
        status = int(exc.code)
        raw = exc.read(262145)
    elapsed_ms = int(round((time.monotonic() - started) * 1000))
    if len(raw) > 262144:
        raise RuntimeError("RADAR_RESPONSE_TOO_LARGE")
    try:
        payload = json.loads(raw.decode("utf-8", "strict"))
    except Exception as exc:
        raise RuntimeError("RADAR_RESPONSE_JSON_INVALID") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("RADAR_RESPONSE_NOT_OBJECT")
    return status, payload, elapsed_ms


def census_frontier_snapshot() -> dict[str, Any]:
    status, payload, elapsed_ms = signed_json_get("/v1/collector/server-census", 45)
    rows = payload.get("servers") if isinstance(payload.get("servers"), list) else []
    sanitized = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        sid = str(row.get("serverId") or "").strip()
        if not sid:
            continue
        sanitized.append({
            "serverId": sid,
            "players": int(row.get("players") or 0),
            "observations": int(row.get("observations") or 0),
            "distinctCycles": int(row.get("distinctCycles") or 0),
        })
    sanitized.sort(key=lambda x: (-x["players"], int(x["serverId"]) if x["serverId"].isdigit() else 10**18, x["serverId"]))
    eligible = [x for x in sanitized if x["players"] >= 50]
    noise = [x for x in sanitized if x["players"] < 50]
    return {
        "http_status": status,
        "elapsed_ms": elapsed_ms,
        "ok": payload.get("ok"),
        "readonly": payload.get("readonly"),
        "census_version": payload.get("censusVersion"),
        "server_count": len(sanitized),
        "seed_floor": 50,
        "eligible_count": len(eligible),
        "noise_count": len(noise),
        "eligible_servers": eligible,
        "noise_servers": noise,
    }


def do_census_frontier_diagnostic(request: dict[str, Any]) -> int:
    try:
        snap = census_frontier_snapshot()
    except RuntimeError as exc:
        return emit(result(request, "FAILED", str(exc)))
    raw = json.dumps(snap, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return emit(result(request, "OK", "RADAR_CENSUS_FRONTIER_DIAGNOSTIC_OK", [{
        "kind": "diagnostic",
        "source": "http://127.0.0.1:8788/v1/collector/server-census",
        "digest": sha256_bytes(raw),
        "details": snap,
    }], [{
        "type": "artifact",
        "id": "radar-census-frontier-diagnostic",
        "status": "UNVERIFIED",
        "reason": "Signed localhost read-only aggregate census diagnostic; independent verification required.",
    }]))


def signed_json_request(method: str, path: str, body_obj: dict[str, Any] | None = None, timeout_seconds: int = 20) -> tuple[int, dict[str, Any], int]:
    secret = connector_shared_key()
    body = b"" if body_obj is None else json.dumps(body_obj, separators=(",", ":")).encode("utf-8")
    timestamp = str(int(time.time()))
    nonce = os.urandom(16).hex()
    signature = radar_signature(method, path, timestamp, nonce, body, secret)
    req = urllib.request.Request(
        "http://127.0.0.1:8788" + path,
        data=None if method.upper() == "GET" else body,
        method=method.upper(),
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-Radar-Timestamp": timestamp,
            "X-Radar-Nonce": nonce,
            "X-Radar-Signature": signature,
        },
    )
    started = time.monotonic()
    status = 0
    raw = b""
    try:
        with urllib.request.urlopen(req, timeout=timeout_seconds) as response:
            status = int(response.status)
            raw = response.read(65537)
    except urllib.error.HTTPError as exc:
        status = int(exc.code)
        raw = exc.read(65537)
    elapsed_ms = int(round((time.monotonic() - started) * 1000))
    if len(raw) > 65536:
        raise RuntimeError("RADAR_ROUTE_DIAGNOSTIC_RESPONSE_TOO_LARGE")
    try:
        payload = json.loads(raw.decode("utf-8", "strict"))
    except Exception:
        payload = {"_invalid_json": True, "_body_length": len(raw)}
    if not isinstance(payload, dict):
        payload = {"_non_object_json": True}
    return status, payload, elapsed_ms


def seed_scout_route_snapshot() -> dict[str, Any]:
    snap = status_snapshot()
    out: dict[str, Any] = {
        "radar_service": snap.get("radar_service"),
        "connector_sha256": snap.get("connector_sha256"),
        "native_sha256": snap.get("native_sha256"),
        "expected_v6193_connector_sha256": "73b64743031e4a47212dfdafae8ad67551f88d131831e70cb08a40957824f9a8",
        "expected_v6193_native_sha256": "274d040f5294cb09422e5d55cc4b5335ac7739924c33dcb67b3f279645814900",
        "v6193_loaded": False,
        "start_guard": {},
        "status_guard": {},
        "route_guards_ready": False,
        "failure_class": None,
    }
    out["v6193_loaded"] = (
        out["connector_sha256"] == out["expected_v6193_connector_sha256"]
        and out["native_sha256"] == out["expected_v6193_native_sha256"]
    )
    try:
        start_status, start_payload, start_ms = signed_json_request(
            "POST", "/v1/collector/server-seed-scout/start", {}, 20
        )
        status_status, status_payload, status_ms = signed_json_request(
            "GET", "/v1/collector/server-seed-scout/status?id=does-not-exist", None, 20
        )
    except RuntimeError as exc:
        out["failure_class"] = str(exc)
        return out

    out["start_guard"] = {
        "http_status": start_status,
        "error": start_payload.get("error"),
        "elapsed_ms": start_ms,
    }
    out["status_guard"] = {
        "http_status": status_status,
        "error": status_payload.get("error"),
        "elapsed_ms": status_ms,
    }

    if start_status != 400:
        out["failure_class"] = "SEED_SCOUT_START_GUARD_HTTP_UNEXPECTED"
        return out
    if start_payload.get("error") != "GAME_TOKEN_REQUIRED":
        out["failure_class"] = "SEED_SCOUT_START_GUARD_ERROR_UNEXPECTED"
        return out
    if status_status != 404:
        out["failure_class"] = "SEED_SCOUT_STATUS_GUARD_HTTP_UNEXPECTED"
        return out
    if status_payload.get("error") != "SEED_SCOUT_JOB_NOT_FOUND":
        out["failure_class"] = "SEED_SCOUT_STATUS_GUARD_ERROR_UNEXPECTED"
        return out

    out["route_guards_ready"] = True
    return out


def do_seed_scout_route_diagnostic(request: dict[str, Any]) -> int:
    try:
        snap = seed_scout_route_snapshot()
    except RuntimeError as exc:
        return emit(result(request, "FAILED", str(exc)))
    raw = json.dumps(snap, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return emit(result(request, "OK", "RADAR_SEED_SCOUT_ROUTE_DIAGNOSTIC_OK", [{
        "kind": "diagnostic",
        "source": "http://127.0.0.1:8788/v1/collector/server-seed-scout",
        "digest": sha256_bytes(raw),
        "details": snap,
    }], [{
        "type": "artifact",
        "id": "radar-seed-scout-route-diagnostic",
        "status": "UNVERIFIED",
        "reason": "Signed localhost guard-only diagnostic; no game token and no game scan.",
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
        if action == "cluster-quality-diagnostic":
            return do_cluster_quality_diagnostic(request)
        if action == "cluster-catalog-probe":
            return do_cluster_catalog_probe(request)
        if action == "history-performance-diagnostic":
            return do_history_performance_diagnostic(request)
        if action == "census-frontier-diagnostic":
            return do_census_frontier_diagnostic(request)
        if action == "seed-scout-route-diagnostic":
            return do_seed_scout_route_diagnostic(request)
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
