#!/bin/bash
set -euo pipefail

ROOT="${CHACHA_DEV_ROOT:-/opt/chacha-dev}"
BIN="$ROOT/platform/bin"
BASE_URL="https://raw.githubusercontent.com/chachasan090375/WfGg/dev-hub-v4.5.1/dev-hub"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
MODE="${1:-}"

mkdir -p "$BIN" "$ROOT/platform/config"

echo "=== CHACHA DEV ARCHITECT V4.5.1 / STORAGE GOVERNOR ==="

if [ -e /usr/local/bin/architectctl ]; then
  cp -a "$(readlink -f /usr/local/bin/architectctl)" "$BIN/architectctl.pre-v4.5.1.$STAMP.bak" 2>/dev/null || true
fi

curl -fsSL "$BASE_URL/storage-governor.py" -o "$BIN/storage-governor.py"
curl -fsSL "$BASE_URL/architectctl-v4.5.py" -o "$BIN/architectctl-v4.5.py"
curl -fsSL "$BASE_URL/architectctl-v4.5.1.py" -o "$BIN/architectctl-v4.5.1.py"
chmod 755 "$BIN/storage-governor.py" "$BIN/architectctl-v4.5.py" "$BIN/architectctl-v4.5.1.py"
ln -sfn "$BIN/storage-governor.py" /usr/local/bin/storage-governor
ln -sfn "$BIN/architectctl-v4.5.1.py" /usr/local/bin/architectctl

python3 -m py_compile "$BIN/storage-governor.py" "$BIN/architectctl-v4.5.py" "$BIN/architectctl-v4.5.1.py"
echo "V4_5_1_SYNTAX=OK"

echo
echo "=== STORAGE BEFORE ==="
storage-governor audit

if [ "$MODE" = "--cleanup-safe" ]; then
  echo
  echo "=== SAFE CLEANUP ==="
  storage-governor cleanup-safe
fi

echo
echo "=== STORAGE PREFLIGHT / HEAVY 512MB ==="
storage-governor preflight --need-mb 512 --heavy || true

echo
echo "=== PLATFORM HEALTH ==="
devhub-health || true

echo
echo "=== ARCHITECT STATUS ==="
architectctl status

echo
echo "=== V4.5.1 POLICY ==="
echo "VPS_ROLE=execution-tier"
echo "NAS_ROLE=capacity-tier"
echo "AUTO_OFFLOAD=NO"
echo "AUTO_DELETE_PROJECT_SOURCES=NO"
echo "AUTO_DELETE_ENGINES=NO"
echo "HEAVY_OPERATIONS_REQUIRE_PREFLIGHT=YES"
echo "ARCHITECT_V4_5_1=READY"
