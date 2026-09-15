#!/usr/bin/env python3
"""ChaCha DEV HUB Project Control JSON API V1.

Local stdin/stdout adapter over project-control.py. No network listener is
created. A request is one JSON object and the response is the same structured
Project Control response emitted by the unified CLI.
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

    script = Path(__file__).with_name("project-control.py")
    repo_root = Path(str(args.get("repo_root") or Path.cwd()))
    policy = Path(str(args.get("policy") or "dev-hub/config/project-control.v1.json"))
    cmd = [sys.executable, str(script), "--repo-root", str(repo_root), "--policy", str(policy), "--json"]

    if operation in {"status", "explain", "verify-state"}:
        cmd += [operation, "--project", project]
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
