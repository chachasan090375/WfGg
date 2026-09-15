#!/usr/bin/env python3
import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(os.environ.get('CHACHA_DEV_ROOT', '/opt/chacha-dev'))
POLICY = ROOT / 'platform' / 'config' / 'storage-policy.json'
DEFAULT = {
    'schema': 'chacha.dev/storage-policy/v1',
    'warn_percent': 80,
    'fail_percent': 90,
    'reserve_mb': 768,
    'heavy_operation_extra_mb': 512,
    'journal_max_mb': 50,
    'nas_role': 'capacity-tier',
    'vps_role': 'execution-tier',
    'auto_delete_project_sources': False,
    'auto_delete_engines': False,
    'auto_offload': False,
}


def ensure_policy():
    POLICY.parent.mkdir(parents=True, exist_ok=True)
    if not POLICY.exists():
        POLICY.write_text(json.dumps(DEFAULT, indent=2) + '\n')
    try:
        data = json.loads(POLICY.read_text())
        out = dict(DEFAULT)
        out.update(data if isinstance(data, dict) else {})
        return out
    except Exception:
        return dict(DEFAULT)


def fmt_bytes(n):
    for unit in ('B','KiB','MiB','GiB','TiB'):
        if n < 1024 or unit == 'TiB':
            return f'{n:.1f}{unit}'
        n /= 1024


def usage():
    u = shutil.disk_usage('/')
    pct = round((u.used / u.total) * 100) if u.total else 100
    return u, pct


def path_size(path):
    p = Path(path)
    if not p.exists():
        return 0
    try:
        out = subprocess.check_output(['du','-sx','-B1',str(p)], text=True, stderr=subprocess.DEVNULL, timeout=60)
        return int(out.split()[0])
    except Exception:
        return 0


def journal_size():
    try:
        out = subprocess.check_output(['journalctl','--disk-usage'], text=True, stderr=subprocess.STDOUT, timeout=20).strip()
        return out
    except Exception:
        return 'unavailable'


def top_usage(base, depth=1, limit=18):
    try:
        out = subprocess.check_output(['du','-x','-B1',f'-d{depth}',base], text=True, stderr=subprocess.DEVNULL, timeout=90)
    except Exception:
        return []
    rows = []
    for line in out.splitlines():
        try:
            n, p = line.split('\t',1)
            rows.append((int(n), p))
        except Exception:
            pass
    rows.sort(reverse=True)
    return rows[:limit]


def state(policy):
    u, pct = usage()
    if pct >= int(policy['fail_percent']):
        s = 'CRITICAL'
    elif pct >= int(policy['warn_percent']):
        s = 'WARN'
    else:
        s = 'OK'
    return u, pct, s


def audit(_args):
    p = ensure_policy()
    u, pct, s = state(p)
    print('=== CHACHA STORAGE GOVERNOR V4.5.1 ===')
    print(f'ROOT_USED_PERCENT={pct}')
    print(f'ROOT_FREE={fmt_bytes(u.free)}')
    print(f'ROOT_USED={fmt_bytes(u.used)}')
    print(f'ROOT_TOTAL={fmt_bytes(u.total)}')
    print(f'STORAGE_PRESSURE={s}')
    print(f'WARN_PERCENT={p["warn_percent"]}')
    print(f'FAIL_PERCENT={p["fail_percent"]}')
    print(f'RESERVE_MB={p["reserve_mb"]}')
    print()
    print('=== SAFE CLEANUP CANDIDATES ===')
    for name, path in [
        ('APT_CACHE','/var/cache/apt'),
        ('APT_LISTS','/var/lib/apt/lists'),
        ('TMP','/tmp'),
        ('VAR_TMP','/var/tmp'),
        ('PLATFORM_PYCACHE',str(ROOT / 'platform')),
    ]:
        print(f'{name}={fmt_bytes(path_size(path))}')
    print(f'JOURNAL={journal_size()}')
    print()
    print('=== TOP LEVEL ===')
    for n, path in top_usage('/',1,20):
        if path == '/':
            continue
        print(f'{fmt_bytes(n):>10} {path}')
    print()
    print('=== /VAR ===')
    for n, path in top_usage('/var',1,16):
        if path != '/var':
            print(f'{fmt_bytes(n):>10} {path}')
    print()
    print('POLICY=No project source, engine, agent, or production data is auto-deleted or auto-offloaded.')
    print('STORAGE_AUDIT=OK')
    return 0


