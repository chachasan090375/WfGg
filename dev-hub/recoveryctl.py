#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path('/opt/chacha-dev')
REGISTRY = ROOT / 'registry' / 'manifests'
RECOVERY_ROOT = ROOT / 'recovery'
POLICY_PATH = ROOT / 'platform' / 'config' / 'recovery-policy.json'
STORAGE_ENV = ROOT / 'platform' / 'config' / 'storage.env'

DEFAULT_POLICY = {
    'schema': 'chacha.dev/recovery-policy/v1',
    'default_rpo_hours': 24,
    'default_rto_hours': 2,
    'require_restore_drill': True,
    'restore_drill_max_age_days': 30,
    'nas_target': '',
    'production_data_restore_requires_explicit_approval': True,
}

EXCLUDES = {'.git', 'node_modules', 'dist', 'build', '.cache', '.wrangler', '__pycache__'}


def load_json(path):
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def ensure_policy():
    POLICY_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not POLICY_PATH.exists():
        POLICY_PATH.write_text(json.dumps(DEFAULT_POLICY, indent=2) + '\n')
    return load_json(POLICY_PATH) or dict(DEFAULT_POLICY)


def manifest(project):
    p = REGISTRY / f'{project}.json'
    data = load_json(p)
    if not data:
        raise SystemExit(f'MANIFEST_NOT_FOUND={p}')
    return data


def workspace_for(project):
    m = manifest(project)
    path = Path((m.get('workspace') or {}).get('local') or '')
    if not path.exists():
        raise SystemExit(f'WORKSPACE_NOT_FOUND={path}')
    return path


