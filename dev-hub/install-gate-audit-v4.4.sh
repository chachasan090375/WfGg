#!/bin/bash
set -euo pipefail

ROOT="${CHACHA_DEV_ROOT:-/opt/chacha-dev}"
BIN="$ROOT/platform/bin"
BASE="https://raw.githubusercontent.com/chachasan090375/WfGg/dev-hub-v4.4/dev-hub"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"

mkdir -p "$BIN" "$ROOT/audits"

if [ -f "$BIN/architectctl.py" ]; then
  cp -a "$BIN/architectctl.py" "$BIN/architectctl.py.v4.3.$STAMP.bak"
fi

curl -fsSL "$BASE/gate-audit.py" -o "$BIN/gate-audit.py"
curl -fsSL "$BASE/architectctl-v4.4.py" -o "$BIN/architectctl.py"
chmod 755 "$BIN/gate-audit.py" "$BIN/architectctl.py"
ln -sfn "$BIN/gate-audit.py" /usr/local/bin/gate-audit
ln -sfn "$BIN/architectctl.py" /usr/local/bin/architectctl

python3 -m py_compile "$BIN/gate-audit.py" "$BIN/architectctl.py"

echo "=== ARCHITECT V4.4 INSTALL ==="
echo "GATE_AUDIT_TOOL=OK"
echo "ARCHITECT_VERSION=4.4"
echo "AUDIT_STORAGE=$ROOT/audits"

echo
echo "=== TOOL STATUS ==="
architectctl status | grep -E '^(AGENT|ARCHITECT_VERSION|TOOL_GATE_AUDIT|PLATFORM_HEALTH|HEALTH_FAIL|DEV_HUB_HEALTH)=' || true

echo
echo "=== WFGG FULL EVIDENCE AUDIT ==="
architectctl full-audit wfgg

echo
echo "=== SAVED REPORT ==="
architectctl audit-report wfgg

echo
echo "ARCHITECT_V4_4=READY"
