#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="$ROOT/scripts/lastwar-formation-visual-human-search-v2.sh"
TMP="$ROOT/scripts/.lastwar-formation-visual-human-search-v2.runtime.sh"
[[ -s "$SRC" ]] || { echo "ERREUR: V2 absent" >&2; exit 1; }
python - "$SRC" "$TMP" <<'PY'
from pathlib import Path
import sys
s=Path(sys.argv[1]).read_text('utf-8')
old="cands=[p,Path.home()/'storage/downloads'/p.name,Path.home()/'storage/shared/Download'/p.name,ROOT/p]"
new="cands=[p,Path.home()/'storage/downloads'/p.name,Path.home()/'storage/shared/Download'/p.name,Path.cwd()/p]"
if old not in s: raise SystemExit('ERREUR: correctif V2 attendu introuvable')
Path(sys.argv[2]).write_text(s.replace(old,new),'utf-8')
PY
chmod +x "$TMP"
trap 'rm -f "$TMP"' EXIT
bash "$TMP"
