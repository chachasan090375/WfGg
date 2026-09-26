#!/usr/bin/env python3
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
p=ROOT/'.github/workflows/dev-hub-guardian-production-deploy.yml'
s=p.read_text()

assert 'workflow_dispatch:' in s
assert "production-guardian-deploy-*" in s
assert ".chacha-approvals/guardian-worker/*.json" in s
assert 'confirm_production' in s
assert "scope')=='guardian-worker-production'" in s
assert "approved_by')=='operator'" in s
assert 'Checkout exact approved revision' in s
assert 'SENTINEL_EXACT_HEAD_ATTESTATION_MISSING' in s
assert 'test_v820_guardian_terminal_hold.py' in s
assert 'version_coupling_audit.py' in s
assert 'wrangler@4.45.0 rollback' in s
assert '"guardian_runtime_contract":"chacha.dev/guardian-runtime/v1"' in s
assert 'CHACHA_DEV_AUTOMATIC_EXTERNAL_SPEND_EUR=0' in s
assert 'guardian_runtime_build' not in s
assert 'branches:\n      - dev-hub-v' not in s
print('CHACHA_DEV_GUARDIAN_PRODUCTION_DEPLOY_EXPLICIT_APPROVAL=PASS')
print('CHACHA_DEV_GUARDIAN_PRODUCTION_DEPLOY_EXACT_REVISION=PASS')
print('CHACHA_DEV_GUARDIAN_PRODUCTION_DEPLOY_SENTINEL_GATE=PASS')
print('CHACHA_DEV_GUARDIAN_PRODUCTION_DEPLOY_ROLLBACK=PASS')
print('CHACHA_DEV_GUARDIAN_PRODUCTION_DEPLOY_VERSION_AGNOSTIC=PASS')
print('CHACHA_DEV_AUTOMATIC_EXTERNAL_SPEND_EUR=0')
