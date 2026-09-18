#!/usr/bin/env bash
set -euo pipefail

PROJECT="${1:-wfgg}"
ROOT="${CHACHA_DEV_ROOT:-/opt/chacha-dev}"
WORKSPACE="$ROOT/projects/$PROJECT/workspace"
BRANCH="dev-hub-v4.6"
ARCHITECTCTL="${ARCHITECTCTL:-/usr/local/bin/architectctl}"
TEST_MATRIX="$ROOT/platform/bin/test-matrix.py"
GATE_AUDIT="$ROOT/platform/bin/gate-audit.py"

echo "=== CHACHA DEV ARCHITECT V4.6 / TESTING FOUNDATION ==="
echo "PROJECT=$PROJECT"
echo "WORKSPACE=$WORKSPACE"
echo "BRANCH=$BRANCH"

if [ ! -d "$WORKSPACE/.git" ]; then
  echo "WORKSPACE_GIT=MISSING"
  exit 2
fi

if command -v "$ARCHITECTCTL" >/dev/null 2>&1; then
  echo "=== STORAGE PREFLIGHT ==="
  "$ARCHITECTCTL" storage-preflight --need-mb 600 --heavy
fi

cd "$WORKSPACE"

echo "=== SOURCE SYNC ==="
git fetch --prune origin "$BRANCH"
git checkout -B "$BRANCH" "origin/$BRANCH"
echo "SOURCE_BRANCH=$(git branch --show-current)"
echo "SOURCE_HEAD=$(git rev-parse --short=12 HEAD)"

echo "=== WORKER DEPENDENCIES ==="
cd "$WORKSPACE/worker"
npm install --no-fund --no-audit

echo "=== STATIC CHECK ==="
npm run check

echo "=== UNIT + INTEGRATION FOUNDATION ==="
npm run test:ci

echo "=== SECURITY SIGNAL ==="
set +e
npm audit --audit-level=high
AUDIT_RC=$?
set -e
echo "NPM_AUDIT_RC=$AUDIT_RC"

cd "$WORKSPACE"

echo "=== TEST MATRIX REFRESH ==="
if [ -x "$TEST_MATRIX" ] || [ -f "$TEST_MATRIX" ]; then
  python3 "$TEST_MATRIX" "$PROJECT"
else
  echo "TEST_MATRIX_TOOL=MISSING"
fi

echo "=== ARCHITECTURE GATE REFRESH ==="
if [ -x "$GATE_AUDIT" ] || [ -f "$GATE_AUDIT" ]; then
  python3 "$GATE_AUDIT" "$PROJECT"
else
  echo "GATE_AUDIT_TOOL=MISSING"
fi

echo "=== V4.6 POLICY ==="
echo "PLAYWRIGHT_INSTALL=DEFERRED"
echo "PRODUCTION_DEPLOY=NO"
echo "MAIN_BRANCH_CHANGED=NO"
echo "TESTING_FOUNDATION=VITEST+CLOUDFLARE_RUNTIME"
echo "ARCHITECT_V4_6=READY"
