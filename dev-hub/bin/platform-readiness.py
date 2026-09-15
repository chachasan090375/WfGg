#!/usr/bin/env python3
"""ChaCha DEV HUB Platform Readiness / Certification Gate V1.

Aggregates repository contracts, adapter contracts, recovery fault-injection,
Control Plane integrity, pending transactions, provider health, storage
preflight, adapter execution coverage and cryptographic trust prerequisites.

The engine is read-only. It never enables adapters, changes provider bindings,
generates keys, grants approvals, dispatches work or mutates production.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

POLICY_SCHEMA = "chacha.dev/platform-readiness/v1"
REPORT_SCHEMA = "chacha.dev/platform-readiness-report/v1"
HEALTH_SCHEMA = "chacha.dev/provider-health-snapshot/v1"


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


def resolve(repo_root: Path, configured: str) -> Path:
    p = Path(configured)
    return p if p.is_absolute() else repo_root / p


def run(argv: list[str], timeout: int = 120) -> tuple[int, str, str]:
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
    except subprocess.TimeoutExpired:
        return 124, "", "TIMEOUT"
    return proc.returncode, proc.stdout, proc.stderr


def add_check(checks: list[dict[str, Any]], cid: str, status: str, blocking: bool,
              detail: str, evidence: dict[str, Any] | None = None) -> None:
    checks.append({
        "id": cid,
        "status": status,
        "blocking": blocking,
        "detail": detail,
        "evidence": evidence or {},
    })


def inherited_checks(policy: dict[str, Any], profile: str) -> set[str]:
    profiles = policy.get("profiles") or {}
    out: set[str] = set()
    seen: set[str] = set()
    current = profile
    while current:
        if current in seen:
            raise RuntimeError(f"PROFILE_INHERITANCE_CYCLE:{current}")
        seen.add(current)
        item = profiles.get(current)
        if not isinstance(item, dict):
            raise RuntimeError(f"PROFILE_NOT_FOUND:{current}")
        out.update(str(x) for x in item.get("required_checks") or [])
        current = str(item.get("extends") or "")
    return out


def profile_permissions(policy: dict[str, Any], profile: str) -> list[str]:
    profiles = policy.get("profiles") or {}
    item = profiles.get(profile) or {}
    return [str(x) for x in item.get("required_permissions") or []]


def check_repository_contracts(repo_root: Path, policy: dict[str, Any], checks: list[dict[str, Any]]) -> None:
    contracts = policy.get("repository_contracts") or {}
    errors: list[str] = []
    count = 0
    for raw in contracts.get("json") or []:
        path = resolve(repo_root, str(raw))
        count += 1
        try:
            load(path)
        except RuntimeError as exc:
            errors.append(str(exc))
    for raw in contracts.get("python") or []:
        path = resolve(repo_root, str(raw))
        count += 1
        try:
            source = path.read_text(encoding="utf-8")
            compile(source, str(path), "exec")
        except Exception as exc:
            errors.append(f"PYTHON_CONTRACT_INVALID:{path}:{type(exc).__name__}:{exc}")
    add_check(
        checks, "repository-contracts", "PASS" if not errors else "FAIL", True,
        f"validated={count}, errors={len(errors)}",
        {"errors": errors},
    )


def adapter_contract(repo_root: Path, policy: dict[str, Any], checks: list[dict[str, Any]],
                     supplied_report: Path | None) -> dict[str, Any] | None:
    refs = policy.get("repository_paths") or {}
    engines = policy.get("engine_paths") or {}
    report: dict[str, Any] | None = None
    report_path: Path | None = supplied_report
    if supplied_report:
        try:
            report = load(supplied_report)
        except RuntimeError as exc:
            add_check(checks, "adapter-static-contract", "FAIL", True, str(exc))
            return None
    else:
        tmp = tempfile.NamedTemporaryFile(prefix="adapter-contract-", suffix=".json", delete=False)
        tmp.close()
        report_path = Path(tmp.name)
        rc, stdout, stderr = run([
            sys.executable,
            str(resolve(repo_root, engines["adapter_contract_harness"])),
            "--registry", str(resolve(repo_root, refs["provider_adapters"])),
            "--policy", str(resolve(repo_root, refs["adapter_contract"])),
            "--report", str(report_path),
        ])
        try:
            report = load(report_path)
        except RuntimeError as exc:
            add_check(checks, "adapter-static-contract", "FAIL", True,
                      f"harness rc={rc}; {exc}", {"stdout": stdout.strip(), "stderr": stderr.strip()})
            return None
    static = (report or {}).get("static") or {}
    ok = report is not None and static.get("status") == "PASS" and int(static.get("failures") or 0) == 0
    add_check(
        checks, "adapter-static-contract", "PASS" if ok else "FAIL", True,
        f"static_status={static.get('status')}, failures={static.get('failures')}",
        {"report": str(report_path) if report_path else None},
    )
    return report


def recovery_drill(repo_root: Path, policy: dict[str, Any], checks: list[dict[str, Any]],
                   supplied_report: Path | None, run_drill: bool) -> dict[str, Any] | None:
    refs = policy.get("repository_paths") or {}
    engines = policy.get("engine_paths") or {}
    report_path = supplied_report
    report: dict[str, Any] | None = None
    if run_drill:
        tmp = tempfile.NamedTemporaryFile(prefix="recovery-drill-", suffix=".json", delete=False)
        tmp.close()
        report_path = Path(tmp.name)
        rc, stdout, stderr = run([
            sys.executable,
            str(resolve(repo_root, engines["recovery_drill"])),
            "--repo-root", str(repo_root),
            "--policy", str(resolve(repo_root, refs["recovery_drill"])),
            "--output", str(report_path),
            "run", "--scenario", "all",
        ], timeout=180)
        try:
            report = load(report_path)
        except RuntimeError as exc:
            add_check(checks, "recovery-drill", "FAIL", True,
                      f"drill rc={rc}; {exc}", {"stdout": stdout[-1000:], "stderr": stderr[-1000:]})
            return None
    elif supplied_report:
        try:
            report = load(supplied_report)
        except RuntimeError as exc:
            add_check(checks, "recovery-drill", "FAIL", True, str(exc))
            return None
    else:
        add_check(checks, "recovery-drill", "UNKNOWN", True,
                  "No recovery drill report supplied and --run-recovery-drill was not requested.")
        return None
    summary = (report or {}).get("summary") or {}
    ok = (
        report is not None
        and report.get("schema") == "chacha.dev/recovery-drill-report/v1"
        and report.get("status") == "PASS"
        and int(summary.get("failed") or 0) == 0
        and int(summary.get("total") or 0) >= 5
    )
    add_check(
        checks, "recovery-drill", "PASS" if ok else "FAIL", True,
        f"status={(report or {}).get('status')}, passed={summary.get('passed')}, failed={summary.get('failed')}",
        {"report": str(report_path) if report_path else None},
    )
    return report


def control_plane_checks(repo_root: Path, policy: dict[str, Any], project: str | None,
                         checks: list[dict[str, Any]]) -> None:
    if not project:
        add_check(checks, "control-plane-integrity", "UNKNOWN", True, "Project is required for runtime readiness.")
        add_check(checks, "no-pending-transactions", "UNKNOWN", True, "Project is required for runtime readiness.")
        return
    refs = policy.get("repository_paths") or {}
    engines = policy.get("engine_paths") or {}
    state_policy_path = resolve(repo_root, refs["control_plane_state"])
    state_policy = load(state_policy_path)
    state_root = Path(str((state_policy.get("storage") or {}).get("runtime_root", "/opt/chacha-dev/runtime/state")))
    rc, stdout, stderr = run([
        sys.executable,
        str(resolve(repo_root, engines["control_plane_store"])),
        "--policy", str(state_policy_path),
        "--root", str(state_root),
        "verify", "--project", project,
    ])
    add_check(
        checks, "control-plane-integrity", "PASS" if rc == 0 else "FAIL", True,
        "Control Plane projection/hash chain verified." if rc == 0 else "Control Plane verification failed.",
        {"stdout": stdout.strip(), "stderr": stderr.strip()},
    )

    recovery_policy_path = resolve(repo_root, refs["transaction_recovery"])
    rc2, stdout2, stderr2 = run([
        sys.executable,
        str(resolve(repo_root, engines["transaction_recovery"])),
        "--policy", str(recovery_policy_path),
        "--repo-root", str(repo_root),
        "--json", "list", "--project", project,
    ])
    try:
        txs = json.loads(stdout2) if stdout2.strip() else {}
    except json.JSONDecodeError:
        txs = {}
    blocking = int(((txs.get("summary") or {}).get("blocking") or 0)) if isinstance(txs, dict) else -1
    ok = rc2 == 0 and blocking == 0
    add_check(
        checks, "no-pending-transactions", "PASS" if ok else "FAIL", True,
        f"blocking_transactions={blocking}" if blocking >= 0 else "Transaction state could not be established.",
        {"stderr": stderr2.strip(), "summary": (txs.get("summary") if isinstance(txs, dict) else None)},
    )


def provider_health_check(policy: dict[str, Any], profile: str, health_path: Path | None,
                          required_provider: list[str], checks: list[dict[str, Any]]) -> dict[str, Any] | None:
    if health_path is None:
        add_check(checks, "provider-health", "UNKNOWN", True, "Provider health snapshot is required for runtime readiness.")
        return None
    try:
        health = load(health_path)
    except RuntimeError as exc:
        add_check(checks, "provider-health", "FAIL", True, str(exc))
        return None
    if health.get("schema") != HEALTH_SCHEMA:
        add_check(checks, "provider-health", "FAIL", True, f"HEALTH_SCHEMA_INVALID:{health.get('schema')}")
        return health
    cfg = policy.get("provider_health") or {}
    required = set(str(x) for x in cfg.get("baseline_required_providers") or [])
    required.update(required_provider)
    if profile == "production":
        required.update(str(x) for x in cfg.get("production_required_providers") or [])
    providers = health.get("providers") or {}
    profile_cfg = (policy.get("profiles") or {}).get(profile) or {}
    allow_degraded = bool(profile_cfg.get("allow_degraded_provider_health", False))
    bad: list[str] = []
    states: dict[str, str] = {}
    for pid in sorted(required):
        state = str(((providers.get(pid) or {}).get("state") or "UNKNOWN"))
        states[pid] = state
        if state == "HEALTHY":
            continue
        if state == "DEGRADED" and allow_degraded:
            continue
        bad.append(f"{pid}:{state}")
    add_check(
        checks, "provider-health", "PASS" if not bad else "FAIL", True,
        f"required={len(required)}, unacceptable={len(bad)}",
        {"states": states, "unacceptable": bad, "snapshot": str(health_path)},
    )
    return health


def storage_status(value: Any) -> str | None:
    if isinstance(value, dict):
        for key in ("status", "preflight", "PREFLIGHT", "result", "storage_status"):
            v = value.get(key)
            if isinstance(v, str):
                return v.upper()
        for nested in value.values():
            found = storage_status(nested)
            if found:
                return found
    return None


def storage_check(policy: dict[str, Any], path: Path | None, checks: list[dict[str, Any]]) -> None:
    if path is None:
        add_check(checks, "storage-preflight", "UNKNOWN", True, "Storage preflight evidence is required for runtime readiness.")
        return
    try:
        value = load(path)
    except RuntimeError as exc:
        add_check(checks, "storage-preflight", "FAIL", True, str(exc))
        return
    status = storage_status(value)
    accepted = set(str(x).upper() for x in ((policy.get("storage") or {}).get("accepted_statuses") or []))
    ok = status in accepted
    add_check(
        checks, "storage-preflight", "PASS" if ok else "FAIL", True,
        f"status={status}", {"artifact": str(path), "accepted": sorted(accepted)},
    )


def adapter_coverage(repo_root: Path, policy: dict[str, Any], profile: str,
                     checks: list[dict[str, Any]]) -> dict[str, Any]:
    registry = load(resolve(repo_root, (policy.get("repository_paths") or {})["provider_adapters"]))
    adapters = registry.get("adapters") or {}
    allowed_cfg = policy.get("adapter_runtime") or {}
    allowed = set(allowed_cfg.get("production_statuses" if profile == "production" else "development_statuses") or [])
    permissions = profile_permissions(policy, profile)
    uncovered: list[str] = []
    coverage: dict[str, list[str]] = {}
    for permission in permissions:
        matched = []
        for aid, item in adapters.items():
            if not isinstance(item, dict):
                continue
            if item.get("status") in allowed and permission in (item.get("supports") or []):
                matched.append(str(aid))
        coverage[permission] = matched
        if not matched:
            uncovered.append(permission)
    add_check(
        checks, "adapter-runtime-coverage", "PASS" if not uncovered else "FAIL", True,
        f"permissions={len(permissions)}, uncovered={len(uncovered)}",
        {"allowed_statuses": sorted(allowed), "coverage": coverage, "uncovered": uncovered},
    )
    if profile == "production":
        add_check(
            checks, "repository-write-coverage", "PASS" if coverage.get("repository-write") else "FAIL", True,
            "ENABLED adapter covers repository-write." if coverage.get("repository-write") else "No ENABLED adapter covers repository-write.",
            {"adapters": coverage.get("repository-write") or []},
        )
        add_check(
            checks, "production-deploy-coverage", "PASS" if coverage.get("production-deploy") else "FAIL", True,
            "ENABLED adapter covers production-deploy." if coverage.get("production-deploy") else "No ENABLED adapter covers production-deploy.",
            {"adapters": coverage.get("production-deploy") or []},
        )
    return registry


def production_trust_checks(repo_root: Path, policy: dict[str, Any], health: dict[str, Any] | None,
                            adapters: dict[str, Any], checks: list[dict[str, Any]]) -> None:
    cfg = policy.get("cryptographic_trust") or {}
    signing_provider = str(cfg.get("signing_provider"))
    signing_adapter = str(cfg.get("signing_adapter"))
    adapter_item = ((adapters.get("adapters") or {}).get(signing_adapter) or {})
    health_state = str((((health or {}).get("providers") or {}).get(signing_provider) or {}).get("state") or "UNKNOWN")
    signing_ok = adapter_item.get("status") == "ENABLED" and health_state == "HEALTHY"
    add_check(
        checks, "signing-runtime", "PASS" if signing_ok else "FAIL", True,
        f"adapter_status={adapter_item.get('status')}, provider_health={health_state}",
        {"provider": signing_provider, "adapter": signing_adapter},
    )

    trust_policy = load(resolve(repo_root, (policy.get("repository_paths") or {})["cryptographic_trust"]))
    anchoring = trust_policy.get("anchoring") or {}
    required = [str(x) for x in cfg.get("required_anchor_providers") or []]
    anchor_states = {pid: str(((anchoring.get(pid) or {}).get("status") or "UNKNOWN")) for pid in required}
    provider_states = {
        pid: str((((health or {}).get("providers") or {}).get(pid) or {}).get("state") or "UNKNOWN")
        for pid in required
    }
    enabled = [pid for pid in required if anchor_states.get(pid) in {"ENABLED", "ADOPT"} and provider_states.get(pid) == "HEALTHY"]
    minimum = int(cfg.get("minimum_independent_anchors") or 2)
    anchors_ok = len(enabled) >= minimum
    add_check(
        checks, "trust-anchor-runtime", "PASS" if anchors_ok else "FAIL", True,
        f"healthy_enabled_anchors={len(enabled)}, minimum={minimum}",
        {"anchor_policy_status": anchor_states, "provider_health": provider_states, "eligible": enabled},
    )

    orchestration = load(resolve(repo_root, (policy.get("repository_paths") or {})["orchestration"]))
    project_control = load(resolve(repo_root, "dev-hub/config/project-control.v1.json"))
    explicit = ((orchestration.get("permissions") or {}).get("production-deploy") or {}).get("approval") == "explicit-human"
    boundary = (project_control.get("approval_boundaries") or {}).get("advance_to_release") == "explicit-human"
    add_check(
        checks, "production-approval-boundary", "PASS" if explicit and boundary else "FAIL", True,
        f"production-deploy={explicit}, advance-to-release={boundary}",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="ChaCha DEV HUB platform readiness certification gate")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--policy", type=Path, default=Path("dev-hub/config/platform-readiness.v1.json"))
    parser.add_argument("--profile", choices=["contract", "development", "production"], default="development")
    parser.add_argument("--project")
    parser.add_argument("--provider-health", type=Path)
    parser.add_argument("--storage-preflight", type=Path)
    parser.add_argument("--adapter-contract-report", type=Path)
    parser.add_argument("--recovery-drill-report", type=Path)
    parser.add_argument("--run-recovery-drill", action="store_true")
    parser.add_argument("--required-provider", action="append", default=[])
    parser.add_argument("--output", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    repo_root = args.repo_root.resolve()
    policy_path = args.policy if args.policy.is_absolute() else repo_root / args.policy
    policy = load(policy_path)
    if policy.get("schema") != POLICY_SCHEMA:
        raise SystemExit(f"POLICY_SCHEMA_INVALID={policy.get('schema')}")

    required = inherited_checks(policy, args.profile)
    checks: list[dict[str, Any]] = []
    evidence: dict[str, Any] = {"policy": str(policy_path)}

    if "repository-contracts" in required:
        check_repository_contracts(repo_root, policy, checks)
    if "adapter-static-contract" in required:
        adapter_contract(repo_root, policy, checks, args.adapter_contract_report)
    if "recovery-drill" in required:
        recovery_drill(repo_root, policy, checks, args.recovery_drill_report, args.run_recovery_drill)

    health: dict[str, Any] | None = None
    adapters: dict[str, Any] | None = None
    if args.profile in {"development", "production"}:
        control_plane_checks(repo_root, policy, args.project, checks)
        health = provider_health_check(policy, args.profile, args.provider_health, args.required_provider, checks)
        storage_check(policy, args.storage_preflight, checks)
        adapters = adapter_coverage(repo_root, policy, args.profile, checks)

    if args.profile == "production":
        production_trust_checks(repo_root, policy, health, adapters or {}, checks)

    blocking = [c for c in checks if c.get("blocking") and c.get("status") != "PASS"]
    blockers = [f"{c['id']}:{c['status']}:{c['detail']}" for c in blocking]
    warnings: list[str] = []
    if args.profile == "contract":
        warnings.append("CONTRACT_PROFILE_DOES_NOT_AUTHORIZE_RUNTIME_EXECUTION")
    if args.profile == "development":
        run_controller = load(resolve(repo_root, (policy.get("repository_paths") or {})["run_controller"]))
        if run_controller.get("mode") != "execute-enabled":
            blockers.append(f"run-controller-mode:{run_controller.get('mode')}")
            blocking.append({"id": "run-controller-mode", "status": "FAIL", "blocking": True,
                             "detail": f"mode={run_controller.get('mode')}"})
            add_check(checks, "run-controller-mode", "FAIL", True,
                      f"mode={run_controller.get('mode')}; execution remains intentionally disabled")

    passed = sum(c.get("status") == "PASS" for c in checks)
    failed = sum(c.get("status") == "FAIL" for c in checks)
    unknown = sum(c.get("status") == "UNKNOWN" for c in checks)
    status = "PASS" if not [c for c in checks if c.get("blocking") and c.get("status") != "PASS"] else "FAIL"
    ready = "YES" if args.profile != "contract" and status == "PASS" else "NO"
    report = {
        "schema": REPORT_SCHEMA,
        "profile": args.profile,
        "project": args.project,
        "observed_at": now_iso(),
        "status": status,
        "ready_for_execution": ready,
        "checks": checks,
        "blockers": [f"{c['id']}:{c['status']}:{c['detail']}" for c in checks if c.get("blocking") and c.get("status") != "PASS"],
        "warnings": warnings,
        "summary": {
            "total": len(checks),
            "passed": passed,
            "failed": failed,
            "unknown": unknown,
            "blocking_failures": sum(c.get("blocking") and c.get("status") != "PASS" for c in checks),
        },
        "evidence": evidence,
    }

    if args.output:
        output = args.output if args.output.is_absolute() else repo_root / args.output
        save(output, report)
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(f"PROFILE={args.profile}")
        print(f"PROJECT={args.project}")
        print(f"STATUS={status}")
        print(f"DEV_HUB_READY_FOR_EXECUTION={ready}")
        for item in report["blockers"]:
            print(f"BLOCKER={item}")
        for item in warnings:
            print(f"WARNING={item}")
        if args.output:
            print(f"PLATFORM_READINESS_REPORT={output}")
    return 0 if status == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
