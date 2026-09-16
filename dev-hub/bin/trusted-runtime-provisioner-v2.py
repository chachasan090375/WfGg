#!/usr/bin/env python3
"""Trusted Runtime Provisioner V2 boundary wrapper.

Derives the Playwright target class and exact allowed origin from the canonical
project manifest before delegating to the already-qualified V1 provisioner.
Caller-supplied PLAYWRIGHT_MCP_TARGET_CLASS / PLAYWRIGHT_MCP_ALLOWED_ORIGIN values
are overwritten and therefore cannot widen the runtime scope.

V1 remains the provisioning engine; this wrapper only adds the trusted boundary
required by Playwright MCP controlled external test/preview navigation.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

MANIFEST_SCHEMA = "chacha.dev/project-manifest/v1"


def arg_value(name: str) -> str | None:
    argv = sys.argv[1:]
    for i, item in enumerate(argv):
        if item == name and i + 1 < len(argv):
            return argv[i + 1]
        prefix = name + "="
        if item.startswith(prefix):
            return item[len(prefix):]
    return None


def normalized_origin(raw: str) -> str:
    try:
        p = urlsplit(raw)
    except ValueError as exc:
        raise SystemExit("TRUSTED_RUNTIME_V2_TARGET_URL_INVALID") from exc
    if p.scheme not in {"http", "https"} or not p.hostname or p.username or p.password:
        raise SystemExit("TRUSTED_RUNTIME_V2_TARGET_URL_DENIED")
    host = p.hostname.lower().rstrip(".")
    default_port = 80 if p.scheme == "http" else 443
    port = p.port or default_port
    suffix = "" if port == default_port else f":{port}"
    return f"{p.scheme}://{host}{suffix}"


def main() -> int:
    manifest_arg = arg_value("--manifest")
    if not manifest_arg:
        raise SystemExit("TRUSTED_RUNTIME_V2_MANIFEST_REQUIRED")
    manifest_path = Path(manifest_arg).resolve()
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit(f"TRUSTED_RUNTIME_V2_MANIFEST_NOT_FOUND={manifest_path}")
    except json.JSONDecodeError as exc:
        raise SystemExit(f"TRUSTED_RUNTIME_V2_MANIFEST_JSON_INVALID={exc.lineno}:{exc.colno}")
    if not isinstance(manifest, dict) or manifest.get("schema") != MANIFEST_SCHEMA:
        raise SystemExit("TRUSTED_RUNTIME_V2_MANIFEST_SCHEMA_INVALID")

    env_class = str(((manifest.get("environment") or {}).get("class")) or "")
    if env_class not in {"test", "preview"}:
        raise SystemExit(f"TRUSTED_RUNTIME_V2_TARGET_CLASS_DENIED={env_class}")

    workflows = manifest.get("workflows")
    if not isinstance(workflows, list) or not workflows:
        raise SystemExit("TRUSTED_RUNTIME_V2_WORKFLOWS_REQUIRED")
    origins: set[str] = set()
    for workflow in workflows:
        target = workflow.get("target") if isinstance(workflow, dict) and isinstance(workflow.get("target"), dict) else {}
        raw = target.get("url")
        if not isinstance(raw, str) or not raw:
            raise SystemExit("TRUSTED_RUNTIME_V2_TARGET_URL_REQUIRED")
        origins.add(normalized_origin(raw))
    if len(origins) != 1:
        raise SystemExit("TRUSTED_RUNTIME_V2_MULTI_ORIGIN_NOT_SUPPORTED")
    allowed_origin = next(iter(origins))

    env = os.environ.copy()
    # Always overwrite caller values: manifest is the only source of authority.
    env["PLAYWRIGHT_MCP_TARGET_CLASS"] = env_class
    env["PLAYWRIGHT_MCP_ALLOWED_ORIGIN"] = allowed_origin
    env["CHACHA_TRUSTED_RUNTIME_V2_BOUNDARY"] = "manifest-exact-origin"

    repo_arg = arg_value("--repo-root")
    repo = Path(repo_arg).resolve() if repo_arg else Path.cwd().resolve()
    engine = repo / "dev-hub" / "bin" / "trusted-runtime-provisioner.py"
    if not engine.is_file():
        raise SystemExit(f"TRUSTED_RUNTIME_V2_ENGINE_NOT_FOUND={engine}")

    proc = subprocess.run(
        [sys.executable, str(engine), *sys.argv[1:]],
        cwd=str(repo), env=env, shell=False, check=False,
    )
    return int(proc.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