def sha256(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def include_path(path, workspace):
    try:
        rel = path.relative_to(workspace)
    except Exception:
        return False
    return not any(part in EXCLUDES for part in rel.parts)


def source_file_count(workspace):
    n = 0
    for root, dirs, files in os.walk(workspace):
        dirs[:] = [d for d in dirs if d not in EXCLUDES]
        n += len(files)
    return n


def make_archive(project, workspace, out_path):
    with tarfile.open(out_path, 'w:gz') as tar:
        def filt(info):
            p = workspace / info.name
            if any(part in EXCLUDES for part in Path(info.name).parts):
                return None
            return info
        tar.add(workspace, arcname=project, recursive=True, filter=filt)


def local_drill(project):
    policy = ensure_policy()
    workspace = workspace_for(project)
    RECOVERY_ROOT.mkdir(parents=True, exist_ok=True)
    project_root = RECOVERY_ROOT / project
    project_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')

    with tempfile.TemporaryDirectory(prefix=f'chacha-recovery-{project}-') as td:
        tmp = Path(td)
        archive = tmp / f'{project}-{stamp}.tar.gz'
        restore = tmp / 'restore'
        restore.mkdir()
        before = source_file_count(workspace)
        make_archive(project, workspace, archive)
        digest = sha256(archive)
        with tarfile.open(archive, 'r:gz') as tar:
            tar.extractall(restore, filter='data')
        restored_root = restore / project
        after = source_file_count(restored_root)
        ok = before == after and before > 0
        result = {
            'schema': 'chacha.dev/recovery-drill/v1',
            'project': project,
            'time': datetime.now(timezone.utc).isoformat(),
            'scope': 'workspace-source-and-config',
            'status': 'OK' if ok else 'FAILED',
            'source_files': before,
            'restored_files': after,
            'archive_sha256': digest,
            'rpo_target_hours': policy.get('default_rpo_hours', 24),
            'rto_target_hours': policy.get('default_rto_hours', 2),
            'production_data_restore_tested': False,
            'note': 'This drill validates archive creation/extraction only; production D1/R2 restore remains a separate controlled drill.',
        }

    (project_root / 'last-drill.json').write_text(json.dumps(result, indent=2) + '\n')
    hist = project_root / 'history'
    hist.mkdir(exist_ok=True)
    (hist / f'{stamp}.json').write_text(json.dumps(result, indent=2) + '\n')
    print('=== CHACHA LOCAL RESTORE DRILL V4.5 ===')
    print(f'PROJECT={project}')
    print(f'SOURCE_FILES={before}')
    print(f'RESTORED_FILES={after}')
    print(f'ARCHIVE_SHA256={digest}')
    print(f'LOCAL_RESTORE_DRILL={result["status"]}')
    print('PRODUCTION_DATA_RESTORE_TESTED=NO')
    print(f'EVIDENCE={project_root / "last-drill.json"}')
    if not ok:
        raise SystemExit(3)


def parse_env(path):
    out = {}
    if not path.exists():
        return out
    for raw in path.read_text(errors='ignore').splitlines():
        raw = raw.strip()
        if not raw or raw.startswith('#') or '=' not in raw:
            continue
        k, v = raw.split('=', 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def infer_nas_target(policy):
    if os.environ.get('RECOVERY_NAS_TARGET'):
        return os.environ['RECOVERY_NAS_TARGET']
    if policy.get('nas_target'):
        return policy['nas_target']
    env = parse_env(STORAGE_ENV)
    user = env.get('NAS_USER')
    host = env.get('NAS_HOST') or env.get('NAS_IP')
    root = env.get('NAS_ROOT')
    if user and host and root:
        return f'{user}@{host}:{root.rstrip("/")}/backups'
    remote = env.get('NAS_STORAGE', '')
    if ':' in remote and '/projects/' in remote:
        hostpart, path = remote.split(':', 1)
        base = path.split('/projects/', 1)[0]
        return f'{hostpart}:{base}/backups'
    return ''


def status(project):
    policy = ensure_policy()
    w = workspace_for(project)
    drill = load_json(RECOVERY_ROOT / project / 'last-drill.json')
    target = infer_nas_target(policy)
    print('=== CHACHA RECOVERY STATUS V4.5 ===')
    print(f'PROJECT={project}')
    print(f'WORKSPACE={w}')
    print(f'RPO_TARGET_HOURS={policy.get("default_rpo_hours", 24)}')
    print(f'RTO_TARGET_HOURS={policy.get("default_rto_hours", 2)}')
    print(f'LOCAL_DRILL={drill.get("status") if drill else "MISSING"}')
    print(f'LOCAL_DRILL_TIME={drill.get("time") if drill else "-"}')
    print(f'PRODUCTION_DATA_RESTORE_TESTED={str(bool(drill and drill.get("production_data_restore_tested"))).upper()}')
    print(f'NAS_TARGET={target if target else "UNCONFIGURED"}')
    print('RECOVERY_STATUS=OK' if drill and drill.get('status') == 'OK' else 'RECOVERY_STATUS=ACTION_REQUIRED')


def nas_snapshot(project):
    policy = ensure_policy()
    target = infer_nas_target(policy)
    if not target:
        raise SystemExit('RECOVERY_NAS_TARGET_UNCONFIGURED')
    workspace = workspace_for(project)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    with tempfile.TemporaryDirectory(prefix=f'chacha-nas-backup-{project}-') as td:
        archive = Path(td) / f'{project}-{stamp}.tar.gz'
        make_archive(project, workspace, archive)
        digest = sha256(archive)
        remote = target.rstrip('/') + '/' + project
        if shutil.which('rsync') is None:
            raise SystemExit('RSYNC_MISSING')
        host, remote_path = remote.split(':', 1)
        subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', host, 'mkdir', '-p', remote_path], check=True)
        subprocess.run(['rsync', '-a', str(archive), remote + '/'], check=True)
        checksum_name = archive.name + '.sha256'
        checksum_file = Path(td) / checksum_name
        checksum_file.write_text(digest + '  ' + archive.name + '\n')
        subprocess.run(['rsync', '-a', str(checksum_file), remote + '/'], check=True)
        print('NAS_SNAPSHOT=OK')
        print(f'NAS_REMOTE={remote}/{archive.name}')
        print(f'ARCHIVE_SHA256={digest}')


def main():
    ap = argparse.ArgumentParser(prog='recoveryctl')
    sub = ap.add_subparsers(dest='cmd', required=True)
    for name in ('status', 'local-drill', 'nas-snapshot'):
        p = sub.add_parser(name)
        p.add_argument('project')
    sub.add_parser('policy')
    args = ap.parse_args()

    if args.cmd == 'policy':
        print(json.dumps(ensure_policy(), indent=2))
    elif args.cmd == 'status':
        status(args.project)
    elif args.cmd == 'local-drill':
        local_drill(args.project)
    elif args.cmd == 'nas-snapshot':
        nas_snapshot(args.project)


if __name__ == '__main__':
    main()
