#!/bin/bash
set -euo pipefail

ROOT="${CHACHA_DEV_ROOT:-/opt/chacha-dev}"
REG="$ROOT/registry/manifests"
TARGET="$REG/wfgg.json"
BACKUP_DIR="$REG/backups"
BASE="https://raw.githubusercontent.com/chachasan090375/WfGg/dev-hub-v4.1/dev-hub"
TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT

mkdir -p "$REG" "$BACKUP_DIR"

if [[ -f "$TARGET" ]]; then
  TS="$(date -u +%Y%m%dT%H%M%SZ)"
  cp -a "$TARGET" "$BACKUP_DIR/wfgg.v1-$TS.json"
  echo "MANIFEST_BACKUP=$BACKUP_DIR/wfgg.v1-$TS.json"
fi

curl -fsSL "$BASE/templates/wfgg-manifest-v2.json" -o "$TMP"
python3 -m json.tool "$TMP" >/dev/null

python3 - "$TMP" <<'PY'
import json, sys
p=sys.argv[1]
d=json.load(open(p))
assert d.get('schema') == 'chacha.dev/project-manifest/v2'
assert d.get('name') == 'wfgg'
components=d.get('components', [])
assert len(components) >= 4
names={c.get('name') for c in components}
for required in ('frontend','api','database','object-storage'):
    assert required in names, required
for key in ('repository','workspace','integrations','agents','storage','security','quality_gates','operations','governance'):
    assert key in d, key
print('MANIFEST_V2_STRUCTURE=OK')
print('MANIFEST_V2_COMPONENTS=' + ','.join(c['name'] for c in components))
PY

install -m 640 "$TMP" "$TARGET"

echo "MANIFEST_V2_INSTALLED=$TARGET"
echo "MANIFEST_V2_SCHEMA=$(python3 -c 'import json; print(json.load(open("'"$TARGET"'"))["schema"])')"

if command -v architectctl >/dev/null 2>&1; then
  echo
  echo "=== ARCHITECT AUDIT ==="
  architectctl audit wfgg
fi

echo
if command -v projectctl >/dev/null 2>&1; then
  echo "=== PLATFORM HEALTH ==="
  projectctl health | tail -n 8
fi

echo "WFGG_MANIFEST_V2_UPGRADE=OK"
