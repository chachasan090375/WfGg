#!/usr/bin/env python3
"""ChaCha DEV HUB external-runtime binding dispatcher.

Hardened facade in front of run-controller.py. The canonical provider-adapter
registry remains authoritative and keeps external adapters at executable=null.
For one ephemeral runner only, a runner-supplied binding snapshot may provide an
executable copy of a versioned adapter. The copy is accepted only when its
SHA-256 digest exactly matches the approved source file in this repository.

The runtime-binding path comes from CHACHA_DEV_HUB_RUNTIME_BINDINGS, never from
the task graph or dispatch envelope. No binding means normal Run Controller
behaviour. The authoritative registry is never modified.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
CORE = REPO / "dev-hub/bin/run-controller.py"
POLICY = REPO / "dev-hub/config/external-runtime-bindings.v1.json"
REGISTRY_SCHEMA = "chacha.dev/provider-adapters/v1"
POLICY_SCHEMA = "chacha.dev/external-runtime-binding-policy/v1"
BINDING_SCHEMA = "chacha.dev/external-runtime-bindings/v1"


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


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--plan", required=True, type=Path)
    p.add_argument("--graph", required=True, type=Path)
    p.add_argument("--ledger", required=True, type=Path)
    p.add_argument("--policy", required=True, type=Path)
    p.add_argument("--adapters", required=True, type=Path)
    p.add_argument("--output-dir", required=True, type=Path)
    p.add_argument("--workspace")
    p.add_argument("--execute", action="store_true")
    return p.parse_args()


def core_argv(args: argparse.Namespace, adapters: Path) -> list[str]:
    out = [
        sys.executable, str(CORE),
        "--plan", str(args.plan), "--graph", str(args.graph),
        "--ledger", str(args.ledger), "--policy", str(args.policy),
        "--adapters", str(adapters), "--output-dir", str(args.output_dir),
    ]
    if args.workspace:
        out += ["--workspace", args.workspace]
    if args.execute:
        out.append("--execute")
    return out


def validate_and_overlay(registry: dict[str, Any], snapshot: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    if registry.get("schema") != REGISTRY_SCHEMA:
        raise SystemExit(f"REGISTRY_SCHEMA_INVALID={registry.get('schema')}")
    if policy.get("schema") != POLICY_SCHEMA:
        raise SystemExit(f"RUNTIME_BINDING_POLICY_SCHEMA_INVALID={policy.get('schema')}")
    if snapshot.get("schema") != BINDING_SCHEMA:
        raise SystemExit(f"RUNTIME_BINDING_SCHEMA_INVALID={snapshot.get('schema')}")
    if snapshot.get("scope") != policy.get("allowed_scope"):
        raise SystemExit("RUNTIME_BINDING_SCOPE_FORBIDDEN")
    if snapshot.get("production_capable") is not False:
        raise SystemExit("RUNTIME_BINDING_PRODUCTION_FORBIDDEN")
    if snapshot.get("authoritative_registry_mutated") is not False:
        raise SystemExit("RUNTIME_BINDING_REGISTRY_MUTATION_CLAIM_INVALID")

    raw = snapshot.get("bindings")
    if not isinstance(raw, list) or not raw:
        raise SystemExit("RUNTIME_BINDINGS_EMPTY")
    allowed_defs = policy.get("adapters") or {}
    out = copy.deepcopy(registry)
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            raise SystemExit("RUNTIME_BINDING_NOT_OBJECT")
        if set(item) != {"adapter", "provider", "executable", "digest"}:
            raise SystemExit("RUNTIME_BINDING_FIELDS_INVALID")
        adapter = str(item.get("adapter") or "")
        provider = str(item.get("provider") or "")
        if not adapter or adapter in seen:
            raise SystemExit(f"RUNTIME_BINDING_ADAPTER_INVALID={adapter}")
        seen.add(adapter)
        allowed = allowed_defs.get(adapter)
        if not isinstance(allowed, dict):
            raise SystemExit(f"RUNTIME_BINDING_ADAPTER_NOT_ALLOWED={adapter}")
        if provider not in set(allowed.get("providers") or []):
            raise SystemExit(f"RUNTIME_BINDING_PROVIDER_NOT_ALLOWED={adapter}:{provider}")
        source = REPO / str(allowed.get("source_path") or "")
        if not source.is_file():
            raise SystemExit(f"RUNTIME_BINDING_SOURCE_MISSING={source}")
        expected_digest = digest(source)
        declared_digest = str(item.get("digest") or "")
        if declared_digest != expected_digest:
            raise SystemExit(f"RUNTIME_BINDING_DECLARED_DIGEST_MISMATCH={adapter}")
        executable = Path(str(item.get("executable") or ""))
        if not executable.is_absolute() or not executable.is_file():
            raise SystemExit(f"RUNTIME_BINDING_EXECUTABLE_INVALID={adapter}")
        if not os.access(executable, os.X_OK):
            raise SystemExit(f"RUNTIME_BINDING_EXECUTABLE_NOT_EXECUTABLE={adapter}")
        if digest(executable) != expected_digest:
            raise SystemExit(f"RUNTIME_BINDING_EXECUTABLE_DIGEST_MISMATCH={adapter}")

        pdef = (registry.get("providers") or {}).get(provider)
        adef = (registry.get("adapters") or {}).get(adapter)
        if not isinstance(pdef, dict) or pdef.get("adapter") != adapter:
            raise SystemExit(f"RUNTIME_BINDING_PROVIDER_MAPPING_INVALID={provider}:{adapter}")
        if pdef.get("execution") != "external" or allowed.get("execution") != "external":
            raise SystemExit(f"RUNTIME_BINDING_EXECUTION_NOT_EXTERNAL={adapter}")
        if not isinstance(adef, dict) or adef.get("status") != "ENABLED":
            raise SystemExit(f"RUNTIME_BINDING_ADAPTER_NOT_ENABLED={adapter}")
        if adef.get("executable") is not None:
            raise SystemExit(f"RUNTIME_BINDING_CANONICAL_EXECUTABLE_NOT_NULL={adapter}")
        if set(adef.get("supports") or []) - set(allowed.get("supports") or []):
            raise SystemExit(f"RUNTIME_BINDING_PERMISSION_POLICY_DRIFT={adapter}")
        if allowed.get("production_capable") is not False:
            raise SystemExit(f"RUNTIME_BINDING_POLICY_PRODUCTION_INVALID={adapter}")
        out["adapters"][adapter]["executable"] = str(executable)
    return out


def main() -> int:
    args = parse_args()
    binding_path = os.environ.get("CHACHA_DEV_HUB_RUNTIME_BINDINGS", "").strip()
    if not binding_path:
        proc = subprocess.run(core_argv(args, args.adapters), cwd=str(REPO), shell=False)
        return proc.returncode

    path = Path(binding_path)
    if not path.is_absolute():
        raise SystemExit("RUNTIME_BINDINGS_PATH_MUST_BE_ABSOLUTE")
    registry = load(args.adapters)
    snapshot = load(path)
    policy = load(POLICY)
    overlay = validate_and_overlay(registry, snapshot, policy)

    fd, temp_name = tempfile.mkstemp(prefix="chacha-external-runtime-registry-", suffix=".json")
    os.close(fd)
    temp = Path(temp_name)
    try:
        temp.write_text(json.dumps(overlay, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        proc = subprocess.run(core_argv(args, temp), cwd=str(REPO), shell=False)
        return proc.returncode
    finally:
        try:
            temp.unlink()
        except FileNotFoundError:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
