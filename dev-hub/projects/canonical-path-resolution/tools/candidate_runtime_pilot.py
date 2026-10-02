#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any

PILOT_SCHEMA = "chacha.dev/canonical-path-runtime-pilot/v1"
CCR_POLICY_SCHEMA = "chacha.dev/canonical-component-registry-policy/v1"
DIRECT_OPERATOR_POLICY_SCHEMA = "chacha.dev/direct-operator-policy/v1"
PROJECT_CONTROL_POLICY_SCHEMA = "chacha.dev/project-control/v1"
RUN_CONTROLLER_POLICY_SCHEMA = "chacha.dev/run-controller/v1"
TERMINAL_JOB_STATES = {"COMPLETE", "FAILED"}


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"JSON_ROOT_NOT_OBJECT:{path}")
    return value


def save(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def digest_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def run(argv: list[str], *, cwd: Path | None = None, timeout: int = 120, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        cwd=str(cwd) if cwd else None,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
        timeout=timeout,
    )


def git(repo: Path, *args: str, timeout: int = 120) -> str:
    proc = run(["git", "-C", str(repo), *args], timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError(f"GIT_FAILED:{' '.join(args)}:{proc.stderr[-800:]}")
    return proc.stdout.strip()


def active_identity(current: Path) -> dict[str, str]:
    resolved = current.resolve()
    revision = "UNKNOWN"
    revision_file = resolved / ".revision"
    if revision_file.is_file():
        revision = revision_file.read_text(encoding="utf-8").strip()
    return {"path": str(resolved), "revision": revision}


def assert_active_unchanged(current: Path, before: dict[str, str]) -> None:
    after = active_identity(current)
    if after != before:
        raise RuntimeError(f"ACTIVE_CHANGED_DURING_PILOT:{before!r}->{after!r}")


def materialize_candidate(source_repo: Path, sha: str, candidate_root: Path) -> dict[str, str]:
    commit = git(source_repo, "rev-parse", f"{sha}^{{commit}}")
    if commit != sha:
        raise RuntimeError(f"CANDIDATE_SHA_NOT_EXACT:{commit}")
    tree = git(source_repo, "rev-parse", f"{sha}^{{tree}}")
    if candidate_root.exists():
        shutil.rmtree(candidate_root)
    candidate_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="chacha-candidate-archive-") as td:
        archive = Path(td) / "candidate.tar"
        proc = run(["git", "-C", str(source_repo), "archive", "--format=tar", "--output", str(archive), sha], timeout=180)
        if proc.returncode != 0:
            raise RuntimeError(f"GIT_ARCHIVE_FAILED:{proc.stderr[-800:]}")
        with tarfile.open(archive, "r") as tf:
            tf.extractall(candidate_root, filter="data")
    (candidate_root / ".revision").write_text(sha + "\n", encoding="utf-8")
    (candidate_root / ".tree").write_text(tree + "\n", encoding="utf-8")
    return {"sha": sha, "tree": tree}


def _component_id(row: dict[str, Any]) -> str:
    return str(row.get("component_id") or row.get("id") or row.get("name") or "").strip()


def rewrite_ccr_snapshot(snapshot: dict[str, Any], project: str, candidate_root: Path, pilot_runtime: Path) -> dict[str, Any]:
    out = json.loads(json.dumps(snapshot))
    components = out.get("components")
    target: dict[str, Any] | None = None
    if isinstance(components, dict):
        row = components.get(project)
        if isinstance(row, dict):
            target = row
    elif isinstance(components, list):
        for row in components:
            if isinstance(row, dict) and _component_id(row) == project:
                target = row
                break
    if target is None:
        raise RuntimeError(f"PILOT_PROJECT_NOT_IN_CANONICAL_REGISTRY:{project}")
    paths = target.setdefault("paths", {})
    if not isinstance(paths, dict):
        raise RuntimeError("PILOT_COMPONENT_PATHS_INVALID")
    paths["source_root"] = str(candidate_root)
    paths["runtime_root"] = str(pilot_runtime)
    paths["state_root"] = str(pilot_runtime / "state" / project)
    return out


def overlay_configs(candidate_root: Path, pilot_root: Path, project: str, port: int, active_runtime: Path) -> dict[str, str]:
    pilot_runtime = pilot_root / "runtime"
    pilot_runtime.mkdir(parents=True, exist_ok=True)

    required_live_reads = (
        ("control/emergency-stop.json", active_runtime / "control/emergency-stop.json"),
        ("agent-evolution/fleet-observatory-latest.json", active_runtime / "agent-evolution/fleet-observatory-latest.json"),
    )
    missing_live = [str(source) for _, source in required_live_reads if not source.is_file()]
    if missing_live:
        raise RuntimeError("PILOT_REQUIRED_LIVE_GOVERNANCE_MISSING:" + ",".join(missing_live))
    for rel, source in required_live_reads:
        target = pilot_runtime / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() or target.is_symlink():
            target.unlink()
        target.symlink_to(source)

    ccr_policy_path = candidate_root / "dev-hub/config/canonical-component-registry.v1.json"
    ccr_policy = load(ccr_policy_path)
    if ccr_policy.get("schema") != CCR_POLICY_SCHEMA:
        raise RuntimeError("PILOT_CCR_POLICY_SCHEMA_INVALID")
    runtime_registry = ccr_policy.setdefault("runtime_registry", {})
    if not isinstance(runtime_registry, dict):
        raise RuntimeError("PILOT_CCR_RUNTIME_REGISTRY_INVALID")
    active_snapshot = Path(str(runtime_registry.get("canonical_snapshot") or ""))
    if not active_snapshot.is_file():
        raise RuntimeError(f"PILOT_ACTIVE_CCR_SNAPSHOT_MISSING:{active_snapshot}")
    pilot_snapshot_path = pilot_root / "canonical-component-registry.json"
    pilot_snapshot = rewrite_ccr_snapshot(load(active_snapshot), project, candidate_root, pilot_runtime)
    save(pilot_snapshot_path, pilot_snapshot)
    runtime_registry["canonical_snapshot"] = str(pilot_snapshot_path)
    save(ccr_policy_path, ccr_policy)

    pc_path = candidate_root / "dev-hub/config/project-control.v1.json"
    pc = load(pc_path)
    if pc.get("schema") != PROJECT_CONTROL_POLICY_SCHEMA:
        raise RuntimeError("PILOT_PROJECT_CONTROL_POLICY_SCHEMA_INVALID")
    runtime = pc.setdefault("runtime", {})
    for key, rel in {
        "state_root": "state",
        "evidence_root": "evidence",
        "plans_root": "plans",
        "health_root": "health",
        "runs_root": "runs",
        "transactions_root": "transactions",
        "locks_root": "locks/control",
        "capsules_root": "capsules",
    }.items():
        runtime[key] = str(pilot_runtime / rel)
    save(pc_path, pc)

    cps_path = candidate_root / "dev-hub/config/control-plane-state.v1.json"
    cps = load(cps_path)
    storage = cps.setdefault("storage", {})
    if isinstance(storage, dict):
        storage["runtime_root"] = str(pilot_runtime / "state")
    save(cps_path, cps)

    rc_path = candidate_root / "dev-hub/config/run-controller.v1.json"
    rc = load(rc_path)
    if rc.get("schema") != RUN_CONTROLLER_POLICY_SCHEMA:
        raise RuntimeError("PILOT_RUN_CONTROLLER_POLICY_SCHEMA_INVALID")
    locking = rc.setdefault("locking", {})
    dispatch = rc.setdefault("dispatch", {})
    workspace = rc.setdefault("workspace", {})
    guardian = rc.setdefault("guardian", {})
    if isinstance(locking, dict):
        locking["root"] = str(pilot_runtime / "locks")
    if isinstance(dispatch, dict):
        dispatch["work_root"] = str(pilot_runtime / "runs")
    if isinstance(workspace, dict):
        workspace["root"] = str(pilot_runtime / "projects")
    if isinstance(guardian, dict):
        guardian["runtime_root"] = str(active_runtime)
    save(rc_path, rc)

    do_path = candidate_root / "dev-hub/config/direct-operator.v1.json"
    do = load(do_path)
    if do.get("schema") != DIRECT_OPERATOR_POLICY_SCHEMA:
        raise RuntimeError("PILOT_DIRECT_OPERATOR_POLICY_SCHEMA_INVALID")
    do["bind"] = "127.0.0.1"
    do["port"] = port
    do["runtime_root"] = str(pilot_runtime / "direct-operator")
    do["pilot"] = {
        "enabled": True,
        "candidate_root": str(candidate_root),
        "runtime_root": str(pilot_runtime),
        "promotion_authority": False,
        "public_ingress_forbidden": True,
    }
    save(do_path, do)

    return {
        "runtime_root": str(pilot_runtime),
        "ccr_snapshot": str(pilot_snapshot_path),
        "direct_operator_policy": str(do_path),
    }


def first_authorized_identity(policy: dict[str, Any]) -> tuple[str, str]:
    auth = policy.get("authentication")
    if not isinstance(auth, dict):
        raise RuntimeError("PILOT_DIRECT_OPERATOR_AUTH_INVALID")
    header = str(auth.get("login_header") or "Tailscale-User-Login")
    users_file = Path(str(auth.get("authorized_users_file") or ""))
    users = load(users_file).get("authorized_logins")
    if not isinstance(users, list):
        raise RuntimeError("PILOT_AUTHORIZED_USERS_INVALID")
    for item in users:
        login = str(item).strip()
        if login:
            return header, login
    raise RuntimeError("PILOT_AUTHORIZED_USER_REQUIRED")


def http_json(url: str, *, headers: dict[str, str] | None = None, body: dict[str, Any] | None = None, timeout: float = 5.0) -> tuple[int, dict[str, Any]]:
    data = None
    req_headers = {"Accept": "application/json"}
    if headers:
        req_headers.update(headers)
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        req_headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=req_headers, method="POST" if body is not None else "GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            return response.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        try:
            payload = json.loads(raw)
        except Exception:
            payload = {"raw": raw[-1000:]}
        return exc.code, payload


def wait_ready(port: int, process: subprocess.Popen[str], timeout: float = 15.0) -> None:
    deadline = time.time() + timeout
    url = f"http://127.0.0.1:{port}/healthz"
    while time.time() < deadline:
        if process.poll() is not None:
            stdout, stderr = process.communicate(timeout=1)
            raise RuntimeError(f"PILOT_DIRECT_OPERATOR_EXITED:{process.returncode}:{stderr[-1000:]}:{stdout[-500:]}")
        try:
            status, payload = http_json(url, timeout=1.0)
            if status == 200 and payload.get("status") == "PASS":
                return
        except Exception:
            pass
        time.sleep(0.2)
    raise RuntimeError("PILOT_DIRECT_OPERATOR_READY_TIMEOUT")


def authenticated_status(port: int, policy: dict[str, Any], project: str) -> dict[str, Any]:
    header, identity = first_authorized_identity(policy)
    status, accepted = http_json(
        f"http://127.0.0.1:{port}/api/v1/intent",
        headers={header: identity},
        body={
            "text": "allo",
            "channel": "BUILD",
            "client_request_id": "canonical-path-pilot-" + uuid.uuid4().hex,
            "project": project,
        },
        timeout=5.0,
    )
    if status != 202 or accepted.get("status") != "ACCEPTED":
        raise RuntimeError(f"PILOT_DIRECT_OPERATOR_INTENT_REJECTED:{status}:{accepted}")
    job_id = str(accepted.get("job_id") or "")
    deadline = time.time() + 30.0
    while time.time() < deadline:
        code, job = http_json(
            f"http://127.0.0.1:{port}/api/v1/jobs/{job_id}",
            headers={header: identity},
            timeout=3.0,
        )
        if code == 200 and str(job.get("state") or "") in TERMINAL_JOB_STATES:
            return {
                "job_id": job_id,
                "state": job.get("state"),
                "response_status": ((job.get("response") or {}).get("status") if isinstance(job.get("response"), dict) else None),
            }
        time.sleep(0.25)
    raise RuntimeError("PILOT_DIRECT_OPERATOR_JOB_TIMEOUT")


def run_gate_attempt(candidate_root: Path, project: str, graph: Path, env: dict[str, str]) -> dict[str, Any]:
    cmd = [
        sys.executable,
        str(candidate_root / "dev-hub/bin/governed-project-control.py"),
        "--repo-root", str(candidate_root),
        "--json",
        "schedule",
        "--project", project,
        "--graph", str(graph),
    ]
    proc = run(cmd, cwd=candidate_root, timeout=90, env=env)
    payload: dict[str, Any] = {}
    try:
        payload = json.loads(proc.stdout)
    except Exception:
        pass
    return {
        "returncode": proc.returncode,
        "payload": payload,
        "stdout_digest": hashlib.sha256(proc.stdout.encode()).hexdigest(),
        "stderr_tail": proc.stderr[-800:],
    }


def pilot(args: argparse.Namespace) -> dict[str, Any]:
    if not args.candidate_sha or len(args.candidate_sha) != 40 or any(c not in "0123456789abcdef" for c in args.candidate_sha.lower()):
        raise RuntimeError("PILOT_CANDIDATE_SHA_INVALID")
    if args.port == 8792:
        raise RuntimeError("PILOT_ACTIVE_DIRECT_OPERATOR_PORT_FORBIDDEN")
    source_repo = args.source_repo.resolve()
    active_current = args.active_current.absolute()
    before = active_identity(active_current)
    pilot_root = args.pilot_root.resolve() / args.candidate_sha
    candidate_root = pilot_root / "candidate"
    active_runtime = args.active_runtime.resolve()

    if pilot_root.exists():
        shutil.rmtree(pilot_root)
    pilot_root.mkdir(parents=True, exist_ok=True)

    candidate = materialize_candidate(source_repo, args.candidate_sha, candidate_root)
    overlay = overlay_configs(candidate_root, pilot_root, args.project, args.port, active_runtime)
    pilot_runtime = Path(overlay["runtime_root"])
    graph = pilot_root / "graph.json"
    graph.write_text('{"schema":"chacha.dev/pilot-graph/v1","tasks":[],"pilot_nonce":1}\n', encoding="utf-8")

    env = dict(os.environ)
    env["CHACHA_RUNTIME_ROOT"] = str(pilot_runtime)
    env["PYTHONDONTWRITEBYTECODE"] = "1"

    policy = load(Path(overlay["direct_operator_policy"]))
    server = subprocess.Popen(
        [
            sys.executable,
            str(candidate_root / "dev-hub/bin/direct-operator-service.py"),
            "--repo-root", str(candidate_root),
            "--runtime-root", str(pilot_runtime),
            "--policy", str(Path(overlay["direct_operator_policy"])),
        ],
        cwd=str(candidate_root),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        wait_ready(args.port, server)
        direct_operator = authenticated_status(args.port, policy, args.project)
        first = run_gate_attempt(candidate_root, args.project, graph, env)
        second = run_gate_attempt(candidate_root, args.project, graph, env)
        graph.write_text('{"schema":"chacha.dev/pilot-graph/v1","tasks":[],"pilot_nonce":2}\n', encoding="utf-8")
        third = run_gate_attempt(candidate_root, args.project, graph, env)

        second_payload = second.get("payload") if isinstance(second.get("payload"), dict) else {}
        third_payload = third.get("payload") if isinstance(third.get("payload"), dict) else {}

        second_details = second_payload.get("details") if isinstance(second_payload.get("details"), dict) else {}
        second_recovery = second_details.get("recovery_plan") if isinstance(second_details.get("recovery_plan"), dict) else {}
        participants = second_recovery.get("participants") if isinstance(second_recovery.get("participants"), list) else []
        first_summary = str((first.get("payload") or {}).get("summary") or "") if isinstance(first.get("payload"), dict) else ""
        third_summary = str(third_payload.get("summary") or "")
        second_summary = str(second_payload.get("summary") or "")
        assertions = {
            "direct_operator_route_complete": direct_operator.get("state") == "COMPLETE",
            "first_reached_downstream": first_summary != "Governed Run Gate prevented downstream execution.",
            "identical_replay_blocked_pre_downstream": (
                second.get("returncode") == 2
                and str(second_payload.get("status") or "") == "BLOCKED"
                and second_summary == "Governed Run Gate prevented downstream execution."
            ),
            "runtime_recovery_never_single_agent": (
                not participants or len(set(str(x) for x in participants if str(x))) >= 2
            ),
            "material_graph_delta_re_admitted": third_summary != "Governed Run Gate prevented downstream execution.",
        }
        status = "PASS" if all(assertions.values()) else "BLOCKED"
        result = {
            "schema": PILOT_SCHEMA,
            "status": status,
            "candidate": candidate,
            "project": args.project,
            "port": args.port,
            "active_before": before,
            "direct_operator": direct_operator,
            "first_attempt": first,
            "identical_replay": second,
            "material_delta_attempt": third,
            "assertions": assertions,
            "promotion_performed": False,
            "current_link_mutated": False,
            "automatic_external_spend_eur": 0,
        }
        assert_active_unchanged(active_current, before)
        result["active_after"] = active_identity(active_current)
        save(pilot_root / "pilot-result.json", result)
        return result
    finally:
        if server.poll() is None:
            server.send_signal(signal.SIGTERM)
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=5)
        assert_active_unchanged(active_current, before)


def main() -> int:
    parser = argparse.ArgumentParser(description="Isolated real-runtime pilot for Canonical Path/Run Gate candidate")
    parser.add_argument("--source-repo", type=Path, required=True)
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--project", default="chacha-dev-platform")
    parser.add_argument("--pilot-root", type=Path, default=Path("/opt/chacha-dev/runtime/pilots/canonical-path"))
    parser.add_argument("--active-current", type=Path, default=Path("/opt/chacha-dev/platform/current"))
    parser.add_argument("--active-runtime", type=Path, default=Path("/opt/chacha-dev/runtime"))
    parser.add_argument("--port", type=int, default=8793)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    try:
        result = pilot(args)
    except Exception as exc:
        result = {
            "schema": PILOT_SCHEMA,
            "status": "BLOCKED",
            "reason": str(exc)[:2000],
            "promotion_performed": False,
            "automatic_external_spend_eur": 0,
        }
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result.get("status") == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
