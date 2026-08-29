#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — native FormationBg transition capture V4.
# Robust path: screencap writes complete PNG files on Android first, then adb pull.
# This avoids truncation/stream corruption from `adb exec-out screencap -p` over wireless ADB.
# No Pillow/numpy. No Termux:API. No generated/altered pixels.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
OUTDIR="$ROOT/frontend/lab/local_assets/lastwar-formation-runtime-frameburst-v2"
MANIFEST="$OUTDIR/manifest.json"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_FORMATION_RUNTIME_FRAMEBURST.txt"
PY="${TMPDIR:-$HOME/.cache}/wfgg-runtime-frameburst-v4.py"
REMOTE="/sdcard/Download/WFGG_formation_frameburst_v4"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
command -v adb >/dev/null 2>&1 || fail "adb absent"
command -v python >/dev/null 2>&1 || fail "python absent"

SERIAL="$(adb devices 2>/dev/null | awk 'NR>1 && $2=="device" {print $1; exit}')"
[[ -n "$SERIAL" ]] || fail "aucun appareil ADB connecte"
adb -s "$SERIAL" shell 'printf ADB_OK' >/dev/null 2>&1 || fail "ADB ne repond pas"

mkdir -p "$OUTDIR" "$(dirname "$REPORT")" "$(dirname "$PY")"
rm -f "$OUTDIR"/frame_*.png "$MANIFEST" 2>/dev/null || true
adb -s "$SERIAL" shell "rm -rf '$REMOTE'; mkdir -p '$REMOTE'" >/dev/null 2>&1 || fail "impossible de preparer le dossier distant"

printf '\n=== CAPTURE FORMATIONBG RUNTIME V4 ===\n'
printf 'Mode robuste : PNG ecrits sur Android puis rapatries par ADB.\n'
printf 'Aucun Pillow/numpy. Aucun Termux:API. Aucun pixel genere.\n\n'
printf '1) Lance le script puis bascule IMMEDIATEMENT dans Last War.\n'
printf '2) Reste sur l ecran MONDE environ 4 secondes.\n'
printf '3) Quand environ 4 secondes se sont ecoulees, ouvre Formation UNE SEULE FOIS.\n'
printf '4) Ne touche plus a rien pendant environ 12 secondes.\n\n'

printf 'PREBURST dans 3...\n'; sleep 1
printf 'PREBURST dans 2...\n'; sleep 1
printf 'PREBURST dans 1...\n'; sleep 1
printf 'FRAMEBURST_START — ouvre Formation dans environ 2 secondes\n'

# Capture on-device. Each PNG is finalized by Android before the next frame starts.
# 48 frames cover both sides of the transition. The adb shell session remains a
# single connection, avoiding one wireless round-trip per PNG transfer.
adb -s "$SERIAL" shell "
  i=1
  while [ \$i -le 48 ]; do
    n=\$(printf '%02d' \$i)
    screencap -p '$REMOTE/frame_'\${n}'.png' >/dev/null 2>&1
    if [ \$((i % 6)) -eq 0 ]; then echo FRAMEBURST_REMOTE_PROGRESS \$n/48; fi
    sleep 0.08
    i=\$((i+1))
  done
" || fail "capture distante interrompue"

printf 'FRAMEBURST_REMOTE_DONE\n'
printf 'Rapatriement des PNG...\n'
adb -s "$SERIAL" pull "$REMOTE/." "$OUTDIR/" >/dev/null 2>&1 || fail "adb pull des frames a echoue"
adb -s "$SERIAL" shell "rm -rf '$REMOTE'" >/dev/null 2>&1 || true

COUNT="$(find "$OUTDIR" -name 'frame_*.png' -size +10k | wc -l | tr -d ' ')"
printf 'FRAMEBURST_CAPTURED count=%s\n' "$COUNT"
[[ "$COUNT" -ge 8 ]] || fail "trop peu de frames natives capturees ($COUNT)"

cat > "$PY" <<'PYEOF'
from pathlib import Path
import json, struct, sys

