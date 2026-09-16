#!/usr/bin/env python3
"""ChaCha DEV HUB preview pipeline orchestrator V1.

Provider-agnostic manifest entry point for preview delivery + browser verification.
Phase A asks the canonical Scheduler to select the preview provider and observes the
immutable preview URL through the ENABLED preview-only adapter. Phase B generates a
browser-verification child manifest from that provider output and delegates to the
already qualified Trusted Runtime V2 chain (Chrome -> Playwright -> Broker).

The manifest never names a provider and never supplies a preview URL. Execution is
explicit. Production branches and production URLs are fail-closed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit

MANIFEST_SCHEMA = "chacha.dev/project-manifest/v1"
CONTRACT_SCHEMA = "chacha.dev/project-manifest-contract/v1"
GRAPH_SCHEMA = "chacha.dev/task-graph/v1"
REGISTRY_SCHEMA = "chacha.dev/capability-registry/v1"
ADAPTER_SCHEMA = "chacha.dev/provider-adapters/v1"
HEALTH_SCHEMA = "chacha.dev/provider-health-snapshot/v1"
BINDING_SCHEMA = "chacha.dev/runtime-bindings/v1"
PROJECT_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
FORBIDDEN_WORKFLOW_KEYS = {"provider", "adapter", "project_name", "pages_project", "account_id", "api_token", "token", "preview_url"}


def now() -> datetime:
    return datetime.now(timezone.utc)


def now_iso() -> str:
    return now().isoformat()


def load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit(f"FILE_NOT_FOUND={path}")
    except json.JSONDecodeError as exc:
        raise SystemExit(f"JSON_INVALID={path}:{exc.lineno}:{exc.colno}:{exc.msg}")
    if not isinstance(value, dict):
        raise SystemExit(f"JSON_ROOT_NOT_OBJECT={path}")
    return value


def save(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def resolve(repo: Path, raw: str | Path) -> Path:
    p = Path(raw)
    return p if p.is_absolute() else repo / p


def inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def run(argv: list[str], repo: Path, env: dict[str, str] | None = None, timeout: int = 1800) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(argv, cwd=str(repo), env=env or os.environ.copy(), stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, text=True, shell=False, check=False, timeout=timeout)
    if proc.returncode != 0:
        raise SystemExit(f"COMMAND_FAILED={proc.returncode}:{' '.join(argv)}\nSTDOUT={proc.stdout[-5000:]}\nSTDERR={proc.stderr[-5000:]}")
    return proc


def project_control(repo: Path, policy: Path, args: list[str], env: dict[str, str] | None = None) -> dict[str, Any]:
    proc = run(["python3", "dev-hub/bin/project-control.py", "--policy", str(policy),
                "--repo-root", str(repo), "--json", *args], repo, env=env, timeout=1200)
    try:
        value = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"PROJECT_CONTROL_JSON_INVALID={exc}:{proc.stdout}:{proc.stderr}")
    if not isinstance(value, dict):
        raise SystemExit("PROJECT_CONTROL_RESPONSE_NOT_OBJECT")
    return value


def recursive_forbidden(value: Any) -> bool:
    if isinstance(value, dict):
        if set(value) & FORBIDDEN_WORKFLOW_KEYS:
            return True
        return any(recursive_forbidden(v) for v in value.values())
    if isinstance(value, list):
        return any(recursive_forbidden(v) for v in value)
    return False


def validate_manifest(manifest: dict[str, Any], contract: dict[str, Any]) -> tuple[str, dict[str, Any], dict[str, Any]]:
    if manifest.get("schema") != MANIFEST_SCHEMA:
        raise SystemExit(f"MANIFEST_SCHEMA_INVALID={manifest.get('schema')}")
    if contract.get("schema") != CONTRACT_SCHEMA or contract.get("manifest_schema") != MANIFEST_SCHEMA:
        raise SystemExit("MANIFEST_CONTRACT_INVALID")
    project = str(manifest.get("project") or "")
    if not PROJECT_RE.fullmatch(project):
        raise SystemExit("MANIFEST_PROJECT_INVALID")
    env_class = str(((manifest.get("environment") or {}).get("class")) or "")
    if env_class != "preview":
        raise SystemExit("PREVIEW_PIPELINE_REQUIRES_PREVIEW_ENVIRONMENT")
    workflows = manifest.get("workflows")
    if not isinstance(workflows, list) or len(workflows) != 1 or not isinstance(workflows[0], dict):
        raise SystemExit("PREVIEW_PIPELINE_V1_SINGLE_WORKFLOW_REQUIRED")
    wf = workflows[0]
    if recursive_forbidden(wf):
        raise SystemExit("PREVIEW_PIPELINE_PROVIDER_OR_URL_OVERRIDE_FORBIDDEN")
    wid = str(wf.get("id") or "")
    if not wid:
        raise SystemExit("PREVIEW_PIPELINE_WORKFLOW_ID_REQUIRED")
    if wf.get("kind") != "preview-browser-verification":
        raise SystemExit("PREVIEW_PIPELINE_WORKFLOW_KIND_REQUIRED")
    definition = ((contract.get("workflow_kinds") or {}).get("preview-browser-verification"))
    if not isinstance(definition, dict):
        raise SystemExit("PREVIEW_PIPELINE_CONTRACT_KIND_MISSING")
    source = wf.get("source") if isinstance(wf.get("source"), dict) else {}
    commit_sha = source.get("commit_sha")
    branch = source.get("branch")
    if not isinstance(commit_sha, str) or not SHA_RE.fullmatch(commit_sha):
        raise SystemExit("PREVIEW_PIPELINE_SOURCE_COMMIT_INVALID")
    if not isinstance(branch, str) or not branch or len(branch) > 255:
        raise SystemExit("PREVIEW_PIPELINE_SOURCE_BRANCH_INVALID")
    target = wf.get("target") if isinstance(wf.get("target"), dict) else {}
    if "url" in target:
        raise SystemExit("PREVIEW_PIPELINE_MANIFEST_TARGET_URL_FORBIDDEN")
    expected = target.get("expected_text")
    if expected is not None and (not isinstance(expected, str) or not expected or len(expected) > 512):
        raise SystemExit("PREVIEW_PIPELINE_EXPECTED_TEXT_INVALID")
    normalized = {"id": wid, "commit_sha": commit_sha, "branch": branch, "expected_text": expected}
    return project, normalized, definition


def require_capability(registry: dict[str, Any], capability: str) -> dict[str, Any]:
    if registry.get("schema") != REGISTRY_SCHEMA:
        raise SystemExit("CANONICAL_CAPABILITY_REGISTRY_SCHEMA_INVALID")
    value = ((registry.get("capabilities") or {}).get(capability))
    if not isinstance(value, dict):
        raise SystemExit(f"CANONICAL_CAPABILITY_MISSING={capability}")
    return value


def provider_requirements(definition: dict[str, Any]) -> list[tuple[str, str]]:
    return [
        (str(definition.get("delivery_capability") or ""), str(definition.get("delivery_permission") or "")),
        (str(definition.get("source_capability") or ""), "read"),
        (str(definition.get("independent_capability") or ""), "read"),
    ]


def bootstrap(repo: Path, project: str, policy: dict[str, Any], policy_path: Path,
              registry: dict[str, Any], adapters: dict[str, Any], definition: dict[str, Any]) -> dict[str, Any]:
    refs = policy.get("repository_paths") or {}
    runtime = policy.get("runtime") or {}
    roots = {
        "state": Path(str(runtime.get("state_root"))) / project,
        "evidence": Path(str(runtime.get("evidence_root"))) / project,
        "plans": Path(str(runtime.get("plans_root"))) / project,
        "health": Path(str(runtime.get("health_root"))) / project,
        "runs": Path(str(runtime.get("runs_root"))) / project,
        "transactions": Path(str(runtime.get("transactions_root"))) / project,
    }
    for p in roots.values():
        p.mkdir(parents=True, exist_ok=True)
    state_path = roots["state"] / "state.json"
    ledger_path = roots["evidence"] / "ledger.json"
    state_policy = resolve(repo, str(refs["control_plane_state"]))
    state_policy_value = load(state_policy)
    state_root = Path(str(((state_policy_value.get("storage") or {}).get("runtime_root"))))
    if not state_path.exists():
        run(["python3", "dev-hub/bin/control-plane-store.py", "--policy", str(state_policy),
             "--root", str(state_root), "init", "--project", project, "--actor", "preview-pipeline"], repo, timeout=120)
    if not ledger_path.exists():
        run(["python3", "dev-hub/bin/evidence-collector.py", "init", "--project", project,
             "--ledger", str(ledger_path)], repo, timeout=120)

    provider_defs = adapters.get("providers") if isinstance(adapters.get("providers"), dict) else {}
    adapter_defs = adapters.get("adapters") if isinstance(adapters.get("adapters"), dict) else {}
    observed = now_iso()
    snapshot: dict[str, Any] = {}
    for capability, permission in provider_requirements(definition):
        if not capability or not permission:
            raise SystemExit("PREVIEW_PIPELINE_CONTRACT_CAPABILITY_INVALID")
        cap = require_capability(registry, capability)
        for item in cap.get("providers") or []:
            if not isinstance(item, dict) or not isinstance(item.get("id"), str):
                continue
            pid = item["id"]
            pdef = provider_defs.get(pid) if isinstance(provider_defs, dict) else None
            adapter_id = pdef.get("adapter") if isinstance(pdef, dict) else None
            adef = adapter_defs.get(adapter_id) if isinstance(adapter_id, str) and isinstance(adapter_defs, dict) else None
            eligible = isinstance(adef, dict) and adef.get("status") == "ENABLED" and permission in set(adef.get("supports") or [])
            snapshot[pid] = {
                "state": "HEALTHY" if eligible else "UNKNOWN",
                "source": "canonical-adapter-eligibility",
                "checked_at": observed,
                "adapter": adapter_id,
                "adapter_status": adef.get("status") if isinstance(adef, dict) else None,
                "required_permission": permission,
                "runtime_availability_verified": False,
            }
    blocked = sorted(pid for pid, item in snapshot.items() if item.get("state") != "HEALTHY")
    if blocked:
        raise SystemExit("PREVIEW_PIPELINE_PROVIDER_NOT_ELIGIBLE=" + ",".join(blocked))
    health_path = roots["health"] / "providers.json"
    save(health_path, {"schema": HEALTH_SCHEMA, "observed_at": observed, "providers": snapshot})
    return {"roots": roots, "health": health_path}


def preview_graph(project: str, wf: dict[str, Any], definition: dict[str, Any]) -> dict[str, Any]:
    task_id = f"{wf['id']}:preview"
    return {
        "schema": GRAPH_SCHEMA,
        "project": project,
        "transition": "MANIFEST->PREVIEW",
        "generated_at": now_iso(),
        "tasks": [{
            "id": task_id,
            "kind": "artifact",
            "description": f"Create or observe immutable preview for {wf['id']}",
            "owner_role": "orchestrator",
            "capabilities": [definition["delivery_capability"]],
            "permission": definition["delivery_permission"],
            "depends_on": [],
            "outputs": [{"type": "artifact", "id": "cloudflare-pages-immutable-preview"}],
            "verification": {"mode": "independent-agent", "self_certification_allowed": False,
                             "required_evidence": ["source", "timestamp", "digest"]},
            "blocking": True,
            "parallel_group": f"preview-{wf['id']}",
            "metadata": {"cloudflare_pages": {"source_commit_sha": wf["commit_sha"], "source_branch": wf["branch"]}},
        }],
        "summary": {"task_count": 1, "artifact_tasks": 1, "gate_tasks": 0, "approval_tasks": 0, "blocking_tasks": 1},
    }


def result_paths(record: dict[str, Any]) -> dict[str, Path]:
    out: dict[str, Path] = {}
    for wave in record.get("waves") or []:
        if not isinstance(wave, dict):
            continue
        for task in wave.get("tasks") or []:
            if isinstance(task, dict) and task.get("task_id") and task.get("task_result"):
                out[str(task["task_id"])] = Path(str(task["task_result"]))
    return out


def wait_for_pages_check(binding: dict[str, Any], commit_sha: str, token: str, timeout_seconds: int) -> None:
    deadline = time.monotonic() + timeout_seconds
    repository = str(binding.get("repository") or "")
    name = str(binding.get("github_check_name") or "")
    app_slug = str(binding.get("github_app_slug") or "")
    if not repository or not name or not app_slug:
        raise SystemExit("PREVIEW_PIPELINE_PROJECT_BINDING_INVALID")
    url = f"https://api.github.com/repos/{repository}/commits/{commit_sha}/check-runs?per_page=100"
    while time.monotonic() < deadline:
        req = Request(url, headers={"Accept": "application/vnd.github+json", "Authorization": f"Bearer {token}",
                                    "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "chacha-dev-hub-preview-pipeline"})
        try:
            with urlopen(req, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError):
            time.sleep(3)
            continue
        checks = payload.get("check_runs") if isinstance(payload, dict) else []
        matched = [x for x in checks or [] if isinstance(x, dict) and x.get("name") == name and
                   isinstance(x.get("app"), dict) and x["app"].get("slug") == app_slug and x.get("head_sha") == commit_sha]
        if any(x.get("status") == "completed" and x.get("conclusion") == "success" for x in matched):
            return
        if matched and all(x.get("status") == "completed" for x in matched) and not any(x.get("conclusion") == "success" for x in matched):
            raise SystemExit("PREVIEW_PIPELINE_CLOUDFLARE_BUILD_FAILED")
        time.sleep(3)
    raise SystemExit("PREVIEW_PIPELINE_CLOUDFLARE_BUILD_TIMEOUT")


def binding_for_project(repo: Path, project: str) -> dict[str, Any]:
    doc = load(repo / "dev-hub/config/cloudflare-pages-project-bindings.v1.json")
    binding = ((doc.get("projects") or {}).get(project))
    if not isinstance(binding, dict):
        raise SystemExit("PREVIEW_PIPELINE_PROJECT_BINDING_MISSING")
    return binding


def create_cloudflare_runtime_binding(repo: Path, runtime_root: Path, project: str,
                                      selected_provider: str, adapters: dict[str, Any]) -> tuple[Path, dict[str, Any]]:
    providers = adapters.get("providers") if isinstance(adapters.get("providers"), dict) else {}
    pdef = providers.get(selected_provider) if isinstance(providers, dict) else None
    if not isinstance(pdef, dict) or pdef.get("execution") != "external":
        raise SystemExit("PREVIEW_PIPELINE_SELECTED_PROVIDER_NOT_EXTERNAL")
    adapter_id = str(pdef.get("adapter") or "")
    adef = ((adapters.get("adapters") or {}).get(adapter_id))
    if not isinstance(adef, dict) or adef.get("status") != "ENABLED" or adef.get("executable") is not None:
        raise SystemExit("PREVIEW_PIPELINE_SELECTED_ADAPTER_NOT_ENABLED_EXTERNAL")
    if adapter_id != "cloudflare-pages-adapter":
        raise SystemExit("PREVIEW_PIPELINE_V1_SELECTED_ADAPTER_UNSUPPORTED")
    source = repo / "dev-hub/adapters/cloudflare-pages-adapter.py"
    if not source.is_file():
        raise SystemExit("PREVIEW_PIPELINE_CLOUDFLARE_ADAPTER_SOURCE_MISSING")
    runtime_root.mkdir(parents=True, exist_ok=True)
    if inside(runtime_root, repo):
        raise SystemExit("PREVIEW_PIPELINE_RUNTIME_ROOT_IN_REPOSITORY")
    launcher_dir = runtime_root / "launchers"
    launcher_dir.mkdir(parents=True, exist_ok=True)
    launcher = launcher_dir / adapter_id
    launcher.write_text("#!/usr/bin/env bash\nset -euo pipefail\nexec python3 " + json.dumps(str(source.resolve())) + "\n", encoding="utf-8")
    launcher.chmod(0o700)
    issued = now()
    binding_file = runtime_root / "runtime-bindings.json"
    doc = {
        "schema": BINDING_SCHEMA,
        "project": project,
        "source": "trusted-runner",
        "issued_at": issued.isoformat(),
        "expires_at": (issued + timedelta(minutes=20)).isoformat(),
        "bindings": {
            adapter_id: {"adapter": adapter_id, "execution": "external", "executable": str(launcher.resolve()),
                         "digest": sha256_file(launcher)}
        },
    }
    save(binding_file, doc)
    return binding_file, {"provider": selected_provider, "adapter": adapter_id, "launcher_digest": doc["bindings"][adapter_id]["digest"]}


def selected_provider(plan: dict[str, Any]) -> str:
    found: list[str] = []
    for wave in plan.get("waves") or []:
        for task in (wave.get("tasks") or []) if isinstance(wave, dict) else []:
            for item in (task.get("provider_bindings") or []) if isinstance(task, dict) else []:
                if isinstance(item, dict) and isinstance(item.get("provider"), str):
                    found.append(item["provider"])
    unique = sorted(set(found))
    if len(unique) != 1:
        raise SystemExit("PREVIEW_PIPELINE_PROVIDER_SELECTION_AMBIGUOUS=" + ",".join(unique))
    return unique[0]


def immutable_preview_url(result: dict[str, Any], binding: dict[str, Any]) -> str:
    if result.get("status") != "OK" or (result.get("verification") or {}).get("status") != "UNVERIFIED":
        raise SystemExit("PREVIEW_PIPELINE_PREVIEW_RESULT_NOT_OK_UNVERIFIED")
    urls = [str(x.get("url")) for x in result.get("outputs") or [] if isinstance(x, dict) and x.get("id") == "cloudflare-pages-immutable-preview" and x.get("url")]
    if len(urls) != 1:
        raise SystemExit("PREVIEW_PIPELINE_IMMUTABLE_URL_MISSING")
    raw = urls[0]
    try:
        p = urlsplit(raw)
    except ValueError as exc:
        raise SystemExit("PREVIEW_PIPELINE_IMMUTABLE_URL_INVALID") from exc
    host = (p.hostname or "").lower().rstrip(".")
    suffix = str(binding.get("immutable_preview_host_suffix") or "").lower()
    production = str(binding.get("production_url") or "").rstrip("/")
    if p.scheme != "https" or not host or not suffix or not host.endswith(suffix) or raw.rstrip("/") == production:
        raise SystemExit("PREVIEW_PIPELINE_IMMUTABLE_URL_NOT_ALLOWED")
    return raw


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True, type=Path)
    ap.add_argument("--repo-root", type=Path, default=Path.cwd())
    ap.add_argument("--project-control-policy", type=Path, default=Path("dev-hub/config/project-control.v1.json"))
    ap.add_argument("--contract", type=Path, default=Path("dev-hub/config/project-manifest-contract.v1.json"))
    ap.add_argument("--runtime-root", type=Path)
    ap.add_argument("--build-wait-seconds", type=int, default=300)
    ap.add_argument("--execute", action="store_true")
    ap.add_argument("--output", type=Path)
    args = ap.parse_args()

    repo = args.repo_root.resolve()
    manifest_path = args.manifest.resolve()
    manifest = load(manifest_path)
    contract = load(resolve(repo, args.contract))
    project, wf, definition = validate_manifest(manifest, contract)
    policy_path = resolve(repo, args.project_control_policy)
    policy = load(policy_path)
    refs = policy.get("repository_paths") or {}
    registry_path = resolve(repo, str(refs["capability_registry"]))
    adapters_path = resolve(repo, str(refs["provider_adapters"]))
    registry = load(registry_path)
    adapters = load(adapters_path)
    for capability, _permission in provider_requirements(definition):
        require_capability(registry, capability)

    binding = binding_for_project(repo, project)
    if wf["branch"] == binding.get("production_branch"):
        raise SystemExit("PREVIEW_PIPELINE_PRODUCTION_BRANCH_FORBIDDEN")
    if os.environ.get("GITHUB_REPOSITORY") and os.environ["GITHUB_REPOSITORY"] != binding.get("repository"):
        raise SystemExit("PREVIEW_PIPELINE_RUNNER_REPOSITORY_MISMATCH")
    if os.environ.get("GITHUB_REF_NAME") and os.environ["GITHUB_REF_NAME"] != wf["branch"]:
        raise SystemExit("PREVIEW_PIPELINE_RUNNER_BRANCH_MISMATCH")
    if os.environ.get("GITHUB_SHA") and os.environ["GITHUB_SHA"] != wf["commit_sha"]:
        raise SystemExit("PREVIEW_PIPELINE_RUNNER_COMMIT_MISMATCH")

    boot = bootstrap(repo, project, policy, policy_path, registry, adapters, definition)
    graph_path = boot["roots"]["plans"] / "preview-pipeline.task-graph.json"
    save(graph_path, preview_graph(project, wf, definition))
    schedule = project_control(repo, policy_path, ["schedule", "--project", project, "--graph", str(graph_path)])
    if schedule.get("status") != "OK":
        raise SystemExit("PREVIEW_PIPELINE_SCHEDULE_BLOCKED=" + json.dumps(schedule, ensure_ascii=False))
    preview_plan_path = Path(str((schedule.get("details") or {}).get("execution_plan") or ""))
    preview_plan = load(preview_plan_path)
    selected = selected_provider(preview_plan)

    receipt: dict[str, Any] = {
        "schema": "chacha.dev/project-preview-pipeline-run/v1",
        "project": project,
        "workflow_id": wf["id"],
        "environment_class": "preview",
        "observed_at": now_iso(),
        "source_commit_sha": wf["commit_sha"],
        "source_branch": wf["branch"],
        "manifest": str(manifest_path),
        "preview_task_graph": str(graph_path),
        "preview_execution_plan": str(preview_plan_path),
        "preview_provider_selected_by_scheduler": selected,
        "provider_selection_owned_by_scheduler": True,
        "executed": False,
        "production_touched": False,
        "blockers": [],
    }
    if not args.execute:
        receipt.update({"status": "PLANNED", "runtime_binding_created": False, "browser_runtime_provisioned": False})
        if args.output:
            save(args.output, receipt)
        print("PREVIEW_PIPELINE_STATUS=PLANNED")
        print(f"PREVIEW_EXECUTION_PLAN={preview_plan_path}")
        return 0

    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not token:
        raise SystemExit("PREVIEW_PIPELINE_GITHUB_TOKEN_MISSING")
    wait_for_pages_check(binding, wf["commit_sha"], token, max(10, min(args.build_wait_seconds, 900)))

    if args.runtime_root:
        runtime_root = args.runtime_root.resolve()
        runtime_root.mkdir(parents=True, exist_ok=True)
    else:
        runtime_root = Path(tempfile.mkdtemp(prefix="chacha-preview-pipeline-"))
    binding_path, binding_receipt = create_cloudflare_runtime_binding(repo, runtime_root / "cloudflare", project, selected, adapters)
    env = os.environ.copy()
    env["CHACHA_DEV_RUNTIME_BINDINGS"] = str(binding_path.resolve())
    dispatch = project_control(repo, policy_path, ["dispatch", "--project", project, "--plan", str(preview_plan_path),
                                                     "--graph", str(graph_path), "--execute"], env=env)
    if dispatch.get("status") != "OK":
        raise SystemExit("PREVIEW_PIPELINE_DISPATCH_FAILED=" + json.dumps(dispatch, ensure_ascii=False))
    preview_run_id = str((dispatch.get("details") or {}).get("RUN_ID") or "")
    preview_run_record = Path(str((dispatch.get("details") or {}).get("RUN_RECORD") or ""))
    results = result_paths(load(preview_run_record))
    preview_task_id = f"{wf['id']}:preview"
    result_path = results.get(preview_task_id)
    if not result_path:
        raise SystemExit("PREVIEW_PIPELINE_PROVIDER_RESULT_MISSING")
    preview_result = load(result_path)
    preview_url = immutable_preview_url(preview_result, binding)

    child_manifest = {
        "schema": MANIFEST_SCHEMA,
        "project": project,
        "environment": {"class": "preview"},
        "workflows": [{"id": f"{wf['id']}:browser", "kind": "browser-verification", "target": {"url": preview_url}}],
    }
    if wf.get("expected_text") is not None:
        child_manifest["workflows"][0]["target"]["expected_text"] = wf["expected_text"]
    child_manifest_path = runtime_root / "browser-verification.manifest.json"
    save(child_manifest_path, child_manifest)
    browser_receipt_path = runtime_root / "browser-verification.receipt.json"
    run(["python3", "dev-hub/bin/trusted-runtime-provisioner-v2.py", "--repo-root", str(repo),
         "--project-control-policy", str(policy_path), "--manifest", str(child_manifest_path),
         "--runtime-root", str(runtime_root / "browser-runtime"), "--execute", "--output", str(browser_receipt_path)],
        repo, env=os.environ.copy(), timeout=1800)
    browser = load(browser_receipt_path)
    if browser.get("status") != "VERIFIED" or browser.get("executed") is not True:
        raise SystemExit("PREVIEW_PIPELINE_BROWSER_VERIFICATION_FAILED=" + json.dumps(browser, ensure_ascii=False))
    integrity = project_control(repo, policy_path, ["verify-state", "--project", project])
    if integrity.get("status") != "OK":
        raise SystemExit("PREVIEW_PIPELINE_AUDIT_INTEGRITY_FAILED")

    receipt.update({
        "status": "VERIFIED",
        "executed": True,
        "cloudflare_managed_build_observed": True,
        "immutable_preview_url": preview_url,
        "preview_run_id": preview_run_id,
        "preview_provider_result": str(result_path),
        "preview_provider_result_status": preview_result.get("status"),
        "preview_provider_result_verification": (preview_result.get("verification") or {}).get("status"),
        "preview_provider_result_used_as_unverified_routing_input": True,
        "runtime_binding_created": True,
        "runtime_binding": binding_receipt,
        "browser_runtime_provisioned": True,
        "browser_chain_status": browser.get("status"),
        "browser_run_id": browser.get("run_id"),
        "browser_verified_workflows": browser.get("verified_workflows") or [],
        "audit_integrity": browser.get("audit_integrity") or "PASS",
        "repository_registry_mutated": False,
        "production_touched": False,
    })
    if args.output:
        save(args.output, receipt)
    print("PREVIEW_PIPELINE_STATUS=VERIFIED")
    print(f"PREVIEW_URL={preview_url}")
    print(f"PREVIEW_RUN_ID={preview_run_id}")
    if browser.get("run_id"):
        print(f"BROWSER_RUN_ID={browser['run_id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
