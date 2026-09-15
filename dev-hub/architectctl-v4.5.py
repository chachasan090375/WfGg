#!/usr/bin/env python3
import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(os.environ.get('CHACHA_DEV_ROOT', '/opt/chacha-dev'))
CONFIG = ROOT / 'platform' / 'config'
REGISTRY = ROOT / 'registry'
AUDITS = ROOT / 'audits'


def run(cmd, timeout=45):
    try:
        p = subprocess.run(cmd, text=True, capture_output=True, timeout=timeout)
        return p.returncode, (p.stdout + p.stderr).strip()
    except Exception as e:
        return 99, str(e)


def load_json(path):
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def passthrough(tool, args, timeout=180):
    path = shutil.which(tool)
    if not path:
        print(f'{tool.upper().replace("-", "_")}=MISSING', file=sys.stderr)
        return 2
    try:
        return subprocess.run([path] + args, timeout=timeout).returncode
    except subprocess.TimeoutExpired:
        print(f'{tool.upper().replace("-", "_")}=TIMEOUT', file=sys.stderr)
        return 124


def cmd_status(_args):
    print('=== CHACHA DEV ARCHITECT ===')
    print('AGENT=chacha-dev-architect')
    print('ARCHITECT_VERSION=4.5')
    tools = {
        'projectctl': shutil.which('projectctl'),
        'devhub-health': shutil.which('devhub-health'),
        'techwatch': shutil.which('techwatch'),
        'gate-audit': shutil.which('gate-audit'),
        'architect-remediation': shutil.which('architect-remediation'),
        'test-matrix': shutil.which('test-matrix'),
        'recoveryctl': shutil.which('recoveryctl'),
        'antigravity': shutil.which('agy-dev') or shutil.which('agy'),
        'git': shutil.which('git'),
        'node': shutil.which('node'),
        'npm': shutil.which('npm'),
        'python': shutil.which('python3'),
        'blender': shutil.which('blender'),
        'rsync': shutil.which('rsync'),
    }
    for name, path in tools.items():
        print(f"TOOL_{name.upper().replace('-', '_')}={'OK' if path else 'MISSING'}")
    agy = shutil.which('agy')
    if agy:
        rc, out = run([agy, 'mcp', 'list'])
        print(f"MCP_LIST={'OK' if rc == 0 else 'FAIL'}")
        if out:
            print(out)
    health = shutil.which('devhub-health')
    if health:
        rc, out = run([health])
        summary = [x for x in out.splitlines() if x.startswith(('HEALTH_', 'DEV_HUB_HEALTH='))]
        for line in summary:
            print(line)
        print(f"PLATFORM_HEALTH={'OK' if rc == 0 else 'CHECK'}")
    return 0


def cmd_radar(_args):
    p = CONFIG / 'technology-radar.json'
    data = load_json(p)
    if not data:
        print(f'RADAR_NOT_FOUND={p}', file=sys.stderr)
        return 2
    print(f"RADAR_SCHEMA={data.get('schema','')}")
    for e in data.get('entries', []):
        print(f"{e.get('ring','?'):6} | {e.get('category','?'):24} | {e.get('name','?')}")
    return 0


def cmd_watch_plan(_args):
    p = CONFIG / 'tech-watch-sources.json'
    data = load_json(p)
    if not data:
        print(f'WATCH_CONFIG_NOT_FOUND={p}', file=sys.stderr)
        return 2
    print('=== TECH WATCH PLAN ===')
    for k, v in data.get('cadence', {}).items():
        print(f'CADENCE_{k.upper()}={v}')
    for item in data.get('sources', []):
        print(f"WATCH={item.get('category')} :: {','.join(item.get('sources', []))}")
    return 0


def cmd_watch_status(_args):
    return passthrough('techwatch', ['status'])


def cmd_watch_report(_args):
    return passthrough('techwatch', ['report'])


def cmd_watch_run(args):
    cmd = ['run']
    if args.market:
        cmd.append('--market')
    return passthrough('techwatch', cmd, timeout=240)


def cmd_audit(args):
    p = REGISTRY / 'manifests' / f'{args.name}.json'
    data = load_json(p)
    if not data:
        print(f'MANIFEST_NOT_FOUND_OR_INVALID={p}', file=sys.stderr)
        return 2
    schema = data.get('schema', '')
    print(f'PROJECT={args.name}')
    print(f'SCHEMA={schema}')
    if schema == 'chacha.dev/project-manifest/v1':
        print('ARCHITECTURE_MODEL=LEGACY_V1')
        print('MULTICOMPONENT=NO')
        print('RECOMMENDATION=UPGRADE_TO_V2')
        return 0
    if schema != 'chacha.dev/project-manifest/v2':
        print('ARCHITECTURE_MODEL=UNKNOWN')
        return 3
    components = data.get('components', [])
    gates = data.get('quality_gates', {})
    unassessed = [k for k, v in gates.items() if v == 'UNASSESSED']
    missing = []
    required_top = ['repository', 'workspace', 'components', 'integrations', 'agents', 'storage', 'security', 'quality_gates', 'operations', 'governance']
    for key in required_top:
        if key not in data:
            missing.append(key)
    score_base = max(0, 100 - len(unassessed) * 5 - len(missing) * 10)
    print(f'COMPONENTS={len(components)}')
    for c in components:
        print(f"COMPONENT={c.get('name','?')} TYPE={c.get('type','?')} PATH={c.get('path','?')}")
    print(f'UNASSESSED_GATES={len(unassessed)}')
    for g in unassessed:
        print(f'GATE_UNASSESSED={g}')
    for m in missing:
        print(f'REQUIRED_MISSING={m}')
    print(f'ARCHITECTURE_SCORE={score_base}')
    print(f"STATUS={'ACTION_REQUIRED' if unassessed or missing else 'OK'}")
    return 0


