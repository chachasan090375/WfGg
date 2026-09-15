#!/usr/bin/env python3
import argparse
import json
import os
from pathlib import Path

ROOT = Path('/opt/chacha-dev')
REGISTRY = ROOT / 'registry' / 'manifests'
SKIP = {'.git', 'node_modules', 'dist', 'build', '.cache', '.wrangler', 'vendor'}


def load_json(path):
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def walk(base):
    for root, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if d not in SKIP]
        for name in files:
            yield Path(root) / name


def detect_packages(workspace):
    packages = []
    for p in walk(workspace):
        if p.name != 'package.json':
            continue
        data = load_json(p)
        if not isinstance(data, dict):
            continue
        deps = {}
        deps.update(data.get('dependencies', {}) or {})
        deps.update(data.get('devDependencies', {}) or {})
        packages.append({
            'path': str(p.relative_to(workspace)),
            'scripts': data.get('scripts', {}) or {},
            'deps': deps,
        })
    return packages


def has_dep(packages, name):
    return any(name in p['deps'] for p in packages)


def has_script(packages, name):
    return any(name in p['scripts'] for p in packages)


def main():
    ap = argparse.ArgumentParser(prog='test-matrix')
    ap.add_argument('project')
    ap.add_argument('--json', action='store_true')
    args = ap.parse_args()

    mp = REGISTRY / f'{args.project}.json'
    manifest = load_json(mp)
    if not manifest:
        raise SystemExit(f'MANIFEST_NOT_FOUND={mp}')
    workspace = Path((manifest.get('workspace') or {}).get('local') or '')
    if not workspace.exists():
        raise SystemExit(f'WORKSPACE_NOT_FOUND={workspace}')

    packages = detect_packages(workspace)
    components = manifest.get('components', []) or []
    component_types = ' '.join(str(x.get('type', '')).lower() for x in components)
    cloudflare_worker = 'cloudflare-worker' in component_types or 'worker' in component_types
    frontend = 'frontend' in component_types or 'pwa' in component_types or 'web-' in component_types

    rows = []

    unit_present = has_dep(packages, 'vitest') or has_dep(packages, 'jest') or has_script(packages, 'test')
    rows.append({
        'layer': 'unit',
        'required': True,
        'status': 'PRESENT' if unit_present else 'MISSING',
        'candidate': 'Vitest' if not unit_present else 'existing',
        'goal': 'business logic and pure functions',
    })

    integration_present = any('integration' in k.lower() for p in packages for k in p['scripts'])
    rows.append({
        'layer': 'integration',
        'required': True,
        'status': 'PRESENT' if integration_present else 'MISSING',
        'candidate': 'Vitest + platform test harness' if cloudflare_worker else 'project-native integration runner',
        'goal': 'API, persistence and external boundaries',
    })

    e2e_present = has_dep(packages, '@playwright/test') or has_dep(packages, 'playwright') or any('e2e' in k.lower() for p in packages for k in p['scripts'])
    rows.append({
        'layer': 'e2e',
        'required': bool(frontend),
        'status': 'PRESENT' if e2e_present else ('MISSING' if frontend else 'NOT_APPLICABLE'),
        'candidate': 'Playwright' if frontend and not e2e_present else 'existing',
        'goal': 'critical user journeys in a real browser',
    })

    smoke_present = any('smoke' in k.lower() for p in packages for k in p['scripts'])
    rows.append({
        'layer': 'smoke',
        'required': True,
        'status': 'PRESENT' if smoke_present else 'MISSING',
        'candidate': 'lightweight post-deploy smoke suite',
        'goal': 'production/preview availability and critical endpoints',
    })

    security_present = any('audit' in k.lower() or 'security' in k.lower() for p in packages for k in p['scripts'])
    rows.append({
        'layer': 'security',
        'required': True,
        'status': 'PRESENT' if security_present else 'MISSING',
        'candidate': 'npm audit + dependency scanning in CI',
        'goal': 'dependency and configuration regression detection',
    })

    performance_present = any('perf' in k.lower() or 'lighthouse' in k.lower() or 'load' in k.lower() for p in packages for k in p['scripts'])
    rows.append({
        'layer': 'performance',
        'required': True,
        'status': 'PRESENT' if performance_present else 'MISSING',
        'candidate': 'Lighthouse/Web Vitals and load test where applicable',
        'goal': 'enforce performance budgets',
    })

    out = {
        'schema': 'chacha.dev/test-matrix/v1',
        'project': args.project,
        'workspace': str(workspace),
        'package_count': len(packages),
        'packages': [{'path': p['path'], 'scripts': sorted(p['scripts'])} for p in packages],
        'matrix': rows,
        'policy': {
            'auto_install': False,
            'requires_approval_before_dependency_changes': True,
            'target': 'unit + integration + e2e(if UI) + smoke + security + performance',
        },
    }

    dest_dir = ROOT / 'tests' / args.project
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / 'matrix.json'
    dest.write_text(json.dumps(out, indent=2) + '\n')

    if args.json:
        print(json.dumps(out, indent=2))
        return

    print('=== CHACHA TEST MATRIX V4.5 ===')
    print(f'PROJECT={args.project}')
    print(f'WORKSPACE={workspace}')
    print(f'PACKAGES={len(packages)}')
    for pkg in out['packages']:
        print(f"PACKAGE={pkg['path']} SCRIPTS={','.join(pkg['scripts']) or '-'}")
    print()
    for row in rows:
        print(f"TEST_LAYER={row['layer']} REQUIRED={str(row['required']).lower()} STATUS={row['status']} CANDIDATE={row['candidate']}")
        print(f"GOAL={row['goal']}")
    missing = sum(1 for r in rows if r['required'] and r['status'] == 'MISSING')
    print()
    print(f'TEST_MATRIX_MISSING_REQUIRED={missing}')
    print(f'TEST_MATRIX_REPORT={dest}')
    print('TEST_MATRIX=OK')


if __name__ == '__main__':
    main()
