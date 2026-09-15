#!/bin/bash
set -euo pipefail

ROOT="${CHACHA_DEV_ROOT:-/opt/chacha-dev}"
BIN="$ROOT/platform/bin"
BASE="https://raw.githubusercontent.com/chachasan090375/WfGg/dev-hub-v4.5/dev-hub"
PROJECT="${1:-wfgg}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"

mkdir -p "$BIN" "$ROOT/recovery" "$ROOT/tests"

echo "=== CHACHA DEV ARCHITECT V4.5 ==="

for pair in \
  "remediation-plan.py:architect-remediation" \
  "test-matrix.py:test-matrix" \
  "recoveryctl.py:recoveryctl"
do
  SRC="${pair%%:*}"
  NAME="${pair##*:}"
  curl -fsSL "$BASE/$SRC" -o "$BIN/$SRC"
  chmod 755 "$BIN/$SRC"
  ln -sfn "$BIN/$SRC" "/usr/local/bin/$NAME"
done

if [ -e /usr/local/bin/architectctl ]; then
  cp -a "$(readlink -f /usr/local/bin/architectctl)" "$BIN/architectctl.pre-v4.5.$STAMP.bak" 2>/dev/null || true
fi
curl -fsSL "$BASE/architectctl-v4.5.py" -o "$BIN/architectctl-v4.5.py"
chmod 755 "$BIN/architectctl-v4.5.py"
ln -sfn "$BIN/architectctl-v4.5.py" /usr/local/bin/architectctl

# Recovery status must never claim full OK while production data restore is untested.
python3 - "$BIN/recoveryctl.py" <<'PY'
from pathlib import Path
import sys
p=Path(sys.argv[1])
s=p.read_text()
old="    print('RECOVERY_STATUS=OK' if drill and drill.get('status') == 'OK' else 'RECOVERY_STATUS=ACTION_REQUIRED')\n"
new=("    local_ok = bool(drill and drill.get('status') == 'OK')\n"
     "    prod_ok = bool(drill and drill.get('production_data_restore_tested'))\n"
     "    if local_ok and prod_ok:\n"
     "        print('RECOVERY_STATUS=OK')\n"
     "    elif local_ok:\n"
     "        print('RECOVERY_STATUS=PARTIAL')\n"
     "    else:\n"
     "        print('RECOVERY_STATUS=ACTION_REQUIRED')\n")
if old in s:
    p.write_text(s.replace(old,new,1))
    print('RECOVERY_STATUS_GUARD=APPLIED')
elif 'RECOVERY_STATUS=PARTIAL' in s:
    print('RECOVERY_STATUS_GUARD=ALREADY_PRESENT')
else:
    raise SystemExit('RECOVERY_STATUS_PATCH_POINT_NOT_FOUND')
PY

echo
echo "=== SYNTAX CHECK ==="
python3 -m py_compile \
  "$BIN/remediation-plan.py" \
  "$BIN/test-matrix.py" \
  "$BIN/recoveryctl.py" \
  "$BIN/architectctl-v4.5.py"
echo "V4_5_SYNTAX=OK"

echo
echo "=== ARCHITECT STATUS ==="
architectctl status

echo
echo "=== REMEDIATION PLAN ==="
architectctl remediation "$PROJECT"

echo
echo "=== TEST MATRIX ==="
architectctl test-matrix "$PROJECT"

echo
echo "=== NON-DESTRUCTIVE RECOVERY DRILL ==="
architectctl recovery-drill "$PROJECT"

echo
echo "=== RECOVERY STATUS ==="
architectctl recovery-status "$PROJECT"

echo
echo "=== V4.5 POLICY ==="
echo "AUTO_DEPENDENCY_INSTALL=NO"
echo "AUTO_PRODUCTION_RESTORE=NO"
echo "NAS_SNAPSHOT_AUTORUN=NO"
echo "PRODUCTION_CHANGES_REQUIRE_APPROVAL=YES"
echo "ARCHITECT_V4_5=READY"
