#!/usr/bin/env python3

import argparse
import json
from pathlib import Path


DEFAULT_REGISTRY = (
    Path(__file__).resolve().parents[1]
    / "config"
    / "chacha-machine-fabric.v1.json"
)


class FabricError(RuntimeError):
    pass


def load_registry(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))

    if data.get("schema") != "chacha.machine-fabric/v1":
        raise FabricError("FABRIC_SCHEMA_INVALID")

    if data.get("state") != "CANDIDATE_NOT_ACTIVE":
        raise FabricError("FABRIC_STATE_UNEXPECTED")

    return data


def resolve(registry: dict, target: str, capability: str) -> dict:
    nodes = registry.get("nodes", {})
    contracts = registry.get("capability_contracts", {})

    if target not in nodes:
        raise FabricError("TARGET_UNKNOWN")

    node = nodes[target]

    if capability not in contracts:
        raise FabricError("CAPABILITY_UNKNOWN")

    if capability not in node.get("capabilities", []):
        raise FabricError("CAPABILITY_NOT_EXPOSED_BY_TARGET")

    contract = contracts[capability]

    return {
        "schema": "chacha.machine-fabric/route-resolution/v1",
        "target": target,
        "display_name": node["display_name"],
        "os_family": node["os_family"],
        "tailscale_name": node["tailscale_name"],
        "capability": capability,
        "risk": contract["risk"],
        "execution": contract["execution"],
        "transport": registry["network"]["control_transport"],
        "arbitrary_shell": registry["governance"]["arbitrary_shell"],
        "guardian_required": registry["governance"]["guardian_required"],
        "state": "RESOLVED_NOT_EXECUTED"
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--registry",
        default=str(DEFAULT_REGISTRY),
    )
    parser.add_argument("--target", required=True)
    parser.add_argument("--capability", required=True)

    args = parser.parse_args()

    registry = load_registry(Path(args.registry))
    result = resolve(
        registry,
        args.target,
        args.capability,
    )

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
