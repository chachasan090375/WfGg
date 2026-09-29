#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path


def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit(f"JSON_ROOT_NOT_OBJECT:{path}")
    return value


def load_gateway(repo: Path):
    path = repo / "dev-hub/bin/direct-operator-control-plane-gateway.py"
    spec = importlib.util.spec_from_file_location("chacha_control_plane_gateway", path)
    if not spec or not spec.loader:
        raise SystemExit("CONTROL_PLANE_GATEWAY_IMPORT_FAILED")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", type=Path, required=True)
    ap.add_argument("--runtime-root", type=Path, default=Path("/opt/chacha-dev/runtime"))
    ap.add_argument("--direct-policy", type=Path)
    ap.add_argument("--control-policy", type=Path)
    ap.add_argument("--output", type=Path)
    args = ap.parse_args()

    repo = args.repo_root.resolve()
    runtime = args.runtime_root.resolve()
    direct_policy_path = args.direct_policy or repo / "dev-hub/config/direct-operator.v1.json"
    control_policy_path = args.control_policy or repo / "dev-hub/config/platform-control-plane.v1.json"

    direct_policy = load(direct_policy_path)
    control_policy = load(control_policy_path)
    module = load_gateway(repo)
    if control_policy.get("schema") != module.POLICY_SCHEMA:
        raise SystemExit("CONTROL_PLANE_POLICY_SCHEMA_INVALID")

    control = module.ControlPlane(repo, runtime, direct_policy, control_policy)
    report = control.report()

    invariants = {
        "mode_local_deterministic": report.get("mode") == "LOCAL_DETERMINISTIC_NO_PROVIDER",
        "provider_not_invoked": report.get("provider_invoked") is False,
        "technology_watch_not_invoked": report.get("technology_watch_invoked") is False,
        "central_orchestrator_not_invoked": report.get("central_orchestrator_invoked") is False,
        "zero_external_spend": report.get("automatic_external_spend_eur") == 0,
        "emergency_stop_observed": isinstance(report.get("emergency_stop"), dict),
        "zero_cost_observed": isinstance(report.get("zero_cost"), dict),
        "domain_observed": isinstance(report.get("domain_execution"), dict),
        "adapters_observed": isinstance(report.get("adapters"), dict),
    }
    status = "PASS" if all(invariants.values()) else "FAIL"
    receipt = {
        "schema": "chacha.dev/platform-control-plane-candidate-pilot/v1",
        "status": status,
        "repo_root": str(repo),
        "runtime_root": str(runtime),
        "read_only": True,
        "provider_invoked": False,
        "automatic_external_spend_eur": 0,
        "invariants": invariants,
        "report": report,
    }

    raw = json.dumps(receipt, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(raw, encoding="utf-8")
    sys.stdout.write(raw)
    return 0 if status == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
