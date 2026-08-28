#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — PHASE 30C
# OFFLINE ONLY. Patches Phase 30B locally so UnityPy receives the exact Unity
# revision read from each parent UnityFS header when node payloads lack it.
# No Last War network connection. No gameplay automation.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="$ROOT/scripts/lastwar-phase30b-node-payload-extraction.sh"
TMP="$ROOT/scripts/.lastwar-phase30c-patched.$$"

[[ -s "$SRC" ]] || { echo "ERREUR: Phase 30B introuvable: $SRC" >&2; exit 1; }
trap 'rm -f "$TMP"' EXIT

python - "$SRC" "$TMP" <<'PY'
from pathlib import Path
import sys
src=Path(sys.argv[1]).read_text(encoding="utf-8")
needle='                env=UnityPy.load(td)\n'
replacement='''                # Node payloads can be valid SerializedFiles while lacking an embedded\n                # Unity version. Recover the exact revision from the parent UnityFS header\n                # and provide it only as UnityPy's parser fallback.\n                _restore=f.tell()\n                _uv=None\n                try:\n                    f.seek(c["start"])\n                    if read_cstr(f)==b"UnityFS":\n                        f.read(4)\n                        _uengine=read_cstr(f).decode("ascii","ignore")\n                        _urev=read_cstr(f).decode("ascii","ignore")\n                        for _cand in (_urev,_uengine):\n                            if re.match(r"^\\d+\\.\\d+\\.\\d+[abcfpx]\\d+", _cand or ""):\n                                _uv=_cand\n                                break\n                        if not _uv:\n                            _uv=_urev or _uengine\n                finally:\n                    f.seek(_restore)\n                if _uv:\n                    UnityPy.config.FALLBACK_UNITY_VERSION=_uv\n                    stats["fallback_version_set"]+=1\n                env=UnityPy.load(td)\n'''
if src.count(needle)!=1:
    raise SystemExit(f"ERREUR: point de patch UnityPy inattendu ({src.count(needle)})")
out=src.replace(needle,replacement,1)
Path(sys.argv[2]).write_text(out,encoding="utf-8")
PY
chmod 700 "$TMP"

echo "=== PHASE 30C · FALLBACK UNITY VERSION ==="
echo "Le script lit la version Unity exacte dans chaque en-tête UnityFS puis relance Phase 30B."
echo "Aucune connexion Last War n'est effectuée."
echo
exec bash "$TMP"
