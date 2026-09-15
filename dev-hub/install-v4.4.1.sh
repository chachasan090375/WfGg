#!/bin/bash
set -euo pipefail

ROOT="${CHACHA_DEV_ROOT:-/opt/chacha-dev}"
BIN="$ROOT/platform/bin"
BASE="https://raw.githubusercontent.com/chachasan090375/WfGg/dev-hub-v4.4.1/dev-hub"
PROJECT="${1:-wfgg}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"

mkdir -p "$BIN"

echo "=== CHACHA ARCHITECT V4.4.1 ==="

curl -fsSL "$BASE/source-sync-v4.4.1.sh" -o "$BIN/source-sync"
chmod 755 "$BIN/source-sync"
ln -sfn "$BIN/source-sync" /usr/local/bin/source-sync

if [ ! -s "$BIN/gate-audit.py" ]; then
  echo "GATE_AUDIT_TOOL=MISSING" >&2
  exit 2
fi

cp -a "$BIN/gate-audit.py" "$BIN/gate-audit.py.v4.4.$STAMP.bak"

python3 - "$BIN/gate-audit.py" <<'PY'
from pathlib import Path
import sys
p=Path(sys.argv[1])
s=p.read_text()
needle='    gates, scanned = assess(args.project, manifest, workspace)\n'
guard=(needle+
       '    if scanned == 0:\n'
       '        raise SystemExit("GATE_AUDIT_INVALID_NO_SOURCE_FILES")\n')
if 'GATE_AUDIT_INVALID_NO_SOURCE_FILES' not in s:
    if needle not in s:
        raise SystemExit('PATCH_POINT_NOT_FOUND')
    s=s.replace(needle, guard, 1)
    p.write_text(s)
    print('EMPTY_SOURCE_GUARD=APPLIED')
else:
    print('EMPTY_SOURCE_GUARD=ALREADY_PRESENT')
PY

python3 -m py_compile "$BIN/gate-audit.py"
echo "GATE_AUDIT_EMPTY_SOURCE_GUARD=OK"

echo
echo "=== HYDRATE PROJECT SOURCE ==="
"$BIN/source-sync" "$PROJECT"

echo
echo "=== SOURCE DISK CHECK ==="
df -h /

echo
echo "=== REAL FULL AUDIT ==="
architectctl full-audit "$PROJECT"

echo
echo "=== AUDIT REPORT ==="
architectctl audit-report "$PROJECT"

echo
echo "ARCHITECT_V4_4_1=READY"
