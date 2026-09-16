#!/usr/bin/env python3
"""Project Control compatible scheduling facade.

Preserves the original Execution Scheduler argv contract used by Project Control,
but inserts Provider Selection Engine before the hardened scheduler. This file
plans only; neither child engine can dispatch.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SELECTOR = ROOT / 'bin' / 'provider-selection-engine.py'
SCHEDULER = ROOT / 'bin' / 'execution-scheduler.py'
ADAPTERS = ROOT / 'config' / 'provider-adapters.v1.json'
SELECTION_POLICY = ROOT / 'config' / 'provider-selection-policy.v1.json'


def run(argv: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        shell=False,
        check=False,
        timeout=120,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--graph', required=True, type=Path)
    parser.add_argument('--registry', required=True, type=Path)
    parser.add_argument('--health', required=True, type=Path)
    parser.add_argument('--policy', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()

    selection_output = args.output.with_suffix('.provider-selection.json')
    selector = run([
        sys.executable, str(SELECTOR),
        '--graph', str(args.graph),
        '--registry', str(args.registry),
        '--adapters', str(ADAPTERS),
        '--health', str(args.health),
        '--policy', str(SELECTION_POLICY),
        '--output', str(selection_output),
    ])
    if selector.returncode != 0:
        sys.stdout.write(selector.stdout)
        sys.stderr.write(selector.stderr)
        print('PROVIDER_SELECTION_FAILED', file=sys.stderr)
        return selector.returncode or 2

    scheduler = run([
        sys.executable, str(SCHEDULER),
        '--graph', str(args.graph),
        '--registry', str(args.registry),
        '--adapters', str(ADAPTERS),
        '--health', str(args.health),
        '--selection-plan', str(selection_output),
        '--policy', str(args.policy),
        '--output', str(args.output),
    ])
    sys.stdout.write(selector.stdout)
    sys.stdout.write(scheduler.stdout)
    sys.stderr.write(scheduler.stderr)
    if scheduler.returncode != 0:
        return scheduler.returncode
    print(f'PROVIDER_SELECTION_PLAN={selection_output}')
    print('SELECTION_AWARE_SCHEDULER=PASS')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
