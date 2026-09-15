#!/usr/bin/env python3
"""ChaCha DEV HUB Transaction Recovery & Reconciliation Engine V1.1.

Reconciles interrupted Project Control transactions against the authoritative,
hash-chained audit journal. Recovery is forward-only: audit events are never
deleted, rewritten, truncated, or rolled back. Derived projections may be
rebuilt and a staged Evidence Ledger may be finalized only under digest guards.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

POLICY_SCHEMA = "chacha.dev/transaction-recovery/v1"
RECEIPT_SCHEMA = "chacha.dev/control-transaction-receipt/v1"
REPORT_SCHEMA = "chacha.dev/transaction-recovery-report/v1"
EVENT_SCHEMA = "chacha.dev/audit-event/v1"
LEDGER_SCHEMA = "chacha.dev/evidence-ledger/v1"


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


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(value, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
        dir_fd = os.open(str(path.parent), os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    finally:
        if tmp.exists():
            tmp.unlink()


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def digest_obj(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical(value)).hexdigest()


def resolve_repo(repo_root: Path, configured: str) -> Path:
    path = Path(configured)
    return path if path.is_absolute() else repo_root / path


def runtime_paths(policy: dict[str, Any], project: str) -> dict[str, Path]:
    runtime = policy.get("runtime") or {}
    tx_root = Path(str(runtime.get("transactions_root", "/opt/chacha-dev/runtime/transactions")))
    state_root = Path(str(runtime.get("state_root", "/opt/chacha-dev/runtime/state")))
    evidence_root = Path(str(runtime.get("evidence_root", "/opt/chacha-dev/runtime/evidence")))
    locks_root = Path(str(runtime.get("locks_root", "/opt/chacha-dev/runtime/locks/control")))
    return {
        "transactions": tx_root / project,
        "state": state_root / project / "state.json",
        "journal": state_root / project / "audit.jsonl",
        "ledger": evidence_root / project / "ledger.json",
        "lock": locks_root / f"{project}.lock",
        "state_root": state_root,
    }


@contextmanager
def project_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as fh:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


def read_events(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise SystemExit(f"JOURNAL_NOT_FOUND={path}")
    events: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError as exc:
                raise SystemExit(f"JOURNAL_JSON_INVALID=line:{lineno}:{exc.msg}")
            if not isinstance(event, dict):
                raise SystemExit(f"JOURNAL_EVENT_NOT_OBJECT=line:{lineno}")
            events.append(event)
    return events


def verify_chain(events: list[dict[str, Any]], project: str) -> list[str]:
    errors: list[str] = []
    previous: str | None = None
    expected_sequence = 1
    for event in events:
        seq = event.get("sequence")
        if event.get("schema") != EVENT_SCHEMA:
            errors.append(f"SCHEMA:{seq}")
        if event.get("project") != project:
            errors.append(f"PROJECT:{seq}")
        if seq != expected_sequence:
            errors.append(f"SEQUENCE:expected={expected_sequence}:actual={seq}")
        if event.get("previous_event_digest") != previous:
            errors.append(f"CHAIN:{seq}")
        unsigned = dict(event)
        declared = unsigned.pop("event_digest", None)
        actual = digest_obj(unsigned)
        if declared != actual:
            errors.append(f"DIGEST:{seq}")
        previous = declared
        expected_sequence += 1
    return sorted(set(errors))


def transaction_events(events: list[dict[str, Any]], txid: str, event_type: str | None = None) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for event in events:
        payload = event.get("payload") or {}
        if not isinstance(payload, dict) or payload.get("transaction_id") != txid:
            continue
        if event_type and event.get("event_type") != event_type:
            continue
        found.append(event)
    return found


def expected_event_type(receipt: dict[str, Any], policy: dict[str, Any]) -> str | None:
    operation = str(receipt.get("operation") or "")
    return (((policy.get("operations") or {}).get(operation) or {}).get("authoritative_event_type"))


def enrich_from_event(receipt: dict[str, Any], event: dict[str, Any] | None) -> dict[str, Any]:
    """Recover preconditions that older failure receipts may have omitted.

    The authoritative EVIDENCE_RECORDED event carries old/new ledger digests and
    staged-ledger path. Receipt enrichment is in-memory only until recovery is
    explicitly applied.
    """
    out = deepcopy(receipt)
    if not event or out.get("operation") != "verify-result":
        return out
    payload = event.get("payload") or {}
    if not isinstance(payload, dict):
        return out
    for key in ("old_ledger_digest", "new_ledger_digest", "staged_ledger"):
        if not out.get(key) and payload.get(key):
            out[key] = payload[key]
    return out


def run_tool(tool: Path, argv: list[str], timeout: int = 60) -> tuple[int, str, str]:
    if not tool.exists():
        return 127, "", f"TOOL_NOT_FOUND={tool}"
    try:
        proc = subprocess.run(
            [sys.executable, str(tool), *argv],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            shell=False,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return 124, "", f"TOOL_TIMEOUT={tool}"
    return proc.returncode, proc.stdout, proc.stderr


def store_call(project: str, action: str, policy: dict[str, Any], repo_root: Path, state_root: Path) -> tuple[int, str, str]:
    repo = policy.get("repository_paths") or {}
    store = resolve_repo(repo_root, str(repo.get("control_plane_store")))
    state_policy = resolve_repo(repo_root, str(repo.get("control_plane_state")))
    return run_tool(store, ["--policy", str(state_policy), "--root", str(state_root), action, "--project", project])


def projection_info(project: str, paths: dict[str, Path], policy: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    rc, stdout, stderr = store_call(project, "verify", policy, repo_root, paths["state_root"])
    state: dict[str, Any] | None = None
    if paths["state"].exists():
        try:
            state = load(paths["state"])
        except SystemExit:
            state = None
    lifecycle = (((state or {}).get("state") or {}).get("lifecycle") or {}) if state else {}
    return {
        "verified": rc == 0,
        "verify_stdout": stdout.strip(),
        "verify_stderr": stderr.strip(),
        "version": state.get("version") if state else None,
        "head_digest": state.get("last_event_digest") if state else None,
        "stage": lifecycle.get("stage") if isinstance(lifecycle, dict) else None,
    }


def ledger_info(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"exists": False, "digest": None, "schema": None}
    try:
        value = load(path)
    except SystemExit as exc:
        return {"exists": True, "digest": None, "schema": None, "error": str(exc)}
    return {"exists": True, "digest": digest_obj(value), "schema": value.get("schema")}


def load_receipt(paths: dict[str, Path], project: str, txid: str) -> tuple[Path, dict[str, Any]]:
    path = paths["transactions"] / txid / "receipt.json"
    receipt = load(path)
    if receipt.get("schema") != RECEIPT_SCHEMA:
        raise SystemExit(f"RECEIPT_SCHEMA_INVALID={receipt.get('schema')}")
    if receipt.get("project") != project:
        raise SystemExit("RECEIPT_PROJECT_MISMATCH")
    if receipt.get("transaction_id") != txid:
        raise SystemExit("RECEIPT_TRANSACTION_ID_MISMATCH")
    return path, receipt


def update_receipt(path: Path, receipt: dict[str, Any], status: str, outcome: str,
                   actor: str, details: dict[str, Any]) -> dict[str, Any]:
    out = deepcopy(receipt)
    out["status"] = status
    out["updated_at"] = now_iso()
    out["recovery_outcome"] = outcome
    out.setdefault("recovery_history", []).append({
        "observed_at": out["updated_at"],
        "actor": actor,
        "status": status,
        "outcome": outcome,
        "details": details,
    })
    atomic_json(path, out)
    return out


def report(project: str, txid: str, operation: str, receipt_status: str, assessment: str,
           apply_requested: bool, event: dict[str, Any] | None = None,
           journal: dict[str, Any] | None = None, projection: dict[str, Any] | None = None,
           ledger: dict[str, Any] | None = None, actions: list[str] | None = None,
           blockers: list[str] | None = None, outcome: str | None = None) -> dict[str, Any]:
    event_summary = None
    if event:
        event_summary = {
            "sequence": event.get("sequence"),
            "event_id": event.get("event_id"),
            "event_type": event.get("event_type"),
            "event_digest": event.get("event_digest"),
            "observed_at": event.get("observed_at"),
        }
    return {
        "schema": REPORT_SCHEMA,
        "project": project,
        "transaction_id": txid,
        "operation": operation,
        "receipt_status": receipt_status,
        "assessment": assessment,
        "apply_requested": apply_requested,
        "authoritative_event": event_summary,
        "journal": journal or {},
        "projection": projection or {},
        "ledger": ledger or {},
        "actions": actions or [],
        "blockers": blockers or [],
        "recovery_outcome": outcome,
        "observed_at": now_iso(),
    }


def inspect_transaction(project: str, txid: str, receipt: dict[str, Any], paths: dict[str, Path],
                        policy: dict[str, Any], repo_root: Path, apply_requested: bool) -> dict[str, Any]:
    status = str(receipt.get("status") or "UNKNOWN")
    operation = str(receipt.get("operation") or "")
    closed = set(policy.get("closed_statuses") or [])

    try:
        events = read_events(paths["journal"])
    except SystemExit as exc:
        return report(project, txid, operation, status, "INVALID", apply_requested,
                      journal={"valid": False, "errors": [str(exc)]}, blockers=[str(exc)])
    chain_errors = verify_chain(events, project)
    journal = {
        "valid": not chain_errors,
        "event_count": len(events),
        "head_digest": events[-1].get("event_digest") if events else None,
        "errors": chain_errors,
    }
    if chain_errors:
        return report(project, txid, operation, status, "INVALID", apply_requested,
                      journal=journal, blockers=["AUDIT_JOURNAL_INVALID", *chain_errors])

    expected = expected_event_type(receipt, policy)
    matches = transaction_events(events, txid, expected)
    all_matches = transaction_events(events, txid, None)
    if len(matches) > 1:
        return report(project, txid, operation, status, "MANUAL_REVIEW", apply_requested,
                      journal=journal, blockers=["MULTIPLE_AUTHORITATIVE_EVENTS_FOR_TRANSACTION"])
    if expected and not matches and all_matches:
        return report(project, txid, operation, status, "MANUAL_REVIEW", apply_requested,
                      journal=journal, blockers=["TRANSACTION_ID_FOUND_WITH_UNEXPECTED_EVENT_TYPE"])

    event = matches[0] if matches else None
    receipt = enrich_from_event(receipt, event)
    projection = projection_info(project, paths, policy, repo_root)
    ledger = ledger_info(paths["ledger"])

    if status in closed:
        return report(project, txid, operation, status, "TERMINAL", apply_requested,
                      event=event, journal=journal, projection=projection, ledger=ledger,
                      actions=["none"], outcome=receipt.get("recovery_outcome"))

    if operation == "advance":
        transition = str(receipt.get("transition") or "")
        target = transition.split("->", 1)[1] if "->" in transition else None
        if event is None:
            actions = ["close transaction as FAILED:ABORTED_BEFORE_AUTHORITATIVE_COMMIT"]
            if not projection.get("verified"):
                actions.insert(0, "rebuild projection from valid authoritative journal")
                assessment = "REPAIRABLE"
            else:
                assessment = "SAFE_TO_ABORT"
            return report(project, txid, operation, status, assessment, apply_requested,
                          journal=journal, projection=projection, ledger=ledger, actions=actions)
        payload = event.get("payload") or {}
        blockers: list[str] = []
        if transition and payload.get("transition") and transition != payload.get("transition"):
            blockers.append("ADVANCE_TRANSITION_MISMATCH")
        if target and payload.get("to") and target != payload.get("to"):
            blockers.append("ADVANCE_TARGET_MISMATCH")
        if blockers:
            return report(project, txid, operation, status, "MANUAL_REVIEW", apply_requested,
                          event=event, journal=journal, projection=projection, ledger=ledger, blockers=blockers)
        if not projection.get("verified"):
            return report(project, txid, operation, status, "REPAIRABLE", apply_requested,
                          event=event, journal=journal, projection=projection, ledger=ledger,
                          actions=["rebuild projection from valid authoritative journal",
                                   "close receipt as COMMITTED:RECOVERED_FROM_AUTHORITATIVE_EVENT"])
        return report(project, txid, operation, status, "ALREADY_EFFECTIVE", apply_requested,
                      event=event, journal=journal, projection=projection, ledger=ledger,
                      actions=["close receipt as COMMITTED:AUTHORITATIVE_EVENT_CONFIRMED"])

    if operation == "verify-result":
        event_payload = (event.get("payload") or {}) if event else {}
        old_digest = receipt.get("old_ledger_digest") or event_payload.get("old_ledger_digest")
        new_digest = receipt.get("new_ledger_digest") or event_payload.get("new_ledger_digest")
        staged_raw = receipt.get("staged_ledger") or event_payload.get("staged_ledger")
        staged = Path(str(staged_raw)) if staged_raw else paths["transactions"] / txid / "staged-ledger.json"
        staged_info = ledger_info(staged)
        ledger.update({
            "staged_path": str(staged),
            "staged_exists": staged_info.get("exists"),
            "staged_digest": staged_info.get("digest"),
            "expected_old_digest": old_digest,
            "expected_new_digest": new_digest,
        })

        if event is None:
            live_digest = ledger.get("digest")
            if new_digest and live_digest == new_digest:
                return report(project, txid, operation, status, "MANUAL_REVIEW", apply_requested,
                              journal=journal, projection=projection, ledger=ledger,
                              blockers=["LEDGER_CHANGED_WITHOUT_AUTHORITATIVE_EVIDENCE_EVENT"])
            if old_digest and live_digest not in {old_digest, None}:
                return report(project, txid, operation, status, "MANUAL_REVIEW", apply_requested,
                              journal=journal, projection=projection, ledger=ledger,
                              blockers=["LIVE_LEDGER_DIVERGED_FROM_TRANSACTION_PRECONDITION"])
            actions = ["close transaction as FAILED:ABORTED_BEFORE_AUTHORITATIVE_COMMIT"]
            assessment = "SAFE_TO_ABORT"
            if not projection.get("verified"):
                actions.insert(0, "rebuild projection from valid authoritative journal")
                assessment = "REPAIRABLE"
            return report(project, txid, operation, status, assessment, apply_requested,
                          journal=journal, projection=projection, ledger=ledger, actions=actions)

        blockers: list[str] = []
        if not old_digest:
            blockers.append("EXPECTED_OLD_LEDGER_DIGEST_MISSING")
        if not new_digest:
            blockers.append("EXPECTED_NEW_LEDGER_DIGEST_MISSING")
        if receipt.get("new_ledger_digest") and event_payload.get("new_ledger_digest") and receipt.get("new_ledger_digest") != event_payload.get("new_ledger_digest"):
            blockers.append("EVIDENCE_EVENT_LEDGER_DIGEST_MISMATCH")
        if new_digest and staged_info.get("digest") and staged_info.get("digest") != new_digest:
            blockers.append("STAGED_LEDGER_DIGEST_MISMATCH")
        if ledger.get("schema") not in {LEDGER_SCHEMA, None}:
            blockers.append("LIVE_LEDGER_SCHEMA_INVALID")
        if blockers:
            return report(project, txid, operation, status, "MANUAL_REVIEW", apply_requested,
                          event=event, journal=journal, projection=projection, ledger=ledger, blockers=blockers)

        live_digest = ledger.get("digest")
        if live_digest == new_digest:
            if not projection.get("verified"):
                return report(project, txid, operation, status, "REPAIRABLE", apply_requested,
                              event=event, journal=journal, projection=projection, ledger=ledger,
                              actions=["rebuild projection from valid authoritative journal",
                                       "close receipt as COMMITTED:LEDGER_ALREADY_FINALIZED"])
            return report(project, txid, operation, status, "ALREADY_EFFECTIVE", apply_requested,
                          event=event, journal=journal, projection=projection, ledger=ledger,
                          actions=["close receipt as COMMITTED:LEDGER_ALREADY_FINALIZED"])

        if live_digest == old_digest:
            if not staged_info.get("exists"):
                return report(project, txid, operation, status, "MANUAL_REVIEW", apply_requested,
                              event=event, journal=journal, projection=projection, ledger=ledger,
                              blockers=["STAGED_LEDGER_MISSING"])
            if staged_info.get("digest") != new_digest:
                return report(project, txid, operation, status, "MANUAL_REVIEW", apply_requested,
                              event=event, journal=journal, projection=projection, ledger=ledger,
                              blockers=["STAGED_LEDGER_NOT_TRUSTWORTHY"])
            actions = ["atomically finalize verified staged ledger",
                       "close receipt as COMMITTED:RECOVERED_LEDGER_FINALIZATION"]
            assessment = "SAFE_TO_FINALIZE"
            if not projection.get("verified"):
                actions.insert(0, "rebuild projection from valid authoritative journal")
                assessment = "REPAIRABLE"
            return report(project, txid, operation, status, assessment, apply_requested,
                          event=event, journal=journal, projection=projection, ledger=ledger, actions=actions)

        return report(project, txid, operation, status, "MANUAL_REVIEW", apply_requested,
                      event=event, journal=journal, projection=projection, ledger=ledger,
                      blockers=["LIVE_LEDGER_DIGEST_IS_NEITHER_EXPECTED_OLD_NOR_NEW"])

    return report(project, txid, operation, status, "MANUAL_REVIEW", apply_requested,
                  event=event, journal=journal, projection=projection, ledger=ledger,
                  blockers=[f"RECOVERY_OPERATION_UNSUPPORTED:{operation}"])


def rebuild_projection(project: str, paths: dict[str, Path], policy: dict[str, Any], repo_root: Path) -> tuple[bool, str]:
    rc, stdout, stderr = store_call(project, "rebuild", policy, repo_root, paths["state_root"])
    if rc != 0:
        return False, (stderr or stdout).strip()
    rc2, stdout2, stderr2 = store_call(project, "verify", policy, repo_root, paths["state_root"])
    return (rc2 == 0, (stderr2 or stdout2).strip())


def finalize_ledger(live: Path, staged: Path, expected_digest: str) -> tuple[bool, str]:
    if not staged.exists():
        return False, "STAGED_LEDGER_MISSING"
    staged_value = load(staged)
    if staged_value.get("schema") != LEDGER_SCHEMA:
        return False, "STAGED_LEDGER_SCHEMA_INVALID"
    if digest_obj(staged_value) != expected_digest:
        return False, "STAGED_LEDGER_DIGEST_MISMATCH"
    live.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix="ledger.recovery.", suffix=".tmp", dir=str(live.parent))
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        shutil.copy2(staged, tmp)
        with tmp.open("r+b") as fh:
            os.fsync(fh.fileno())
        os.replace(tmp, live)
        dir_fd = os.open(str(live.parent), os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    finally:
        if tmp.exists():
            tmp.unlink()
    final = load(live)
    if digest_obj(final) != expected_digest:
        return False, "FINAL_LEDGER_DIGEST_MISMATCH"
    return True, "LEDGER_FINALIZED"


def apply_recovery(project: str, txid: str, receipt_path: Path, receipt: dict[str, Any],
                   paths: dict[str, Path], policy: dict[str, Any], repo_root: Path,
                   actor: str) -> dict[str, Any]:
    current = inspect_transaction(project, txid, receipt, paths, policy, repo_root, True)
    if current.get("assessment") in {"TERMINAL", "INVALID", "MANUAL_REVIEW"}:
        return current

    if not (current.get("projection") or {}).get("verified"):
        ok, detail = rebuild_projection(project, paths, policy, repo_root)
        if not ok:
            current["assessment"] = "MANUAL_REVIEW"
            current["blockers"] = ["PROJECTION_REBUILD_FAILED:" + detail]
            return current
        receipt_path, receipt = load_receipt(paths, project, txid)
        current = inspect_transaction(project, txid, receipt, paths, policy, repo_root, True)
        if current.get("assessment") in {"INVALID", "MANUAL_REVIEW"}:
            return current

    operation = str(receipt.get("operation") or "")
    assessment = str(current.get("assessment") or "")
    event = current.get("authoritative_event") or {}

    if assessment == "SAFE_TO_ABORT":
        updated = update_receipt(
            receipt_path, receipt, "FAILED", "ABORTED_BEFORE_AUTHORITATIVE_COMMIT", actor,
            {"journal_head_digest": (current.get("journal") or {}).get("head_digest")},
        )
        final = inspect_transaction(project, txid, updated, paths, policy, repo_root, True)
        final["recovery_outcome"] = "ABORTED_BEFORE_AUTHORITATIVE_COMMIT"
        return final

    if operation == "advance" and assessment == "ALREADY_EFFECTIVE":
        updated = update_receipt(
            receipt_path, receipt, "COMMITTED", "RECOVERED_FROM_AUTHORITATIVE_EVENT", actor,
            {"event_sequence": event.get("sequence"), "event_digest": event.get("event_digest")},
        )
        final = inspect_transaction(project, txid, updated, paths, policy, repo_root, True)
        final["recovery_outcome"] = "RECOVERED_FROM_AUTHORITATIVE_EVENT"
        return final

    if operation == "verify-result" and assessment in {"SAFE_TO_FINALIZE", "ALREADY_EFFECTIVE"}:
        # Re-enrich from the authoritative event because older failure receipts may
        # have omitted old_ledger_digest or staged_ledger on their final write.
        events = read_events(paths["journal"])
        matches = transaction_events(events, txid, expected_event_type(receipt, policy))
        auth_event = matches[0] if len(matches) == 1 else None
        enriched = enrich_from_event(receipt, auth_event)
        event_payload = (auth_event.get("payload") or {}) if auth_event else {}
        new_digest = enriched.get("new_ledger_digest") or event_payload.get("new_ledger_digest")
        old_digest = enriched.get("old_ledger_digest") or event_payload.get("old_ledger_digest")
        staged_raw = enriched.get("staged_ledger") or event_payload.get("staged_ledger")
        staged = Path(str(staged_raw)) if staged_raw else paths["transactions"] / txid / "staged-ledger.json"
        live = ledger_info(paths["ledger"])

        if assessment == "SAFE_TO_FINALIZE":
            if not old_digest or live.get("digest") != old_digest:
                current["assessment"] = "MANUAL_REVIEW"
                current["blockers"] = ["LIVE_LEDGER_PRECONDITION_CHANGED_DURING_RECOVERY"]
                return current
            if not new_digest:
                current["assessment"] = "MANUAL_REVIEW"
                current["blockers"] = ["EXPECTED_NEW_LEDGER_DIGEST_MISSING"]
                return current
            ok, detail = finalize_ledger(paths["ledger"], staged, str(new_digest))
            if not ok:
                current["assessment"] = "MANUAL_REVIEW"
                current["blockers"] = [detail]
                return current
            outcome = "RECOVERED_LEDGER_FINALIZATION"
        else:
            outcome = "LEDGER_ALREADY_FINALIZED"

        updated = update_receipt(
            receipt_path, enriched, "COMMITTED", outcome, actor,
            {"event_sequence": event.get("sequence"), "event_digest": event.get("event_digest"),
             "old_ledger_digest": old_digest, "new_ledger_digest": new_digest,
             "staged_ledger": str(staged)},
        )
        final = inspect_transaction(project, txid, updated, paths, policy, repo_root, True)
        final["recovery_outcome"] = outcome
        return final

    current["assessment"] = "MANUAL_REVIEW"
    current["blockers"] = [f"RECOVERY_STATE_NOT_APPLICABLE:{operation}:{assessment}"]
    return current


def list_transactions(project: str, paths: dict[str, Path], policy: dict[str, Any]) -> dict[str, Any]:
    closed = set(policy.get("closed_statuses") or [])
    items: list[dict[str, Any]] = []
    if paths["transactions"].exists():
        for receipt_file in sorted(paths["transactions"].glob("*/receipt.json")):
            try:
                receipt = load(receipt_file)
                status = str(receipt.get("status") or "UNKNOWN")
                items.append({
                    "transaction_id": receipt.get("transaction_id") or receipt_file.parent.name,
                    "operation": receipt.get("operation"),
                    "status": status,
                    "blocking": status not in closed,
                    "updated_at": receipt.get("updated_at"),
                    "recovery_outcome": receipt.get("recovery_outcome"),
                    "receipt": str(receipt_file),
                })
            except SystemExit as exc:
                items.append({
                    "transaction_id": receipt_file.parent.name,
                    "operation": None,
                    "status": "INVALID",
                    "blocking": True,
                    "updated_at": None,
                    "recovery_outcome": None,
                    "receipt": str(receipt_file),
                    "error": str(exc),
                })
    return {
        "schema": "chacha.dev/transaction-list/v1",
        "project": project,
        "observed_at": now_iso(),
        "transactions": items,
        "summary": {
            "count": len(items),
            "blocking": sum(bool(item.get("blocking")) for item in items),
            "closed": sum(not bool(item.get("blocking")) for item in items),
        },
    }


def render(value: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(value, indent=2, ensure_ascii=False))
        return
    if value.get("schema") == "chacha.dev/transaction-list/v1":
        print(f"PROJECT={value.get('project')}")
        print(f"TRANSACTIONS={value.get('summary', {}).get('count', 0)}")
        print(f"BLOCKING={value.get('summary', {}).get('blocking', 0)}")
        for item in value.get("transactions") or []:
            print(f"TRANSACTION={item.get('transaction_id')}:{item.get('operation')}:{item.get('status')}:blocking={str(item.get('blocking')).lower()}")
        return
    print(f"PROJECT={value.get('project')}")
    print(f"TRANSACTION_ID={value.get('transaction_id')}")
    print(f"OPERATION={value.get('operation')}")
    print(f"RECEIPT_STATUS={value.get('receipt_status')}")
    print(f"ASSESSMENT={value.get('assessment')}")
    print(f"RECOVERY_OUTCOME={value.get('recovery_outcome')}")
    for action in value.get("actions") or []:
        print(f"ACTION={action}")
    for blocker in value.get("blockers") or []:
        print(f"BLOCKER={blocker}")


def main() -> int:
    parser = argparse.ArgumentParser(description="ChaCha DEV HUB transaction recovery and reconciliation")
    parser.add_argument("--policy", required=True, type=Path)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--json", action="store_true")
    sub = parser.add_subparsers(dest="cmd", required=True)

    tx_list = sub.add_parser("list")
    tx_list.add_argument("--project", required=True)

    inspect = sub.add_parser("inspect")
    inspect.add_argument("--project", required=True)
    inspect.add_argument("--transaction-id", required=True)
    inspect.add_argument("--report", type=Path)

    recover = sub.add_parser("recover")
    recover.add_argument("--project", required=True)
    recover.add_argument("--transaction-id", required=True)
    recover.add_argument("--actor", default="recovery-engineer")
    recover.add_argument("--apply", action="store_true")
    recover.add_argument("--report", type=Path)

    args = parser.parse_args()
    policy = load(args.policy)
    if policy.get("schema") != POLICY_SCHEMA:
        raise SystemExit(f"POLICY_SCHEMA_INVALID={policy.get('schema')}")
    paths = runtime_paths(policy, args.project)

    if args.cmd == "list":
        value = list_transactions(args.project, paths, policy)
        render(value, args.json)
        return 0

    receipt_path, receipt = load_receipt(paths, args.project, args.transaction_id)
    if args.cmd == "inspect":
        value = inspect_transaction(args.project, args.transaction_id, receipt, paths, policy, args.repo_root, False)
    elif not args.apply:
        value = inspect_transaction(args.project, args.transaction_id, receipt, paths, policy, args.repo_root, False)
        if value.get("assessment") not in {"TERMINAL", "INVALID", "MANUAL_REVIEW"}:
            value["actions"] = list(value.get("actions") or []) + ["re-run with --apply to perform permitted recovery"]
    else:
        with project_lock(paths["lock"]):
            receipt_path, receipt = load_receipt(paths, args.project, args.transaction_id)
            value = apply_recovery(args.project, args.transaction_id, receipt_path, receipt,
                                   paths, policy, args.repo_root, args.actor)

    if getattr(args, "report", None):
        atomic_json(args.report, value)
    render(value, args.json)
    return 0 if not value.get("blockers") else 2


if __name__ == "__main__":
    raise SystemExit(main())