def cmd_inspect(args):
    cmd = [args.name]
    if args.json:
        cmd.append('--json')
    return passthrough('gate-audit', cmd)


def cmd_full_audit(args):
    rc = cmd_audit(args)
    if rc != 0:
        return rc
    print()
    return cmd_inspect(args)


def cmd_audit_report(args):
    p = AUDITS / args.name / 'latest.json'
    data = load_json(p)
    if not data:
        print(f'AUDIT_REPORT_NOT_FOUND={p}', file=sys.stderr)
        return 2
    gates = data.get('gates', {})
    print('=== LATEST EVIDENCE AUDIT ===')
    print(f"PROJECT={data.get('project','')}")
    print(f"TIME={data.get('time','')}")
    print(f"FILES_SCANNED={data.get('files_scanned',0)}")
    scores = []
    for name, g in gates.items():
        print(f"GATE={name} STATUS={g.get('status')} SCORE={g.get('score')}")
        scores.append(int(g.get('score', 0)))
    if scores:
        print(f'ARCHITECTURE_EVIDENCE_SCORE={round(sum(scores)/len(scores))}')
    return 0


def cmd_remediation(args):
    cmd = [args.name]
    if args.json:
        cmd.append('--json')
    return passthrough('architect-remediation', cmd)


def cmd_test_matrix(args):
    cmd = [args.name]
    if args.json:
        cmd.append('--json')
    return passthrough('test-matrix', cmd)


def cmd_recovery_status(args):
    return passthrough('recoveryctl', ['status', args.name])


def cmd_recovery_drill(args):
    return passthrough('recoveryctl', ['local-drill', args.name], timeout=300)


def cmd_improve(args):
    print('=== CHACHA ARCHITECT IMPROVEMENT CYCLE V4.5 ===')
    steps = [
        ('AUDIT', ['full-audit', args.name]),
        ('REMEDIATION', ['remediation', args.name]),
        ('TEST_MATRIX', ['test-matrix', args.name]),
        ('RECOVERY_STATUS', ['recovery-status', args.name]),
    ]
    self_bin = shutil.which('architectctl') or sys.argv[0]
    for label, argv in steps:
        print()
        print(f'=== {label} ===')
        rc = subprocess.run([self_bin] + argv).returncode
        if rc != 0:
            print(f'IMPROVEMENT_STEP_FAILED={label}')
            return rc
    print()
    print('IMPROVEMENT_CYCLE=OK')
    return 0


def parser():
    p = argparse.ArgumentParser(prog='architectctl', description='ChaCha DEV Architect controller')
    sp = p.add_subparsers(dest='sub', required=True)
    sp.add_parser('status').set_defaults(func=cmd_status)
    sp.add_parser('radar').set_defaults(func=cmd_radar)
    sp.add_parser('watch-plan').set_defaults(func=cmd_watch_plan)
    sp.add_parser('watch-status').set_defaults(func=cmd_watch_status)
    sp.add_parser('watch-report').set_defaults(func=cmd_watch_report)
    wx = sp.add_parser('watch-run')
    wx.add_argument('--market', action='store_true')
    wx.set_defaults(func=cmd_watch_run)
    a = sp.add_parser('audit', help='validate manifest architecture')
    a.add_argument('name')
    a.set_defaults(func=cmd_audit)
    i = sp.add_parser('inspect', help='run evidence-based 14-gate source audit')
    i.add_argument('name')
    i.add_argument('--json', action='store_true')
    i.set_defaults(func=cmd_inspect)
    f = sp.add_parser('full-audit', help='manifest audit plus deep evidence scan')
    f.add_argument('name')
    f.add_argument('--json', action='store_true')
    f.set_defaults(func=cmd_full_audit)
    r = sp.add_parser('audit-report', help='show latest saved gate audit summary')
    r.add_argument('name')
    r.set_defaults(func=cmd_audit_report)
    rm = sp.add_parser('remediation', help='generate prioritized evidence-based remediation plan')
    rm.add_argument('name')
    rm.add_argument('--json', action='store_true')
    rm.set_defaults(func=cmd_remediation)
    tm = sp.add_parser('test-matrix', help='generate project test coverage matrix')
    tm.add_argument('name')
    tm.add_argument('--json', action='store_true')
    tm.set_defaults(func=cmd_test_matrix)
    rs = sp.add_parser('recovery-status', help='show recovery policy/readiness')
    rs.add_argument('name')
    rs.set_defaults(func=cmd_recovery_status)
    rd = sp.add_parser('recovery-drill', help='perform non-destructive local restore drill')
    rd.add_argument('name')
    rd.set_defaults(func=cmd_recovery_drill)
    im = sp.add_parser('improve', help='run audit -> remediation -> test matrix -> recovery status')
    im.add_argument('name')
    im.set_defaults(func=cmd_improve)
    return p


def main():
    args = parser().parse_args()
    raise SystemExit(args.func(args))


if __name__ == '__main__':
    main()
