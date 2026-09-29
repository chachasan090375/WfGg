#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

SHA = "70f4e826d369cfee870c64ca5386c06959d25c7f"
CAND = Path(f"/tmp/chacha-domain-candidate-{SHA[:12]}")
CONTROL = Path("/tmp/chacha-control-plane-after-attestation.json")
CURRENT = Path("/opt/chacha-dev/platform/current")

WANTED = {
    "capability:domain-knowledge-research:technology-radar",
    "capability:domain-knowledge-research:architecture-optimization",
    "capability:domain-knowledge-research:library-docs",
    "capability:domain-knowledge-research:collector-knowledge-inspect",
}
PERMISSIONS = {
    "technology-radar": "read",
    "architecture-optimization": "plan",
    "library-docs": "read",
    "collector-knowledge-inspect": "read",
}
ADAPTER_FILES = {
    "platform-command-adapter": "dev-hub/adapters/platform-command-adapter.py",
    "context7-mcp-adapter": "dev-hub/adapters/context7-mcp-adapter.py",
    "collector-knowledge-adapter": "dev-hub/adapters/collector-knowledge-adapter.py",
}


def load(path: Path):
    return json.loads(path.read_text())


def run(argv, **kwargs):
    return subprocess.run(argv, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, **kwargs)


def pairs(outputs):
    return {
        (str(x.get("type")), str(x.get("id")))
        for x in outputs or []
        if isinstance(x, dict) and x.get("type") and x.get("id")
    }


def fail(msg: str):
    raise SystemExit("PILOT_FAIL=" + msg)


def find_old_result(report_path: Path, task_id: str):
    rows = []
    for p in report_path.parent.glob("*.json"):
        try:
            x = load(p)
        except Exception:
            continue
        if x.get("schema") == "chacha.dev/task-result/v1" and str(x.get("task_id")) == task_id:
            rows.append((p, x))
    for p, x in rows:
        if (x.get("verification") or {}).get("status") != "VERIFIED":
            return p, x
    if rows:
        return rows[0]
    fail("OLD_RESULT_NOT_FOUND:" + task_id)


def collector_declared_outputs(report: dict, old_result: dict):
    for c in report.get("checks") or []:
        if c.get("id") != "outputs-declared" or c.get("status") != "FAIL":
            continue
        detail = str(c.get("detail") or "")
        if "undeclared=" not in detail or "missing=" in detail:
            continue
        actual = pairs(old_result.get("outputs"))
        if actual == {("artifact", "collector-knowledge-status")}:
            return []
    fail("COLLECTOR_CONTRACT_NOT_PROVEN_EMPTY")


