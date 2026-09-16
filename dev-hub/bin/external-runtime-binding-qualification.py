#!/usr/bin/env python3
"""Qualify real external-provider dispatch through Project Control.

Runs Chrome DevTools MCP as an actual ENABLED external provider while preserving
its canonical registry entry at executable=null. A digest-bound executable copy
is staged under /tmp and supplied through CHACHA_DEV_HUB_RUNTIME_BINDINGS.

This qualification intentionally expects Verification Broker to return
NEEDS_INDEPENDENT_CHECK for the current Chrome URL-backed evidence source. That
is not hidden or upgraded: it becomes the next explicit platform gap.
"""
from __future__ import annotations

import argparse
import hashlib
import http.server
import json
import os
import shutil
import socketserver
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT = "dev-hub-v5-external-chrome-fixture"
SCHEMA = "chacha.dev/external-runtime-dispatch-qualification/v1"


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


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def run_json(argv: list[str], repo: Path, env: dict[str, str], allowed: set[int] | None = None) -> dict[str, Any]:
    p = subprocess.run(argv, cwd=str(repo), env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       text=True, shell=False, check=False, timeout=120)
    allowed = allowed or {0}
    if p.returncode not in allowed:
        raise SystemExit("EXTERNAL_RUNTIME_COMMAND_FAILED=" + json.dumps({
            "argv": argv, "returncode": p.returncode, "stdout": p.stdout[-5000:], "stderr": p.stderr[-5000:]
        }, ensure_ascii=False))
    try:
        value = json.loads(p.stdout)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"EXTERNAL_RUNTIME_JSON_INVALID={exc}:{p.stdout[-3000:]}")
    if not isinstance(value, dict):
        raise SystemExit("EXTERNAL_RUNTIME_JSON_NOT_OBJECT")
    return value


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api/ping":
            body = b'{"ok":true,"source":"external-runtime-binding"}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers(); self.wfile.write(body); return
        body = b'''<!doctype html><html><head><title>External Runtime Binding</title></head><body><h1>external-runtime-binding-ready</h1><script>console.log('external-runtime-console-ok');fetch('/api/ping')</script></body></html>'''
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers(); self.wfile.write(body)

    def log_message(self, *_args):
        pass


