#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET="$ROOT/scripts/lastwar-phase41-resolve-missing-prefab-bundles.sh"
BRANCH="portal-auth-lastwar-lab-v1"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
[[ -s "$TARGET" ]] || fail "Phase41 absente: $TARGET"
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche active incorrecte"

python - "$TARGET" <<'PY'
from pathlib import Path
import sys
p=Path(sys.argv[1])
s=p.read_text(encoding='utf-8')
old='command -v zip >/dev/null 2>&1 || fail "zip absent"\n'
if old in s:
    s=s.replace(old,'',1)
old='''  (cd "$LOCAL" && zip -q -9 "$PACK" ./*.bundle)\n  sha256sum "$PACK" > "$PACK.sha256"\n'''
new='''  python - "$LOCAL" "$PACK" <<'PYZIP'\nfrom pathlib import Path\nimport sys, zipfile\nsrc=Path(sys.argv[1]); dst=Path(sys.argv[2])\nfiles=sorted(src.glob('*.bundle'))\nwith zipfile.ZipFile(dst,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:\n    for f in files:\n        z.write(f,arcname=f.name)\nprint(f"PHASE41_PACK_OK files={len(files)} bytes={dst.stat().st_size}")\nPYZIP\n  sha256sum "$PACK" > "$PACK.sha256"\n'''
if old not in s:
    if 'zip -q -9 "$PACK"' in s:
        raise SystemExit('packaging block shape changed; refusing unsafe patch')
else:
    s=s.replace(old,new,1)
p.write_text(s,encoding='utf-8')
print('PHASE41_ZIP_DEPENDENCY_REMOVED')
PY

chmod +x "$TARGET"
exec bash "$TARGET"
