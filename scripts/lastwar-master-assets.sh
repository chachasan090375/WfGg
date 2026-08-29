#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# Stable entrypoint for MASTER UI asset recovery.
# It applies two narrow corrections to Phase 33 before execution:
# 1) hero portrait atlases do not consume the UI raw-bundle quota;
# 2) internal Last War asset aliases are joined to the public hero names so queue/model
#    bundles for the active squads can be retained.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="$ROOT/scripts/lastwar-phase33-master-ui-assets.sh"
TMP="$ROOT/scripts/.lastwar-master-assets-run.$$"

cleanup(){ rm -f "$TMP"; }
trap cleanup EXIT
[[ -s "$SRC" ]] || { echo "ERREUR: Phase 33 absente: $SRC" >&2; exit 1; }
command -v python >/dev/null 2>&1 || { echo "ERREUR: python Termux absent" >&2; exit 1; }

python - "$SRC" "$TMP" <<'PY'
from pathlib import Path
import sys
src=Path(sys.argv[1]).read_text(encoding='utf-8')

# Hero portrait atlases are already recovered by the exact V2 extractor. They remain
# in the package through catalog selection, but must not be considered generic UI bundles.
src=src.replace(
'   "hero_frame","rankicon","staricon","heroiconsbig","heroiconssmall"\n',
'   "hero_frame","rankicon","staricon"\n',1)

# Inject internal asset aliases into the temporary Phase30B patch before candidate scanning.
marker="# Replace the broad historical category scan by the precise families seen in the\n# installed gameres catalogue and in the two master screens.\n"
insert=r'''# Join authoritative internal Last War asset tokens to the display-name aliases.
alias_repls={
 '"Williams":["williams","william"]':'"Williams":["williams","william","rick"]',
 '"Marshall":["marshall"]':'"Marshall":["marshall","nimitz"]',
 '"Kimberly":["kimberly","kimberlyzombie"]':'"Kimberly":["kimberly","kimberlyzombie","katyusha"]',
 '"Stetmann":["stetmann","stettmann"]':'"Stetmann":["stetmann","stettmann","stetman"]',
 '"Carlie":["carlie","carli"]':'"Carlie":["carlie","carli","carly"]',
 '"Schuyler":["schuyler"]':'"Schuyler":["schuyler","sally_ride"]',
 '"Swift":["swift"]':'"Swift":["swift","tom"]',
}
for old,new in alias_repls.items():
    if old in s:s=s.replace(old,new,1)

'''
if marker not in src:
    raise SystemExit('ERREUR: point insertion alias Phase33 introuvable')
src=src.replace(marker,insert+marker,1)
Path(sys.argv[2]).write_text(src,encoding='utf-8')
PY

chmod 700 "$TMP"
exec bash "$TMP"
