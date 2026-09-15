#!/usr/bin/env python3
"""ChaCha DEV HUB Transaction Recovery & Reconciliation Engine V1.

Inspects incomplete Project Control transactions and reconciles derived state
with the authoritative hash-chained audit journal. Recovery is forward-only:
audit events are never deleted, rewritten, truncated, or rolled back.
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
STATE_SCHEMA = "chacha.dev/control-plane-state/v1"
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
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
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
        if os.path.exists(tmp):
            os.unlink(tmp)


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def digest_obj(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical(value)).hexdigest()


def file_digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def resolve_repo(repo_root: Path, configured: str) -> Path:
    p = Path(configured)
    return p if p.is_absolute() else repo_root / p


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
                item = json.loads(line)
            except json.JSONDecodeError as exc:
                raise SystemExit(f"JOURNAL_JSON_INVALID=line:{lineno}:{exc.msg}")
            if not isinstance(item, dict):
                raise SystemExit(f"JOURNAL_EVENT_NOT_OBJECT=line:{lineno}")
            events.append(item)
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
        declared = event.get("event_digest")
        unsigned = dict(event)
        unsigned.pop("event_digest", None)
        actual = digest_obj(unsigned)
        if declared != actual:
            errors.append(f"DIGEST:{seq}")
        previous = declared
        expected_sequence += 1
    return sorted(set(errors))


def transaction_events(events: list[dict[str, Any]], txid: str, expected_type: str | None) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for event in events:
        payload = event.get("payload") or {}
        if not isinstance(payload, dict) or payload.get("transaction_id") != txid:
            continue
        if expected_type and event.get("event_type") != expected_type:
            continue
        matches.append(event)
    return matches


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


def projection_status(project: str, paths: dict[str, Path], policy: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    rc, out, err = store_call(project, "verify", policy, repo_root, paths["state_root"])
    state: dict[str, Any] | None = None
    if paths["state"].exists():
        try:
            state = load(paths["state"])
        except SystemExit:
            state = None
    return {
        "verified": rc == 0,
        "verify_stdout": out.strip(),
        "verify_stderr": err.strip(),
        "version": state.get("version") if state else None,
        "head_digest": state.get("last_event_digest") if state else None,
        "stage": (((state or {}).get("state") or {}).get("lifecycle") or {}).get("stage") if state else None,
    }


def ledger_info(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"exists": False, "digest": None, "schema": None}
    try:
        value = load(path)
    except SystemExit as exc:
        return {"exists": True, "digest": None, "schema": None, "error": str(exc)}
    return {"exists": True, "digest": digest_obj(value), "schema": value.get("schema")}


def receipt_path(paths: dict[str, Path], txid: str) -> Path:
    return paths["transactions"] / txid / "receipt.json"


def load_receipt(paths: dict[str, Path], txid: str, project: str) -> tuple[Path, dict[str, Any]]:
    path = receipt_path(paths, txid)
    receipt = load(path)
    if receipt.get("schema") != RECEIPT_SCHEMA:
        raise SystemExit(f"RECEIPT_SCHEMA_INVALID={receipt.get('schema')}")
    if receipt.get("transaction_id") != txid:
        raise SystemExit("RECEIPT_TRANSACTION_ID_MISMATCH")
    if receipt.get("project") != project:
        raise SystemExit("RECEIPT_PROJECT_MISMATCH")
    return path, receipt


def update_receipt(path: Path, receipt: dict[str, Any], status: str, outcome: str, actor: str,
                   details: dict[str, Any] | None = None) -> dict[str, Any]:
    out = deepcopy(receipt)
    out["status"] = status
    out["updated_at"] = now_iso()
    out["recovery_outcome"] = outcome
    history = list(out.get("recovery_history") or [])
    history.append({
        "observed_at": out["updated_at"],
        "actor": actor,
        "status": status,
        "outcome": outcome,
        "details": details or {},
    })
    out["recovery_history"] = history
    atomic_json(path, out)
    return out


def expected_event_type(receipt: dict[str, Any], policy: dict[str, Any]) -> str | None:
    op = str(receipt.get("operation") or "")
    return (((policy.get("operations") or {}).get(op) or {}).get("authoritative_event_type"))


def assess(project: str, txid: str, receipt: dict[str, Any], paths: dict[str, Path],
           policy: dict[str, Any], repo_root: Path, apply_requested: bool) -> dict[str, Any]:
    blockers: list[str] = []
    actions: list[str] = []
    closed = set(policy.get("closed_statuses") or [])
    status = str(receipt.get("status") or "UNKNOWN")
    operation = str(receipt.get("operation") or "")

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
                      journal=journal, authoritative_event=None,
                      blockers=["MULTIPLE_AUTHORITATIVE_EVENTS_FOR_TRANSACTION"])
    if expected and not matches and all_matches:
        return report(project, txid, operation, status, "MANUAL_REVIEW", apply_requested,
                      journal=journal, authoritative_event=None,
                      blockers=["TRANSACTION_ID_FOUND_WITH_UNEXPECTED_EVENT_TYPE"])

    event = matches[0] if matches else None
    projection = projection_status(project, paths, policy, repo_root)
    ledger = ledger_info(paths["ledger"])

    if status in closed:
        return report(project, txid, operation, status, "TERMINAL", apply_requested,
                      authoritative_event=event, journal=journal, projection=projection, ledger=ledger,
                      actions=["none"])

    if operation == "advance":
        transition = str(receipt.get("transition") or "")
        target = transition.split("->", 1)[1] if "->" in transition else None
        if event is None:
            actions.append("close transaction as FAILED:ABORTED_BEFORE_AUTHORITATIVE_COMMIT")
            if not projection.get("verified"):
                actions.insert(0, "rebuild projection from valid authoritative journal")
            return report(project, txid, operation, status,
                          "REPAIRABLE" if not projection.get("verified") else "SAFE_TO_ABORT",
                          apply_requested, authoritative_event=None, journal=journal,
                          projection=projection, ledger=ledger, actions=actions)
        payload = event.get("payload") or {}
        event_transition = payload.get("transition")
        if transition and event_transition and transition != event_transition:
            blockers.append("ADVANCE_TRANSITION_MISMATCH")
        if target and payload.get("to") and target != payload.get("to"):
            blockers.append("ADVANCE_TARGET_MISMATCH")
        if blockers:
            return report(project, txid, operation, status, "MANUAL_REVIEW", apply_requested,
                          authoritative_event=event, journal=journal, projection=projection,
                          ledger=ledger, blockers=blockers)
        if not projection.get("verified"):
            actions.append("rebuild projection from valid authoritative journal")
            actions.append("close receipt as COMMITTED:RECOVERED_FROM_AUTHORITATIVE_EVENT")
            return report(project, txid, operation, status, "REPAIRABLE", apply_requested,
                          authoritative_event=event, journal=journal, projection=projection,
                          ledger=ledger, actions=actions)
        actions.append("close receipt as COMMITTED:AUTHORITATIVE_EVENT_CONFIRMED")
        return report(project, txid, operation, status, "ALREADY_EFFECTIVE", apply_requested,
                      authoritative_event=event, journal=journal, projection=projection,
                      ledger=ledger, actions=actions)

    if operation == "verify-result":
        old_digest = receipt.get("old_ledger_digest")
        new_digest = receipt.get("new_ledger_digest")
        txdir = paths["transactions"] / txid
        staged_raw = receipt.get("staged_ledger")
        if not staged_raw and event:
            staged_raw = ((event.get("payload") or {}).get("staged_ledger"))
        staged = Path(str(staged_raw)) if staged_raw else txdir / "staged-ledger.json"
        staged_info = ledger_info(staged)
        ledger["staged_path"] = str(staged)
        ledger["staged_exists"] = staged_info.get("exists")
        ledger["staged_digest"] = staged_info.get("digest")
        ledger["expected_old_digest"] = old_digest
        ledger["expected_new_digest"] = new_digest

        if event is None:
            if new_digest and ledger.get("digest") == new_digest:
                return report(project, txid, operation, status, "MANUAL_REVIEW", apply_requested,
                              journal=journal, projection=projection, ledger=ledger,
                              blockers=["LEDGER_CHANGED_WITHOUT_AUTHORITATIVE_EVIDENCE_EVENT"])
            if old_digest and ledger.get("digest") not in {old_digest, None}:
                return report(project, txid, operation, status, "MANUAL_REVIEW", apply_requested,
                              journal=journal, projection=projection, ledger=ledger,
                              blockers=["LIVE_LEDGER_DIVERGED_FROM_TRANSACTION_PRECONDITION"])
            if not projection.get("verified"):
                actions.append("rebuild projection from valid authoritative journal")
            actions.append("close transaction as FAILED:ABORTED_BEFORE_AUTHORITATIVE_COMMIT")
            return report(project, txid, operation, status,
                          "REPAIRABLE" if not projection.get("verified") else "SAFE_TO_ABORT",
                          apply_requested, journal=journal, projection=projection,
                          ledger=ledger, actions=actions)

        payload = event.get("payload") or {}
        event_new = payload.get("new_ledger_digest")
        if new_digest and event_new and new_digest != event_new:
            blockers.append("EVIDENCE_EVENT_LEDGER_DIGEST_MISMATCH")
        if new_digest and staged_info.get("digest") and new_digest != staged_info.get("digest"):
            blockers.append("STAGED_LEDGER_DIGEST_MISMATCH")
        if ledger.get("schema") not in {LEDGER_SCHEMA, None}:
            blockers.append("LIVE_LEDGER_SCHEMA_INVALID")
        if blockers:
            return report(project, txid, operation, status, "MANUAL_REVIEW", apply_requested,
                          authoritative_event=event, journal=journal, projection=projection,
                          ledger=ledger, blockers=blockers)

        live_digest = ledger.get("digest")
        if new_digest and live_digest == new_digest:
            if not projection.get("verified"):
                actions.append("rebuild projection from valid authoritative journal")
                actions.append("close receipt as COMMITTED:LEDGER_ALREADY_FINALIZED")
                return report(project, txid, operation, status, "REPAIRABLE", apply_requested,
                              authoritative_event=event, journal=journal, projection=projection,
                              ledger=ledger, actions=actions)
            actions.append("close receipt as COMMITTED:LEDGER_ALREADY_FINALIZED")
            return report(project, txid, operation, status, "ALREADY_EFFECTIVE", apply_requested,
                          authoritative_event=event, journal=journal, projection=projection,
                          ledger=ledger, actions=actions)

        if old_digest and live_digest == old_digest:
            if not staged_info.get("exists"):
                return report(project, txid, operation, status, "MANUAL_REVIEW", apply_requested,
                              authoritative_event=event, journal=journal, projection=projection,
                              ledger=ledger, blockers=["STAGED_LEDGER_MISSING"])
            if not new_digest or staged_info.get("digest") != new_digest:
                return report(project, txid, operation, status, "MANUAL_REVIEW", apply_requested,
                              authoritative_event=event, journal=journal, projection=projection,
                              ledger=ledger, blockers=["STAGED_LEDGER_NOT_TRUSTWORTHY"])
            if not projection.get("verified"):
                actions.append("rebuild projection from valid authoritative journal")
            actions.append("atomically finalize verified staged ledger")
            actions.append("close receipt as COMMITTED:RECOVERED_LEDGER_FINALIZATION")
            return report(project, txid, operation, status, "SAFE_TO_FINALIZE", apply_requested,
                          authoritative_event=event, journal=journal, projection=projection,
                          ledger=ledger, actions=actions)

        return report(project, txid, operation, status, "MANUAL_REVIEW", apply_requested,
                      authoritative_event=event, journal=journal, projection=projection,
                      ledger=ledger, blockers=["LIVE_LEDGER_DIGEST_IS_NEITHER_EXPECTED_OLD_NOR_NEW"])

    return report(project, txid, operation, status, "MANUAL_REVIEW", apply_requested,
                  authoritative_event=event, journal=journal, projection=projection,
                  ledger=ledger, blockers=[f"RECOVERY_OPERATION_UNSUPPORTED:{operation}"])


def report(project: str, txid: str, operation: str, receipt_status: str, assessment: str,
           apply_requested: bool, authoritative_event: dict[str, Any] | None = None,
           journal: dict[str, Any] | None = None, projection: dict[str, Any] | None = None,
           ledger: dict[str, Any] | None = None, actions: list[str] | None = None,
           blockers: list[str] | None = None, recovery_outcome: str | None = None) -> dict[str, Any]:
    event_summary = None
    if authoritative_event:
        event_summary = {
            "sequence": authoritative_event.get("sequence"),
            "event_id": authoritative_event.get("event_id"),
            "event_type": authoritative_event.get("event_type"),
            "event_digest": authoritative_event.get("event_digest"),
            "observed_at": authoritative_event.get("observed_at"),
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
        "recovery_outcome": recovery_outcome,
        "observed_at": now_iso(),
    }


def rebuild_projection(project: str, paths: dict[str, Path], policy: dict[str, Any], repo_root: Path) -> tuple[bool, str]:
    rc, out, err = store_call(project, "rebuild", policy, repo_root, paths["state_root"])
    if rc != 0:
        return False, (err or out).strip()
    rc2, out2, err2 = store_call(project, "verify", policy, repo_root, paths["state_root"])
    if rc2 != 0:
        return False, (err2 or out2).strip()
    return True, out2.strip()


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
        with tmp.open("rb") as fh:
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
    final_value = load(live)
    if digest_obj(final_value) != expected_digest:
        return False, "FINAL_LEDGER_DIGEST_MISMATCH"
    return True, "LEDGER_FINALIZED"


def apply_recovery(project: str, txid: str, receipt_path_value: Path, receipt: dict[str, Any],
                   initial: dict[str, Any], paths: dict[str, Path], policy: dict[str, Any],
                   repo_root: Path, actor: str) -> dict[str, Any]:
    assessment = initial.get("assessment")
    operation = str(receipt.get("operation") or "")
    if assessment in {"TERMINAL", "INVALID", "MANUAL_REVIEW"}:
        return {**initial, "apply_requested": True}

    # Journal validity was already established by assessment; re-read under lock
    # before applying any repair to prevent stale recovery decisions.
    events = read_events(paths["journal"])
    errors = verify_chain(events, project)
    if errors:
        return report(project, txid, operation, str(receipt.get("status")), "INVALID", True,
                      journal={"valid": False, "errors": errors}, blockers=["AUDIT_JOURNAL_INVALID", *errors])
    expected = expected_event_type(receipt, policy)
    matches = transaction_events(events, txid, expected)
    event = matches[0] if len(matches) == 1 else None

    projection = projection_status(project, paths, policy, repo_root)
    if not projection.get("verified"):
        ok, detail = rebuild_projection(project, paths, policy, repo_root)
        if not ok:
            return report(project, txid, operation, str(receipt.get("status")), "MANUAL_REVIEW", True,
                          authoritative_event=event,
                          journal={"valid": True, "event_count": len(events), "errors": []},
                          projection=projection, ledger=ledger_info(paths["ledger"]),
                          blockers=["PROJECTION_REBUILD_FAILED:" + detail])

    if operation == "advance":
        if event is None:
            updated = update_receipt(
                receipt_path_value, receipt, "FAILED", "ABORTED_BEFORE_AUTHORITATIVE_COMMIT", actor,
                {"journal_head_digest": events[-1].get("event_digest") if events else None},
            )
            final = assess(project, txid, updated, paths, policy, repo_root, True)
            final["recovery_outcome"] = "ABORTED_BEFORE_AUTHORITATIVE_COMMIT"
            return final
        updated = update_receipt(
            receipt_path_value, receipt, "COMMITTED", "RECOVERED_FROM_AUTHORITATIVE_EVENT", actor,
            {"event_sequence": event.get("sequence"), "event_digest": event.get("event_digest")},
        )
        final = assess(project, txid, updated, paths, policy, repo_root, True)
        final["recovery_outcome"] = "RECOVERED_FROM_AUTHORITATIVE_EVENT"
        return final

    if operation == "verify-result":
        if event is None:
            live = ledger_info(paths["ledger"])
            old_digest = receipt.get("old_ledger_digest")
            if old_digest and live.get("digest") not in {old_digest, None}:
                return report(project, txid, operation, str(receipt.get("status")), "MANUAL_REVIEW", True,
                              journal={"valid": True, "event_count": len(events), "errors": []},
                              projection=projection_status(project, paths, policy, repo_root), ledger=live,
                              blockers=["LIVE_LEDGER_DIVERGED_FROM_TRANSACTION_PRECONDITION"])
            updated = update_receipt(
                receipt_path_value, receipt, "FAILED", "ABORTED_BEFORE_AUTHORITATIVE_COMMIT", actor,
                {"ledger_digest": live.get("digest")},
            )
            final = assess(project, txid, updated, paths, policy, repo_root, True)
            final["recovery_outcome"] = "ABORTED_BEFORE_AUTHORITATIVE_COMMIT"
            return final

        new_digest = str(receipt.get("new_ledger_digest") or ((event.get("payload") or {}).get("new_ledger_digest") or ""))
        old_digest = receipt.get("old_ledger_digest")
        txdir = paths["transactions"] / txid
        staged_raw = receipt.get("staged_ledger") or ((event.get("payload") or {}).get("staged_ledger"))
        staged = Path(str(staged_raw)) if staged_raw else txdir / "staged-ledger.json"
        live = ledger_info(paths["ledger"])
        if live.get("digest") == new_digest and new_digest:
            updated = update_receipt(
                receipt_path_value, receipt, "COMMITTED", "LEDGER_ALREADY_FINALIZED", actor,
                {"event_sequence": event.get("sequence"), "event_digest": event.get("event_digest"),
                 "ledger_digest": new_digest},
            )
            final = assess(project, txid, updated, paths, policy, repo_root, True)
            final["recovery_outcome"] = "LEDGER_ALREADY_FINALIZED"
            return final
        if not old_digest or live.get("digest") != old_digest:
            return report(project, txid, operation, str(receipt.get("status")), "MANUAL_REVIEW", True,
                          authoritative_event=event,
                          journal={"valid": True, "event_count": len(events), "errors": []},
                          projection=projection_status(project, paths, policy, repo_root), ledger=live,
                          blockers=["LIVE_LEDGER_DIGEST_IS_NEITHER_EXPECTED_OLD_NOR_NEW"])
        if not new_digest:
            return report(project, txid, operation, str(receipt.get("status")), "MANUAL_REVIEW", True,
                          authoritative_event=event,
                          journal={"valid": True, "event_count": len(events), "errors": []},
                          projection=projection_status(project, paths, policy, repo_root), ledger=live,
                          blockers=["EXPECTED_NEW_LEDGER_DIGEST_MISSING"])
        ok, detail = finalize_ledger(paths["ledger"], staged, new_digest)
        if not ok:
            return report(project, txid, operation, str(receipt.get("status")), "MANUAL_REVIEW", True,
                          authoritative_event=event,
                          journal={"valid": True, "event_count": len(events), "errors": []},
                          projection=projection_status(project, paths, policy, repo_root), ledger=ledger_info(paths["ledger"]),
                          blockers=[detail])
        updated = update_receipt(
            receipt_path_value, receipt, "COMMITTED", "RECOVERED_LEDGER_FINALIZATION", actor,
            {"event_sequence": event.get("sequence"), "event_digest": event.get("event_digest"),
             "ledger_digest": new_digest, "staged_ledger": str(staged)},
        )
        final = assess(project, txid, updated, paths, policy, repo_root, True)
        final["recovery_outcome"] = "RECOVERED_LEDGER_FINALIZATION"
        return final

    return report(project, txid, operation, str(receipt.get("status")), "MANUAL_REVIEW", True,
                  authoritative_event=event,
                  journal={"valid": True, "event_count": len(events), "errors": []},
                  projection=projection_status(project, paths, policy, repo_root), ledger=ledger_info(paths["ledger"]),
                  blockers=[f"RECOVERY_OPERATION_UNSUPPORTED:{operation}"])


def list_transactions(project: str, paths: dict[str, Path], policy: dict[str, Any]) -> dict[str, Any]:
    closed = set(policy.get("closed_statuses") or [])
    items: list[dict[str, Any]] = []
    if paths["transactions"].exists():
        for receipt_file in sorted(paths["transactions"].glob("*/receipt.json")):
            try:
                value = load(receipt_file)
                status = str(value.get("status") or "UNKNOWN")
                items.append({
                    "transaction_id": value.get("transaction_id") or receipt_file.parent.name,
                    "operation": value.get("operation"),
                    "status": status,
                    "blocking": status not in closed,
                    "updated_at": value.get("updated_at"),
                    "recovery_outcome": value.get("recovery_outcome"),
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
            "blocking": sum(bool(x.get("blocking")) for x in items),
            "closed": sum(not bool(x.get("blocking")) for x in items),
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

    p_list = sub.add_parser("list")
    p_list.add_argument("--project", required=True)

    p_inspect = sub.add_parser("inspect")
    p_inspect.add_argument("--project", required=True)
    p_inspect.add_argument("--transaction-id", required=True)
    p_inspect.add_argument("--report", type=Path)

    p_recover = sub.add_parser("recover")
    p_recover.add_argument("--project", required=True)
    p_recover.add_argument("--transaction-id", required=True)
    p_recover.add_argument("--actor", default="recovery-engineer")
    p_recover.add_argument("--apply", action="store_true")
    p_recover.add_argument("--report", type=Path)

    args = parser.parse_args()
    policy = load(args.policy)
    if policy.get("schema") != POLICY_SCHEMA:
        raise SystemExit(f"POLICY_SCHEMA_INVALID={policy.get('schema')}")
    paths = runtime_paths(policy, args.project)

    if args.cmd == "list":
        value = list_transactions(args.project, paths, policy)
        render(value, args.json)
        return 0

    receipt_file, receipt = load_receipt(paths, args.transaction_id, args.project)
    if args.cmd == "inspect":
        value = assess(args.project, args.transaction_id, receipt, paths, policy, args.repo_root, False)
    else:
        initial = assess(args.project, args.transaction_id, receipt, paths, policy, args.repo_root, bool(args.apply))
        if not args.apply:
            initial["actions"] = list(initial.get("actions") or []) + ["re-run with --apply to perform permitted recovery"]
            value = initial
        else:
            with project_lock(paths["lock"]):
                # Re-read receipt after lock acquisition to avoid recovering a stale transaction snapshot.
                receipt_file, receipt = load_receipt(paths, args.transaction_id, args.project)
                refreshed = assess(args.project, args.transaction_id, receipt, paths, policy, args.repo_root, True)
                value = apply_recovery(args.project, args.transaction_id, receipt_file, receipt, refreshed,
                                       paths, policy, args.repo_root, args.actor)

    if getattr(args, "report", None):
        atomic_json(args.report, value)
    render(value, args.json)
    return 0 if not value.get("blockers") else 2


if __name__ == "__main__":
    raise SystemExit(main())
