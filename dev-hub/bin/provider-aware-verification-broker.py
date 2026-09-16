#!/usr/bin/env python3
"""ChaCha DEV HUB Provider-Aware Verification Broker V1.

Backward-compatible front door for verification-broker.py.

Without CHACHA_DEV_INDEPENDENT_RESULT it delegates byte-for-byte semantics to the
core broker. With a runner-owned independent result path, it lets the core broker
perform all ordinary result/output checks, then resolves only the external
browser-evidence NEEDS_CHECK boundary when a second provider independently
observed the same verification subject.

The independent provider never marks the source VERIFIED. Its own task-result
must remain UNVERIFIED. Only this broker emits the final VERIFIED result.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

CORE = Path(__file__).with_name("verification-broker.py")
RESULT_SCHEMA = "chacha.dev/task-result/v1"
GRAPH_SCHEMA = "chacha.dev/task-graph/v1"
REPORT_SCHEMA = "chacha.dev/verification-report/v1"
ENV_NAME = "CHACHA_DEV_INDEPENDENT_RESULT"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON_ROOT_NOT_OBJECT:{path}")
    return value


def save(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def text_digest(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def canonical_url(value: str) -> str | None:
    try:
        p = urlsplit(value)
        if p.scheme not in {"http", "https"} or not p.hostname or p.username or p.password:
            return None
        host = p.hostname.lower().rstrip(".")
        port = p.port
        default = 80 if p.scheme == "http" else 443
        netloc = host if not port or port == default else f"{host}:{port}"
        return urlunsplit((p.scheme, netloc, p.path or "/", "", ""))
    except ValueError:
        return None


def origin(value: str) -> str | None:
    url = canonical_url(value)
    if not url:
        return None
    p = urlsplit(url)
    return f"{p.scheme}://{p.netloc}"


def task_for(graph: dict[str, Any], task_id: str) -> dict[str, Any] | None:
    for task in graph.get("tasks") or []:
        if isinstance(task, dict) and task.get("id") == task_id:
            return task
    return None


def subject(task: dict[str, Any]) -> dict[str, Any] | None:
    meta = task.get("metadata") if isinstance(task.get("metadata"), dict) else {}
    value = meta.get("verification_subject")
    return value if isinstance(value, dict) else None


def fail(report_path: Path, source: dict[str, Any], verifier: str, method: str,
         checks: list[dict[str, str]], reason: str) -> int:
    checks.append({"id": "independent-observation", "status": "FAIL", "detail": reason})
    report = {
        "schema": REPORT_SCHEMA,
        "project": source.get("project"),
        "task_id": source.get("task_id"),
        "verifier": verifier,
        "method": method,
        "status": "REJECTED",
        "observed_at": now_iso(),
        "source_result_digest": digest(source),
        "checks": checks,
        "notes": [reason],
        "verified_task_result": None,
    }
    save(report_path, report)
    print(f"VERIFICATION_REPORT={report_path}")
    print("VERIFICATION_STATUS=REJECTED")
    print(f"CHECKS={len(checks)}")
    return 3


def parse() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--result", required=True, type=Path)
    p.add_argument("--graph", required=True, type=Path)
    p.add_argument("--policy", required=True, type=Path)
    p.add_argument("--report", required=True, type=Path)
    p.add_argument("--verified-result", type=Path)
    p.add_argument("--verifier", default="verification-broker")
    p.add_argument("--method", choices=["machine", "independent-agent", "human"], default="machine")
    return p.parse_args()


def delegate() -> int:
    os.execv(sys.executable, [sys.executable, str(CORE), *sys.argv[1:]])
    return 127


def main() -> int:
    independent_raw = os.environ.get(ENV_NAME, "").strip()
    if not independent_raw:
        return delegate()

    args = parse()
    source = load(args.result)
    graph = load(args.graph)
    independent_path = Path(independent_raw)
    if not independent_path.is_absolute() or not independent_path.is_file():
        return fail(args.report, source, args.verifier, args.method, [], "INDEPENDENT_RESULT_PATH_INVALID")
    independent = load(independent_path)

    if source.get("schema") != RESULT_SCHEMA or independent.get("schema") != RESULT_SCHEMA:
        return fail(args.report, source, args.verifier, args.method, [], "INDEPENDENT_RESULT_SCHEMA_INVALID")
    if graph.get("schema") != GRAPH_SCHEMA:
        return fail(args.report, source, args.verifier, args.method, [], "GRAPH_SCHEMA_INVALID")

    # Let the historical broker run first. It remains authoritative for ordinary
    # result/output/mode checks. External URL evidence is expected to remain
    # NEEDS_CHECK at this stage.
    with tempfile.TemporaryDirectory(prefix="chacha-provider-aware-broker-") as td:
        core_report_path = Path(td) / "core-report.json"
        core_verified_path = Path(td) / "core-verified.json"
        proc = subprocess.run(
            [sys.executable, str(CORE), "--result", str(args.result), "--graph", str(args.graph),
             "--policy", str(args.policy), "--report", str(core_report_path),
             "--verified-result", str(core_verified_path), "--verifier", args.verifier,
             "--method", args.method],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, shell=False, check=False,
        )
        core_report = load(core_report_path) if core_report_path.exists() else {
            "checks": [{"id": "core-broker", "status": "FAIL", "detail": proc.stderr.strip() or "core report missing"}]
        }

    checks = list(core_report.get("checks") or [])
    if any(isinstance(x, dict) and x.get("status") == "FAIL" for x in checks):
        save(args.report, core_report)
        print(f"VERIFICATION_REPORT={args.report}")
        print(f"VERIFICATION_STATUS={core_report.get('status') or 'REJECTED'}")
        print(f"CHECKS={len(checks)}")
        return 3

    if args.method != "independent-agent":
        return fail(args.report, source, args.verifier, args.method, checks, "INDEPENDENT_AGENT_METHOD_REQUIRED")
    if source.get("status") != "OK" or independent.get("status") != "OK":
        return fail(args.report, source, args.verifier, args.method, checks, "SOURCE_OR_INDEPENDENT_RESULT_NOT_OK")
    if source.get("project") != independent.get("project") or source.get("project") != graph.get("project"):
        return fail(args.report, source, args.verifier, args.method, checks, "INDEPENDENT_PROJECT_MISMATCH")
    source_producer = str(source.get("producer") or "")
    independent_producer = str(independent.get("producer") or "")
    if not source_producer or not independent_producer or source_producer == independent_producer:
        return fail(args.report, source, args.verifier, args.method, checks, "INDEPENDENT_PRODUCER_NOT_DISTINCT")
    if (source.get("verification") or {}).get("status") != "UNVERIFIED":
        return fail(args.report, source, args.verifier, args.method, checks, "SOURCE_MUST_ENTER_UNVERIFIED")
    if (independent.get("verification") or {}).get("status") != "UNVERIFIED":
        return fail(args.report, source, args.verifier, args.method, checks, "INDEPENDENT_RESULT_MUST_REMAIN_UNVERIFIED")

    source_task = task_for(graph, str(source.get("task_id") or ""))
    independent_task = task_for(graph, str(independent.get("task_id") or ""))
    if not source_task or not independent_task or source_task.get("id") == independent_task.get("id"):
        return fail(args.report, source, args.verifier, args.method, checks, "INDEPENDENT_TASK_INVALID")
    if ((source_task.get("verification") or {}).get("mode")) != "independent-agent":
        return fail(args.report, source, args.verifier, args.method, checks, "SOURCE_TASK_NOT_INDEPENDENT_AGENT_MODE")

    source_subject = subject(source_task)
    independent_subject = subject(independent_task)
    if not source_subject or source_subject != independent_subject:
        return fail(args.report, source, args.verifier, args.method, checks, "VERIFICATION_SUBJECT_MISMATCH")
    target_url = canonical_url(str(source_subject.get("target_url") or ""))
    if not target_url:
        return fail(args.report, source, args.verifier, args.method, checks, "VERIFICATION_SUBJECT_TARGET_INVALID")

    source_urls = [canonical_url(str(e.get("source") or "")) for e in source.get("evidence") or [] if isinstance(e, dict)]
    source_urls = [x for x in source_urls if x]
    if target_url not in source_urls:
        return fail(args.report, source, args.verifier, args.method, checks, "SOURCE_TARGET_NOT_OBSERVED")

    independent_details = [
        e.get("details") for e in independent.get("evidence") or []
        if isinstance(e, dict) and isinstance(e.get("details"), dict)
    ]
    target_origin = origin(target_url)
    if not any(d.get("target_origin") == target_origin for d in independent_details):
        return fail(args.report, source, args.verifier, args.method, checks, "INDEPENDENT_TARGET_ORIGIN_MISMATCH")
    if not any((d.get("checks") or {}).get("snapshot_digest") for d in independent_details if isinstance(d.get("checks"), dict)):
        return fail(args.report, source, args.verifier, args.method, checks, "INDEPENDENT_SNAPSHOT_UNOBSERVED")

    # Every unresolved historical NEEDS_CHECK must be external evidence; that is
    # the only class this provider corroboration is allowed to resolve.
    unresolved = [x for x in checks if isinstance(x, dict) and x.get("status") == "NEEDS_CHECK"]
    if any(not str(x.get("id") or "").startswith("evidence-") for x in unresolved):
        return fail(args.report, source, args.verifier, args.method, checks, "NON_EVIDENCE_CHECK_CANNOT_BE_CORROBORATED")
    for item in unresolved:
        item["status"] = "PASS"
        item["detail"] = str(item.get("detail") or "") + "; independently corroborated by second provider"

    checks.append({
        "id": "independent-observation",
        "status": "PASS",
        "detail": f"producer={independent_producer}; task={independent.get('task_id')}; subject={digest(source_subject)}",
    })
    observed = now_iso()
    verified = deepcopy(source)
    verified["verification"] = {
        "status": "VERIFIED",
        "method": "independent-agent",
        "verifier": args.verifier,
        "observed_at": observed,
        "notes": "Verified by broker after independent provider corroboration.",
    }
    report = {
        "schema": REPORT_SCHEMA,
        "project": source.get("project"),
        "task_id": source.get("task_id"),
        "verifier": args.verifier,
        "method": "independent-agent",
        "status": "VERIFIED",
        "observed_at": observed,
        "source_result_digest": digest(source),
        "checks": checks,
        "notes": ["External provider evidence resolved only by independent provider observation."],
        "independent_observation": {
            "task_id": independent.get("task_id"),
            "producer": independent_producer,
            "result_digest": digest(independent),
            "verification_status": (independent.get("verification") or {}).get("status"),
            "subject_digest": digest(source_subject),
        },
        "verified_task_result": verified,
    }
    save(args.report, report)
    if args.verified_result:
        save(args.verified_result, verified)
        print(f"VERIFIED_TASK_RESULT={args.verified_result}")
    print(f"VERIFICATION_REPORT={args.report}")
    print("VERIFICATION_STATUS=VERIFIED")
    print(f"CHECKS={len(checks)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
