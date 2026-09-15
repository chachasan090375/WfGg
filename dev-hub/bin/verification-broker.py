#!/usr/bin/env python3
"""ChaCha DEV HUB Independent Verification Broker V1.

Verifies an UNVERIFIED Task Result against its Task Graph contract and evidence.
It never executes the task itself and never performs human verification.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TASK_RESULT_SCHEMA = "chacha.dev/task-result/v1"
TASK_GRAPH_SCHEMA = "chacha.dev/task-graph/v1"
POLICY_SCHEMA = "chacha.dev/verification-broker/v1"
REPORT_SCHEMA = "chacha.dev/verification-report/v1"


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


def save(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def canonical_digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def file_digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def find_task(graph: dict[str, Any], task_id: str) -> dict[str, Any]:
    for task in graph.get("tasks") or []:
        if isinstance(task, dict) and task.get("id") == task_id:
            return task
    raise SystemExit(f"TASK_NOT_IN_GRAPH={task_id}")


def add(checks: list[dict[str, str]], cid: str, status: str, detail: str = "") -> None:
    checks.append({"id": cid, "status": status, "detail": detail})


def verify_evidence(result: dict[str, Any], policy: dict[str, Any], checks: list[dict[str, str]]) -> bool:
    evidence = result.get("evidence") or []
    if not evidence:
        add(checks, "evidence-present", "FAIL", "no evidence entries")
        return False
    add(checks, "evidence-present", "PASS", f"count={len(evidence)}")
    external_needs_check = False
    for idx, item in enumerate(evidence):
        if not isinstance(item, dict):
            add(checks, f"evidence-{idx}", "FAIL", "entry is not an object")
            continue
        source = str(item.get("source") or "")
        declared = str(item.get("digest") or "")
        if not source or not declared.startswith("sha256:"):
            add(checks, f"evidence-{idx}", "FAIL", "source/digest missing or unsupported")
            continue
        p = Path(source)
        if p.is_absolute() and p.exists() and p.is_file():
            actual = file_digest(p)
            if actual == declared:
                add(checks, f"evidence-{idx}", "PASS", f"digest matched {source}")
            else:
                add(checks, f"evidence-{idx}", "FAIL", f"digest mismatch {source}")
        elif p.is_absolute():
            add(checks, f"evidence-{idx}", "FAIL", f"local source missing {source}")
        else:
            external_needs_check = True
            add(checks, f"evidence-{idx}", "NEEDS_CHECK", f"external/non-local source {source}")
    return external_needs_check


def verify_outputs(task: dict[str, Any], result: dict[str, Any], checks: list[dict[str, str]]) -> None:
    declared = {(x.get("type"), x.get("id")) for x in task.get("outputs") or [] if isinstance(x, dict)}
    actual = {(x.get("type"), x.get("id")) for x in result.get("outputs") or [] if isinstance(x, dict)}
    undeclared = sorted(actual - declared)
    missing = sorted(declared - actual)
    if undeclared:
        add(checks, "outputs-declared", "FAIL", f"undeclared={undeclared}")
    elif missing:
        add(checks, "outputs-declared", "FAIL", f"missing={missing}")
    else:
        add(checks, "outputs-declared", "PASS", "task output contract matched")


def choose_status(checks: list[dict[str, str]], required_mode: str, method: str, execution_status: str) -> str:
    if execution_status in {"FAILED", "BLOCKED"}:
        return "REJECTED"
    if any(c["status"] == "FAIL" for c in checks):
        return "REJECTED"
    if required_mode == "human" and method != "human":
        return "NEEDS_INDEPENDENT_CHECK"
    if any(c["status"] == "NEEDS_CHECK" for c in checks):
        return "NEEDS_INDEPENDENT_CHECK"
    return "VERIFIED"


def build_verified_result(source: dict[str, Any], report: dict[str, Any]) -> dict[str, Any] | None:
    if report.get("status") != "VERIFIED":
        return None
    out = deepcopy(source)
    out["verification"] = {
        "status": "VERIFIED",
        "method": report.get("method"),
        "verifier": report.get("verifier"),
        "observed_at": report.get("observed_at"),
        "notes": "Verified by independent verification broker/report.",
    }
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--result", required=True, type=Path)
    parser.add_argument("--graph", required=True, type=Path)
    parser.add_argument("--policy", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--verified-result", type=Path)
    parser.add_argument("--verifier", default="verification-broker")
    parser.add_argument("--method", choices=["machine", "independent-agent", "human"], default="machine")
    args = parser.parse_args()

    result, graph, policy = load(args.result), load(args.graph), load(args.policy)
    if result.get("schema") != TASK_RESULT_SCHEMA:
        raise SystemExit(f"RESULT_SCHEMA_INVALID={result.get('schema')}")
    if graph.get("schema") != TASK_GRAPH_SCHEMA:
        raise SystemExit(f"GRAPH_SCHEMA_INVALID={graph.get('schema')}")
    if policy.get("schema") != POLICY_SCHEMA:
        raise SystemExit(f"POLICY_SCHEMA_INVALID={policy.get('schema')}")
    if result.get("project") != graph.get("project"):
        raise SystemExit("PROJECT_MISMATCH")

    task = find_task(graph, str(result.get("task_id")))
    producer = str(result.get("producer") or "")
    required_mode = str(((task.get("verification") or {}).get("mode")) or "machine-or-human")
    checks: list[dict[str, str]] = []

    if not producer:
        add(checks, "producer-present", "FAIL", "producer missing")
    else:
        add(checks, "producer-present", "PASS", producer)
    if args.verifier == producer:
        add(checks, "independent-verifier", "FAIL", "verifier equals producer")
    else:
        add(checks, "independent-verifier", "PASS", f"producer={producer}; verifier={args.verifier}")

    if required_mode == "human" and args.method != "human":
        add(checks, "verification-mode", "NEEDS_CHECK", "human verification required")
    elif required_mode == "machine" and args.method != "machine":
        add(checks, "verification-mode", "FAIL", f"machine required, got {args.method}")
    elif required_mode == "independent-agent" and args.method not in {"independent-agent", "human"}:
        add(checks, "verification-mode", "NEEDS_CHECK", f"independent-agent/human required, got {args.method}")
    else:
        add(checks, "verification-mode", "PASS", required_mode)

    verify_outputs(task, result, checks)
    verify_evidence(result, policy, checks)
    report_status = choose_status(checks, required_mode, args.method, str(result.get("status")))
    observed = now_iso()
    report: dict[str, Any] = {
        "schema": REPORT_SCHEMA,
        "project": result.get("project"),
        "task_id": result.get("task_id"),
        "verifier": args.verifier,
        "method": args.method,
        "status": report_status,
        "observed_at": observed,
        "source_result_digest": canonical_digest(result),
        "checks": checks,
        "notes": [],
        "verified_task_result": None,
    }
    verified = build_verified_result(result, report)
    report["verified_task_result"] = verified
    save(args.report, report)
    if verified is not None and args.verified_result:
        save(args.verified_result, verified)
        print(f"VERIFIED_TASK_RESULT={args.verified_result}")
    print(f"VERIFICATION_REPORT={args.report}")
    print(f"VERIFICATION_STATUS={report_status}")
    print(f"CHECKS={len(checks)}")
    if report_status != "VERIFIED":
        raise SystemExit(3)


if __name__ == "__main__":
    main()