def main():
    if not CAND.is_dir():
        fail("CANDIDATE_WORKTREE_MISSING:" + str(CAND))
    got = run(["git", "-C", str(CAND), "rev-parse", "HEAD"]).stdout.strip()
    if got != SHA:
        fail("CANDIDATE_SHA_MISMATCH:" + got)
    if not CONTROL.is_file():
        fail("CONTROL_PLANE_JSON_MISSING")

    active_before = str(CURRENT.resolve())
    health_before = urllib.request.urlopen("http://127.0.0.1:8792/healthz", timeout=5).read().decode()
    print("DECIDED=pilot_only_four_previous_failures")
    print("CANDIDATE=" + SHA)
    print("PRODUCTION_BEFORE=" + active_before)
    print("DIRECT_OPERATOR_BEFORE=" + health_before)

    decision = load(CONTROL)["report"]["domain_execution"]["decision"]
    tasks = decision["domain_toolchain_readiness"]["tasks"]
    task_map = {str(t.get("_task_id") or t.get("task_id") or t.get("id")): t for t in tasks}
    if not WANTED.issubset(task_map):
        fail("TASK_CONTRACT_SET_INCOMPLETE")

    rows = decision["independent_verification"]["rows"]
    old_pass = sum(1 for r in rows if r.get("returncode") == 0)
    reports = {}
    for row in rows:
        tid = str(row.get("task_id") or "")
        if tid not in WANTED or row.get("returncode") == 0:
            continue
        blob = json.dumps(row, ensure_ascii=False)
        hits = re.findall(r'/opt/chacha-dev/runtime/transactions/[^"\\\s]+/verification-report\.json', blob)
        if not hits:
            fail("REPORT_PATH_MISSING:" + tid)
        p = Path(hits[0])
        if not p.is_file():
            fail("REPORT_FILE_MISSING:" + str(p))
        reports[tid] = p
    if set(reports) != WANTED:
        fail("FAILED_REPORT_SET_MISMATCH")

    work = Path(tempfile.mkdtemp(prefix="chacha-domain-4of4-"))
    evidence_root = work / "evidence"
    broker = CAND / "dev-hub/bin/verification-broker.py"
    policy = CAND / "dev-hub/config/verification-broker.v1.json"
    verified = []

    for i, tid in enumerate(sorted(WANTED), 1):
        readiness = task_map[tid]
        if readiness.get("gate") != "READY":
            fail("GATE_NOT_READY:" + tid)
        report_path = reports[tid]
        old_report = load(report_path)
        _, old_result = find_old_result(report_path, tid)
        suffix = tid.rsplit(":", 1)[-1]
        caps = readiness.get("capabilities") or []
        if len(caps) != 1:
            fail("CAPABILITY_CARDINALITY:" + tid)
        cap = str(caps[0])
        selected = readiness.get("selected_candidate") or {}
        provider = str(readiness.get("selected_provider") or selected.get("provider") or "")
        adapter = str(selected.get("adapter_id") or "")
        if adapter not in ADAPTER_FILES:
            fail("ADAPTER_UNSUPPORTED:" + adapter)

        declared = collector_declared_outputs(old_report, old_result) if suffix == "collector-knowledge-inspect" else [
            {"type": x.get("type"), "id": x.get("id")}
            for x in old_result.get("outputs") or []
            if isinstance(x, dict) and x.get("type") and x.get("id")
        ]
        metadata = {"collector_knowledge": {"action": "status"}} if suffix == "collector-knowledge-inspect" else {}
        project = str(old_result.get("project") or "chacha-dev-platform")
        task = {
            "id": tid,
            "kind": "capability",
            "capabilities": [cap],
            "permission": PERMISSIONS[suffix],
            "outputs": declared,
            "verification": {"mode": "independent-agent"},
        }
        envelope = {
            "schema": "chacha.dev/dispatch-envelope/v1",
            "project": project,
            "transition": "PILOT",
            "run_id": f"pilot-four-{i}",
            "wave": 0,
            "task": task,
            "bindings": [{"capability": cap, "provider": provider, "adapter": adapter, "health_state": "HEALTHY"}],
            "policy_context": {"human_approval_required": False, "timeout_seconds": 120},
            "workspace": None,
            "metadata": metadata,
        }

        tdir = work / f"task-{i}"
        tdir.mkdir(parents=True)
        env = dict(os.environ)
        env["CHACHA_DEV_EVIDENCE_ROOT"] = str(evidence_root)
        env["CHACHA_DEV_PLATFORM_ROOT"] = str(CURRENT)
        proc = run(["python3", str(CAND / ADAPTER_FILES[adapter])], input=json.dumps(envelope), env=env, timeout=120)
        if proc.returncode != 0:
            print(proc.stdout[-3000:]); print(proc.stderr[-3000:])
            fail("ADAPTER_FAILED:" + tid)
        result = json.loads(proc.stdout.strip().splitlines()[-1])
        if result.get("status") != "OK":
            fail("RESULT_NOT_OK:" + tid + ":" + str(result.get("summary")))

        evidence = result.get("evidence") or []
        if not evidence:
            fail("NO_EVIDENCE:" + tid)
        for ev in evidence:
            src = Path(str(ev.get("source") or ""))
            if not src.is_absolute() or not src.is_file():
                fail("NON_LOCAL_EVIDENCE:" + tid)
            digest = "sha256:" + hashlib.sha256(src.read_bytes()).hexdigest()
            if digest != str(ev.get("digest") or ""):
                fail("EVIDENCE_DIGEST_MISMATCH:" + tid)
        if pairs(result.get("outputs")) != pairs(declared):
            fail("OUTPUT_CONTRACT_MISMATCH:" + tid)

        result_path = tdir / "task-result.json"
        graph_path = tdir / "task-graph.json"
        vr_path = tdir / "verification-report.json"
        verified_path = tdir / "verified-task-result.json"
        result_path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
        graph_path.write_text(json.dumps({"schema": "chacha.dev/task-graph/v1", "project": project, "tasks": [task]}, indent=2, ensure_ascii=False) + "\n")
        vr = run([
            "python3", str(broker), "--result", str(result_path), "--graph", str(graph_path), "--policy", str(policy),
            "--report", str(vr_path), "--verified-result", str(verified_path), "--verifier", "verification-broker", "--method", "independent-agent"
        ], timeout=60)
        if vr.returncode != 0:
            if vr_path.is_file(): print(vr_path.read_text())
            print(vr.stdout); print(vr.stderr)
            fail("BROKER_FAILED:" + tid)
        if load(vr_path).get("status") != "VERIFIED":
            fail("BROKER_NOT_VERIFIED:" + tid)
        final = load(verified_path)
        if (final.get("verification") or {}).get("status") != "VERIFIED":
            fail("FINAL_NOT_VERIFIED:" + tid)
        if any(x.get("status") != "VERIFIED" for x in final.get("outputs") or []):
            fail("OUTPUT_NOT_VERIFIED:" + tid)
        verified.append(tid)
        print("VERIFIED=" + tid)

    active_after = str(CURRENT.resolve())
    health_after = urllib.request.urlopen("http://127.0.0.1:8792/healthz", timeout=5).read().decode()
    if active_after != active_before:
        fail("PRODUCTION_RELEASE_CHANGED")
    if len(verified) != 4:
        fail("FOUR_TASK_PILOT_INCOMPLETE")
    if old_pass != 3:
        fail("HISTORICAL_PASS_COUNT_CHANGED:" + str(old_pass))

    print("EXECUTED=4_previously_failed_tasks_only")
    print("VERIFIED_TASKS=4")
    print("HISTORICAL_VERIFIED_TASKS=3")
    print("DOMAIN_VERIFICATION_7_OF_7=PASS")
    print("PRODUCTION_RELEASE_UNCHANGED=PASS")
    print("DIRECT_OPERATOR_AFTER=" + health_after)
    print("PILOT_ROOT=" + str(work))
    print("HUMAN_APPROVAL_REQUIRED_BEFORE_PROMOTION=YES")


if __name__ == "__main__":
    main()
