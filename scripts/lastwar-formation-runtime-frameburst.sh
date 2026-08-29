#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — native FormationBg transition capture V3.
# Dependency-free, no Termux:API call, and each ADB screencap is timeout-guarded.
# Captures native compositor pixels only. No generated/altered artwork.

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
command -v timeout >/dev/null 2>&1 || fail "timeout absent"

SERIAL="$(adb devices 2>/dev/null | awk 'NR>1 && $2=="device" {print $1; exit}')"
[[ -n "$SERIAL" ]] || fail "aucun appareil ADB connecte"
timeout 3 adb -s "$SERIAL" shell 'printf ADB_OK' >/dev/null 2>&1 || fail "ADB ne repond pas"

mkdir -p "$OUTDIR" "$(dirname "$REPORT")" "$(dirname "$PY")"
rm -f "$OUTDIR"/frame_*.png "$MANIFEST" 2>/dev/null || true

printf '\n=== CAPTURE FORMATIONBG RUNTIME V3 ===\n'
printf 'Aucun Pillow/numpy. Aucun Termux:API. Aucun pixel genere.\n\n'
printf '1) Lance le script puis bascule IMMEDIATEMENT dans Last War.\n'
printf '2) Reste sur l ecran MONDE environ 5 secondes.\n'
printf '3) Puis ouvre Formation UNE SEULE FOIS.\n'
printf '4) Ne touche plus a rien pendant environ 12 secondes.\n'
printf 'Le burst commence AVANT l ouverture et continue APRES : pas besoin de vibration.\n\n'

# Start capturing before the expected user tap. This removes any dependency on a
# vibration/notification signal and guarantees pre-transition reference frames.
printf 'PREBURST dans 3...\n'; sleep 1
printf 'PREBURST dans 2...\n'; sleep 1
printf 'PREBURST dans 1...\n'; sleep 1
printf 'FRAMEBURST_START — ouvre Formation dans environ 2 secondes\n'

# 48 native frames. Each capture is individually guarded so one stalled ADB
# request cannot freeze the whole script. The user can open Formation around
# frames 6-12; the burst spans both sides of the transition.
for i in $(seq -w 1 48); do
  TMP="$OUTDIR/.frame_${i}.tmp"
  OUT="$OUTDIR/frame_${i}.png"
  rm -f "$TMP" "$OUT" 2>/dev/null || true
  if timeout 2 adb -s "$SERIAL" exec-out screencap -p > "$TMP" 2>/dev/null; then
    if [[ -s "$TMP" ]]; then mv -f "$TMP" "$OUT"; else rm -f "$TMP"; fi
  else
    rm -f "$TMP"
    printf 'FRAME_TIMEOUT %s\n' "$i"
  fi
  # Progress every 6 frames so it is obvious that the process is alive.
  N=$((10#$i))
  if (( N % 6 == 0 )); then printf 'FRAMEBURST_PROGRESS %02d/48\n' "$N"; fi
  sleep 0.05
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

# Container-only ranking. It never asserts visual correctness.
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
  'format':'WFGG_LASTWAR_FORMATION_RUNTIME_FRAMEBURST_V3',
  'generatedArtwork':False,
  'networkUsed':False,
  'source':'adb-screencap-native-compositor',
  'selectionMethod':'PNG size/delta only; visual validation required',
  'frameCount':len(rows),
  'width':rows[0]['width'],'height':rows[0]['height'],
  'frames':rows,'candidates':cand,
  'guardrails':{'nativePixelsOnly':True,'noPillow':True,'noNumpy':True,'noTermuxApi':True,'adbCaptureTimeoutSeconds':2,'noInpainting':True,'noGeneratedLandscape':True,'notAutoWiredIntoLayer0':True}
}
manifest.write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n','utf-8')
lines=['WfGg Last War — FORMATION RUNTIME FRAMEBURST V3','',f"frames={len(rows)} size={rows[0]['width']}x{rows[0]['height']}",'','CANDIDATES (validation visuelle requise)']
by={r['file']:r for r in rows}
for i,c in enumerate(cand,1):
    r=by[c['file']]
    lines.append(f"  {i:02d}. {c['file']} bytes={r['bytes']} delta={r['deltaBytes']} reason={c['reason']}")
lines += ['','LAB PREVIEW','  http://127.0.0.1:8877/lab/lastwar-formation-frameburst.html','','NOTE','  Frames = pixels natifs ADB uniquement.','  Aucun candidat n est branche automatiquement dans Layer0.']
report.write_text('\n'.join(lines)+'\n','utf-8')
print('FORMATION_RUNTIME_FRAMEBURST_OK',f"frames={len(rows)}",f"size={rows[0]['width']}x{rows[0]['height']}",f"candidates={len(cand)}")
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
