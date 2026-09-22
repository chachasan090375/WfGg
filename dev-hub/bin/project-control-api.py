#!/usr/bin/env python3
"""ChaCha DEV HUB Project Control JSON API V1.4.

Local stdin/stdout adapter over the unified Project Control CLI router. No
network listener is created. Human verification cannot be asserted through this
agent-facing adapter, recovery cannot mutate unless apply=true is explicit, and
platform readiness remains read-only.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

REQUEST_SCHEMA = "chacha.dev/project-control-request/v1"


def fail(message: str, project: str = "unknown", operation: str = "api") -> None:
    print(json.dumps({
        "schema": "chacha.dev/project-control-response/v1",
        "project": project,
        "operation": operation,
        "status": "FAILED",
        "observed_at": "",
        "summary": message,
        "details": {},
        "blockers": [message],
        "next_actions": [],
        "artifacts": []
    }, ensure_ascii=False))
    raise SystemExit(2)


def read_request() -> dict[str, Any]:
    try:
        value = json.load(sys.stdin)
    except Exception as exc:
        fail(f"REQUEST_JSON_INVALID:{exc}")
    if not isinstance(value, dict):
        fail("REQUEST_ROOT_NOT_OBJECT")
    if value.get("schema") != REQUEST_SCHEMA:
        fail(f"REQUEST_SCHEMA_INVALID:{value.get('schema')}")
    if not value.get("project") or not value.get("operation"):
        fail("REQUEST_PROJECT_OR_OPERATION_MISSING", str(value.get("project") or "unknown"))
    return value


def main() -> int:
    request = read_request()
    project = str(request["project"])
    operation = str(request["operation"])
    args = request.get("arguments") or {}
    if not isinstance(args, dict):
        fail("REQUEST_ARGUMENTS_NOT_OBJECT", project, operation)

    script = Path(__file__).with_name("project-control-cli.py")
    repo_root = Path(str(args.get("repo_root") or Path.cwd()))
    policy = Path(str(args.get("policy") or "dev-hub/config/project-control.v1.json"))
    cmd = [sys.executable, str(script), "--repo-root", str(repo_root), "--policy", str(policy), "--json"]

    if operation in {"status", "explain", "verify-state", "transactions"}:
        cmd += [operation, "--project", project]
    elif operation == "recover-transaction":
        if not args.get("transaction_id"):
            fail("REQUEST_TRANSACTION_ID_REQUIRED", project, operation)
        cmd += [operation, "--project", project, "--transaction-id", str(args["transaction_id"])]
        cmd += ["--actor", str(args.get("actor") or request.get("actor") or "recovery-engineer")]
        if args.get("apply") is True:
            cmd.append("--apply")
        if args.get("report"):
            cmd += ["--report", str(args["report"])]
    elif operation == "functional-orchestrate":
        if not args.get("intent"):
            fail("REQUEST_FUNCTIONAL_INTENT_REQUIRED", project, operation)
        cmd += [operation, "--project", project, "--intent", str(args["intent"])]
        if args.get("output"):
            cmd += ["--output", str(args["output"])]
    elif operation == "technical-design":
        if not args.get("requirement") or not args.get("manifest"):
            fail("REQUEST_REQUIREMENT_AND_MANIFEST_REQUIRED", project, operation)
        cmd += [
            operation, "--project", project,
            "--requirement", str(args["requirement"]),
            "--manifest", str(args["manifest"]),
        ]
        if args.get("output"):
            cmd += ["--output", str(args["output"])]
        if args.get("task_graph_output"):
            cmd += ["--task-graph-output", str(args["task_graph_output"])]
    elif operation == "platform-readiness":
        cmd += [operation, "--project", project]
        if args.get("profile"):
            cmd += ["--profile", str(args["profile"])]
        for key, flag in (
            ("provider_health", "--provider-health"),
            ("storage_preflight", "--storage-preflight"),
            ("adapter_contract_report", "--adapter-contract-report"),
            ("recovery_drill_report", "--recovery-drill-report"),
            ("report", "--report"),
        ):
            if args.get(key):
                cmd += [flag, str(args[key])]
        if args.get("run_recovery_drill") is True:
            cmd.append("--run-recovery-drill")
        providers = args.get("required_providers") or []
        if not isinstance(providers, list):
            fail("REQUEST_REQUIRED_PROVIDERS_NOT_ARRAY", project, operation)
        for provider in providers:
            cmd += ["--required-provider", str(provider)]
    elif operation == "plan-transition":
        cmd += [operation, "--project", project]
        if args.get("target"):
            cmd += ["--target", str(args["target"])]
    elif operation == "schedule":
        cmd += [operation, "--project", project]
        if args.get("graph"):
            cmd += ["--graph", str(args["graph"])]
    elif operation in {"prepare-run", "dispatch"}:
        if not args.get("plan") or not args.get("graph"):
            fail("REQUEST_PLAN_AND_GRAPH_REQUIRED", project, operation)
        cmd += [operation, "--project", project, "--plan", str(args["plan"]), "--graph", str(args["graph"])]
        if args.get("workspace"):
            cmd += ["--workspace", str(args["workspace"])]
        if operation == "dispatch" and args.get("execute") is True:
            cmd.append("--execute")
    elif operation == "verify-result":
        if not args.get("result") or not args.get("graph"):
            fail("REQUEST_RESULT_AND_GRAPH_REQUIRED", project, operation)
        if str(args.get("method") or "machine") == "human":
            fail("HUMAN_VERIFICATION_NOT_ACCEPTED_VIA_JSON_API", project, operation)
        cmd += [operation, "--project", project, "--result", str(args["result"]), "--graph", str(args["graph"])]
        if args.get("method"):
            cmd += ["--method", str(args["method"])]
        if args.get("verifier"):
            cmd += ["--verifier", str(args["verifier"])]
        if args.get("ingest") is True:
            cmd.append("--ingest")
    elif operation == "record-control-event":
        if not args.get("event_type") or not args.get("actor"):
            fail("REQUEST_EVENT_TYPE_AND_ACTOR_REQUIRED", project, operation)
        cmd += [operation, "--project", project, "--event-type", str(args["event_type"]), "--actor", str(args["actor"])]
        for key, flag in (("payload", "--payload"), ("patch", "--patch"), ("references", "--references")):
            if args.get(key):
                cmd += [flag, str(args[key])]
    elif operation == "advance":
        cmd += [operation, "--project", project, "--actor", str(args.get("actor") or request.get("actor") or "project-owner")]
        if args.get("target"):
            cmd += ["--target", str(args["target"])]
    elif operation == "crypto-verify":
        if not args.get("checkpoint") or not args.get("public_key"):
            fail("REQUEST_CHECKPOINT_AND_PUBLIC_KEY_REQUIRED", project, operation)
        cmd += [operation, "--project", project, "--checkpoint", str(args["checkpoint"]), "--public-key", str(args["public_key"])]
    else:
        fail(f"REQUEST_OPERATION_UNSUPPORTED:{operation}", project, operation)

    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, shell=False, timeout=3700, check=False)
    except subprocess.TimeoutExpired:
        fail("PROJECT_CONTROL_TIMEOUT", project, operation)

    if proc.stdout.strip():
        try:
            parsed = json.loads(proc.stdout)
        except json.JSONDecodeError:
            fail("PROJECT_CONTROL_NON_JSON_RESPONSE", project, operation)
        print(json.dumps(parsed, ensure_ascii=False))
    else:
        fail("PROJECT_CONTROL_EMPTY_RESPONSE:" + proc.stderr.strip(), project, operation)
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
