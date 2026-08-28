#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — PHASE 30D
# OFFLINE ONLY. Discovers the real Unity editor/runtime version from authoritative
# installed game files (globalgamemanagers/Data/libunity), then patches Phase 30B
# to use that exact version as UnityPy fallback. No Last War network connection.

PKG="com.fun.lastwar.gp"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="$ROOT/scripts/lastwar-phase30b-node-payload-extraction.sh"
DOWNLOADS="${HOME}/storage/downloads"
OUT="${DOWNLOADS}/WFGG_LASTWAR_PHASE30D_ENGINE_VERSION_DISCOVERY_REDACTED.txt"
SCAN="${TMPDIR:-${HOME}/.cache}/wfgg-phase30d-version-scan.py"
PATCHED="$ROOT/scripts/.lastwar-phase30d-patched.$$"
VERSION_FILE="${TMPDIR:-${HOME}/.cache}/wfgg-phase30d-version.txt"

cleanup(){ rm -f "$SCAN" "$PATCHED" "$VERSION_FILE"; }
trap cleanup EXIT

die(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
command -v python >/dev/null 2>&1 || die "python Termux absent"
command -v pm >/dev/null 2>&1 || die "commande Android pm absente"
[[ -s "$SRC" ]] || die "Phase 30B introuvable: $SRC"

mapfile -t APK_PATHS < <(pm path "$PKG" 2>/dev/null | sed -n 's/^package://p')
if [[ ${#APK_PATHS[@]} -eq 0 ]]; then
  mapfile -t APK_PATHS < <(cmd package path "$PKG" 2>/dev/null | sed -n 's/^package://p')
fi
[[ ${#APK_PATHS[@]} -gt 0 ]] || die "installation Last War introuvable ($PKG)"
mkdir -p "$(dirname "$SCAN")"

cat > "$SCAN" <<'PY'
import os,re,sys,zipfile
from collections import defaultdict

out_path,version_file,*apks=sys.argv[1:]
# Canonical Unity version strings. Reject bundle stripping placeholders such as 5.x.x/0.0.0.
rx=re.compile(rb'(?<![0-9A-Za-z])((?:20\d{2}|[567])\.\d+\.\d+[abcfpx]\d+(?:_[0-9A-Za-z.-]+)?)(?![0-9A-Za-z])')

rows=[]
def rank_path(p):
    q=p.lower()
    if q.endswith('globalgamemanagers') or '/globalgamemanagers' in q:return 100
    if q.endswith('data.unity3d'):return 95
    if q.endswith('resources.assets'):return 90
    if 'sharedassets' in q and q.endswith('.assets'):return 85
    if q.endswith('/libunity.so') or q.endswith('libunity.so'):return 80
    if q.endswith('boot.config'):return 60
    if '/assets/bin/data/' in q:return 50
    return 10

def interesting(p,size):
    q=p.lower()
    if size<=0:return False
    return ('globalgamemanagers' in q or q.endswith('data.unity3d') or q.endswith('resources.assets') or
            ('sharedassets' in q and q.endswith('.assets')) or q.endswith('libunity.so') or
            q.endswith('boot.config') or ('/assets/bin/data/' in q and size<64*1024*1024))

for apk in apks:
    try:
        with zipfile.ZipFile(apk) as z:
            for zi in z.infolist():
                if not interesting(zi.filename,zi.file_size):continue
                try:
                    data=z.read(zi)
                except Exception:
                    continue
                vals=[]
                for m in rx.finditer(data):
                    v=m.group(1).decode('ascii','ignore')
                    if v not in vals:vals.append(v)
                if vals:
                    rows.append((rank_path(zi.filename),os.path.basename(apk),zi.filename,zi.file_size,vals))
    except Exception:
        pass

# If targeted scan found nothing, scan only modest APK entries for an exact Unity version token.
if not rows:
    for apk in apks:
        try:
            with zipfile.ZipFile(apk) as z:
                for zi in z.infolist():
                    if zi.file_size<=0 or zi.file_size>16*1024*1024:continue
                    try:data=z.read(zi)
                    except Exception:continue
                    vals=[]
                    for m in rx.finditer(data):
                        v=m.group(1).decode('ascii','ignore')
                        if v not in vals:vals.append(v)
                    if vals:rows.append((rank_path(zi.filename),os.path.basename(apk),zi.filename,zi.file_size,vals))
        except Exception:pass

rows.sort(key=lambda x:(-x[0],x[1],x[2]))
# Score versions by strongest source, then number of distinct authoritative sources.
score=defaultdict(lambda:[0,set()])
for r,apk,path,size,vals in rows:
    for v in vals:
        score[v][0]=max(score[v][0],r)
        score[v][1].add((apk,path))
ranked=sorted(score.items(),key=lambda kv:(-kv[1][0],-len(kv[1][1]),kv[0]))
chosen=ranked[0][0] if ranked else None
ambiguous=False
if len(ranked)>1 and ranked[0][1][0]==ranked[1][1][0] and len(ranked[0][1][1])==len(ranked[1][1][1]):
    ambiguous=True

with open(out_path,'w',encoding='utf-8') as o:
    o.write('WfGg Last War LAB — PHASE 30D ENGINE VERSION DISCOVERY\n')
    o.write('OFFLINE ONLY · installed APK/splits only · no Last War network connection\n\n')
    o.write('WHY_PHASE30C_FAILED\n')
    o.write('  UnityFS_parent_header_generation=5.x.x\n')
    o.write('  UnityFS_parent_header_revision=0.0.0\n')
    o.write('  stripped_bundle_header_is_not_authoritative_engine_version=true\n\n')
    o.write('ENGINE_VERSION_EVIDENCE\n')
    if not rows:o.write('  (aucune version Unity canonique trouvée)\n')
    for r,apk,path,size,vals in rows[:120]:
        o.write(f'  rank={r} apk={apk} entry={path} bytes={size} versions={";".join(vals)}\n')
    o.write('\nRANKED_VERSIONS\n')
    for v,(r,sources) in ranked[:20]:o.write(f'  version={v} bestRank={r} sourceCount={len(sources)}\n')
    o.write('\nDECISION\n')
    o.write(f'  selected={chosen or "NONE"}\n')
    o.write(f'  ambiguous={str(ambiguous).lower()}\n')
    o.write('  rule=never_use_5.x.x_or_0.0.0_as_UnityPy_fallback\n')
    o.write('  next=run_phase30b_only_when_real_engine_version_is_resolved\n')

if not chosen or ambiguous:
    raise SystemExit(3)
with open(version_file,'w',encoding='ascii') as f:f.write(chosen+'\n')
print(chosen)
PY

set +e
python "$SCAN" "$OUT" "$VERSION_FILE" "${APK_PATHS[@]}"
RC=$?
set -e
chmod 600 "$OUT" 2>/dev/null || true
if [[ $RC -ne 0 || ! -s "$VERSION_FILE" ]]; then
  echo "=== PHASE 30D · VERSION NON RESOLUE ==="
  echo "Aucune version Unity suffisamment autoritative n'a été sélectionnée."
  echo "Fichier à partager : Téléchargements/WFGG_LASTWAR_PHASE30D_ENGINE_VERSION_DISCOVERY_REDACTED.txt"
  exit 0
fi
UNITY_VERSION="$(tr -d '\r\n' < "$VERSION_FILE")"
[[ "$UNITY_VERSION" =~ ^(20[0-9]{2}|[567])\.[0-9]+\.[0-9]+[abcfpx][0-9]+ ]] || die "version Unity invalide: $UNITY_VERSION"

echo "=== PHASE 30D · VERSION UNITY RESOLUE ==="
echo "Unity détecté localement : $UNITY_VERSION"
echo "Patch temporaire de Phase 30B puis relance…"

python - "$SRC" "$PATCHED" "$UNITY_VERSION" <<'PY'
from pathlib import Path
import json,sys
src=Path(sys.argv[1]).read_text(encoding='utf-8')
version=sys.argv[3]
# Patch only the embedded Phase-30B extractor Python, not the small PYTEST preflight.
needle='import UnityPy\nfrom PIL import Image\n\nout_path, kit_dir, catalog_path, *apk_paths = sys.argv[1:]\n'
replacement=(
             '# Phase 30D: graphics-only Android compatibility shim.\n'
             '# UnityPy.export imports its audio converter too; fmod_toolkit rejects\n'
             '# platform.system()=="Android" even though no audio is used here.\n'
             'import platform, types\n'
             'if platform.system() == "Android":\n'
             '    _fmod=types.ModuleType("fmod_toolkit")\n'
             '    def _wfgg_audio_disabled(*args, **kwargs):\n'
             '        raise RuntimeError("FMOD audio conversion disabled in WfGg graphics extraction")\n'
             '    _fmod.raw_to_wav=_wfgg_audio_disabled\n'
             '    _fmod.get_pyfmodex_system_instance=_wfgg_audio_disabled\n'
             '    _fmod.sound_to_wav=_wfgg_audio_disabled\n'
             '    _fmod.subsound_to_wav=_wfgg_audio_disabled\n'
             '    _fmod.__version__="disabled-android-graphics-only"\n'
             '    sys.modules["fmod_toolkit"]=_fmod\n\n'
             'import UnityPy\nfrom PIL import Image\n\n'
             '# Phase 30D: authoritative version discovered from installed game files.\n'
             f'UnityPy.config.FALLBACK_UNITY_VERSION={json.dumps(version)}\n\n'
             'out_path, kit_dir, catalog_path, *apk_paths = sys.argv[1:]\n')
if src.count(needle)!=1:
    raise SystemExit(f'ERREUR: point de patch extracteur UnityPy inattendu ({src.count(needle)})')
out=src.replace(needle,replacement,1)
Path(sys.argv[2]).write_text(out,encoding='utf-8')
PY
chmod 700 "$PATCHED"
exec bash "$PATCHED"