def run_quiet(cmd):
    try:
        subprocess.run(cmd, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
    except Exception:
        pass


def cleanup_safe(_args):
    p = ensure_policy()
    before, before_pct = usage()
    print('=== SAFE STORAGE CLEANUP V4.5.1 ===')
    print(f'BEFORE_PERCENT={before_pct}')
    print(f'BEFORE_FREE={fmt_bytes(before.free)}')
    if os.geteuid() != 0:
        print('SAFE_CLEANUP=REFUSED_NOT_ROOT')
        return 3

    if shutil.which('apt-get'):
        run_quiet(['apt-get','clean'])
        lists = Path('/var/lib/apt/lists')
        if lists.exists():
            for child in lists.iterdir():
                if child.name == 'lock':
                    continue
                try:
                    if child.is_dir() and not child.is_symlink():
                        shutil.rmtree(child)
                    else:
                        child.unlink(missing_ok=True)
                except Exception:
                    pass
        print('APT_CACHE_CLEAN=OK')
        print('APT_LISTS_CLEAN=OK')

    if shutil.which('journalctl'):
        run_quiet(['journalctl',f'--vacuum-size={int(p["journal_max_mb"])}M'])
        print('JOURNAL_VACUUM=OK')

    platform = ROOT / 'platform'
    removed = 0
    if platform.exists():
        for d in list(platform.rglob('__pycache__')):
            try:
                shutil.rmtree(d)
                removed += 1
            except Exception:
                pass
    print(f'PYCACHE_DIRS_REMOVED={removed}')

    after, after_pct = usage()
    freed = max(0, after.free - before.free)
    print(f'AFTER_PERCENT={after_pct}')
    print(f'AFTER_FREE={fmt_bytes(after.free)}')
    print(f'FREED={fmt_bytes(freed)}')
    _, _, s = state(p)
    print(f'STORAGE_PRESSURE={s}')
    print('SAFE_CLEANUP=OK')
    return 0


def preflight(args):
    p = ensure_policy()
    u, pct, s = state(p)
    need = max(0, int(args.need_mb))
    reserve = int(p['reserve_mb'])
    if args.heavy:
        reserve += int(p['heavy_operation_extra_mb'])
    required = need + reserve
    free_mb = u.free // (1024*1024)
    ok = free_mb >= required and pct < int(p['fail_percent'])
    print('=== STORAGE PREFLIGHT ===')
    print(f'NEED_MB={need}')
    print(f'RESERVE_MB={reserve}')
    print(f'REQUIRED_FREE_MB={required}')
    print(f'CURRENT_FREE_MB={free_mb}')
    print(f'CURRENT_USED_PERCENT={pct}')
    print(f'STORAGE_PRESSURE={s}')
    print(f'PREFLIGHT={"OK" if ok else "BLOCKED"}')
    return 0 if ok else 4


def policy_cmd(_args):
    print(json.dumps(ensure_policy(), indent=2))
    return 0


def main():
    ap = argparse.ArgumentParser(prog='storage-governor')
    sp = ap.add_subparsers(dest='cmd', required=True)
    sp.add_parser('audit').set_defaults(func=audit)
    sp.add_parser('cleanup-safe').set_defaults(func=cleanup_safe)
    pf = sp.add_parser('preflight')
    pf.add_argument('--need-mb', type=int, default=0)
    pf.add_argument('--heavy', action='store_true')
    pf.set_defaults(func=preflight)
    sp.add_parser('policy').set_defaults(func=policy_cmd)
    args = ap.parse_args()
    raise SystemExit(args.func(args))


if __name__ == '__main__':
    main()
