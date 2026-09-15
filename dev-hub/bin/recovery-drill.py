#!/usr/bin/env python3
"""ChaCha DEV HUB Recovery Drill / Fault Injection V1.

Runs destructive-looking recovery scenarios only inside an isolated temporary
sandbox. It never targets configured production runtime paths. The harness
injects failures at transaction boundaries and proves that Transaction Recovery
is forward-only, hash-chain aware, and conservative when state is ambiguous.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

POLICY_SCHEMA = "chacha.dev/recovery-drill/v1"
REPORT_SCHEMA = "chacha.dev/recovery-drill-report/v1"
LEDGER_SCHEMA = "chacha.dev/evidence-ledger/v1"
RECEIPT_SCHEMA = "chacha.dev/control-transaction-receipt/v1"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise RuntimeError(f"FILE_NOT_FOUND:{path}")
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"JSON_INVALID:{path}:{exc.lineno}:{exc.colno}:{exc.msg}")
    if not isinstance(value, dict):
        raise RuntimeError(f"JSON_ROOT_NOT_OBJECT:{path}")
    return value


def save(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def digest_obj(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def resolve_repo(repo_root: Path, configured: str) -> Path:
    p = Path(configured)
    return p if p.is_absolute() else repo_root / p


def run_text(argv: list[str], timeout: int = 30) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            shell=False,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"COMMAND_TIMEOUT:{argv[0]}:{exc}")
    return proc.returncode, proc.stdout, proc.stderr


def run_json(argv: list[str], timeout: int = 30) -> tuple[int, dict[str, Any], str]:
    rc, stdout, stderr = run_text(argv, timeout)
    try:
        value = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"COMMAND_NON_JSON:rc={rc}:stderr={stderr.strip()}:stdout={stdout[:400]}:{exc}")
    if not isinstance(value, dict):
        raise RuntimeError("COMMAND_JSON_ROOT_NOT_OBJECT")
    return rc, value, stderr.strip()


def import_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"MODULE_LOAD_FAILED:{path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def ensure_sandbox(root: Path, policy: dict[str, Any]) -> Path:
    resolved = root.expanduser().resolve()
    if resolved == Path("/"):
        raise RuntimeError("SANDBOX_ROOT_FORBIDDEN:/")
    for prefix in policy.get("forbidden_runtime_prefixes") or []:
        forbidden = Path(str(prefix)).expanduser()
        try:
            forbidden = forbidden.resolve()
        except FileNotFoundError:
            forbidden = forbidden.absolute()
        if resolved == forbidden or forbidden in resolved.parents:
            raise RuntimeError(f"SANDBOX_ROOT_FORBIDDEN:{resolved}")
    resolved.mkdir(parents=True, exist_ok=True)
    marker = resolved / ".chacha-recovery-drill-sandbox"
    marker.write_text("sandbox-only\n", encoding="utf-8")
    return resolved


class Context:
    def __init__(self, repo_root: Path, policy_path: Path, work_root: Path):
        self.repo_root = repo_root.resolve()
        self.policy_path = policy_path.resolve()
        self.policy = load(self.policy_path)
        if self.policy.get("schema") != POLICY_SCHEMA:
            raise RuntimeError(f"POLICY_SCHEMA_INVALID:{self.policy.get('schema')}")
        self.root = ensure_sandbox(work_root, self.policy)
        refs = self.policy.get("repository_paths") or {}
        self.store_tool = resolve_repo(self.repo_root, refs["control_plane_store"]).resolve()
        self.recovery_tool = resolve_repo(self.repo_root, refs["transaction_recovery"]).resolve()
        self.store_module = import_module(self.store_tool, "chacha_control_plane_store_drill")

        state_policy = load(resolve_repo(self.repo_root, refs["control_plane_policy"]))
        state_policy.setdefault("storage", {})["runtime_root"] = str(self.root / "state")
        state_policy["storage"]["transaction_root"] = str(self.root / "transactions")
        self.state_policy_path = self.root / "policies" / "control-plane-state.json"
        save(self.state_policy_path, state_policy)

        recovery_policy = load(resolve_repo(self.repo_root, refs["recovery_policy"]))
        recovery_policy["runtime"] = {
            "transactions_root": str(self.root / "transactions"),
            "state_root": str(self.root / "state"),
            "evidence_root": str(self.root / "evidence"),
            "locks_root": str(self.root / "locks"),
        }
        recovery_policy["repository_paths"] = {
            "control_plane_state": str(self.state_policy_path),
            "control_plane_store": str(self.store_tool),
        }
        self.recovery_policy_path = self.root / "policies" / "transaction-recovery.json"
        save(self.recovery_policy_path, recovery_policy)

    def project_state(self, project: str) -> Path:
        return self.root / "state" / project / "state.json"

    def journal(self, project: str) -> Path:
        return self.root / "state" / project / "audit.jsonl"

    def ledger(self, project: str) -> Path:
        return self.root / "evidence" / project / "ledger.json"

    def txdir(self, project: str, txid: str) -> Path:
        return self.root / "transactions" / project / txid

    def receipt(self, project: str, txid: str) -> Path:
        return self.txdir(project, txid) / "receipt.json"

    def init_project(self, project: str) -> None:
        rc, out, err = run_text([
            sys.executable, str(self.store_tool),
            "--policy", str(self.state_policy_path),
            "--root", str(self.root / "state"),
            "init", "--project", project, "--actor", "recovery-drill",
        ])
        if rc != 0:
            raise RuntimeError(f"INIT_FAILED:{project}:{err or out}")

    def verify_project(self, project: str) -> tuple[bool, str]:
        rc, out, err = run_text([
            sys.executable, str(self.store_tool),
            "--policy", str(self.state_policy_path),
            "--root", str(self.root / "state"),
            "verify", "--project", project,
        ])
        return rc == 0, (out + "\n" + err).strip()

    def write_receipt(self, project: str, txid: str, operation: str, status: str,
                      **extra: Any) -> Path:
        value: dict[str, Any] = {
            "schema": RECEIPT_SCHEMA,
            "transaction_id": txid,
            "project": project,
            "operation": operation,
            "status": status,
            "updated_at": now_iso(),
            "actor": "recovery-drill",
        }
        value.update(extra)
        path = self.receipt(project, txid)
        save(path, value)
        return path

    def append_event_only(self, project: str, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        journal = self.journal(project)
        events = self.store_module.read_events(journal)
        if not events:
            raise RuntimeError(f"NO_INITIAL_EVENT:{project}")
        event = self.store_module.make_event(
            project,
            len(events) + 1,
            event_type,
            "recovery-drill",
            events[-1].get("event_digest"),
            payload,
            [],
        )
        self.store_module.append_jsonl(journal, event)
        return event

    def inspect(self, project: str, txid: str) -> tuple[int, dict[str, Any], str]:
        return run_json([
            sys.executable, str(self.recovery_tool),
            "--policy", str(self.recovery_policy_path),
            "--repo-root", str(self.repo_root),
            "--json", "inspect", "--project", project, "--transaction-id", txid,
        ])

    def recover(self, project: str, txid: str) -> tuple[int, dict[str, Any], str]:
        return run_json([
            sys.executable, str(self.recovery_tool),
            "--policy", str(self.recovery_policy_path),
            "--repo-root", str(self.repo_root),
            "--json", "recover", "--project", project, "--transaction-id", txid,
            "--actor", "recovery-drill", "--apply",
        ])


def require(condition: bool, message: str, checks: list[str]) -> None:
    if not condition:
        raise AssertionError(message)
    checks.append(message)


def result_ok(sid: str, fault: str, checks: list[str], inspection: dict[str, Any] | None = None,
              recovery: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "id": sid,
        "status": "PASS",
        "fault_point": fault,
        "inspection": inspection or {},
        "recovery": recovery or {},
        "checks": checks,
        "error": None,
    }


def scenario_prepared_before_authority(ctx: Context, spec: dict[str, Any]) -> dict[str, Any]:
    sid = "prepared-before-authority"
    project, txid = "drill-prepared", "ctx-prepared"
    checks: list[str] = []
    ctx.init_project(project)
    ctx.write_receipt(project, txid, "advance", "PREPARED", transition="IDEA->DESIGN", pre_version=1)
    _rc, inspection, _err = ctx.inspect(project, txid)
    require(inspection.get("assessment") == spec["expected_assessment"], "inspection classified SAFE_TO_ABORT", checks)
    _rc2, recovery, _err2 = ctx.recover(project, txid)
    receipt = load(ctx.receipt(project, txid))
    require(receipt.get("status") == "FAILED", "receipt closed as FAILED before authoritative commit", checks)
    require(receipt.get("recovery_outcome") == spec["expected_outcome"], "abort outcome recorded", checks)
    valid, _ = ctx.verify_project(project)
    require(valid, "journal and projection remain valid after abort", checks)
    return result_ok(sid, spec["fault_point"], checks, inspection, recovery)


def scenario_journal_before_projection(ctx: Context, spec: dict[str, Any]) -> dict[str, Any]:
    sid = "journal-before-projection"
    project, txid = "drill-projection", "ctx-projection"
    checks: list[str] = []
    ctx.init_project(project)
    ctx.write_receipt(project, txid, "advance", "COMMIT_UNCERTAIN", transition="IDEA->DESIGN", pre_version=1)
    patch = {"lifecycle": {"stage": "DESIGN"}}
    ctx.append_event_only(project, "LIFECYCLE_TRANSITION", {
        "transaction_id": txid,
        "transition": "IDEA->DESIGN",
        "from": "IDEA",
        "to": "DESIGN",
        "state_patch": patch,
    })
    valid_before, _ = ctx.verify_project(project)
    require(not valid_before, "fault injection produced stale projection", checks)
    _rc, inspection, _err = ctx.inspect(project, txid)
    require(inspection.get("assessment") == spec["expected_assessment"], "stale projection classified REPAIRABLE", checks)
    _rc2, recovery, _err2 = ctx.recover(project, txid)
    receipt = load(ctx.receipt(project, txid))
    state = load(ctx.project_state(project))
    valid_after, _ = ctx.verify_project(project)
    require(receipt.get("status") == "COMMITTED", "receipt recovered to COMMITTED", checks)
    require(receipt.get("recovery_outcome") == spec["expected_outcome"], "authoritative-event recovery outcome recorded", checks)
    require(((state.get("state") or {}).get("lifecycle") or {}).get("stage") == "DESIGN", "projection rebuilt to DESIGN", checks)
    require(valid_after, "rebuilt projection verifies against hash chain", checks)
    return result_ok(sid, spec["fault_point"], checks, inspection, recovery)


def seed_ledgers(ctx: Context, project: str, txid: str) -> tuple[dict[str, Any], dict[str, Any], Path, str, str]:
    old = {
        "schema": LEDGER_SCHEMA,
        "project": project,
        "artifacts": [],
        "quality_gates": {},
        "approvals": [],
    }
    new = {
        "schema": LEDGER_SCHEMA,
        "project": project,
        "artifacts": [{"id": "drill-evidence", "status": "VERIFIED", "digest": "sha256:demo"}],
        "quality_gates": {},
        "approvals": [],
    }
    save(ctx.ledger(project), old)
    staged = ctx.txdir(project, txid) / "staged-ledger.json"
    save(staged, new)
    return old, new, staged, digest_obj(old), digest_obj(new)


def scenario_evidence_before_finalize(ctx: Context, spec: dict[str, Any]) -> dict[str, Any]:
    sid = "evidence-before-ledger-finalize"
    project, txid = "drill-evidence", "ctx-evidence"
    checks: list[str] = []
    ctx.init_project(project)
    _old, _new, staged, old_digest, new_digest = seed_ledgers(ctx, project, txid)
    ctx.write_receipt(
        project, txid, "verify-result", "CONTROL_EVENT_COMMITTED_LEDGER_PENDING",
        old_ledger_digest=old_digest,
        new_ledger_digest=new_digest,
        staged_ledger=str(staged),
    )
    ctx.append_event_only(project, "EVIDENCE_RECORDED", {
        "transaction_id": txid,
        "old_ledger_digest": old_digest,
        "new_ledger_digest": new_digest,
        "staged_ledger": str(staged),
        "commit_protocol": "journal-first-ledger-finalize",
    })
    _rc, inspection, _err = ctx.inspect(project, txid)
    require(inspection.get("assessment") == spec["expected_assessment"], "partial evidence commit classified REPAIRABLE", checks)
    _rc2, recovery, _err2 = ctx.recover(project, txid)
    receipt = load(ctx.receipt(project, txid))
    live = load(ctx.ledger(project))
    valid, _ = ctx.verify_project(project)
    require(receipt.get("status") == "COMMITTED", "evidence transaction recovered to COMMITTED", checks)
    require(receipt.get("recovery_outcome") == spec["expected_outcome"], "ledger finalization recovery outcome recorded", checks)
    require(digest_obj(live) == new_digest, "live Evidence Ledger matches staged verified digest", checks)
    require(valid, "control-plane hash chain verifies after evidence recovery", checks)
    return result_ok(sid, spec["fault_point"], checks, inspection, recovery)


def scenario_tampered_journal(ctx: Context, spec: dict[str, Any]) -> dict[str, Any]:
    sid = "tampered-journal"
    project, txid = "drill-tamper", "ctx-tamper"
    checks: list[str] = []
    ctx.init_project(project)
    ctx.write_receipt(project, txid, "advance", "PREPARED", transition="IDEA->DESIGN", pre_version=1)
    journal = ctx.journal(project)
    lines = journal.read_text(encoding="utf-8").splitlines()
    event = json.loads(lines[0])
    event["actor"] = "tampered-actor"
    lines[0] = json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    journal.write_text("\n".join(lines) + "\n", encoding="utf-8")
    _rc, inspection, _err = ctx.inspect(project, txid)
    require(inspection.get("assessment") == spec["expected_assessment"], "tampered journal classified INVALID", checks)
    blockers = inspection.get("blockers") or []
    require(spec["expected_blocker"] in blockers, "tampered journal blocker exposed", checks)
    receipt = load(ctx.receipt(project, txid))
    require(receipt.get("status") == "PREPARED", "tampered journal was not auto-repaired", checks)
    return result_ok(sid, spec["fault_point"], checks, inspection, {})


def scenario_divergent_ledger(ctx: Context, spec: dict[str, Any]) -> dict[str, Any]:
    sid = "divergent-ledger"
    project, txid = "drill-divergent", "ctx-divergent"
    checks: list[str] = []
    ctx.init_project(project)
    _old, _new, staged, old_digest, new_digest = seed_ledgers(ctx, project, txid)
    ctx.write_receipt(
        project, txid, "verify-result", "CONTROL_EVENT_COMMITTED_LEDGER_PENDING",
        old_ledger_digest=old_digest,
        new_ledger_digest=new_digest,
        staged_ledger=str(staged),
    )
    ctx.append_event_only(project, "EVIDENCE_RECORDED", {
        "transaction_id": txid,
        "old_ledger_digest": old_digest,
        "new_ledger_digest": new_digest,
        "staged_ledger": str(staged),
    })
    divergent = {
        "schema": LEDGER_SCHEMA,
        "project": project,
        "artifacts": [{"id": "unexpected-third-state", "status": "VERIFIED"}],
        "quality_gates": {},
        "approvals": [],
    }
    save(ctx.ledger(project), divergent)
    _rc, inspection, _err = ctx.inspect(project, txid)
    require(inspection.get("assessment") == spec["expected_assessment"], "divergent ledger classified MANUAL_REVIEW", checks)
    blockers = inspection.get("blockers") or []
    require(spec["expected_blocker"] in blockers, "divergent ledger blocker exposed", checks)
    require(digest_obj(load(ctx.ledger(project))) == digest_obj(divergent), "ambiguous live ledger was not overwritten", checks)
    return result_ok(sid, spec["fault_point"], checks, inspection, {})


SCENARIOS: dict[str, Callable[[Context, dict[str, Any]], dict[str, Any]]] = {
    "prepared-before-authority": scenario_prepared_before_authority,
    "journal-before-projection": scenario_journal_before_projection,
    "evidence-before-ledger-finalize": scenario_evidence_before_finalize,
    "tampered-journal": scenario_tampered_journal,
    "divergent-ledger": scenario_divergent_ledger,
}


def main() -> int:
    parser = argparse.ArgumentParser(description="ChaCha DEV HUB sandbox recovery drill")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--policy", type=Path, default=Path("dev-hub/config/recovery-drill.v1.json"))
    parser.add_argument("--work-root", type=Path)
    parser.add_argument("--keep-workdir", action="store_true")
    parser.add_argument("--output", type=Path)
    sub = parser.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run")
    run.add_argument("--scenario", default="all", choices=["all", *SCENARIOS.keys()])
    args = parser.parse_args()

    repo_root = args.repo_root.resolve()
    policy_path = args.policy if args.policy.is_absolute() else repo_root / args.policy
    created_temp = args.work_root is None
    work_root = args.work_root.resolve() if args.work_root else Path(tempfile.mkdtemp(prefix="chacha-recovery-drill-"))

    report: dict[str, Any]
    try:
        ctx = Context(repo_root, policy_path, work_root)
        configured = ctx.policy.get("scenarios") or {}
        selected = list(SCENARIOS) if args.scenario == "all" else [args.scenario]
        results: list[dict[str, Any]] = []
        for sid in selected:
            spec = configured.get(sid)
            if not isinstance(spec, dict):
                results.append({
                    "id": sid,
                    "status": "FAIL",
                    "fault_point": "unknown",
                    "inspection": {},
                    "recovery": {},
                    "checks": [],
                    "error": "SCENARIO_POLICY_MISSING",
                })
                continue
            try:
                results.append(SCENARIOS[sid](ctx, spec))
            except Exception as exc:
                results.append({
                    "id": sid,
                    "status": "FAIL",
                    "fault_point": str(spec.get("fault_point") or "unknown"),
                    "inspection": {},
                    "recovery": {},
                    "checks": [],
                    "error": f"{type(exc).__name__}:{exc}",
                })
        failed = sum(item["status"] != "PASS" for item in results)
        report = {
            "schema": REPORT_SCHEMA,
            "observed_at": now_iso(),
            "status": "PASS" if failed == 0 else "FAIL",
            "policy": str(policy_path),
            "work_root": str(work_root),
            "scenarios": results,
            "summary": {
                "total": len(results),
                "passed": len(results) - failed,
                "failed": failed,
            },
        }
    except Exception as exc:
        report = {
            "schema": REPORT_SCHEMA,
            "observed_at": now_iso(),
            "status": "FAIL",
            "policy": str(policy_path),
            "work_root": str(work_root),
            "scenarios": [],
            "summary": {"total": 0, "passed": 0, "failed": 1},
            "fatal_error": f"{type(exc).__name__}:{exc}",
        }

    if args.output:
        output = args.output if args.output.is_absolute() else repo_root / args.output
        save(output, report)
        print(f"RECOVERY_DRILL_REPORT={output}")
    print(json.dumps(report, indent=2, ensure_ascii=False))

    if created_temp and not args.keep_workdir:
        shutil.rmtree(work_root, ignore_errors=True)
    elif args.keep_workdir:
        print(f"RECOVERY_DRILL_WORK_ROOT={work_root}")
    return 0 if report.get("status") == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
