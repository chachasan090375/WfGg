#!/usr/bin/env python3
"""ChaCha DEV HUB Trusted Runtime Provisioner V1.

One explicit execution entry point for provider-agnostic project manifests.
The provisioner first asks project-bootstrap to create/schedule the project in
plan-only mode, reads the resulting canonical execution plan, provisions only
required ENABLED external providers using exact versions from their authoritative
provider contracts, creates short-lived runner-owned SHA-256 bindings outside the
repository, then asks project-bootstrap to execute with those bindings.

No task can select a package version, executable, binding file, or provider.
Provider selection stays Scheduler-owned and provider results stay UNVERIFIED
until the Verification Broker completes independent verification.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

POLICY_SCHEMA = "chacha.dev/trusted-runtime-provisioner-policy/v1"
BINDING_POLICY_SCHEMA = "chacha.dev/external-runtime-binding-policy/v1"
BINDING_SCHEMA = "chacha.dev/runtime-bindings/v1"
ADAPTER_SCHEMA = "chacha.dev/provider-adapters/v1"
PLAN_SCHEMA = "chacha.dev/execution-plan/v1"
MANIFEST_SCHEMA = "chacha.dev/project-manifest/v1"
PROJECT_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$")


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


def run(argv: list[str], cwd: Path, env: dict[str, str] | None = None, timeout: int = 1200) -> subprocess.CompletedProcess[str]:
    started = time.monotonic()
    proc = subprocess.run(
        argv,
        cwd=str(cwd),
        env=env or os.environ.copy(),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        shell=False,
        check=False,
        timeout=timeout,
    )
    proc.elapsed_seconds = round(time.monotonic() - started, 3)  # type: ignore[attr-defined]
    if proc.returncode != 0:
        raise SystemExit(
            f"COMMAND_FAILED={proc.returncode}:{' '.join(argv)}\n"
            f"STDOUT={proc.stdout[-4000:]}\nSTDERR={proc.stderr[-4000:]}"
        )
    return proc


def origin(raw: str) -> str:
    try:
        p = urlsplit(raw)
    except ValueError as exc:
        raise SystemExit("MANIFEST_TARGET_URL_INVALID") from exc
    if p.scheme not in {"http", "https"} or not p.hostname or p.username or p.password:
        raise SystemExit("MANIFEST_TARGET_URL_DENIED")
    host = p.hostname.lower().rstrip(".")
    default_port = 80 if p.scheme == "http" else 443
    port = p.port or default_port
    suffix = "" if port == default_port else f":{port}"
    return f"{p.scheme}://{host}{suffix}"


def manifest_identity(manifest: dict[str, Any]) -> tuple[str, str, set[str]]:
    if manifest.get("schema") != MANIFEST_SCHEMA:
        raise SystemExit(f"MANIFEST_SCHEMA_INVALID={manifest.get('schema')}")
    project = str(manifest.get("project") or "")
    if not PROJECT_RE.match(project):
        raise SystemExit("MANIFEST_PROJECT_INVALID")
    env_class = str(((manifest.get("environment") or {}).get("class")) or "")
    targets: set[str] = set()
    workflows = manifest.get("workflows")
    if not isinstance(workflows, list) or not workflows:
        raise SystemExit("MANIFEST_WORKFLOWS_REQUIRED")
    for item in workflows:
        target = item.get("target") if isinstance(item, dict) and isinstance(item.get("target"), dict) else {}
        raw = target.get("url")
        if not isinstance(raw, str) or not raw:
            raise SystemExit("MANIFEST_TARGET_URL_REQUIRED")
        targets.add(origin(raw))
    return project, env_class, targets


def required_external_providers(plan: dict[str, Any], registry: dict[str, Any]) -> list[str]:
    if plan.get("schema") != PLAN_SCHEMA:
        raise SystemExit(f"EXECUTION_PLAN_SCHEMA_INVALID={plan.get('schema')}")
    if registry.get("schema") != ADAPTER_SCHEMA:
        raise SystemExit(f"PROVIDER_ADAPTER_SCHEMA_INVALID={registry.get('schema')}")
    providers = registry.get("providers") if isinstance(registry.get("providers"), dict) else {}
    required: set[str] = set()
    for wave in plan.get("waves") or []:
        if not isinstance(wave, dict):
            continue
        for task in wave.get("tasks") or []:
            if not isinstance(task, dict):
                continue
            for binding in task.get("provider_bindings") or []:
                if not isinstance(binding, dict):
                    continue
                provider = binding.get("provider")
                pdef = providers.get(provider) if isinstance(provider, str) else None
                if isinstance(pdef, dict) and pdef.get("execution") == "external":
                    required.add(provider)
    return sorted(required)


def package_json_path(workdir: Path, package: str) -> Path:
    parts = package.split("/")
    return workdir / "node_modules" / Path(*parts) / "package.json"


def node_major(repo: Path) -> int:
    proc = run(["node", "--version"], repo, timeout=30)
    text = proc.stdout.strip().lstrip("v")
    try:
        return int(text.split(".", 1)[0])
    except Exception as exc:
        raise SystemExit(f"NODE_VERSION_UNPARSEABLE={text}") from exc


def browser_version(repo: Path) -> str:
    for candidate in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
        path = shutil.which(candidate)
        if not path:
            continue
        proc = run([path, "--version"], repo, timeout=30)
        value = proc.stdout.strip() or proc.stderr.strip()
        if value:
            return value
    raise SystemExit("TRUSTED_RUNTIME_CHROME_NOT_FOUND")


def verify_provider_contract(
    repo: Path,
    provider: str,
    pconfig: dict[str, Any],
    registry: dict[str, Any],
) -> tuple[dict[str, Any], str, str, str]:
    provider_defs = registry.get("providers") if isinstance(registry.get("providers"), dict) else {}
    adapter_defs = registry.get("adapters") if isinstance(registry.get("adapters"), dict) else {}
    pdef = provider_defs.get(provider)
    if not isinstance(pdef, dict) or pdef.get("execution") != "external":
        raise SystemExit(f"TRUSTED_RUNTIME_PROVIDER_NOT_EXTERNAL={provider}")
    adapter = str(pconfig.get("adapter") or "")
    if not adapter or pdef.get("adapter") != adapter:
        raise SystemExit(f"TRUSTED_RUNTIME_ADAPTER_BINDING_MISMATCH={provider}")
    adef = adapter_defs.get(adapter)
    if not isinstance(adef, dict) or adef.get("status") != "ENABLED":
        raise SystemExit(f"TRUSTED_RUNTIME_ADAPTER_NOT_ENABLED={provider}:{adapter}")
    if adef.get("executable") is not None:
        raise SystemExit(f"TRUSTED_RUNTIME_STATIC_EXECUTABLE_FORBIDDEN={provider}")

    contract_path = resolve(repo, str(pconfig.get("contract") or ""))
    contract = load(contract_path)
    if contract.get("provider_id") != provider or contract.get("adapter_id") != adapter:
        raise SystemExit(f"TRUSTED_RUNTIME_CONTRACT_ID_MISMATCH={provider}")
    if contract.get("runtime_status") != "ENABLED":
        raise SystemExit(f"TRUSTED_RUNTIME_CONTRACT_NOT_ENABLED={provider}")
    upstream = contract.get("upstream") if isinstance(contract.get("upstream"), dict) else {}
    if upstream.get("runtime_must_pin_exact_version") is not True:
        raise SystemExit(f"TRUSTED_RUNTIME_EXACT_PIN_NOT_REQUIRED={provider}")
    package = str(upstream.get("package") or "")
    version = str(upstream.get("design_reference_version") or "")
    if not package or not version:
        raise SystemExit(f"TRUSTED_RUNTIME_PACKAGE_PIN_MISSING={provider}")
    minimum_node = upstream.get("minimum_node_major")
    if isinstance(minimum_node, int) and node_major(repo) < minimum_node:
        raise SystemExit(f"TRUSTED_RUNTIME_NODE_TOO_OLD={provider}:{minimum_node}")
    return contract, package, version, adapter


def provision_provider(
    repo: Path,
    session: Path,
    provider: str,
    pconfig: dict[str, Any],
    registry: dict[str, Any],
    env_class: str,
    origins: set[str],
) -> tuple[dict[str, Any], dict[str, str], dict[str, Any]]:
    contract, package, version, adapter = verify_provider_contract(repo, provider, pconfig, registry)
    workdir = session / "providers" / provider
    workdir.mkdir(parents=True, exist_ok=False)
    run(["npm", "init", "-y"], workdir, timeout=60)
    install = run(["npm", "install", "--no-save", "--no-audit", "--no-fund", f"{package}@{version}"], workdir, timeout=600)

    installed_json = package_json_path(workdir, package)
    installed = load(installed_json)
    if str(installed.get("version")) != version:
        raise SystemExit(f"TRUSTED_RUNTIME_INSTALLED_VERSION_MISMATCH={provider}:{installed.get('version')}:{version}")
    package_binary = workdir / "node_modules" / ".bin" / str(pconfig.get("package_binary") or "")
    if not package_binary.exists():
        raise SystemExit(f"TRUSTED_RUNTIME_PACKAGE_BINARY_MISSING={provider}:{package_binary}")

    browser_install = pconfig.get("browser_install")
    browser_install_seconds = 0.0
    if browser_install == "playwright-chromium-with-deps":
        playwright_cli = workdir / "node_modules" / ".bin" / "playwright"
        if not playwright_cli.exists():
            raise SystemExit("TRUSTED_RUNTIME_PLAYWRIGHT_INSTALLER_MISSING")
        browser_proc = run([str(playwright_cli), "install", "--with-deps", "chromium"], workdir, timeout=1200)
        browser_install_seconds = float(getattr(browser_proc, "elapsed_seconds", 0.0))
    elif browser_install != "none":
        raise SystemExit(f"TRUSTED_RUNTIME_BROWSER_INSTALL_MODE_DENIED={provider}:{browser_install}")

    source = resolve(repo, str(pconfig.get("launcher_source") or ""))
    if not source.is_file() or not inside(source, repo):
        raise SystemExit(f"TRUSTED_RUNTIME_LAUNCHER_SOURCE_INVALID={provider}")
    launcher_dir = session / "launchers"
    launcher_dir.mkdir(parents=True, exist_ok=True)
    launcher = launcher_dir / adapter
    launcher.write_text(
        "#!/usr/bin/env bash\nset -euo pipefail\nexec python3 " + json.dumps(str(source)) + "\n",
        encoding="utf-8",
    )
    launcher.chmod(0o700)

    env_names = pconfig.get("runtime_environment") if isinstance(pconfig.get("runtime_environment"), dict) else {}
    runtime_env: dict[str, str] = {}
    server_var, workdir_var = env_names.get("server"), env_names.get("workdir")
    if not isinstance(server_var, str) or not isinstance(workdir_var, str):
        raise SystemExit(f"TRUSTED_RUNTIME_ENVIRONMENT_CONTRACT_INVALID={provider}")
    runtime_env[server_var] = str(package_binary.resolve())
    runtime_env[workdir_var] = str(workdir.resolve())

    observed_browser: str | None = None
    if provider == "chrome-devtools-mcp":
        if len(origins) != 1:
            raise SystemExit("TRUSTED_RUNTIME_CHROME_MULTI_ORIGIN_NOT_SUPPORTED_V1")
        observed_browser = browser_version(repo)
        for logical, value in {
            "package_version": version,
            "browser_version": observed_browser,
            "target_class": env_class,
            "allowed_origin": next(iter(origins)),
        }.items():
            env_name = env_names.get(logical)
            if not isinstance(env_name, str) or not env_name:
                raise SystemExit(f"TRUSTED_RUNTIME_ENVIRONMENT_CONTRACT_INVALID={provider}:{logical}")
            runtime_env[env_name] = value

    binding = {
        "adapter": adapter,
        "execution": "external",
        "executable": str(launcher.resolve()),
        "digest": sha256_file(launcher),
    }
    receipt = {
        "provider": provider,
        "adapter": adapter,
        "contract": str(resolve(repo, str(pconfig.get("contract")))),
        "package": package,
        "version": version,
        "package_binary_digest": sha256_file(package_binary.resolve()),
        "launcher_digest": binding["digest"],
        "browser_install": browser_install,
        "browser_version": observed_browser,
        "npm_install_seconds": float(getattr(install, "elapsed_seconds", 0.0)),
        "browser_install_seconds": browser_install_seconds,
        "contract_runtime_status": contract.get("runtime_status"),
        "provider_result_trust": ((contract.get("protocol") or {}).get("provider_result_trust") or
                                  (contract.get("protocol") or {}).get("provider_result_verification") or "UNVERIFIED"),
    }
    return binding, runtime_env, receipt


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True, type=Path)
    ap.add_argument("--repo-root", type=Path, default=Path.cwd())
    ap.add_argument("--project-control-policy", type=Path, default=Path("dev-hub/config/project-control.v1.json"))
    ap.add_argument("--provisioner-policy", type=Path, default=Path("dev-hub/config/trusted-runtime-provisioner.v1.json"))
    ap.add_argument("--runtime-root", type=Path)
    ap.add_argument("--execute", action="store_true")
    ap.add_argument("--output", type=Path)
    args = ap.parse_args()

    repo = args.repo_root.resolve()
    manifest_path = args.manifest.resolve()
    manifest = load(manifest_path)
    project, env_class, origins = manifest_identity(manifest)
    policy_path = resolve(repo, args.provisioner_policy)
    policy = load(policy_path)
    if policy.get("schema") != POLICY_SCHEMA:
        raise SystemExit(f"TRUSTED_RUNTIME_POLICY_SCHEMA_INVALID={policy.get('schema')}")
    project_policy = resolve(repo, args.project_control_policy)
    project_policy_value = load(project_policy)
    refs = project_policy_value.get("repository_paths") if isinstance(project_policy_value.get("repository_paths"), dict) else {}
    registry_path = resolve(repo, str(refs.get("provider_adapters") or "dev-hub/config/provider-adapters.v1.json"))
    registry = load(registry_path)

    binding_policy_path = resolve(repo, str(policy.get("binding_policy") or ""))
    binding_policy = load(binding_policy_path)
    if binding_policy.get("schema") != BINDING_POLICY_SCHEMA:
        raise SystemExit("TRUSTED_RUNTIME_BINDING_POLICY_INVALID")
    ttl = int(policy.get("binding_ttl_seconds") or 0)
    maximum_ttl = int(((binding_policy.get("time") or {}).get("maximum_ttl_seconds")) or 0)
    if ttl <= 0 or maximum_ttl <= 0 or ttl > maximum_ttl:
        raise SystemExit("TRUSTED_RUNTIME_BINDING_TTL_INVALID")

    if args.runtime_root:
        runtime_parent = args.runtime_root.resolve()
        if inside(runtime_parent, repo):
            raise SystemExit("TRUSTED_RUNTIME_ROOT_IN_REPOSITORY")
        runtime_parent.mkdir(parents=True, exist_ok=True)
        session = Path(tempfile.mkdtemp(prefix=f"{project}-", dir=str(runtime_parent)))
    else:
        session = Path(tempfile.mkdtemp(prefix=f"chacha-trusted-runtime-{project}-"))
    if inside(session, repo):
        raise SystemExit("TRUSTED_RUNTIME_SESSION_IN_REPOSITORY")

    output = args.output.resolve() if args.output else session / "trusted-runtime-receipt.json"
    if inside(output, repo):
        raise SystemExit("TRUSTED_RUNTIME_OUTPUT_IN_REPOSITORY")

    bootstrap_plan = session / "bootstrap-plan.json"
    plan_command = [
        "python3", "dev-hub/bin/project-bootstrap.py",
        "--repo-root", str(repo),
        "--project-control-policy", str(project_policy),
        "--manifest", str(manifest_path),
        "--output", str(bootstrap_plan),
    ]
    run(plan_command, repo, timeout=1200)
    planned = load(bootstrap_plan)
    if planned.get("status") != "PLANNED" or planned.get("executed") is not False:
        raise SystemExit(f"TRUSTED_RUNTIME_PLAN_BOOTSTRAP_INVALID={planned.get('status')}")
    plan_path = Path(str(planned.get("execution_plan") or ""))
    execution_plan = load(plan_path)
    required = required_external_providers(execution_plan, registry)

    base_receipt: dict[str, Any] = {
        "schema": "chacha.dev/trusted-runtime-provisioning-run/v1",
        "project": project,
        "environment_class": env_class,
        "observed_at": now_iso(),
        "manifest": str(manifest_path),
        "session_root": str(session),
        "execution_plan": str(plan_path),
        "provider_selection_owned_by_scheduler": planned.get("provider_selection_owned_by_scheduler") is True,
        "required_external_providers": required,
        "versions_selected_by_task": False,
        "executables_selected_by_task": False,
        "binding_selected_by_task": False,
        "registry_mutated": False,
        "production_touched": False,
        "blockers": [],
    }
    if not args.execute:
        base_receipt.update({
            "status": "PLANNED",
            "executed": False,
            "provisioned": {},
            "runtime_binding_created": False,
            "project_bootstrap": planned,
        })
        save(output, base_receipt)
        print("TRUSTED_RUNTIME_STATUS=PLANNED")
        print(f"PROJECT={project}")
        print(f"EXECUTION_PLAN={plan_path}")
        print("RUNTIME_PROVISIONED=NO")
        return 0

    provider_configs = policy.get("providers") if isinstance(policy.get("providers"), dict) else {}
    bindings: dict[str, dict[str, Any]] = {}
    execution_env = os.environ.copy()
    provisioned: dict[str, Any] = {}
    for provider in required:
        pconfig = provider_configs.get(provider)
        if not isinstance(pconfig, dict):
            raise SystemExit(f"TRUSTED_RUNTIME_PROVIDER_NOT_ALLOWLISTED={provider}")
        binding, provider_env, provider_receipt = provision_provider(
            repo, session, provider, pconfig, registry, env_class, origins
        )
        bindings[binding["adapter"]] = binding
        execution_env.update(provider_env)
        provisioned[provider] = provider_receipt

    binding_env_name = str(((binding_policy.get("environment") or {}).get("binding_file_variable")) or "")
    binding_source = str(((binding_policy.get("environment") or {}).get("allowed_source")) or "")
    if not binding_env_name or not binding_source:
        raise SystemExit("TRUSTED_RUNTIME_BINDING_ENVIRONMENT_INVALID")
    issued = now()
    binding_path = session / "runtime-bindings.json"
    binding_document = {
        "schema": BINDING_SCHEMA,
        "project": project,
        "source": binding_source,
        "issued_at": issued.isoformat(),
        "expires_at": (issued + timedelta(seconds=ttl)).isoformat(),
        "bindings": bindings,
    }
    save(binding_path, binding_document)
    execution_env[binding_env_name] = str(binding_path.resolve())

    executed_path = session / "bootstrap-executed.json"
    execute_command = [
        "python3", "dev-hub/bin/project-bootstrap.py",
        "--repo-root", str(repo),
        "--project-control-policy", str(project_policy),
        "--manifest", str(manifest_path),
        "--execute",
        "--output", str(executed_path),
    ]
    run(execute_command, repo, env=execution_env, timeout=1800)
    executed = load(executed_path)
    if executed.get("status") != "VERIFIED" or executed.get("executed") is not True:
        raise SystemExit(f"TRUSTED_RUNTIME_EXECUTION_NOT_VERIFIED={executed.get('status')}")
    if executed.get("runtime_availability_verified") is not True:
        raise SystemExit("TRUSTED_RUNTIME_AVAILABILITY_NOT_VERIFIED")
    if executed.get("audit_integrity") != "PASS":
        raise SystemExit("TRUSTED_RUNTIME_AUDIT_INTEGRITY_FAILED")

    base_receipt.update({
        "status": "VERIFIED",
        "executed": True,
        "provisioned": provisioned,
        "runtime_binding_created": True,
        "runtime_binding": {
            "schema": BINDING_SCHEMA,
            "source": binding_source,
            "ttl_seconds": ttl,
            "digest": sha256_file(binding_path),
            "path": str(binding_path),
        },
        "initial_project_bootstrap": {
            "status": planned.get("status"),
            "state_created": planned.get("state_created"),
            "ledger_created": planned.get("ledger_created"),
        },
        "project_bootstrap": executed,
        "run_id": executed.get("run_id"),
        "verified_workflows": executed.get("verified_workflows") or [],
        "audit_integrity": executed.get("audit_integrity"),
        "runtime_availability_verified": True,
    })
    save(output, base_receipt)
    print("TRUSTED_RUNTIME_STATUS=VERIFIED")
    print(f"PROJECT={project}")
    print("PROVISIONED_PROVIDERS=" + ",".join(required))
    print(f"RUN_ID={executed.get('run_id')}")
    print(f"RECEIPT={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
