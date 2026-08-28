#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — PHASE 31
# OFFLINE ONLY. Reuses the proven Phase30B/30D Unity pipeline, but filters exports
# to high-value squad graphics: real hero portraits, Drone/UAV icons, Dominator
# icons, and formation/squad UI pieces. No Last War network connection.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASE="$ROOT/scripts/lastwar-phase30b-node-payload-extraction.sh"
RUNNER="$ROOT/scripts/lastwar-phase30d-engine-version-discovery.sh"
TMP="$ROOT/scripts/.lastwar-phase31-targeted.$$"

cleanup(){ rm -f "$TMP"; }
trap cleanup EXIT

die(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
command -v python >/dev/null 2>&1 || die "python Termux absent"
[[ -s "$BASE" ]] || die "Phase 30B introuvable: $BASE"
[[ -s "$RUNNER" ]] || die "Phase 30D introuvable: $RUNNER"

cp "$BASE" "$TMP"

python - "$TMP" <<'PY'
from pathlib import Path
import sys
p=Path(sys.argv[1])
s=p.read_text(encoding='utf-8')

repls={
 'WFGG_LASTWAR_PHASE30B_NODE_PAYLOAD_EXTRACTION_REDACTED.txt':'WFGG_LASTWAR_PHASE31_TARGETED_GRAPHICS_REDACTED.txt',
 'MAX_CANDIDATES_TO_LOAD=520':'MAX_CANDIDATES_TO_LOAD=1800',
 'MAX_EXPORTED=1200':'MAX_EXPORTED=900',
 'MAX_OUTPUT_BYTES=350*1024*1024':'MAX_OUTPUT_BYTES=180*1024*1024',
 'PHASE30B_DONE':'PHASE31_DONE',
 'WfGg Last War LAB — PHASE 30B NODE PAYLOAD EXTRACTION':'WfGg Last War LAB — PHASE 31 TARGETED GRAPHICS EXTRACTION',
 '=== PHASE 30B TERMINEE ===':'=== PHASE 31 TERMINEE ===',
}
for a,b in repls.items():
    if a not in s:
        raise SystemExit(f'point de patch absent: {a}')
    s=s.replace(a,b)

needle='def save_image(img,name,objtype,candidate,path_id):\n    global output_bytes\n'
insert=r'''def phase31_wanted_asset(name,candidate):
    low=str(name or '').lower()
    bad=('eff_','effect','smoke','noise','crack','trail','particle','mask','normal','lightmap','shadow')
    # Hero mapping stays name-based, but only icon/portrait-like objects qualify.
    for hero,als in hero_aliases.items():
        if any(a in low for a in als):
            iconish=('hero_icon_' in low or 'halfbody' in low or 'herohead' in low or 'headicon' in low or 'portrait' in low)
            secondary=('zhuanwu' in low or 'lrb_' in low or 'ljq_icon' in low or '_skill' in low or 'weapon' in low)
            if iconish and not secondary and not any(x in low for x in bad):
                return True
    # Drone: require an actual UI/icon-looking asset, never a generic effect/texture.
    if any(x in low for x in ('drone','uav')):
        if any(x in low for x in ('icon','head','portrait','item_uav_equip')) and not any(x in low for x in bad):
            return True
    # Dominator / Overlord families.
    if any(x in low for x in ('dominator','gorilla','cockatrice','hawk')):
        if any(x in low for x in ('icon','head','portrait','pic','avatar')) and not any(x in low for x in bad):
            return True
    # Formation/squad UI. Keep this narrow enough not to flood the phone with FX.
    if any(x in low for x in ('formation','squad','qualityframe','quality_frame','rankicon','staricon','hero_frame','rarity')):
        if not any(x in low for x in bad):
            return True
    return False

def save_image(img,name,objtype,candidate,path_id):
    global output_bytes
    if not phase31_wanted_asset(name,candidate):
        return False
'''
if s.count(needle)!=1:
    raise SystemExit(f'point de patch save_image inattendu ({s.count(needle)})')
s=s.replace(needle,insert,1)

# Report the targeted contract explicitly.
report_needle='    o.write("GAME DATA LOCAL ONLY · custom UnityFS decode -> node payloads -> UnityPy\\n\\n")\n'
report_repl=(report_needle+
 '    o.write("TARGET=hero portraits + Drone/UAV icons + Dominator icons + formation/squad UI\\n")\n'
 '    o.write("FILTER=object-name semantic match only; generic effects rejected\\n\\n")\n')
if s.count(report_needle)!=1:
    raise SystemExit('point de patch rapport introuvable')
s=s.replace(report_needle,report_repl,1)

p.write_text(s,encoding='utf-8')
PY

chmod 700 "$TMP"
echo "=== PHASE 31 · EXTRACTION GRAPHIQUE CIBLEE ==="
echo "Portraits héros + Drone/UAV + Dominator + UI Formation."
echo "Les PNG existants du kit sont conservés; seuls de nouveaux assets ciblés sont ajoutés."
echo "Aucune connexion Last War n'est effectuée."

WFGG_PHASE30B_SRC="$TMP" bash "$RUNNER"

printf 'Fichier à partager : Téléchargements/WFGG_LASTWAR_PHASE31_TARGETED_GRAPHICS_REDACTED.txt\n'
