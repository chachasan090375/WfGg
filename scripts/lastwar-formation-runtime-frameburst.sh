#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — native FormationBg transition capture V2.
# Dependency-free image capture: ADB + Python standard library only.
# The script does NOT generate/alter pixels and does NOT auto-wire a frame.
# It records the native compositor burst locally and builds a LAB gallery.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
OUTDIR="$ROOT/frontend/lab/local_assets/lastwar-formation-runtime-frameburst-v2"
MANIFEST="$OUTDIR/manifest.json"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_FORMATION_RUNTIME_FRAMEBURST.txt"
PY="${TMPDIR:-$HOME/.cache}/wfgg-runtime-frameburst-v2.py"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
command -v adb >/dev/null 2>&1 || fail "adb absent"
command -v python >/dev/null 2>&1 || fail "python absent"

SERIAL="$(adb devices 2>/dev/null | awk 'NR>1 && $2=="device" {print $1; exit}')"
[[ -n "$SERIAL" ]] || fail "aucun appareil ADB connecte"
mkdir -p "$OUTDIR" "$(dirname "$REPORT")" "$(dirname "$PY")"
rm -f "$OUTDIR"/frame_*.png "$MANIFEST" 2>/dev/null || true

printf '\n=== CAPTURE FORMATIONBG RUNTIME V2 ===\n'
printf 'Aucune dependance Pillow/numpy. Aucun pixel genere.\n\n'
printf '1) Apres lancement, bascule immediatement dans Last War.\n'
printf '2) Reste sur l ecran MONDE pendant le compte a rebours.\n'
printf '3) A la vibration (ou apres 5 s), ouvre Formation UNE SEULE FOIS.\n'
printf '4) Ne touche plus a rien jusqu a FRAMEBURST_CAPTURED.\n\n'

for n in 5 4 3 2 1; do printf 'Capture dans %s...\n' "$n"; sleep 1; done
if command -v termux-vibrate >/dev/null 2>&1; then termux-vibrate -d 250 >/dev/null 2>&1 || true; fi

printf 'FRAMEBURST_START\n'
# Keep enough frames around the transition. screencap itself is the pacing factor.
for i in $(seq -w 1 36); do
  adb -s "$SERIAL" exec-out screencap -p > "$OUTDIR/frame_${i}.png" 2>/dev/null || true
  sleep 0.06
done
COUNT="$(find "$OUTDIR" -name 'frame_*.png' -size +10k | wc -l | tr -d ' ')"
printf 'FRAMEBURST_CAPTURED count=%s\n' "$COUNT"
[[ "$COUNT" -ge 8 ]] || fail "trop peu de frames natives capturees ($COUNT)"

cat > "$PY" <<'PYEOF'
from pathlib import Path
import json, struct, sys

src=Path(sys.argv[1]); manifest=Path(sys.argv[2]); report=Path(sys.argv[3])
rows=[]
prev=None
for p in sorted(src.glob('frame_*.png')):
    try:
        raw=p.read_bytes()
        if len(raw)<24 or raw[:8] != b'\x89PNG\r\n\x1a\n':
            continue
        w,h=struct.unpack('>II',raw[16:24])
    except Exception:
        continue
    size=len(raw)
    delta=0 if prev is None else size-prev
    rows.append({'file':p.name,'index':len(rows)+1,'bytes':size,'deltaBytes':delta,'width':w,'height':h})
    prev=size
if len(rows)<8:
    raise SystemExit('NO_VALID_PNG_BURST')

# Ranking intentionally uses only container-level facts (PNG size and deltas).
# It does not pretend to know which frame is visually correct; gallery validation is mandatory.
lo=rows[3:max(4,len(rows)-2)]
small=sorted(lo,key=lambda r:r['bytes'])[:6]
trans=sorted(lo,key=lambda r:abs(r['deltaBytes']),reverse=True)[:6]

cand=[]; seen=set()
def add(r,reason):
    if not r or r['file'] in seen:return
    seen.add(r['file']); cand.append({'file':r['file'],'reason':reason})
for r in small:add(r,'petite taille PNG : candidat flou/transition')
for r in trans:
    add(r,'fort delta PNG : bord de transition')
    idx=r['index']-1
    if idx>0:add(rows[idx-1],'voisin avant fort delta')
    if idx+1<len(rows):add(rows[idx+1],'voisin apres fort delta')
cand=cand[:14]

summary={
  'format':'WFGG_LASTWAR_FORMATION_RUNTIME_FRAMEBURST_V2',
  'generatedArtwork':False,
  'networkUsed':False,
  'source':'adb-screencap-native-compositor',
  'selectionMethod':'PNG size/delta only; visual validation required',
  'frameCount':len(rows),
  'width':rows[0]['width'],'height':rows[0]['height'],
  'frames':rows,'candidates':cand,
  'guardrails':{'nativePixelsOnly':True,'noPillow':True,'noNumpy':True,'noInpainting':True,'noGeneratedLandscape':True,'notAutoWiredIntoLayer0':True}
}
manifest.write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n','utf-8')
lines=['WfGg Last War — FORMATION RUNTIME FRAMEBURST V2','',f"frames={len(rows)} size={rows[0]['width']}x{rows[0]['height']}",'','CANDIDATES (validation visuelle requise)']
by={r['file']:r for r in rows}
for i,c in enumerate(cand,1):
    r=by[c['file']]
    lines.append(f"  {i:02d}. {c['file']} bytes={r['bytes']} delta={r['deltaBytes']} reason={c['reason']}")
lines += ['','LAB PREVIEW','  http://127.0.0.1:8877/lab/lastwar-formation-frameburst.html','','NOTE','  Frames = pixels natifs ADB uniquement.','  Aucun candidat n est branche automatiquement dans Layer0.']
report.write_text('\n'.join(lines)+'\n','utf-8')
print('FORMATION_RUNTIME_FRAMEBURST_OK',f"frames={len(rows)}",f"size={rows[0]['width']}x{rows[0]['height']}",f"candidates={len(cand)}")
for i,c in enumerate(cand[:8],1):
    r=by[c['file']]
    print('FORMATION_RUNTIME_CANDIDATE',f"rank={i}",f"file={c['file']}",f"bytes={r['bytes']}",f"delta={r['deltaBytes']}")
print('FORMATION_RUNTIME_MANIFEST',manifest)
print('FORMATION_RUNTIME_REPORT',report)
PYEOF

python "$PY" "$OUTDIR" "$MANIFEST" "$REPORT"
rm -f "$PY"

echo "=== FORMATION RUNTIME FRAMEBURST TERMINE ==="
echo "Rapport : $REPORT"
echo "Preview : http://127.0.0.1:8877/lab/lastwar-formation-frameburst.html"
echo "Frames locales uniquement. main non modifiee."
