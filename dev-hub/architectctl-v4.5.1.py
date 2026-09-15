#!/usr/bin/env python3
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(os.environ.get('CHACHA_DEV_ROOT', '/opt/chacha-dev'))
BASE = ROOT / 'platform' / 'bin' / 'architectctl-v4.5.py'
STORAGE = shutil.which('storage-governor') or str(ROOT / 'platform' / 'bin' / 'storage-governor.py')


def run(cmd):
    return subprocess.run(cmd).returncode


def help_text():
    if BASE.exists():
        subprocess.run([sys.executable, str(BASE), '--help'])
    print('\nStorage governor:')
    print('  architectctl storage-audit')
    print('  architectctl storage-clean-safe')
    print('  architectctl storage-preflight [--need-mb N] [--heavy]')
    print('  architectctl storage-policy')


def status():
    print('=== CHACHA DEV ARCHITECT V4.5.1 ===')
    print('ARCHITECT_VERSION=4.5.1')
    print(f"TOOL_STORAGE_GOVERNOR={'OK' if Path(STORAGE).exists() or shutil.which('storage-governor') else 'MISSING'}")
    if BASE.exists():
        return run([sys.executable, str(BASE), 'status'])
    print(f'BASE_ARCHITECT_MISSING={BASE}')
    return 2


def main():
    argv = sys.argv[1:]
    if not argv or argv[0] in ('-h','--help','help'):
        help_text()
        return 0
    cmd = argv[0]
    if cmd == 'status':
        return status()
    if cmd == 'storage-audit':
        return run([STORAGE, 'audit'])
    if cmd == 'storage-clean-safe':
        return run([STORAGE, 'cleanup-safe'])
    if cmd == 'storage-policy':
        return run([STORAGE, 'policy'])
    if cmd == 'storage-preflight':
        return run([STORAGE, 'preflight'] + argv[1:])
    if not BASE.exists():
        print(f'BASE_ARCHITECT_MISSING={BASE}', file=sys.stderr)
        return 2
    return run([sys.executable, str(BASE)] + argv)


if __name__ == '__main__':
    raise SystemExit(main())
