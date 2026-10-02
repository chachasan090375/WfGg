#!/usr/bin/env python3
"""Governed entrypoint for the ChaCha DEV central interface.

The public/canonical path stays stable. The previously qualified controller is
kept byte-for-byte as central-interface-controller-core.py; this wrapper only
injects the governed Project Control boundary.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

DEFAULT_REPO_ROOT = Path("/opt/chacha-dev/platform/current")


def _value(argv: list[str], flag: str) -> str | None:
    try:
        idx = argv.index(flag)
    except ValueError:
        return None
    return argv[idx + 1] if idx + 1 < len(argv) else None


def _without_option(argv: list[str], flag: str) -> list[str]:
    out: list[str] = []
    idx = 0
    while idx < len(argv):
        if argv[idx] == flag:
            idx += 2
            continue
        out.append(argv[idx])
        idx += 1
    return out


def governed_argv(argv: list[str]) -> list[str]:
    repo_root = Path(_value(argv, "--repo-root") or str(DEFAULT_REPO_ROOT)).resolve()
    core = repo_root / "dev-hub/bin/central-interface-controller-core.py"
    governed_project_control = repo_root / "dev-hub/bin/governed-project-control.py"
    clean = _without_option(list(argv), "--project-control")
    return [
        sys.executable,
        str(core),
        "--project-control",
        str(governed_project_control),
        *clean,
    ]


def main() -> int:
    target = governed_argv(sys.argv[1:])
    core = Path(target[1])
    governed = Path(target[3])
    if not core.is_file():
        print(f"CENTRAL_INTERFACE_CORE_NOT_FOUND={core}", file=sys.stderr)
        return 127
    if not governed.is_file():
        print(f"GOVERNED_PROJECT_CONTROL_NOT_FOUND={governed}", file=sys.stderr)
        return 127
    os.execv(sys.executable, target)
    return 127


if __name__ == "__main__":
    raise SystemExit(main())