src=Path(sys.argv[1]); manifest=Path(sys.argv[2]); report=Path(sys.argv[3])
rows=[]
rejected=[]
prev=None
for p in sorted(src.glob('frame_*.png')):
    try:
        raw=p.read_bytes()
        # Require a canonical PNG signature, IHDR dimensions and a finalized IEND chunk.
        if len(raw)<33 or raw[:8] != b'\x89PNG\r\n\x1a\n':
            rejected.append((p.name,'bad-signature'))
            continue
        if raw[12:16] != b'IHDR':
            rejected.append((p.name,'missing-IHDR'))
            continue
        if b'IEND' not in raw[-32:]:
            rejected.append((p.name,'missing-IEND'))
            continue
        w,h=struct.unpack('>II',raw[16:24])
        if not (200 <= w <= 5000 and 200 <= h <= 5000):
            rejected.append((p.name,'bad-dimensions'))
            continue
    except Exception as e:
        rejected.append((p.name,'read-error'))
        continue
    size=len(raw)
    delta=0 if prev is None else size-prev
    rows.append({'file':p.name,'index':len(rows)+1,'bytes':size,'deltaBytes':delta,'width':w,'height':h})
    prev=size

print('PNG_VALIDATION',f'valid={len(rows)}',f'rejected={len(rejected)}')
for name,why in rejected[:8]:
    print('PNG_REJECTED',name,why)
if len(rows)<8:
    raise SystemExit('NO_VALID_PNG_BURST')

# Container-only ranking. This does not claim which frame is visually correct.
lo=rows[2:max(3,len(rows)-1)]
small=sorted(lo,key=lambda r:r['bytes'])[:7]
trans=sorted(lo,key=lambda r:abs(r['deltaBytes']),reverse=True)[:7]

cand=[]; seen=set()
def add(r,reason):
    if not r or r['file'] in seen:return
    seen.add(r['file']); cand.append({'file':r['file'],'reason':reason})
for r in trans:
    idx=r['index']-1
    if idx>0:add(rows[idx-1],'voisin avant fort delta')
    add(r,'fort delta PNG : bord de transition')
    if idx+1<len(rows):add(rows[idx+1],'voisin apres fort delta')
for r in small:add(r,'petite taille PNG : candidat flou/transition')
cand=cand[:18]

summary={
  'format':'WFGG_LASTWAR_FORMATION_RUNTIME_FRAMEBURST_V4',
  'generatedArtwork':False,
  'networkUsed':False,
  'source':'adb-shell-screencap-to-android-files-then-pull',
  'selectionMethod':'PNG size/delta only; visual validation required',
  'frameCount':len(rows),
  'rejectedCount':len(rejected),
  'width':rows[0]['width'],'height':rows[0]['height'],
  'frames':rows,'candidates':cand,
  'guardrails':{'nativePixelsOnly':True,'completePngRequired':True,'noPillow':True,'noNumpy':True,'noTermuxApi':True,'noInpainting':True,'noGeneratedLandscape':True,'notAutoWiredIntoLayer0':True}
}
manifest.write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n','utf-8')
lines=['WfGg Last War — FORMATION RUNTIME FRAMEBURST V4','',f"frames={len(rows)} rejected={len(rejected)} size={rows[0]['width']}x{rows[0]['height']}",'','CANDIDATES (validation visuelle requise)']
by={r['file']:r for r in rows}
for i,c in enumerate(cand,1):
    r=by[c['file']]
    lines.append(f"  {i:02d}. {c['file']} bytes={r['bytes']} delta={r['deltaBytes']} reason={c['reason']}")
lines += ['','LAB PREVIEW','  http://127.0.0.1:8877/lab/lastwar-formation-frameburst.html','','NOTE','  Frames = pixels natifs ADB uniquement.','  Aucun candidat n est branche automatiquement dans Layer0.']
report.write_text('\n'.join(lines)+'\n','utf-8')
print('FORMATION_RUNTIME_FRAMEBURST_OK',f"frames={len(rows)}",f"rejected={len(rejected)}",f"size={rows[0]['width']}x{rows[0]['height']}",f"candidates={len(cand)}")
for i,c in enumerate(cand[:10],1):
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
