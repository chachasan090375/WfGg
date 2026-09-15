#!/bin/bash
set -euo pipefail

ROOT="${CHACHA_DEV_ROOT:-/opt/chacha-dev}"
BIN="$ROOT/platform/bin"
CFG="$ROOT/platform/config"
RADAR="$ROOT/radar"
BASE="https://raw.githubusercontent.com/chachasan090375/WfGg/dev-hub-v4.3/dev-hub"

mkdir -p "$BIN" "$CFG" "$RADAR/history"

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
[ -f "$CFG/tech-watch-targets.json" ] && cp -a "$CFG/tech-watch-targets.json" "$CFG/tech-watch-targets.v4.2.$STAMP.json" || true
[ -f "$RADAR/latest.json" ] && cp -a "$RADAR/latest.json" "$RADAR/latest.v4.2.$STAMP.json" || true

curl -fsSL "$BASE/tech-watch-v4.3.py" -o "$BIN/tech-watch.py"
curl -fsSL "$BASE/tech-watch-targets-v4.3.json" -o "$CFG/tech-watch-targets.json"
chmod 755 "$BIN/tech-watch.py"
chmod 644 "$CFG/tech-watch-targets.json"
ln -sfn "$BIN/tech-watch.py" /usr/local/bin/techwatch

python3 -m py_compile "$BIN/tech-watch.py"
python3 -m json.tool "$CFG/tech-watch-targets.json" >/dev/null

echo "=== TECH WATCH V4.3 INSTALL ==="
echo "TECHWATCH_VERSION=4.3"
echo "TECHWATCH_POLICY=EVIDENCE_SAFE"
echo "TECHWATCH_AUTO_PILOT=NO"
echo "TECHWATCH_AUTO_RECOMMEND=NO"
echo "TECHWATCH_AUTO_REPLACE=NO"

echo
echo "=== FILTERED MARKET TEST ==="
/usr/local/bin/techwatch run --market

echo
echo "=== STATUS ==="
/usr/local/bin/techwatch status

echo
echo "TECH_WATCH_V4_3=READY"