class Server(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


def pc(repo: Path, policy: Path, env: dict[str, str], *args: str, allowed: set[int] | None = None) -> dict[str, Any]:
    return run_json([
        sys.executable, str(repo / "dev-hub/bin/project-control.py"),
        "--policy", str(policy), "--repo-root", str(repo), "--json", *args,
    ], repo, env, allowed)


def configure(repo: Path, root: Path) -> dict[str, Path]:
    runtime, cfg = root / "runtime", root / "config"
    dirs = {name: runtime / name for name in ("state", "evidence", "plans", "health", "runs", "transactions", "locks")}
    for p in [cfg, *dirs.values()]:
        p.mkdir(parents=True, exist_ok=True)

    state = load(repo / "dev-hub/config/control-plane-state.v1.json")
    state["storage"]["runtime_root"] = str(dirs["state"])
    state["storage"]["transaction_root"] = str(dirs["transactions"])
    state_path = cfg / "control-plane-state.json"; save(state_path, state)

    run_policy = load(repo / "dev-hub/config/run-controller.v1.json")
    run_policy["mode"] = "execute-enabled"
    run_policy["locking"]["root"] = str(dirs["locks"] / "run-controller")
    run_policy["dispatch"]["work_root"] = str(dirs["runs"])
    run_policy_path = cfg / "run-controller.json"; save(run_policy_path, run_policy)

    capabilities = load(repo / "dev-hub/config/capability-registry.v1.json")
    capabilities.setdefault("capabilities", {})["browser-diagnostics"] = {
        "class": "verification",
        "providers": [{
            "id": "chrome-devtools-mcp", "status": "ADOPT", "health": "mcp-runtime",
            "cost_class": "free", "scope": "test-preview", "fallback": ["playwright-mcp"]
        }]
    }
    capability_path = cfg / "capability-registry.json"; save(capability_path, capabilities)

    project_policy = load(repo / "dev-hub/config/project-control.v1.json")
    project_policy["runtime"] = {
        "state_root": str(dirs["state"]), "evidence_root": str(dirs["evidence"]),
        "plans_root": str(dirs["plans"]), "health_root": str(dirs["health"]),
        "runs_root": str(dirs["runs"]), "transactions_root": str(dirs["transactions"]),
        "locks_root": str(dirs["locks"] / "control"),
    }
    project_policy["repository_paths"]["control_plane_state"] = str(state_path)
    project_policy["repository_paths"]["run_controller"] = str(run_policy_path)
    project_policy["repository_paths"]["capability_registry"] = str(capability_path)
    project_policy["engine_paths"]["run_controller"] = "dev-hub/bin/run-controller-external-dispatch.py"
    project_policy_path = cfg / "project-control.json"; save(project_policy_path, project_policy)

    return {**dirs, "state_policy": state_path, "run_policy": run_policy_path,
            "capabilities": capability_path, "project_policy": project_policy_path}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", type=Path, default=Path.cwd())
    ap.add_argument("--work-dir", type=Path, default=Path("/tmp/chacha-external-runtime-binding"))
    ap.add_argument("--output", type=Path)
    args = ap.parse_args()
    repo, root = args.repo_root.resolve(), args.work_dir.resolve()
    if root.exists(): shutil.rmtree(root)
    root.mkdir(parents=True)

    required = ["CHACHA_CHROME_DEVTOOLS_MCP_SERVER", "CHACHA_CHROME_DEVTOOLS_MCP_WORKDIR",
                "CHACHA_CHROME_DEVTOOLS_MCP_PACKAGE_VERSION", "CHACHA_CHROME_DEVTOOLS_BROWSER_VERSION"]
    missing = [x for x in required if not os.environ.get(x)]
    if missing: raise SystemExit("EXTERNAL_RUNTIME_ENV_MISSING=" + ",".join(missing))

    cfg = configure(repo, root)
    adapter_source = repo / "dev-hub/adapters/chrome-devtools-mcp-adapter.py"
    staged_adapter = root / "runtime-binding" / "chrome-devtools-mcp-adapter"
    staged_adapter.parent.mkdir(parents=True)
    shutil.copy2(adapter_source, staged_adapter); staged_adapter.chmod(0o700)
    source_digest = digest(adapter_source)
    if digest(staged_adapter) != source_digest:
        raise SystemExit("EXTERNAL_RUNTIME_STAGED_ADAPTER_DIGEST_MISMATCH")

    canonical = load(repo / "dev-hub/config/provider-adapters.v1.json")
    chrome = canonical["adapters"]["chrome-devtools-mcp-adapter"]
    if chrome != {"status": "ENABLED", "executable": None, "supports": ["read"]}:
        raise SystemExit(f"EXTERNAL_RUNTIME_CANONICAL_BOUNDARY_INVALID={chrome}")

    binding = root / "runtime-binding.json"
    save(binding, {
        "schema": "chacha.dev/external-runtime-bindings/v1",
        "scope": "ephemeral-runner", "observed_at": now(),
        "production_capable": False, "authoritative_registry_mutated": False,
        "bindings": [{"adapter": "chrome-devtools-mcp-adapter", "provider": "chrome-devtools-mcp",
                      "executable": str(staged_adapter), "digest": source_digest}],
    })

    state_init = subprocess.run([
        sys.executable, str(repo / "dev-hub/bin/control-plane-store.py"), "--policy", str(cfg["state_policy"]),
        "--root", str(cfg["state"]), "init", "--project", PROJECT, "--actor", "external-runtime-binding-qualification"
    ], cwd=str(repo), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
    if state_init.returncode != 0: raise SystemExit(state_init.stderr or state_init.stdout)
    ledger = cfg["evidence"] / PROJECT / "ledger.json"
    ledger_init = subprocess.run([
        sys.executable, str(repo / "dev-hub/bin/evidence-collector.py"), "init", "--project", PROJECT, "--ledger", str(ledger)
    ], cwd=str(repo), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
    if ledger_init.returncode != 0: raise SystemExit(ledger_init.stderr or ledger_init.stdout)

    with Server(("127.0.0.1", 0), Handler) as server:
        threading.Thread(target=server.serve_forever, daemon=True).start()
        origin = f"http://127.0.0.1:{server.server_address[1]}"
        graph = root / "task-graph.json"
        save(graph, {
            "schema": "chacha.dev/task-graph/v1", "project": PROJECT, "transition": "IDEA->DESIGN", "generated_at": now(),
            "tasks": [{
                "id": "external:chrome-diagnostics", "kind": "artifact",
                "description": "Qualify actual external Chrome DevTools MCP dispatch", "owner_role": "dev-hub-runtime",
                "capabilities": ["browser-diagnostics"], "permission": "read", "depends_on": [],
                "metadata": {"chrome_devtools_mcp": {"operation": "inspect_url", "url": origin + "/", "expected_text": "external-runtime-binding-ready"}},
                "outputs": [{"type": "artifact", "id": "chrome-devtools-mcp-controlled-diagnostics"}],
                "verification": {"mode": "machine", "self_certification_allowed": False,
                                 "required_evidence": ["source", "timestamp", "digest"]},
                "blocking": True, "parallel_group": "external-runtime"
            }],
            "summary": {"task_count": 1, "artifact_tasks": 1, "gate_tasks": 0, "approval_tasks": 0, "blocking_tasks": 1}
        })
        health = cfg["health"] / PROJECT / "providers.json"
        save(health, {"schema": "chacha.dev/provider-health-snapshot/v1", "observed_at": now(),
                      "providers": {"chrome-devtools-mcp": {"state": "HEALTHY", "checked_at": now(),
                      "source": "external-runtime-binding-qualification", "details": {"package": "1.9.0", "production": False}}}})

        env = os.environ.copy()
        env.update({
            "CHACHA_DEV_HUB_RUNTIME_BINDINGS": str(binding),
            "CHACHA_CHROME_DEVTOOLS_ALLOWED_ORIGIN": origin,
            "CHACHA_CHROME_DEVTOOLS_TARGET_CLASS": "test",
        })
        schedule = pc(repo, cfg["project_policy"], env, "schedule", "--project", PROJECT, "--graph", str(graph))
        if schedule.get("status") != "OK": raise SystemExit(f"EXTERNAL_RUNTIME_SCHEDULE_FAILED={schedule}")
        plan_path = Path(str((schedule.get("details") or {}).get("execution_plan")))
        plan = load(plan_path)
        selected = ((((plan.get("waves") or [{}])[0].get("tasks") or [{}])[0].get("provider_bindings") or [{}])[0])
        if selected.get("provider") != "chrome-devtools-mcp" or selected.get("health_state") != "HEALTHY":
            raise SystemExit(f"EXTERNAL_RUNTIME_PROVIDER_SELECTION_INVALID={selected}")

        dispatch = pc(repo, cfg["project_policy"], env, "dispatch", "--project", PROJECT,
                      "--plan", str(plan_path), "--graph", str(graph), "--execute")
        if dispatch.get("status") != "OK": raise SystemExit(f"EXTERNAL_RUNTIME_DISPATCH_FAILED={dispatch}")
        record_path = Path(str((dispatch.get("details") or {}).get("RUN_RECORD")))
        record = load(record_path)
        tasks = [t for w in record.get("waves") or [] for t in w.get("tasks") or []]
        if len(tasks) != 1 or tasks[0].get("status") != "SUCCEEDED":
            raise SystemExit(f"EXTERNAL_RUNTIME_RUN_FAILED={record}")
        result_path = Path(str(tasks[0]["task_result"])); result = load(result_path)
        if result.get("producer") != "chrome-devtools-mcp-adapter" or result.get("status") != "OK":
            raise SystemExit(f"EXTERNAL_RUNTIME_RESULT_INVALID={result}")
        if (result.get("verification") or {}).get("status") != "UNVERIFIED":
            raise SystemExit("EXTERNAL_RUNTIME_PROVIDER_SELF_VERIFIED")
        evidence_details = ((result.get("evidence") or [{}])[0].get("details") or {})
        if evidence_details.get("operation") != "inspect_url" or evidence_details.get("final_origin_revalidated") is not True:
            raise SystemExit(f"EXTERNAL_RUNTIME_NAVIGATION_NOT_QUALIFIED={evidence_details}")

        broker = pc(repo, cfg["project_policy"], env, "verify-result", "--project", PROJECT,
                    "--result", str(result_path), "--graph", str(graph), "--method", "machine",
                    "--verifier", "verification-broker", allowed={0, 2})
        expected_gap = any("VERIFICATION_STATUS:NEEDS_INDEPENDENT_CHECK" in x for x in broker.get("blockers") or [])
        if broker.get("status") != "BLOCKED" or not expected_gap:
            raise SystemExit(f"EXTERNAL_RUNTIME_BROKER_BOUNDARY_INVALID={broker}")
        server.shutdown()

    bad = load(binding); bad["bindings"][0]["digest"] = "sha256:" + "0" * 64
    bad_binding = root / "runtime-binding-bad.json"; save(bad_binding, bad)
    bad_env = os.environ.copy(); bad_env["CHACHA_DEV_HUB_RUNTIME_BINDINGS"] = str(bad_binding)
    core_test = subprocess.run([
        sys.executable, str(repo / "dev-hub/bin/run-controller-external-dispatch.py"),
        "--plan", str(plan_path), "--graph", str(graph), "--ledger", str(ledger),
        "--policy", str(cfg["run_policy"]), "--adapters", str(repo / "dev-hub/config/provider-adapters.v1.json"),
        "--output-dir", str(root / "bad-binding-run"), "--execute"
    ], cwd=str(repo), env=bad_env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
    if core_test.returncode == 0 or "RUNTIME_BINDING_DECLARED_DIGEST_MISMATCH" not in (core_test.stdout + core_test.stderr):
        raise SystemExit("EXTERNAL_RUNTIME_BAD_DIGEST_NOT_BLOCKED")

    canonical_after = load(repo / "dev-hub/config/provider-adapters.v1.json")["adapters"]["chrome-devtools-mcp-adapter"]
    if canonical_after != chrome: raise SystemExit("EXTERNAL_RUNTIME_CANONICAL_REGISTRY_MUTATED")

    out = {
        "schema": SCHEMA, "status": "EXTERNAL_RUNTIME_DISPATCH_QUALIFIED", "project": PROJECT,
        "qualified_at": now(), "provider": "chrome-devtools-mcp", "adapter": "chrome-devtools-mcp-adapter",
        "run_id": record.get("run_id"), "runtime_binding": {"scope": "ephemeral-runner", "digest_match": True,
        "canonical_executable": None, "staged_executable": str(staged_adapter), "source_digest": source_digest},
        "execution": {"status": "OK", "producer_verification": "UNVERIFIED", "controlled_navigation": True,
                      "final_origin_revalidated": True, "production": False},
        "verification_boundary": {"status": "NEEDS_INDEPENDENT_CHECK", "expected": True,
                                  "reason": "URL-backed external provider evidence is not locally machine-addressable"},
        "negative_paths": {"bad_runtime_binding_digest": "BLOCKED"},
        "authoritative_registry_mutated": False, "vps_modified": False, "production_modified": False,
        "next_gap": "EXTERNAL_PROVIDER_EVIDENCE_HANDOFF", "blockers": ["EXTERNAL_PROVIDER_EVIDENCE_HANDOFF"]
    }
    output = args.output or root / "qualification.json"; save(output, out)
    print("EXTERNAL_RUNTIME_DISPATCH=PASS")
    print("EXTERNAL_RUNTIME_PROVIDER=chrome-devtools-mcp")
    print("EXTERNAL_RUNTIME_VERIFICATION_BOUNDARY=NEEDS_INDEPENDENT_CHECK")
    print(f"EXTERNAL_RUNTIME_OUTPUT={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
