#!/usr/bin/env python3
"""ChaCha DEV HUB Evidence Collector V1.

Consumes task results, verifies that they belong to a generated Task Graph and
writes only admissible evidence into the lifecycle Evidence Ledger. A producer
claim is never enough to create OK evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

GRAPH_SCHEMA = "chacha.dev/task-graph/v1"
RESULT_SCHEMA = "chacha.dev/task-result/v1"
LEDGER_SCHEMA = "chacha.dev/evidence-ledger/v1"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit(f"FILE_NOT_FOUND={path}")
    except json.JSONDecodeError as exc:
        raise SystemExit(f"JSON_INVALID={path}:{exc.lineno}:{exc.colno}:{exc.msg}")
    if not isinstance(value, dict):
        raise SystemExit(f"JSON_ROOT_NOT_OBJECT={path}")
    return value


def save_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def init_ledger(project: str) -> dict[str, Any]:
    return {
        "schema": LEDGER_SCHEMA,
        "project": project,
        "updated_at": now_iso(),
        "artifacts": {},
        "gates": {},
        "approvals": {},
        "risk_acceptances": [],
        "history": [],
    }


def task_for(graph: dict[str, Any], task_id: str) -> dict[str, Any]:
    for item in graph.get("tasks") or []:
        if isinstance(item, dict) and item.get("id") == task_id:
            return item
    raise SystemExit(f"TASK_NOT_IN_GRAPH={task_id}")


def validate_result(graph: dict[str, Any], task: dict[str, Any], result: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if graph.get("schema") != GRAPH_SCHEMA:
        errors.append(f"GRAPH_SCHEMA_INVALID:{graph.get('schema')}")
    if result.get("schema") != RESULT_SCHEMA:
        errors.append(f"RESULT_SCHEMA_INVALID:{result.get('schema')}")
    if result.get("project") != graph.get("project"):
        errors.append("PROJECT_MISMATCH")
    if result.get("task_id") != task.get("id"):
        errors.append("TASK_ID_MISMATCH")

    verification = result.get("verification") or {}
    mode = verification.get("method")
    verifier = verification.get("verifier")
    producer = result.get("producer")
    required_mode = ((task.get("verification") or {}).get("mode"))

    if result.get("status") == "OK":
        if verification.get("status") != "VERIFIED":
            errors.append("SUCCESS_NOT_VERIFIED")
        if not result.get("evidence"):
            errors.append("SUCCESS_WITHOUT_EVIDENCE")
        if not verifier:
            errors.append("VERIFIER_MISSING")
        if task.get("kind") != "approval" and verifier == producer:
            errors.append("SELF_CERTIFICATION_FORBIDDEN")
        if required_mode == "human" and mode != "human":
            errors.append(f"VERIFICATION_MODE_REQUIRED:human:actual={mode}")
        if required_mode == "machine" and mode != "machine":
            errors.append(f"VERIFICATION_MODE_REQUIRED:machine:actual={mode}")
        if required_mode == "independent-agent" and mode not in {"independent-agent", "human"}:
            errors.append(f"VERIFICATION_MODE_REQUIRED:independent-agent:actual={mode}")
        if required_mode == "machine-or-human" and mode not in {"machine", "human", "independent-agent"}:
            errors.append(f"VERIFICATION_MODE_INVALID:{mode}")

    declared = {(o.get("type"), o.get("id")) for o in task.get("outputs") or [] if isinstance(o, dict)}
    for output in result.get("outputs") or []:
        key = (output.get("type"), output.get("id"))
        if key not in declared:
            errors.append(f"UNDECLARED_OUTPUT:{key[0]}:{key[1]}")
        if output.get("status") == "NOT_APPLICABLE" and not output.get("reason"):
            errors.append(f"NOT_APPLICABLE_REASON_REQUIRED:{key[0]}:{key[1]}")
    return sorted(set(errors))


def normalized_status(result: dict[str, Any], requested: str) -> str:
    verification = result.get("verification") or {}
    if requested in {"APPROVED", "REJECTED"}:
        return requested
    if result.get("status") != "OK" or verification.get("status") != "VERIFIED":
        return "UNVERIFIED"
    return requested if requested in {"OK", "PARTIAL", "MISSING", "NOT_APPLICABLE"} else "UNVERIFIED"


def ingest(graph: dict[str, Any], ledger: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    task = task_for(graph, str(result.get("task_id")))
    errors = validate_result(graph, task, result)
    if errors:
        raise SystemExit("RESULT_REJECTED=" + ",".join(errors))

    result_digest = digest(result)
    verification = result.get("verification") or {}
    evidence_sources = [str(e.get("source")) for e in result.get("evidence") or [] if isinstance(e, dict) and e.get("source")]
    source = ";".join(evidence_sources) or "task-result"
    observed = result.get("observed_at") or now_iso()
    producer = str(result.get("producer") or "unknown")
    verifier = str(verification.get("verifier") or "unknown")
    method = str(verification.get("method") or "none")

    changes: list[str] = []
    for output in result.get("outputs") or []:
        otype = output.get("type")
        oid = output.get("id")
        requested = output.get("status")
        if not otype or not oid:
            continue

        if otype == "approval":
            if method != "human" or verification.get("status") != "VERIFIED":
                raise SystemExit(f"APPROVAL_REQUIRES_VERIFIED_HUMAN={oid}")
            if requested not in {"APPROVED", "REJECTED"}:
                raise SystemExit(f"APPROVAL_STATUS_INVALID={oid}:{requested}")
            ledger.setdefault("approvals", {})[oid] = {
                "status": requested,
                "actor": verifier,
                "observed_at": observed,
                "digest": result_digest,
                "task_id": task.get("id"),
                "summary": result.get("summary", ""),
            }
            changes.append(f"approval:{oid}:{requested}")
            continue

        status = normalized_status(result, str(requested))
        record = {
            "status": status,
            "source": source,
            "observed_at": observed,
            "digest": result_digest,
            "producer": producer,
            "verifier": verifier,
            "verification_method": method,
            "task_id": task.get("id"),
            "summary": result.get("summary", ""),
        }
        if output.get("reason"):
            record["reason"] = output.get("reason")
        bucket = "artifacts" if otype == "artifact" else "gates"
        ledger.setdefault(bucket, {})[oid] = record
        changes.append(f"{otype}:{oid}:{status}")

    ledger["schema"] = LEDGER_SCHEMA
    ledger["project"] = graph.get("project")
    ledger["updated_at"] = now_iso()
    ledger.setdefault("risk_acceptances", [])
    ledger.setdefault("history", []).append({
        "event": "task-result-ingested",
        "task_id": task.get("id"),
        "producer": producer,
        "verifier": verifier,
        "verification_method": method,
        "result_status": result.get("status"),
        "result_digest": result_digest,
        "changes": changes,
        "observed_at": now_iso(),
    })
    return ledger


def summary(ledger: dict[str, Any]) -> dict[str, Any]:
    return {
        "project": ledger.get("project"),
        "artifacts": len(ledger.get("artifacts") or {}),
        "gates": len(ledger.get("gates") or {}),
        "approvals": len(ledger.get("approvals") or {}),
        "verified_artifacts": sum(1 for x in (ledger.get("artifacts") or {}).values() if x.get("status") == "OK"),
        "ok_gates": sum(1 for x in (ledger.get("gates") or {}).values() if x.get("status") == "OK"),
        "unverified": sum(1 for bucket in ("artifacts", "gates") for x in (ledger.get(bucket) or {}).values() if x.get("status") == "UNVERIFIED"),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init")
    p_init.add_argument("--project", required=True)
    p_init.add_argument("--ledger", required=True, type=Path)

    p_ingest = sub.add_parser("ingest")
    p_ingest.add_argument("--graph", required=True, type=Path)
    p_ingest.add_argument("--result", required=True, type=Path)
    p_ingest.add_argument("--ledger", required=True, type=Path)

    p_summary = sub.add_parser("summary")
    p_summary.add_argument("--ledger", required=True, type=Path)

    args = parser.parse_args()
    if args.cmd == "init":
        if args.ledger.exists():
            raise SystemExit(f"LEDGER_ALREADY_EXISTS={args.ledger}")
        save_json(args.ledger, init_ledger(args.project))
        print(f"EVIDENCE_LEDGER_INIT=OK:{args.ledger}")
        return

    ledger = load_json(args.ledger)
    if ledger.get("schema") != LEDGER_SCHEMA:
        raise SystemExit(f"LEDGER_SCHEMA_INVALID={ledger.get('schema')}")

    if args.cmd == "summary":
        print(json.dumps(summary(ledger), indent=2, ensure_ascii=False))
        return

    graph = load_json(args.graph)
    result = load_json(args.result)
    updated = ingest(graph, ledger, result)
    save_json(args.ledger, updated)
    print("EVIDENCE_INGEST=OK")
    print(json.dumps(summary(updated), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
