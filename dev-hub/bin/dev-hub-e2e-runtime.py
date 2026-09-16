#!/usr/bin/env python3
"""ChaCha DEV HUB V5 end-to-end control-plane qualification.

This is a CI-only qualification harness. It does not register a new production
provider and it never touches VPS or production state. It creates an isolated
runtime under /tmp and proves the complete control flow through the real DEV HUB
engines:

Manifest V3 -> Project Control audit -> Scheduler -> Run Controller ->
UNVERIFIED provider result -> Project Control -> Verification Broker ->
Evidence Collector -> hash-chained audit -> final integrity verification.

A tiny executable fixture adapter is generated under /tmp only so the Run
Controller can exercise its real provider/adapter protocol. Two negative paths
are also required: scheduler capability blocking and tampered-evidence rejection.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT = "dev-hub-v5-e2e-fixture"
SCHEMA = "chacha.dev/dev-hub-e2e-qualification/v1"
CANONICAL_GATES = [
    "product-domain", "ux-frontend", "api-backend", "data", "integrations",
    "identity-security", "testing", "build-dependencies", "ci-cd-release",
    "environments-infra", "observability", "performance", "reliability-resilience",
    "backup-recovery", "documentation", "operations-sre", "finops-capacity",
    "governance-compliance",
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def save(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit(f"JSON_ROOT_NOT_OBJECT={path}")
    return value


def digest_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def digest_json(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def run(argv: list[str], *, cwd: Path, stdin: str | None = None, expect: int | set[int] = 0) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        argv,
        cwd=str(cwd),
        input=stdin,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        shell=False,
        check=False,
        timeout=120,
    )
    allowed = {expect} if isinstance(expect, int) else set(expect)
    if proc.returncode not in allowed:
        raise SystemExit(
            "E2E_COMMAND_FAILED=" + json.dumps({
                "argv": argv,
                "returncode": proc.returncode,
                "stdout": proc.stdout[-5000:],
                "stderr": proc.stderr[-5000:],
            }, ensure_ascii=False)
        )
    return proc


def run_json(argv: list[str], *, cwd: Path, expect: int | set[int] = 0) -> dict[str, Any]:
    proc = run(argv, cwd=cwd, expect=expect)
    try:
        value = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"E2E_JSON_OUTPUT_INVALID={argv[1] if len(argv)>1 else argv[0]}:{exc}:{proc.stdout[-3000:]}")
    if not isinstance(value, dict):
        raise SystemExit("E2E_JSON_OUTPUT_NOT_OBJECT")
    return value


def create_manifest(path: Path) -> dict[str, Any]:
    manifest = {
        "schema": "chacha.dev/project-manifest/v3",
        "identity": {
            "name": "DEV HUB V5 E2E Fixture",
            "slug": PROJECT,
            "lifecycle_stage": "IDEA",
            "criticality": "low",
        },
        "repository": {"provider": "fixture", "name": PROJECT, "default_branch": "none"},
        "ownership": {"product": "e2e-qualification", "technical": "chacha-dev-architect"},
        "components": [
            {"id": "fixture-web", "type": "static-web", "path": ".", "depends_on": [], "commands": {}}
        ],
        "dependencies": [],
        "environments": [
            {"name": "test", "class": "test", "approval_required": False}
        ],
        "capabilities": [
            {"id": "smoke-test-web", "required": True, "preferred_provider": "http-smoke", "fallback_allowed": False}
        ],
        "quality_gates": {gate: {"required": False} for gate in CANONICAL_GATES},
        "storage": {"tiers": [{"name": "ephemeral", "class": "temporary"}], "governor_required": True},
        "technology_policy": {"auto_replace_production": False},
        "recovery": {},
        "agents": [],
        "knowledge_sources": [],
    }
    save(path, manifest)
    return manifest


def create_task_graph(path: Path, *, blocked: bool = False) -> dict[str, Any]:
    capability = "e2e-capability-does-not-exist" if blocked else "smoke-test-web"
    task_id = "e2e:blocked-capability" if blocked else "e2e:smoke"
    output_id = "e2e-blocked-report" if blocked else "e2e-smoke-report"
    graph = {
        "schema": "chacha.dev/task-graph/v1",
        "project": PROJECT,
        "transition": "IDEA->DESIGN",
        "generated_at": now_iso(),
        "tasks": [{
            "id": task_id,
            "kind": "artifact",
            "description": "DEV HUB E2E deterministic fixture task",
            "owner_role": "e2e-fixture-provider",
            "capabilities": [capability],
            "permission": "read",
            "depends_on": [],
            "outputs": [{"type": "artifact", "id": output_id}],
            "verification": {
                "mode": "machine",
                "self_certification_allowed": False,
                "required_evidence": ["source", "timestamp", "digest"],
            },
            "blocking": True,
            "parallel_group": "e2e",
        }],
        "summary": {
            "task_count": 1,
            "artifact_tasks": 1,
            "gate_tasks": 0,
            "approval_tasks": 0,
            "blocking_tasks": 1,
        },
    }
    save(path, graph)
    return graph


def write_fixture_adapter(path: Path, evidence_root: Path) -> None:
    code = f'''#!/usr/bin/env python3
import hashlib,json,sys
from datetime import datetime,timezone
from pathlib import Path
request=json.load(sys.stdin)
task=request.get("task") or {{}}
task_id=str(task.get("id") or "unknown")
root=Path({str(evidence_root)!r})
root.mkdir(parents=True,exist_ok=True)
evidence=root/(task_id.replace(":","_")+".txt")
evidence.write_text("DEV HUB E2E fixture evidence\\nproject="+str(request.get("project"))+"\\nrun_id="+str(request.get("run_id"))+"\\ntask_id="+task_id+"\\n",encoding="utf-8")
digest="sha256:"+hashlib.sha256(evidence.read_bytes()).hexdigest()
outputs=[]
for item in task.get("outputs") or []:
    if isinstance(item,dict) and item.get("type") and item.get("id"):
        outputs.append({{"type":item["type"],"id":item["id"],"status":"OK"}})
observed=datetime.now(timezone.utc).isoformat()
result={{
 "schema":"chacha.dev/task-result/v1",
 "project":request.get("project"),
 "task_id":task_id,
 "status":"OK",
 "producer":"http-smoke-adapter",
 "observed_at":observed,
 "summary":"E2E fixture provider completed read-only task.",
 "evidence":[{{"kind":"report","source":str(evidence),"digest":digest,"details":{{"fixture":True,"run_id":request.get("run_id"),"production":False}}}}],
 "verification":{{"status":"UNVERIFIED","method":"none","verifier":"pending-independent-verifier","observed_at":observed,"notes":"Fixture producer cannot self-verify."}},
 "outputs":outputs,
}}
print(json.dumps(result,separators=(",",":")))
'''
    path.write_text(code, encoding="utf-8")
    path.chmod(0o700)


def configure(root: Path, repo: Path) -> dict[str, Path]:
    cfg = root / "config"
    runtime = root / "runtime"
    paths = {
        "cfg": cfg,
        "runtime": runtime,
        "state_root": runtime / "state",
        "evidence_root": runtime / "evidence",
        "plans_root": runtime / "plans",
        "health_root": runtime / "health",
        "runs_root": runtime / "runs",
        "transactions_root": runtime / "transactions",
        "locks_root": runtime / "locks",
    }
    for p in paths.values():
        p.mkdir(parents=True, exist_ok=True)

    state_policy = load(repo / "dev-hub/config/control-plane-state.v1.json")
    state_policy["storage"]["runtime_root"] = str(paths["state_root"])
    state_policy["storage"]["transaction_root"] = str(paths["transactions_root"])
    state_policy_path = cfg / "control-plane-state.json"
    save(state_policy_path, state_policy)

    run_policy = load(repo / "dev-hub/config/run-controller.v1.json")
    run_policy["mode"] = "execute-enabled"
    run_policy["locking"]["root"] = str(paths["locks_root"] / "run-controller")
    run_policy["dispatch"]["work_root"] = str(paths["runs_root"])
    run_policy_path = cfg / "run-controller.json"
    save(run_policy_path, run_policy)

    fixture_adapter = root / "fixture-adapter"
    write_fixture_adapter(fixture_adapter, root / "provider-evidence")
    adapters = load(repo / "dev-hub/config/provider-adapters.v1.json")
    adapters["adapters"]["http-smoke-adapter"] = {
        "status": "ENABLED",
        "executable": str(fixture_adapter),
        "supports": ["read"],
    }
    adapter_path = cfg / "provider-adapters.json"
    save(adapter_path, adapters)

    policy = load(repo / "dev-hub/config/project-control.v1.json")
    policy["runtime"] = {
        "state_root": str(paths["state_root"]),
        "evidence_root": str(paths["evidence_root"]),
        "plans_root": str(paths["plans_root"]),
        "health_root": str(paths["health_root"]),
        "runs_root": str(paths["runs_root"]),
        "transactions_root": str(paths["transactions_root"]),
        "locks_root": str(paths["locks_root"] / "control"),
    }
    policy["repository_paths"]["control_plane_state"] = str(state_policy_path)
    policy["repository_paths"]["run_controller"] = str(run_policy_path)
    policy["repository_paths"]["provider_adapters"] = str(adapter_path)
    policy_path = cfg / "project-control.json"
    save(policy_path, policy)

    paths.update({
        "state_policy": state_policy_path,
        "run_policy": run_policy_path,
        "adapters": adapter_path,
        "project_policy": policy_path,
        "fixture_adapter": fixture_adapter,
    })
    return paths


def pc(repo: Path, policy: Path, *args: str, expect: int | set[int] = 0) -> dict[str, Any]:
    return run_json([
        sys.executable, str(repo / "dev-hub/bin/project-control.py"),
        "--policy", str(policy), "--repo-root", str(repo), "--json", *args,
    ], cwd=repo, expect=expect)


def find_single_task_result(run_record: dict[str, Any]) -> Path:
    found: list[Path] = []
    for wave in run_record.get("waves") or []:
        for task in wave.get("tasks") or []:
            if task.get("task_result"):
                found.append(Path(str(task["task_result"])))
    if len(found) != 1:
        raise SystemExit(f"E2E_TASK_RESULT_COUNT={len(found)}")
    return found[0]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--work-dir", type=Path, default=Path("/tmp/chacha-dev-hub-v5-e2e"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    repo = args.repo_root.resolve()
    root = args.work_dir.resolve()
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    cfg = configure(root, repo)

    # 1. Manifest V3 ingestion/validation.
    manifest_path = root / "manifest-v3.json"
    create_manifest(manifest_path)
    manifest_report = run_json([
        sys.executable, str(repo / "dev-hub/bin/manifest-v3-engine.py"),
        "inspect", str(manifest_path),
        "--registry", str(repo / "dev-hub/config/capability-registry.v1.json"),
        "--json",
    ], cwd=repo)
    if manifest_report.get("valid") is not True or manifest_report.get("capability_resolution", {}).get("execution_ready") is not True:
        raise SystemExit(f"E2E_MANIFEST_NOT_READY={manifest_report}")

    # 2. Initialize the real hash-chained Control Plane store and Evidence Ledger.
    run([
        sys.executable, str(repo / "dev-hub/bin/control-plane-store.py"),
        "--policy", str(cfg["state_policy"]), "--root", str(cfg["state_root"]),
        "init", "--project", PROJECT, "--actor", "dev-hub-e2e-harness",
    ], cwd=repo)
    ledger = cfg["evidence_root"] / PROJECT / "ledger.json"
    run([
        sys.executable, str(repo / "dev-hub/bin/evidence-collector.py"),
        "init", "--project", PROJECT, "--ledger", str(ledger),
    ], cwd=repo)

    # Record manifest admission through Project Control itself.
    manifest_payload = root / "manifest-ingested.json"
    save(manifest_payload, {
        "kind": "manifest-ingested",
        "manifest": str(manifest_path),
        "manifest_digest": digest_file(manifest_path),
        "validation": {"valid": True, "execution_ready": True},
        "fixture_only": True,
    })
    manifest_event = pc(
        repo, cfg["project_policy"],
        "record-control-event", "--project", PROJECT,
        "--event-type", "DECISION_RECORDED", "--actor", "dev-hub-e2e-harness",
        "--payload", str(manifest_payload),
    )
    if manifest_event.get("status") != "OK":
        raise SystemExit(f"E2E_MANIFEST_CONTROL_EVENT_FAILED={manifest_event}")

    # 3. Fresh provider health and success graph.
    health_path = cfg["health_root"] / PROJECT / "providers.json"
    save(health_path, {
        "schema": "chacha.dev/provider-health-snapshot/v1",
        "observed_at": now_iso(),
        "providers": {
            "http-smoke": {
                "state": "HEALTHY", "checked_at": now_iso(),
                "source": "dev-hub-e2e-fixture-health",
                "details": {"fixture_only": True, "production": False},
            }
        },
    })
    graph_path = root / "task-graph-success.json"
    create_task_graph(graph_path)

    schedule = pc(repo, cfg["project_policy"], "schedule", "--project", PROJECT, "--graph", str(graph_path))
    if schedule.get("status") != "OK" or schedule.get("blockers") != []:
        raise SystemExit(f"E2E_SCHEDULE_FAILED={schedule}")
    plan_path = Path(str((schedule.get("details") or {}).get("execution_plan")))
    plan = load(plan_path)
    first = (((plan.get("waves") or [{}])[0].get("tasks") or [{}])[0])
    binding = ((first.get("provider_bindings") or [{}])[0])
    if binding.get("provider") != "http-smoke" or binding.get("health_state") != "HEALTHY":
        raise SystemExit(f"E2E_PROVIDER_SELECTION_INVALID={binding}")

    # 4. Real Project Control dispatch -> Run Controller -> executable fixture adapter.
    dispatch = pc(
        repo, cfg["project_policy"],
        "dispatch", "--project", PROJECT,
        "--plan", str(plan_path), "--graph", str(graph_path), "--execute",
    )
    if dispatch.get("status") != "OK":
        raise SystemExit(f"E2E_DISPATCH_FAILED={dispatch}")
    run_record_path = Path(str((dispatch.get("details") or {}).get("RUN_RECORD")))
    run_record = load(run_record_path)
    run_id = str(run_record.get("run_id"))
    if not run_id or run_record.get("mode") != "execute" or run_record.get("summary", {}).get("succeeded") != 1:
        raise SystemExit(f"E2E_RUN_RECORD_INVALID={run_record}")
    result_path = find_single_task_result(run_record)
    producer_result = load(result_path)
    if producer_result.get("status") != "OK" or (producer_result.get("verification") or {}).get("status") != "UNVERIFIED":
        raise SystemExit(f"E2E_PROVIDER_RESULT_TRUST_BOUNDARY_FAILED={producer_result}")

    # 5. Real Project Control verification + Evidence Collector ingestion + audit link.
    verify = pc(
        repo, cfg["project_policy"],
        "verify-result", "--project", PROJECT,
        "--result", str(result_path), "--graph", str(graph_path),
        "--method", "machine", "--verifier", "verification-broker", "--ingest",
    )
    if verify.get("status") != "OK" or (verify.get("details") or {}).get("verification_status") != "VERIFIED":
        raise SystemExit(f"E2E_VERIFICATION_FAILED={verify}")
    verified_ledger = load(ledger)
    artifact = (verified_ledger.get("artifacts") or {}).get("e2e-smoke-report") or {}
    if artifact.get("status") != "OK" or artifact.get("producer") != "http-smoke-adapter" or artifact.get("verifier") != "verification-broker":
        raise SystemExit(f"E2E_LEDGER_CORRELATION_FAILED={artifact}")

    integrity = pc(repo, cfg["project_policy"], "verify-state", "--project", PROJECT)
    if integrity.get("status") != "OK":
        raise SystemExit(f"E2E_AUDIT_INTEGRITY_FAILED={integrity}")

    # Locate verification report committed by Project Control transaction.
    verify_report_path = Path(str((verify.get("details") or {}).get("report")))
    verification_report = load(verify_report_path)
    if verification_report.get("status") != "VERIFIED" or verification_report.get("verifier") != "verification-broker":
        raise SystemExit(f"E2E_VERIFICATION_REPORT_INVALID={verification_report}")

    # 6. Negative scheduler path: unknown capability must fail closed.
    blocked_graph_path = root / "task-graph-blocked.json"
    create_task_graph(blocked_graph_path, blocked=True)
    blocked_schedule = pc(
        repo, cfg["project_policy"],
        "schedule", "--project", PROJECT, "--graph", str(blocked_graph_path), expect={0, 2},
    )
    if blocked_schedule.get("status") != "BLOCKED" or not any("CAPABILITY_BLOCKED" in x for x in blocked_schedule.get("blockers") or []):
        raise SystemExit(f"E2E_BLOCKER_PATH_NOT_FAIL_CLOSED={blocked_schedule}")

    # 7. Negative verification path: tamper the evidence after production.
    tampered = load(result_path)
    tampered_path = root / "tampered-task-result.json"
    evidence_source = Path(str((tampered.get("evidence") or [{}])[0].get("source")))
    evidence_source.write_text(evidence_source.read_text(encoding="utf-8") + "tampered-after-provider\n", encoding="utf-8")
    save(tampered_path, tampered)
    tampered_verify = pc(
        repo, cfg["project_policy"],
        "verify-result", "--project", PROJECT,
        "--result", str(tampered_path), "--graph", str(graph_path),
        "--method", "machine", "--verifier", "verification-broker", expect={0, 2},
    )
    if tampered_verify.get("status") not in {"FAILED", "BLOCKED"}:
        raise SystemExit(f"E2E_TAMPERED_EVIDENCE_ACCEPTED={tampered_verify}")
    if not any("VERIFICATION_STATUS:REJECTED" in x for x in tampered_verify.get("blockers") or []):
        raise SystemExit(f"E2E_TAMPERED_EVIDENCE_NOT_REJECTED={tampered_verify}")

    # Correlation artifact: one run chain from manifest through verifier/audit.
    audit_path = cfg["state_root"] / PROJECT / "audit.jsonl"
    audit_lines = [json.loads(x) for x in audit_path.read_text(encoding="utf-8").splitlines() if x.strip()]
    evidence_event = [x for x in audit_lines if x.get("event_type") == "EVIDENCE_RECORDED"]
    if len(evidence_event) != 1:
        raise SystemExit(f"E2E_EVIDENCE_AUDIT_EVENT_COUNT={len(evidence_event)}")

    summary = {
        "schema": SCHEMA,
        "project": PROJECT,
        "qualified_at": now_iso(),
        "fixture_scope": "ci-only-no-provider-registration",
        "production_mutation": False,
        "vps_mutation": False,
        "manifest": {
            "path": str(manifest_path),
            "digest": digest_file(manifest_path),
            "valid": True,
            "execution_ready": True,
            "project_control_event": "DECISION_RECORDED",
        },
        "provider_selection": {
            "capability": "smoke-test-web",
            "provider": "http-smoke",
            "adapter": "http-smoke-adapter",
            "health": "HEALTHY",
            "fixture_adapter_override": True,
        },
        "execution": {
            "run_id": run_id,
            "run_record": str(run_record_path),
            "task_id": producer_result.get("task_id"),
            "producer": producer_result.get("producer"),
            "producer_result_status": producer_result.get("status"),
            "producer_result_verification": (producer_result.get("verification") or {}).get("status"),
            "result_digest": digest_json(producer_result),
        },
        "verification": {
            "verifier": verification_report.get("verifier"),
            "method": verification_report.get("method"),
            "status": verification_report.get("status"),
            "report": str(verify_report_path),
            "report_digest": digest_json(verification_report),
        },
        "evidence_ledger": {
            "path": str(ledger),
            "artifact": "e2e-smoke-report",
            "status": artifact.get("status"),
            "producer": artifact.get("producer"),
            "verifier": artifact.get("verifier"),
        },
        "audit": {
            "path": str(audit_path),
            "chain_integrity": "PASS",
            "event_count": len(audit_lines),
            "evidence_event_sequence": evidence_event[0].get("sequence"),
            "evidence_event_digest": evidence_event[0].get("event_digest"),
        },
        "negative_paths": {
            "unknown_capability": "BLOCKED",
            "tampered_evidence": "REJECTED",
        },
        "gates": {
            "manifest_ingested": "PASS",
            "provider_selected": "PASS",
            "scheduler_plan": "PASS",
            "run_controller_dispatch": "PASS",
            "producer_result_unverified": "PASS",
            "independent_verification": "PASS",
            "evidence_ingested": "PASS",
            "audit_correlated": "PASS",
            "blocker_path": "PASS",
            "tamper_rejection": "PASS",
        },
        "status": "E2E_QUALIFIED",
        "blockers": [],
    }
    output = args.output or (root / "e2e-qualification.json")
    save(output, summary)
    print(f"DEV_HUB_E2E_STATUS={summary['status']}")
    print(f"DEV_HUB_E2E_RUN_ID={run_id}")
    print(f"DEV_HUB_E2E_OUTPUT={output}")
    print("DEV_HUB_E2E_NEGATIVE_PATHS=unknown-capability:BLOCKED,tampered-evidence:REJECTED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
