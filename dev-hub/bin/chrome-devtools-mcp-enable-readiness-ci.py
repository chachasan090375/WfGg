#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import http.server
import json
import os
import shutil
import socketserver
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT = Path('/tmp/chrome-devtools-mcp-enable-readiness')
RUNTIME = REPO / 'dev-hub/adapters/chrome-devtools-mcp-adapter.py'
READINESS = REPO / 'dev-hub/bin/adapter-enable-readiness.py'
ROLLBACKS = REPO / 'dev-hub/config/adapter-rollbacks.v1.json'


def load(path: Path):
    return json.loads(path.read_text(encoding='utf-8'))


def save(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def digest(value) -> str:
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    return 'sha256:' + hashlib.sha256(raw).hexdigest()


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/api/ping':
            body = b'{"ok":true,"source":"chrome-devtools-enable-readiness"}'
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        body = b'''<!doctype html><html><head><title>DEV HUB Chrome Readiness</title></head><body><h1>chrome-enable-readiness-ready</h1><script>console.log('chrome-readiness-console-ok');fetch('/api/ping').then(r=>r.json()).then(x=>console.log('chrome-readiness-network-ok',x.ok));</script></body></html>'''
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        pass


class Server(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


def envelope(url: str) -> dict:
    return {
        'schema': 'chacha.dev/dispatch-envelope/v1',
        'project': 'dev-hub-v5',
        'task': {'id': 'chrome-devtools-mcp-enable-readiness', 'permission': 'read'},
        'bindings': [{'provider': 'chrome-devtools-mcp', 'adapter': 'chrome-devtools-mcp-adapter'}],
        'metadata': {'chrome_devtools_mcp': {'operation': 'inspect_url', 'url': url, 'expected_text': 'chrome-enable-readiness-ready'}},
        'policy_context': {'timeout_seconds': 45},
    }


def run_adapter(index: int, request: dict, allowed_origin: str) -> tuple[Path, dict]:
    env = os.environ.copy()
    env['CHACHA_CHROME_DEVTOOLS_ALLOWED_ORIGIN'] = allowed_origin
    proc = subprocess.run(
        [sys.executable, str(RUNTIME)],
        cwd=str(REPO),
        input=json.dumps(request),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
        check=False,
    )
    if proc.returncode != 0:
        raise SystemExit(f'CHROME_READINESS_ADAPTER_EXIT_{index}={proc.returncode}\n{proc.stderr[-4000:]}')
    try:
        result = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise SystemExit(f'CHROME_READINESS_RESULT_JSON_INVALID_{index}={exc}')
    if result.get('schema') != 'chacha.dev/task-result/v1':
        raise SystemExit(f'CHROME_READINESS_SCHEMA_INVALID_{index}')
    if result.get('status') != 'OK':
        raise SystemExit(f'CHROME_READINESS_RESULT_NOT_OK_{index}={result}')
    if result.get('producer') != 'chrome-devtools-mcp-adapter':
        raise SystemExit(f'CHROME_READINESS_PRODUCER_INVALID_{index}')
    if (result.get('verification') or {}).get('status') != 'UNVERIFIED':
        raise SystemExit(f'CHROME_READINESS_VERIFICATION_INVALID_{index}')
    details = ((result.get('evidence') or [{}])[0].get('details') or {})
    if details.get('operation') != 'inspect_url' or details.get('final_origin_revalidated') is not True:
        raise SystemExit(f'CHROME_READINESS_NAVIGATION_BOUNDARY_INVALID_{index}')
    if details.get('browser_interaction') is not False or details.get('workspace_write') is not False or details.get('repository_write') is not False:
        raise SystemExit(f'CHROME_READINESS_WRITE_BOUNDARY_INVALID_{index}')
    path = OUT / f'task-result-{index}.json'
    save(path, result)
    return path, result


def main() -> int:
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)

    required_env = [
        'CHACHA_CHROME_DEVTOOLS_MCP_SERVER',
        'CHACHA_CHROME_DEVTOOLS_MCP_WORKDIR',
        'CHACHA_CHROME_DEVTOOLS_MCP_PACKAGE_VERSION',
        'CHACHA_CHROME_DEVTOOLS_BROWSER_VERSION',
        'CHACHA_CHROME_DEVTOOLS_TARGET_CLASS',
    ]
    missing = [name for name in required_env if not os.environ.get(name)]
    if missing:
        raise SystemExit('CHROME_READINESS_ENV_MISSING=' + ','.join(missing))
    if os.environ['CHACHA_CHROME_DEVTOOLS_TARGET_CLASS'] not in {'test', 'preview'}:
        raise SystemExit('CHROME_READINESS_TARGET_CLASS_INVALID')

    with Server(('127.0.0.1', 0), Handler) as server:
        threading.Thread(target=server.serve_forever, daemon=True).start()
        port = server.server_address[1]
        allowed_origin = f'http://127.0.0.1:{port}'
        request = envelope(allowed_origin + '/')
        results: list[tuple[Path, dict]] = []
        for index in (1, 2, 3):
            results.append(run_adapter(index, request, allowed_origin))
            # Isolated Chrome teardown is asynchronous after the MCP server exits.
            # Give the provider enough time to release its temporary browser profile
            # before the next independent repeatability run.
            if index != 3:
                time.sleep(1.5)
        server.shutdown()

    identities = {(r['project'], r['task_id']) for _, r in results}
    observed = {r['observed_at'] for _, r in results}
    result_digests = {digest(r) for _, r in results}
    if len(identities) != 1:
        raise SystemExit(f'CHROME_READINESS_IDENTITY_DRIFT={identities}')
    if len(observed) != 3:
        raise SystemExit(f'CHROME_READINESS_TIMESTAMPS_NOT_DISTINCT={len(observed)}')
    if len(result_digests) != 3:
        raise SystemExit(f'CHROME_READINESS_DIGESTS_NOT_DISTINCT={len(result_digests)}')

    checked_at = datetime.now(timezone.utc).isoformat()
    health = {
        'schema': 'chacha.dev/provider-health-snapshot/v1',
        'observed_at': checked_at,
        'providers': {
            'chrome-devtools-mcp': {
                'state': 'HEALTHY',
                'checked_at': checked_at,
                'source': 'chrome-devtools-mcp-enable-readiness-ci',
                'details': {
                    'successful_runtime_contract_runs': 3,
                    'execution_surface': 'github-actions-ephemeral',
                    'package_version': os.environ['CHACHA_CHROME_DEVTOOLS_MCP_PACKAGE_VERSION'],
                    'browser_version': os.environ['CHACHA_CHROME_DEVTOOLS_BROWSER_VERSION'],
                    'compatibility_mode': 'EXPLICIT_PROVIDER_COMPATIBILITY',
                    'dev_hub_protocol_baseline': '2026-07-28',
                    'upstream_protocol': '2025-11-25',
                    'controlled_navigation': True,
                    'production_target': False,
                    'result_trust': 'UNVERIFIED',
                },
            }
        },
    }
    health_path = OUT / 'provider-health.json'
    save(health_path, health)

    readiness_dir = OUT / 'readiness'
    cmd = [
        sys.executable, str(READINESS),
        '--adapter', 'chrome-devtools-mcp-adapter',
        '--provider', 'chrome-devtools-mcp',
        '--health', str(health_path),
        '--rollbacks', str(ROLLBACKS),
        '--work-dir', str(readiness_dir),
        '--json',
    ]
    for path, _result in results:
        cmd.extend(['--result', str(path)])
    proc = subprocess.run(cmd, cwd=str(REPO), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
    (OUT / 'readiness-stdout.txt').write_text(proc.stdout, encoding='utf-8')
    (OUT / 'readiness-stderr.txt').write_text(proc.stderr, encoding='utf-8')
    receipt_path = readiness_dir / 'enablement-readiness.json'
    if proc.returncode != 0 or not receipt_path.is_file():
        raise SystemExit(f'CHROME_READINESS_FAILED={proc.returncode}\n{proc.stdout[-4000:]}\n{proc.stderr[-4000:]}')

    receipt = load(receipt_path)
    plan = load(readiness_dir / 'enablement-promotion-plan.json')
    evidence = load(readiness_dir / 'enablement-evidence.json')
    if receipt.get('status') != 'READY_FOR_ENABLEMENT' or receipt.get('registry_mutated') is not False or receipt.get('blockers') != []:
        raise SystemExit(f'CHROME_READINESS_RECEIPT_INVALID={receipt}')
    if plan.get('eligible') is not True or plan.get('blockers') != []:
        raise SystemExit(f'CHROME_READINESS_PROMOTION_PLAN={plan}')
    for gate in ('repeatable-pass', 'provider-health-pass', 'rollback-defined'):
        if (evidence.get('evidence', {}).get(gate) or {}).get('status') != 'PASS':
            raise SystemExit(f'CHROME_READINESS_GATE_FAILED={gate}')

    manifest = {
        'schema': 'chacha.dev/chrome-devtools-mcp-enable-readiness-manifest/v1',
        'adapter': 'chrome-devtools-mcp-adapter',
        'provider': 'chrome-devtools-mcp',
        'current_status': 'PILOT',
        'target_status': 'ENABLED',
        'status': 'READY_FOR_ENABLEMENT',
        'promotion_eligible': True,
        'promotion_applied': False,
        'registry_mutated': False,
        'provider_health': 'HEALTHY',
        'repeatability_runs': 3,
        'task_identity': list(next(iter(identities))),
        'distinct_observed_at': len(observed),
        'distinct_result_digests': len(result_digests),
        'result_digests': sorted(result_digests),
        'provider_result_verification': 'UNVERIFIED',
        'verification_broker_required': True,
        'compatibility_mode': 'EXPLICIT_PROVIDER_COMPATIBILITY',
        'dev_hub_protocol_baseline': '2026-07-28',
        'upstream_protocol': '2025-11-25',
        'controlled_navigation': True,
        'production_capable': False,
        'automatic_promotion': False,
        'blockers': [],
        'observed_at': datetime.now(timezone.utc).isoformat(),
    }
    save(OUT / 'manifest.json', manifest)
    print('CHROME_DEVTOOLS_MCP_ENABLEMENT_READINESS=PASS status=READY_FOR_ENABLEMENT registry_status=PILOT mutation=false')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
