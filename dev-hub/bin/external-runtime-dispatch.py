#!/usr/bin/env python3
"""ChaCha DEV HUB External Runtime Dispatcher V1.

Transparent front door for run-controller.py. Local/VPS adapters keep using the
canonical registry. ENABLED providers whose execution class is `external` keep
`executable: null` in that registry and receive an executable only from a
short-lived runner-owned binding file.

The binding file path comes exclusively from CHACHA_DEV_RUNTIME_BINDINGS. Task
metadata and dispatch envelopes cannot select or override it. Before execution
this dispatcher verifies project scope, source, TTL, executable location,
executable bit and SHA-256, then injects the verified executable into a temporary
copy of the adapter registry. The canonical registry is never modified.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / "dev-hub/config/external-runtime-binding.v1.json"
CORE_CONTROLLER = REPO_ROOT / "dev-hub/bin/run-controller.py"
POLICY_SCHEMA = "chacha.dev/external-runtime-binding-policy/v1"
BINDING_SCHEMA = "chacha.dev/runtime-bindings/v1"
ADAPTER_SCHEMA = "chacha.dev/provider-adapters/v1"
PLAN_SCHEMA = "chacha.dev/execution-plan/v1"


def load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ValueError(f"FILE_NOT_FOUND:{path}")
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON_INVALID:{path}:{exc.lineno}:{exc.colno}:{exc.msg}")
    if not isinstance(value, dict):
        raise ValueError(f"JSON_ROOT_NOT_OBJECT:{path}")
    return value


def parse_time(value: Any) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("RUNTIME_BINDING_TIME_MISSING")
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        result = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError("RUNTIME_BINDING_TIME_INVALID") from exc
    if result.tzinfo is None:
        raise ValueError("RUNTIME_BINDING_TIME_MUST_BE_OFFSET_AWARE")
    return result.astimezone(timezone.utc)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def is_inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def block(reason: str) -> int:
    print("EXTERNAL_RUNTIME_BINDING_STATUS=BLOCKED")
    print(f"BLOCKER={reason}")
    return 2


def delegate(argv: list[str]) -> int:
    proc = subprocess.run(
        [sys.executable, str(CORE_CONTROLLER), *argv],
        cwd=str(REPO_ROOT),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        shell=False,
        check=False,
        env=os.environ.copy(),
    )
    if proc.stdout:
        sys.stdout.write(proc.stdout)
    if proc.stderr:
        sys.stderr.write(proc.stderr)
    return proc.returncode


def parse_front(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--adapters", type=Path)
    parser.add_argument("--execute", action="store_true")
    args, _ = parser.parse_known_args(argv)
    return args


def required_external_adapters(plan: dict[str, Any], registry: dict[str, Any]) -> set[str]:
    required: set[str] = set()
    providers = registry.get("providers") if isinstance(registry.get("providers"), dict) else {}
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
                pdef = providers.get(provider) if isinstance(providers, dict) else None
                if isinstance(pdef, dict) and pdef.get("execution") == "external":
                    adapter = pdef.get("adapter")
                    if isinstance(adapter, str) and adapter:
                        required.add(adapter)
    return required


def replace_adapters_arg(argv: list[str], replacement: Path) -> list[str]:
    out = list(argv)
    try:
        idx = out.index("--adapters")
    except ValueError as exc:
        raise ValueError("ADAPTER_REGISTRY_ARGUMENT_MISSING") from exc
    if idx + 1 >= len(out):
        raise ValueError("ADAPTER_REGISTRY_ARGUMENT_INVALID")
    out[idx + 1] = str(replacement)
    return out


def verify_binding_file(
    project: str,
    required: set[str],
    registry: dict[str, Any],
    policy: dict[str, Any],
    binding_path: Path,
) -> dict[str, str]:
    if not binding_path.is_absolute():
        raise ValueError("EXTERNAL_RUNTIME_BINDING_PATH_NOT_ABSOLUTE")
    if is_inside(binding_path, REPO_ROOT):
        raise ValueError("EXTERNAL_RUNTIME_BINDING_FILE_IN_REPOSITORY")
    values = load(binding_path)
    if values.get("schema") != BINDING_SCHEMA:
        raise ValueError(f"EXTERNAL_RUNTIME_BINDING_SCHEMA_INVALID:{values.get('schema')}")
    if values.get("project") != project:
        raise ValueError("EXTERNAL_RUNTIME_BINDING_PROJECT_MISMATCH")
    env_policy = policy.get("environment") if isinstance(policy.get("environment"), dict) else {}
    if values.get("source") != env_policy.get("allowed_source"):
        raise ValueError("EXTERNAL_RUNTIME_BINDING_SOURCE_NOT_TRUSTED")

    issued = parse_time(values.get("issued_at"))
    expires = parse_time(values.get("expires_at"))
    now = datetime.now(timezone.utc)
    time_policy = policy.get("time") if isinstance(policy.get("time"), dict) else {}
    max_ttl = int(time_policy.get("maximum_ttl_seconds") or 3600)
    skew = int(time_policy.get("clock_skew_seconds") or 60)
    if expires <= issued:
        raise ValueError("EXTERNAL_RUNTIME_BINDING_TTL_INVALID")
    if (expires - issued).total_seconds() > max_ttl:
        raise ValueError("EXTERNAL_RUNTIME_BINDING_TTL_TOO_LONG")
    if issued.timestamp() > now.timestamp() + skew:
        raise ValueError("EXTERNAL_RUNTIME_BINDING_ISSUED_IN_FUTURE")
    if expires.timestamp() <= now.timestamp() - skew:
        raise ValueError("EXTERNAL_RUNTIME_BINDING_EXPIRED")

    bindings = values.get("bindings") if isinstance(values.get("bindings"), dict) else {}
    adapters = registry.get("adapters") if isinstance(registry.get("adapters"), dict) else {}
    resolved: dict[str, str] = {}
    for adapter in sorted(required):
        static = adapters.get(adapter) if isinstance(adapters, dict) else None
        if not isinstance(static, dict):
            raise ValueError(f"EXTERNAL_RUNTIME_ADAPTER_NOT_REGISTERED:{adapter}")
        if static.get("status") != "ENABLED":
            raise ValueError(f"EXTERNAL_RUNTIME_ADAPTER_NOT_ENABLED:{adapter}:{static.get('status')}")
        if static.get("executable") is not None:
            raise ValueError(f"EXTERNAL_RUNTIME_STATIC_EXECUTABLE_FORBIDDEN:{adapter}")
        item = bindings.get(adapter) if isinstance(bindings, dict) else None
        if not isinstance(item, dict):
            raise ValueError(f"EXTERNAL_RUNTIME_BINDING_MISSING:{adapter}")
        if item.get("adapter") != adapter:
            raise ValueError(f"EXTERNAL_RUNTIME_BINDING_ADAPTER_MISMATCH:{adapter}")
        if item.get("execution") != "external":
            raise ValueError(f"EXTERNAL_RUNTIME_BINDING_EXECUTION_INVALID:{adapter}")
        raw_executable = item.get("executable")
        if not isinstance(raw_executable, str) or not raw_executable:
            raise ValueError(f"EXTERNAL_RUNTIME_EXECUTABLE_MISSING:{adapter}")
        executable = Path(raw_executable)
        if not executable.is_absolute():
            raise ValueError(f"EXTERNAL_RUNTIME_EXECUTABLE_NOT_ABSOLUTE:{adapter}")
        if is_inside(executable, REPO_ROOT):
            raise ValueError(f"EXTERNAL_RUNTIME_EXECUTABLE_IN_REPOSITORY:{adapter}")
        if not executable.is_file():
            raise ValueError(f"EXTERNAL_RUNTIME_EXECUTABLE_NOT_FILE:{adapter}")
        if not os.access(executable, os.X_OK):
            raise ValueError(f"EXTERNAL_RUNTIME_EXECUTABLE_NOT_EXECUTABLE:{adapter}")
        declared = item.get("digest")
        if not isinstance(declared, str) or not declared.startswith("sha256:"):
            raise ValueError(f"EXTERNAL_RUNTIME_DIGEST_MISSING:{adapter}")
        actual = sha256_file(executable)
        if actual != declared:
            raise ValueError(f"EXTERNAL_RUNTIME_DIGEST_MISMATCH:{adapter}")
        resolved[adapter] = str(executable)
    return resolved


def main() -> int:
    argv = sys.argv[1:]
    front = parse_front(argv)
    if not front.execute:
        return delegate(argv)
    if not front.plan or not front.adapters:
        return block("EXTERNAL_RUNTIME_DISPATCH_ARGUMENTS_MISSING")

    try:
        policy = load(POLICY_PATH)
        if policy.get("schema") != POLICY_SCHEMA:
            raise ValueError(f"EXTERNAL_RUNTIME_POLICY_SCHEMA_INVALID:{policy.get('schema')}")
        plan = load(front.plan)
        registry = load(front.adapters)
        if plan.get("schema") != PLAN_SCHEMA:
            raise ValueError(f"EXTERNAL_RUNTIME_PLAN_SCHEMA_INVALID:{plan.get('schema')}")
        if registry.get("schema") != ADAPTER_SCHEMA:
            raise ValueError(f"EXTERNAL_RUNTIME_ADAPTER_SCHEMA_INVALID:{registry.get('schema')}")
        required = required_external_adapters(plan, registry)
        if not required:
            return delegate(argv)

        env_policy = policy.get("environment") if isinstance(policy.get("environment"), dict) else {}
        env_name = str(env_policy.get("binding_file_variable") or "CHACHA_DEV_RUNTIME_BINDINGS")
        raw_binding = os.environ.get(env_name, "").strip()
        if not raw_binding:
            raise ValueError("EXTERNAL_RUNTIME_BINDING_PATH_MISSING")
        binding_path = Path(raw_binding)
        project = str(plan.get("project") or "")
        if not project:
            raise ValueError("EXTERNAL_RUNTIME_PROJECT_MISSING")
        resolved = verify_binding_file(project, required, registry, policy, binding_path)

        patched = deepcopy(registry)
        for adapter, executable in resolved.items():
            patched["adapters"][adapter]["executable"] = executable
        with tempfile.TemporaryDirectory(prefix="chacha-external-runtime-") as td:
            temporary_registry = Path(td) / "provider-adapters.runtime.json"
            temporary_registry.write_text(json.dumps(patched, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            print("EXTERNAL_RUNTIME_BINDING_STATUS=VERIFIED")
            print("EXTERNAL_RUNTIME_BINDINGS=" + ",".join(sorted(required)))
            return delegate(replace_adapters_arg(argv, temporary_registry))
    except ValueError as exc:
        return block(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
