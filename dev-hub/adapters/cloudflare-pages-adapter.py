#!/usr/bin/env python3
"""ChaCha DEV HUB Cloudflare Pages Git Integration Adapter V1.

Preview-only observer for existing Cloudflare Pages Git integration. The adapter
never calls the Cloudflare API and never receives Cloudflare credentials. It
observes the exact Cloudflare Pages GitHub check run for a trusted project
binding and emits the immutable preview URL as UNVERIFIED provider evidence.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit

INPUT_SCHEMA = "chacha.dev/dispatch-envelope/v1"
OUTPUT_SCHEMA = "chacha.dev/task-result/v1"
ADAPTER_ID = "cloudflare-pages-adapter"
PROVIDER_ID = "cloudflare-pages"
BINDING_SCHEMA = "chacha.dev/cloudflare-pages-project-bindings/v1"
REPO_ROOT = Path(__file__).resolve().parents[2]
BINDINGS_PATH = REPO_ROOT / "dev-hub/config/cloudflare-pages-project-bindings.v1.json"
ALLOWED_METADATA_KEYS = {"source_commit_sha", "source_branch"}
DENIED_METADATA_KEYS = {
    "account_id", "api_token", "token", "project", "project_name",
    "pages_project", "repository", "production_branch", "branch_alias",
    "deployment_id", "preview_url", "provider", "adapter",
}
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
URL_RE = re.compile(r"https://[A-Za-z0-9._-]+\.pages\.dev(?:/[A-Za-z0-9._~!$&'()*+,;=:@%/-]*)?")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("JSON_ROOT_NOT_OBJECT")
    return value


def task_result(request: dict[str, Any], status: str, summary: str,
                evidence: list[dict[str, Any]] | None = None,
                outputs: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    task = request.get("task") if isinstance(request.get("task"), dict) else {}
    observed = now_iso()
    return {
        "schema": OUTPUT_SCHEMA,
        "project": str(request.get("project") or "unknown"),
        "task_id": str(task.get("id") or "unknown"),
        "status": status,
        "producer": ADAPTER_ID,
        "observed_at": observed,
        "summary": summary,
        "evidence": evidence or [],
        "verification": {
            "status": "UNVERIFIED",
            "method": "none",
            "verifier": "none",
            "observed_at": observed,
            "notes": "Cloudflare Pages provider output is unverified until Verification Broker validation.",
        },
        "outputs": outputs or [],
    }


def emit(payload: dict[str, Any], code: int = 0) -> int:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
    return code


def block(request: dict[str, Any], reason: str, code: int = 0) -> int:
    return emit(task_result(request, "BLOCKED", reason, [{
        "kind": "report",
        "source": "cloudflare-pages-adapter-policy",
        "digest": sha256_text(reason),
        "details": {"reason": reason},
    }]), code)


def binding_for(project: str) -> dict[str, Any]:
    doc = load_json(BINDINGS_PATH)
    if doc.get("schema") != BINDING_SCHEMA:
        raise ValueError("CLOUDFLARE_PAGES_BINDING_SCHEMA_INVALID")
    projects = doc.get("projects") if isinstance(doc.get("projects"), dict) else {}
    binding = projects.get(project)
    if not isinstance(binding, dict):
        raise ValueError("CLOUDFLARE_PAGES_PROJECT_BINDING_MISSING")
    return binding


def validate_request(request: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any] | None, str | None]:
    if request.get("schema") != INPUT_SCHEMA:
        return None, None, "INPUT_SCHEMA_INVALID"
    project = request.get("project")
    if not isinstance(project, str) or not project:
        return None, None, "PROJECT_MISSING"
    task = request.get("task")
    if not isinstance(task, dict) or not task.get("id"):
        return None, None, "TASK_ID_MISSING"
    if task.get("permission") != "preview-deploy":
        return None, None, "CLOUDFLARE_PAGES_PREVIEW_PERMISSION_REQUIRED"
    bindings = request.get("bindings")
    if not isinstance(bindings, list) or not any(
        isinstance(x, dict) and x.get("provider") == PROVIDER_ID and x.get("adapter") == ADAPTER_ID
        for x in bindings
    ):
        return None, None, "CLOUDFLARE_PAGES_BINDING_MISSING"
    metadata = request.get("metadata")
    cfg = metadata.get("cloudflare_pages") if isinstance(metadata, dict) else None
    if not isinstance(cfg, dict):
        return None, None, "CLOUDFLARE_PAGES_METADATA_MISSING"
    unknown = sorted(set(cfg) - ALLOWED_METADATA_KEYS)
    if unknown or set(cfg) & DENIED_METADATA_KEYS:
        return None, None, "CLOUDFLARE_PAGES_CALLER_OVERRIDE_FORBIDDEN"
    sha = cfg.get("source_commit_sha")
    branch = cfg.get("source_branch")
    if not isinstance(sha, str) or not SHA_RE.fullmatch(sha):
        return None, None, "CLOUDFLARE_PAGES_SOURCE_COMMIT_INVALID"
    if not isinstance(branch, str) or not branch or len(branch) > 255:
        return None, None, "CLOUDFLARE_PAGES_SOURCE_BRANCH_INVALID"
    try:
        binding = binding_for(project)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return None, None, str(exc)
    if branch == binding.get("production_branch"):
        return None, None, "CLOUDFLARE_PAGES_PRODUCTION_BRANCH_FORBIDDEN"
    runner_repo = os.environ.get("GITHUB_REPOSITORY", "").strip()
    if runner_repo and runner_repo != binding.get("repository"):
        return None, None, "CLOUDFLARE_PAGES_RUNNER_REPOSITORY_MISMATCH"
    runner_branch = os.environ.get("GITHUB_REF_NAME", "").strip()
    if runner_branch and runner_branch != branch:
        return None, None, "CLOUDFLARE_PAGES_RUNNER_BRANCH_MISMATCH"
    return cfg, binding, None


def parse_preview_urls(summary: str, pages_project: str) -> tuple[str | None, str | None]:
    immutable: str | None = None
    alias: str | None = None
    production_host = f"{pages_project}.pages.dev"
    suffix = f".{pages_project}.pages.dev"
    for raw in URL_RE.findall(summary or ""):
        p = urlsplit(raw)
        host = (p.hostname or "").lower().rstrip(".")
        if host == production_host or not host.endswith(suffix):
            continue
        first = host[: -len(suffix)]
        if re.fullmatch(r"[0-9a-f]{8,64}", first):
            immutable = f"https://{host}{p.path or ''}"
        else:
            alias = f"https://{host}{p.path or ''}"
    return immutable, alias


def matching_check(checks: list[Any], binding: dict[str, Any], commit_sha: str) -> tuple[dict[str, Any] | None, str | None, str | None]:
    matches: list[tuple[dict[str, Any], str, str | None]] = []
    for item in checks:
        if not isinstance(item, dict):
            continue
        app = item.get("app") if isinstance(item.get("app"), dict) else {}
        if item.get("name") != binding.get("github_check_name"):
            continue
        if app.get("slug") != binding.get("github_app_slug"):
            continue
        if item.get("head_sha") != commit_sha:
            continue
        output = item.get("output") if isinstance(item.get("output"), dict) else {}
        immutable, alias = parse_preview_urls(str(output.get("summary") or ""), str(binding.get("pages_project") or ""))
        if immutable:
            matches.append((item, immutable, alias))
    successful = [x for x in matches if x[0].get("status") == "completed" and x[0].get("conclusion") == "success"]
    if len(successful) != 1:
        return None, None, None
    return successful[0]


def github_checks(repository: str, commit_sha: str, token: str) -> list[Any]:
    url = f"https://api.github.com/repos/{repository}/commits/{commit_sha}/check-runs?per_page=100"
    req = Request(url, headers={
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "chacha-dev-hub-cloudflare-pages-adapter",
    })
    with urlopen(req, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return payload.get("check_runs") if isinstance(payload, dict) and isinstance(payload.get("check_runs"), list) else []


def main() -> int:
    try:
        request = json.load(sys.stdin)
    except Exception as exc:
        return emit(task_result({"project":"unknown","task":{"id":"unknown"}}, "BLOCKED", f"INPUT_JSON_INVALID:{type(exc).__name__}"), 2)
    if not isinstance(request, dict):
        return block({"project":"unknown","task":{"id":"unknown"}}, "INPUT_ROOT_NOT_OBJECT", 2)
    cfg, binding, error = validate_request(request)
    if error:
        return block(request, error)
    assert cfg is not None and binding is not None
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not token:
        return block(request, "CLOUDFLARE_PAGES_GITHUB_TOKEN_MISSING")
    try:
        checks = github_checks(str(binding["repository"]), str(cfg["source_commit_sha"]), token)
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError):
        return block(request, "CLOUDFLARE_PAGES_GITHUB_CHECKS_UNAVAILABLE")
    check, immutable, alias = matching_check(checks, binding, str(cfg["source_commit_sha"]))
    if check is None or immutable is None:
        return block(request, "CLOUDFLARE_PAGES_PREVIEW_CHECK_NOT_SUCCESSFUL_OR_AMBIGUOUS")
    if immutable.rstrip("/") == str(binding.get("production_url") or "").rstrip("/"):
        return block(request, "CLOUDFLARE_PAGES_PRODUCTION_URL_FORBIDDEN")
    observed = now_iso()
    evidence_details = {
        "binding_id": binding.get("binding_id"),
        "repository": binding.get("repository"),
        "pages_project": binding.get("pages_project"),
        "integration_mode": "git-integration",
        "deployment_environment": "preview",
        "source_commit_sha": cfg.get("source_commit_sha"),
        "source_branch": cfg.get("source_branch"),
        "github_check_run_id": check.get("id"),
        "cloudflare_build_identity": check.get("external_id"),
        "github_check_status": check.get("status"),
        "github_check_conclusion": check.get("conclusion"),
        "branch_alias": alias,
        "immutable_preview_url": immutable,
        "observed_at": observed,
        "cloudflare_credentials_used": False,
        "production_target": False,
        "workers_target_selected": False,
    }
    evidence = [{
        "kind": "url",
        "source": immutable,
        "digest": sha256_text(json.dumps(evidence_details, sort_keys=True, separators=(",", ":"))),
        "details": evidence_details,
    }]
    outputs = [{
        "type": "artifact",
        "id": "cloudflare-pages-immutable-preview",
        "status": "OK",
        "reason": "Trusted Git integration check exposed an immutable non-production Pages preview URL.",
        "url": immutable,
    }]
    return emit(task_result(request, "OK", "CLOUDFLARE_PAGES_PREVIEW_OBSERVED", evidence, outputs))


if __name__ == "__main__":
    raise SystemExit(main())
