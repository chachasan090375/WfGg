#!/usr/bin/env python3
"""DEV HUB V5 end-to-end control-plane qualification (CI-only).

Uses the real Manifest V3, Project Control, Scheduler, Run Controller,
Verification Broker, Evidence Collector and hash-chained Control Plane Store.
All mutable state and the executable fixture adapter live under /tmp only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT = "dev-hub-v5-e2e-fixture"
SCHEMA = "chacha.dev/dev-hub-e2e-qualification/v1"
GATES = [
    "product-domain", "ux-frontend", "api-backend", "data", "integrations",
    "identity-security", "testing", "build-dependencies", "ci-cd-release",
    "environments-infra", "observability", "performance", "reliability-resilience",
    "backup-recovery", "documentation", "operations-sre", "finops-capacity",
    "governance-compliance",
]


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def save(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit(f"JSON_ROOT_NOT_OBJECT={path}")
    return value


def file_digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def json_digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def run(argv: list[str], repo: Path, allowed: set[int] | None = None) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        argv, cwd=str(repo), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, shell=False, check=False, timeout=120,
    )
    allowed = allowed or {0}
    if proc.returncode not in allowed:
        raise SystemExit("E2E_COMMAND_FAILED=" + json.dumps({
            "argv": argv, "returncode": proc.returncode,
            "stdout": proc.stdout[-5000:], "stderr": proc.stderr[-5000:],
        }, ensure_ascii=False))
    return proc


def run_json(argv: list[str], repo: Path, allowed: set[int] | None = None) -> dict[str, Any]:
    proc = run(argv, repo, allowed)
    try:
        value = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"E2E_JSON_INVALID={exc}:{proc.stdout[-3000:]}")
    if not isinstance(value, dict):
        raise SystemExit("E2E_JSON_NOT_OBJECT")
    return value


def manifest(path: Path) -> None:
    save(path, {
        "schema": "chacha.dev/project-manifest/v3",
        "identity": {"name": "DEV HUB V5 E2E Fixture", "slug": PROJECT, "lifecycle_stage": "IDEA", "criticality": "low"},
        "repository": {"provider": "fixture", "name": PROJECT, "default_branch": "none"},
        "ownership": {"product": "e2e-qualification", "technical": "chacha-dev-architect"},
        "components": [{"id": "fixture-web", "type": "static-web", "path": ".", "depends_on": [], "commands": {}}],
        "dependencies": [],
        "environments": [{"name": "test", "class": "test", "approval_required": False}],
        "capabilities": [{"id": "smoke-test-web", "required": True, "preferred_provider": "http-smoke", "fallback_allowed": False}],
        "quality_gates": {gate: {"required": False} for gate in GATES},
        "storage": {"tiers": [{"name": "ephemeral", "class": "temporary"}], "governor_required": True},
        "technology_policy": {"auto_replace_production": False},
        "recovery": {}, "agents": [], "knowledge_sources": [],
    })


def graph(path: Path, blocked: bool = False) -> None:
    capability = "e2e-capability-does-not-exist" if blocked else "smoke-test-web"
    tid = "e2e:blocked-capability" if blocked else "e2e:smoke"
    oid = "e2e-blocked-report" if blocked else "e2e-smoke-report"
    save(path, {
        "schema": "chacha.dev/task-graph/v1", "project": PROJECT,
        "transition": "IDEA->DESIGN", "generated_at": now(),
        "tasks": [{
            "id": tid, "kind": "artifact", "description": "DEV HUB E2E deterministic fixture task",
            "owner_role": "e2e-fixture-provider", "capabilities": [capability], "permission": "read",
            "depends_on": [], "outputs": [{"type": "artifact", "id": oid}],
            "verification": {"mode": "machine", "self_certification_allowed": False,
                             "required_evidence": ["source", "timestamp", "digest"]},
            "blocking": True, "parallel_group": "e2e",
        }],
        "summary": {"task_count": 1, "artifact_tasks": 1, "gate_tasks": 0, "approval_tasks": 0, "blocking_tasks": 1},
    })


def fixture_adapter(path: Path, evidence_root: Path) -> None:
    code = f'''#!/usr/bin/env python3
import hashlib,json,sys
from datetime import datetime,timezone
from pathlib import Path
request=json.load(sys.stdin)
task=request.get("task") or {{}}
task_id=str(task.get("id") or "unknown")
root=Path({str(evidence_root)!r}); root.mkdir(parents=True,exist_ok=True)
evidence=root/(task_id.replace(":","_")+".txt")
evidence.write_text("DEV HUB E2E fixture evidence\\nproject="+str(request.get("project"))+"\\nrun_id="+str(request.get("run_id"))+"\\ntask_id="+task_id+"\\n",encoding="utf-8")
digest="sha256:"+hashlib.sha256(evidence.read_bytes()).hexdigest()
observed=datetime.now(timezone.utc).isoformat()
outputs=[{{"type":x["type"],"id":x["id"],"status":"OK"}} for x in task.get("outputs") or [] if isinstance(x,dict) and x.get("type") and x.get("id")]
print(json.dumps({{
 "schema":"chacha.dev/task-result/v1","project":request.get("project"),"task_id":task_id,
 "status":"OK","producer":"http-smoke-adapter","observed_at":observed,
 "summary":"E2E fixture provider completed read-only task.",
 "evidence":[{{"kind":"report","source":str(evidence),"digest":digest,"details":{{"fixture":True,"run_id":request.get("run_id"),"production":False}}}}],
 "verification":{{"status":"UNVERIFIED","method":"none","verifier":"pending-independent-verifier","observed_at":observed,"notes":"Fixture producer cannot self-verify."}},
 "outputs":outputs
}},separators=(",",":")))
'''
    path.write_text(code, encoding="utf-8")
    path.chmod(0o700)


def configure(root: Path, repo: Path) -> dict[str, Path]:
    runtime = root / "runtime"
    cfg = root / "config"
    p = {
        "state": runtime / "state", "evidence": runtime / "evidence",
        "plans": runtime / "plans", "health": runtime / "health",
        "runs": runtime / "runs", "transactions": runtime / "transactions",
        "locks": runtime / "locks", "cfg": cfg,
    }
    for value in p.values():
        value.mkdir(parents=True, exist_ok=True)

    state_policy = load(repo / "dev-hub/config/control-plane-state.v1.json")
    state_policy["storage"]["runtime_root"] = str(p["state"])
    state_policy["storage"]["transaction_root"] = str(p["transactions"])
    p["state_policy"] = cfg / "control-plane-state.json"
    save(p["state_policy"], state_policy)

    run_policy = load(repo / "dev-hub/config/run-controller.v1.json")
    run_policy["mode"] = "execute-enabled"
    run_policy["locking"]["root"] = str(p["locks"] / "run-controller")
    run_policy["dispatch"]["work_root"] = str(p["runs"])
    p["run_policy"] = cfg / "run-controller.json"
    save(p["run_policy"], run_policy)

    p["fixture_adapter"] = root / "fixture-adapter"
    fixture_adapter(p["fixture_adapter"], root / "provider-evidence")
    adapters = load(repo / "dev-hub/config/provider-adapters.v1.json")
    adapters["adapters"]["http-smoke-adapter"] = {
        "status": "ENABLED", "executable": str(p["fixture_adapter"]), "supports": ["read"]
    }
    p["adapters"] = cfg / "provider-adapters.json"
    save(p["adapters"], adapters)

    policy = load(repo / "dev-hub/config/project-control.v1.json")
    policy["runtime"] = {
        "state_root": str(p["state"]), "evidence_root": str(p["evidence"]),
        "plans_root": str(p["plans"]), "health_root": str(p["health"]),
        "runs_root": str(p["runs"]), "transactions_root": str(p["transactions"]),
        "locks_root": str(p["locks"] / "control"),
    }
    policy["repository_paths"]["control_plane_state"] = str(p["state_policy"])
    policy["repository_paths"]["run_controller"] = str(p["run_policy"])
    policy["repository_paths"]["provider_adapters"] = str(p["adapters"])
    p["project_policy"] = cfg / "project-control.json"
    save(p["project_policy"], policy)
    return p


def pc(repo: Path, policy: Path, *args: str, allowed: set[int] | None = None) -> dict[str, Any]:
    return run_json([
        sys.executable, str(repo / "dev-hub/bin/project-control.py"),
        "--policy", str(policy), "--repo-root", str(repo), "--json", *args,
    ], repo, allowed)


def task_result_from(run_record: dict[str, Any]) -> Path:
    found = [Path(str(t["task_result"])) for w in run_record.get("waves") or []
             for t in w.get("tasks") or [] if t.get("task_result")]
    if len(found) != 1:
        raise SystemExit(f"E2E_TASK_RESULT_COUNT={len(found)}")
    return found[0]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", type=Path, default=Path.cwd())
    ap.add_argument("--work-dir", type=Path, default=Path("/tmp/chacha-dev-hub-v5-e2e"))
    ap.add_argument("--output", type=Path)
    args = ap.parse_args()
    repo, root = args.repo_root.resolve(), args.work_dir.resolve()
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    cfg = configure(root, repo)

    # Manifest V3.
    manifest_path = root / "manifest-v3.json"
    manifest(manifest_path)
    m = run_json([
        sys.executable, str(repo / "dev-hub/bin/manifest-v3-engine.py"), "inspect", str(manifest_path),
        "--registry", str(repo / "dev-hub/config/capability-registry.v1.json"), "--json",
    ], repo)
    if m.get("valid") is not True or m.get("capability_resolution", {}).get("execution_ready") is not True:
        raise SystemExit(f"E2E_MANIFEST_NOT_READY={m}")

    # Canonical temporary control-plane store and evidence ledger.
    run([sys.executable, str(repo / "dev-hub/bin/control-plane-store.py"),
         "--policy", str(cfg["state_policy"]), "--root", str(cfg["state"]),
         "init", "--project", PROJECT, "--actor", "dev-hub-e2e-harness"], repo)
    ledger = cfg["evidence"] / PROJECT / "ledger.json"
    run([sys.executable, str(repo / "dev-hub/bin/evidence-collector.py"),
         "init", "--project", PROJECT, "--ledger", str(ledger)], repo)

    manifest_payload = root / "manifest-ingested.json"
    save(manifest_payload, {"kind": "manifest-ingested", "manifest": str(manifest_path),
                            "manifest_digest": file_digest(manifest_path),
                            "validation": {"valid": True, "execution_ready": True}, "fixture_only": True})
    ev = pc(repo, cfg["project_policy"], "record-control-event", "--project", PROJECT,
            "--event-type", "DECISION_RECORDED", "--actor", "dev-hub-e2e-harness",
            "--payload", str(manifest_payload))
    if ev.get("status") != "OK":
        raise SystemExit(f"E2E_MANIFEST_CONTROL_EVENT_FAILED={ev}")

    # Fresh health, scheduling, provider selection.
    health = cfg["health"] / PROJECT / "providers.json"
    save(health, {"schema": "chacha.dev/provider-health-snapshot/v1", "observed_at": now(),
                  "providers": {"http-smoke": {"state": "HEALTHY", "checked_at": now(),
                  "source": "dev-hub-e2e-fixture-health", "details": {"fixture_only": True, "production": False}}}})
    graph_path = root / "task-graph-success.json"
    graph(graph_path)
    schedule = pc(repo, cfg["project_policy"], "schedule", "--project", PROJECT, "--graph", str(graph_path))
    if schedule.get("status") != "OK" or schedule.get("blockers"):
        raise SystemExit(f"E2E_SCHEDULE_FAILED={schedule}")
    plan_path = Path(str((schedule.get("details") or {}).get("execution_plan")))
    plan = load(plan_path)
    binding = ((((plan.get("waves") or [{}])[0].get("tasks") or [{}])[0].get("provider_bindings") or [{}])[0])
    if binding.get("provider") != "http-smoke" or binding.get("health_state") != "HEALTHY":
        raise SystemExit(f"E2E_PROVIDER_SELECTION_INVALID={binding}")

    # Project Control -> Run Controller -> fixture adapter.
    dispatch = pc(repo, cfg["project_policy"], "dispatch", "--project", PROJECT,
                  "--plan", str(plan_path), "--graph", str(graph_path), "--execute")
    if dispatch.get("status") != "OK":
        raise SystemExit(f"E2E_DISPATCH_FAILED={dispatch}")
    run_record_path = Path(str((dispatch.get("details") or {}).get("RUN_RECORD")))
    run_record = load(run_record_path)
    run_id = str(run_record.get("run_id") or "")
    if not run_id or run_record.get("mode") != "execute" or run_record.get("summary", {}).get("succeeded") != 1:
        raise SystemExit(f"E2E_RUN_RECORD_INVALID={run_record}")
    result_path = task_result_from(run_record)
    producer_result = load(result_path)
    if producer_result.get("status") != "OK" or (producer_result.get("verification") or {}).get("status") != "UNVERIFIED":
        raise SystemExit(f"E2E_PROVIDER_RESULT_TRUST_BOUNDARY_FAILED={producer_result}")

    # Independent verification, ledger ingestion and audit commit.
    verify = pc(repo, cfg["project_policy"], "verify-result", "--project", PROJECT,
                "--result", str(result_path), "--graph", str(graph_path), "--method", "machine",
                "--verifier", "verification-broker", "--ingest")
    details = verify.get("details") or {}
    if verify.get("status") != "OK" or details.get("verification_status") != "VERIFIED":
        raise SystemExit(f"E2E_VERIFICATION_FAILED={verify}")
    txid = str(details.get("transaction_id") or "")
    if not txid:
        raise SystemExit(f"E2E_VERIFICATION_TRANSACTION_MISSING={verify}")
    verify_report_path = cfg["transactions"] / PROJECT / txid / "verification-report.json"
    verification_report = load(verify_report_path)
    if verification_report.get("status") != "VERIFIED" or verification_report.get("verifier") != "verification-broker":
        raise SystemExit(f"E2E_VERIFICATION_REPORT_INVALID={verification_report}")
    verified_ledger = load(ledger)
    artifact = (verified_ledger.get("artifacts") or {}).get("e2e-smoke-report") or {}
    if artifact.get("status") != "OK" or artifact.get("producer") != "http-smoke-adapter" or artifact.get("verifier") != "verification-broker":
        raise SystemExit(f"E2E_LEDGER_CORRELATION_FAILED={artifact}")
    integrity = pc(repo, cfg["project_policy"], "verify-state", "--project", PROJECT)
    if integrity.get("status") != "OK":
        raise SystemExit(f"E2E_AUDIT_INTEGRITY_FAILED={integrity}")

    # Fail-closed scheduler path.
    blocked_graph = root / "task-graph-blocked.json"
    graph(blocked_graph, True)
    bs = pc(repo, cfg["project_policy"], "schedule", "--project", PROJECT, "--graph", str(blocked_graph), allowed={0, 2})
    if bs.get("status") != "BLOCKED" or not any("CAPABILITY_BLOCKED" in x for x in bs.get("blockers") or []):
        raise SystemExit(f"E2E_BLOCKER_PATH_NOT_FAIL_CLOSED={bs}")

    # Fail-closed verification path: change evidence bytes without changing declared digest.
    tampered = load(result_path)
    evidence_source = Path(str((tampered.get("evidence") or [{}])[0].get("source")))
    evidence_source.write_text(evidence_source.read_text(encoding="utf-8") + "tampered-after-provider\n", encoding="utf-8")
    tampered_path = root / "tampered-task-result.json"
    save(tampered_path, tampered)
    tv = pc(repo, cfg["project_policy"], "verify-result", "--project", PROJECT,
            "--result", str(tampered_path), "--graph", str(graph_path), "--method", "machine",
            "--verifier", "verification-broker", allowed={0, 2})
    if tv.get("status") not in {"FAILED", "BLOCKED"} or not any("VERIFICATION_STATUS:REJECTED" in x for x in tv.get("blockers") or []):
        raise SystemExit(f"E2E_TAMPERED_EVIDENCE_ACCEPTED={tv}")

    # Final correlation from Project Control audit.
    audit_path = cfg["state"] / PROJECT / "audit.jsonl"
    events = [json.loads(x) for x in audit_path.read_text(encoding="utf-8").splitlines() if x.strip()]
    evidence_events = [x for x in events if x.get("event_type") == "EVIDENCE_RECORDED"]
    if len(evidence_events) != 1:
        raise SystemExit(f"E2E_EVIDENCE_AUDIT_EVENT_COUNT={len(evidence_events)}")

    summary = {
        "schema": SCHEMA, "project": PROJECT, "qualified_at": now(),
        "fixture_scope": "ci-only-no-provider-registration", "production_mutation": False, "vps_mutation": False,
        "manifest": {"path": str(manifest_path), "digest": file_digest(manifest_path), "valid": True,
                     "execution_ready": True, "project_control_event": "DECISION_RECORDED"},
        "provider_selection": {"capability": "smoke-test-web", "provider": "http-smoke",
                               "adapter": "http-smoke-adapter", "health": "HEALTHY", "fixture_adapter_override": True},
        "execution": {"run_id": run_id, "run_record": str(run_record_path), "task_id": producer_result.get("task_id"),
                      "producer": producer_result.get("producer"), "producer_result_status": producer_result.get("status"),
                      "producer_result_verification": (producer_result.get("verification") or {}).get("status"),
                      "result_digest": json_digest(producer_result)},
        "verification": {"verifier": verification_report.get("verifier"), "method": verification_report.get("method"),
                         "status": verification_report.get("status"), "report": str(verify_report_path),
                         "report_digest": json_digest(verification_report)},
        "evidence_ledger": {"path": str(ledger), "artifact": "e2e-smoke-report", "status": artifact.get("status"),
                            "producer": artifact.get("producer"), "verifier": artifact.get("verifier")},
        "audit": {"path": str(audit_path), "chain_integrity": "PASS", "event_count": len(events),
                  "evidence_event_sequence": evidence_events[0].get("sequence"),
                  "evidence_event_digest": evidence_events[0].get("event_digest")},
        "negative_paths": {"unknown_capability": "BLOCKED", "tampered_evidence": "REJECTED"},
        "gates": {"manifest_ingested": "PASS", "provider_selected": "PASS", "scheduler_plan": "PASS",
                  "run_controller_dispatch": "PASS", "producer_result_unverified": "PASS",
                  "independent_verification": "PASS", "evidence_ingested": "PASS", "audit_correlated": "PASS",
                  "blocker_path": "PASS", "tamper_rejection": "PASS"},
        "status": "E2E_QUALIFIED", "blockers": [],
    }
    output = args.output or root / "e2e-qualification.json"
    save(output, summary)
    print("DEV_HUB_E2E_STATUS=E2E_QUALIFIED")
    print(f"DEV_HUB_E2E_RUN_ID={run_id}")
    print(f"DEV_HUB_E2E_OUTPUT={output}")
    print("DEV_HUB_E2E_NEGATIVE_PATHS=unknown-capability:BLOCKED,tampered-evidence:REJECTED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
