#!/usr/bin/env python3
"""Canonical entry for Playwright MCP adapter V2.

Delegates all runtime/network policy to playwright-mcp-adapter-runtime-v2.py and
preserves the historical `target_origin` evidence alias consumed by the existing
provider-aware Verification Broker. The alias is added only after V2 has already
revalidated the final origin; evidence digests are recomputed after augmentation.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

CORE = Path(__file__).with_name("playwright-mcp-adapter-runtime-v2.py")


def digest_json(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def main() -> int:
    raw = sys.stdin.read()
    proc = subprocess.run(
        [sys.executable, str(CORE)],
        input=raw,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=os.environ.copy(),
        shell=False,
        check=False,
    )
    try:
        result = json.loads(proc.stdout)
    except Exception:
        sys.stderr.write(proc.stderr)
        sys.stdout.write(proc.stdout)
        return proc.returncode or 2
    if isinstance(result, dict):
        for item in result.get("evidence") or []:
            if not isinstance(item, dict) or not isinstance(item.get("details"), dict):
                continue
            details = item["details"]
            if (
                details.get("final_origin_revalidated") is True
                and isinstance(details.get("initial_target_origin"), str)
                and isinstance(details.get("final_target_origin"), str)
                and details.get("initial_target_origin") == details.get("final_target_origin")
            ):
                details["target_origin"] = details["final_target_origin"]
                item["digest"] = digest_json(details)
    sys.stdout.write(json.dumps(result, ensure_ascii=False, separators=(",", ":")) + "\n")
    if proc.stderr:
        sys.stderr.write(proc.stderr)
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
