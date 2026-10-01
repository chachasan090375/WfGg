from __future__ import annotations
import argparse, hashlib, json, os, subprocess, sys, time
from pathlib import Path
from typing import Any

SCHEMA = "chacha.dev/guardian-stop-latch-reconciliation/v1"
LATCH_SCHEMA = "chacha.dev/guardian-stop-required/v1"
CANONICAL_STOP = Path("/opt/chacha-dev/runtime/control/emergency-stop.json")
DEFAULT_POLICY = Path("/opt/chacha-dev/platform/current/dev-hub/config/guardian-runtime-policy.v1.json")
DEFAULT_CONFIG = Path("/opt/chacha-dev/platform/current/dev-hub/config/guardian-stop-latch-reconciliation.v1.json")
DEFAULT_CLIENT = Path("/opt/chacha-dev/platform/current/dev-hub/bin/guardian-client.py")
COVERAGE_MARKER = "CHACHA_DEV_GUARDIAN_CRITICAL_STATE_RECONCILIATION=PASS"


def load(path: Path) -> dict[str, Any]:
    x = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(x, dict):
        raise ValueError("JSON_ROOT_NOT_OBJECT:" + str(path))
    return x


def stable(x: Any) -> str:
    return json.dumps(x, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def digest_obj(x: Any) -> str:
    return "sha256:" + hashlib.sha256(stable(x).encode()).hexdigest()


def atomic(path: Path, obj: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp-" + str(os.getpid()))
    tmp.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    dfd = os.open(str(path.parent), os.O_DIRECTORY)
    try:
        os.fsync(dfd)
    finally:
        os.close(dfd)


def call_client(client: Path, policy: Path, kind: str, status: str) -> list[dict[str, Any]]:
    p = subprocess.run(
        [sys.executable, str(client), "--policy", str(policy), kind,
         "--status", status, "--limit", "100"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        check=False, timeout=30,
    )
    if p.returncode != 0:
        raise RuntimeError(f"GUARDIAN_{kind.upper()}_{status}_RC_{p.returncode}")
    x = json.loads(p.stdout)
    if not isinstance(x, dict) or not isinstance(x.get("items"), list):
        raise RuntimeError(f"GUARDIAN_{kind.upper()}_{status}_INVALID")
    return [r for r in x["items"] if isinstance(r, dict)]


def snapshot(client: Path, policy: Path) -> dict[str, Any]:
    alerts = call_client(client, policy, "alerts", "OPEN")
    rem_open = call_client(client, policy, "remediations", "OPEN")
    rem_delivered = call_client(client, policy, "remediations", "DELIVERED")
    critical: list[dict[str, Any]] = []
    for r in alerts:
        if str(r.get("severity") or "").upper() == "CRITICAL":
            critical.append({"type": "alert", "id": str(r.get("alert_id") or ""),
                             "status": "OPEN", "severity": "CRITICAL"})
    for status, rows in (("OPEN", rem_open), ("DELIVERED", rem_delivered)):
        for r in rows:
            if str(r.get("severity") or "").upper() == "CRITICAL":
                critical.append({"type": "remediation", "id": str(r.get("directive_id") or ""),
                                 "status": status, "severity": "CRITICAL",
                                 "source_alert_id": r.get("source_alert_id")})
    critical.sort(key=lambda x: (x["type"], x["id"], x["status"]))
    return {"critical_sources": critical,
            "open_alert_count": len(alerts),
            "open_remediation_count": len(rem_open),
            "delivered_remediation_count": len(rem_delivered)}


def active_latch(snap: dict[str, Any], previous: dict[str, Any] | None) -> dict[str, Any]:
    sources = snap["critical_sources"]
    return {"schema": LATCH_SCHEMA, "active": True, "auto_stop_executed": False,
            "reason": "GUARDIAN_CRITICAL_SOURCE_CONFIRMED",
            "critical_source_count": len(sources), "critical_sources": sources,
            "source_state_digest": digest_obj(snap),
            "previous_reason": (previous or {}).get("reason"),
            "human_or_out_of_band_stop_required": True}


def cleared_latch(previous: dict[str, Any] | None, snap: dict[str, Any]) -> dict[str, Any]:
    return {"schema": LATCH_SCHEMA, "active": False, "auto_stop_executed": False,
            "reason": "NO_ACTIVE_GUARDIAN_CRITICAL_SOURCE",
            "critical_source_count": 0, "critical_sources": [],
            "source_state_digest": digest_obj(snap),
            "previous_reason": (previous or {}).get("reason"),
            "previous_directive_id": (previous or {}).get("directive_id"),
            "previous_alert_id": (previous or {}).get("alert_id") or (previous or {}).get("source_alert_id"),
            "human_or_out_of_band_stop_required": False,
            "cleared_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}


def receipt(status: str, action: str, latch: Path, snap: dict[str, Any] | None,
            blockers: list[str] | None = None) -> dict[str, Any]:
    return {"schema": SCHEMA, "status": status, "action": action,
            "latch_file": str(latch), "critical_sources": (snap or {}).get("critical_sources", []),
            "blockers": blockers or [], "canonical_emergency_stop_mutated": False,
            "automatic_external_spend_eur": 0,
            "observed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}


def current_latch(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    x = load(path)
    if x.get("schema") != LATCH_SCHEMA:
        raise ValueError("GUARDIAN_LATCH_SCHEMA_INVALID")
    return x


def reconcile(policy_path: Path, config_path: Path, client: Path, dry_run: bool) -> tuple[int, dict[str, Any]]:
    policy, cfg = load(policy_path), load(config_path)
    latch = Path(str(policy.get("critical_stop_required_file") or ""))
    if not latch.is_absolute():
        raise ValueError("GUARDIAN_LATCH_PATH_NOT_ABSOLUTE")
    if latch.resolve() == CANONICAL_STOP.resolve():
        raise ValueError("CANONICAL_EMERGENCY_STOP_MUTATION_FORBIDDEN")
    previous = current_latch(latch)
    try:
        first = snapshot(client, policy_path)
    except Exception as exc:
        obj = active_latch({"critical_sources": [{"type": "availability", "id": type(exc).__name__,
                            "status": "UNKNOWN", "severity": "CRITICAL"}]}, previous)
        obj["reason"] = "GUARDIAN_STATE_UNAVAILABLE_FAIL_CLOSED"
        if not dry_run:
            atomic(latch, obj)
        return 0, receipt("DEFERRED", "FAIL_CLOSED_ACTIVE" if not dry_run else "DRY_RUN_FAIL_CLOSED", latch,
                          {"critical_sources": obj["critical_sources"]}, [str(exc)[:200]])
    if first["critical_sources"]:
        if not dry_run:
            atomic(latch, active_latch(first, previous))
        return 0, receipt("PASS", "KEEP_OR_SET_ACTIVE" if not dry_run else "DRY_RUN_KEEP_ACTIVE", latch, first)
    delay = float(cfg.get("confirmation_delay_seconds") or 1.0)
    if delay > 0:
        time.sleep(min(delay, 5.0))
    try:
        second = snapshot(client, policy_path)
    except Exception as exc:
        obj = active_latch({"critical_sources": [{"type": "availability", "id": type(exc).__name__,
                            "status": "UNKNOWN", "severity": "CRITICAL"}]}, previous)
        obj["reason"] = "GUARDIAN_STATE_UNAVAILABLE_FAIL_CLOSED"
        if not dry_run:
            atomic(latch, obj)
        return 0, receipt("DEFERRED", "FAIL_CLOSED_ACTIVE" if not dry_run else "DRY_RUN_FAIL_CLOSED", latch,
                          {"critical_sources": obj["critical_sources"]}, [str(exc)[:200]])
    if second["critical_sources"]:
        if not dry_run:
            atomic(latch, active_latch(second, previous))
        return 0, receipt("PASS", "KEEP_OR_SET_ACTIVE" if not dry_run else "DRY_RUN_KEEP_ACTIVE", latch, second)
    managed = set(str(x) for x in (cfg.get("managed_active_reasons") or []))
    if previous and previous.get("active") is True and str(previous.get("reason") or "") not in managed:
        return 0, receipt("HOLD", "UNRECOGNIZED_ACTIVE_LATCH_PRESERVED", latch, second,
                          ["UNRECOGNIZED_ACTIVE_LATCH_REASON"])
    if not dry_run:
        atomic(latch, cleared_latch(previous, second))
    return 0, receipt("PASS", "CLEAR_STALE_LATCH" if not dry_run else "DRY_RUN_CLEAR_STALE_LATCH", latch, second)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    ap.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    ap.add_argument("--client", type=Path, default=DEFAULT_CLIENT)
    ap.add_argument("--receipt", type=Path)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    try:
        rc, out = reconcile(a.policy, a.config, a.client, a.dry_run)
    except Exception as exc:
        out = {"schema": SCHEMA, "status": "BLOCK", "action": "NO_MUTATION",
               "blockers": [type(exc).__name__ + ":" + str(exc)[:240]],
               "canonical_emergency_stop_mutated": False,
               "automatic_external_spend_eur": 0,
               "observed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        rc = 20
    if a.receipt:
        atomic(a.receipt, out)
    print(json.dumps(out, sort_keys=True, ensure_ascii=False))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
