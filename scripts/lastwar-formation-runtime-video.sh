#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — capture vidéo native continue de la transition Formation.
# Aucun Pillow/numpy/ffmpeg. Aucun pixel généré. main non modifiée.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
OUTDIR="$ROOT/frontend/lab/local_assets/lastwar-formation-runtime-video-v1"
OUT="$OUTDIR/formation-transition-v1.mp4"
META="$OUTDIR/manifest.json"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_FORMATION_RUNTIME_VIDEO.txt"
REMOTE="/sdcard/Download/WFGG_formation_transition_v1.mp4"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
command -v adb >/dev/null 2>&1 || fail "adb absent"
command -v python >/dev/null 2>&1 || fail "python absent"
SERIAL="$(adb devices 2>/dev/null | awk 'NR>1 && $2=="device" {print $1; exit}')"
[[ -n "$SERIAL" ]] || fail "aucun appareil ADB connecte"
adb -s "$SERIAL" shell 'command -v screenrecord >/dev/null 2>&1' || fail "screenrecord Android absent"
mkdir -p "$OUTDIR" "$(dirname "$REPORT")"
rm -f "$OUT" "$META" 2>/dev/null || true
adb -s "$SERIAL" shell "rm -f '$REMOTE'" >/dev/null 2>&1 || true

printf '\n=== CAPTURE VIDEO NATIVE FORMATION ===\n'
printf 'Aucun ffmpeg/Pillow/numpy. Aucun pixel genere.\n\n'
printf '1) Lance le script puis bascule IMMEDIATEMENT dans Last War.\n'
printf '2) Reste environ 4 secondes sur l ecran MONDE.\n'
printf '3) Ouvre Formation UNE SEULE FOIS.\n'
printf '4) Ne touche plus a rien jusqu au retour Termux.\n\n'
printf 'VIDEO_RECORD_START — bascule maintenant dans Last War\n'

# Enregistrement continu natif Android. Le shell reste bloqué pendant la capture,
# ce qui est voulu : il n y a aucun trou de sampling entre les frames.
adb -s "$SERIAL" shell "screenrecord --time-limit 16 --bit-rate 12000000 '$REMOTE'" >/dev/null 2>&1 || true

printf 'VIDEO_RECORD_DONE\n'
adb -s "$SERIAL" shell "test -s '$REMOTE'" >/dev/null 2>&1 || fail "video distante absente ou vide"
printf 'Rapatriement video...\n'
adb -s "$SERIAL" pull "$REMOTE" "$OUT" >/dev/null 2>&1 || fail "adb pull video a echoue"
adb -s "$SERIAL" shell "rm -f '$REMOTE'" >/dev/null 2>&1 || true
[[ -s "$OUT" ]] || fail "video locale vide"

BYTES="$(wc -c < "$OUT" | tr -d ' ')"
python - "$OUT" "$META" "$REPORT" "$BYTES" <<'PY'
from pathlib import Path
import json, sys
video=Path(sys.argv[1]); meta=Path(sys.argv[2]); report=Path(sys.argv[3]); size=int(sys.argv[4])
summary={
  'format':'WFGG_LASTWAR_FORMATION_RUNTIME_VIDEO_V1',
  'generatedArtwork':False,
  'networkUsed':False,
  'source':'android-screenrecord-native-compositor',
  'video':video.name,
  'bytes':size,
  'durationTargetSeconds':16,
  'guardrails':{'nativePixelsOnly':True,'noFfmpeg':True,'noPillow':True,'noNumpy':True,'noInpainting':True,'notAutoWiredIntoLayer0':True}
}
meta.write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n','utf-8')
report.write_text('\n'.join([
'WfGg Last War — FORMATION RUNTIME VIDEO V1','',
f'video={video}',f'bytes={size}','duration_target=16s','',
'LAB PREVIEW','  http://127.0.0.1:8877/lab/lastwar-formation-transition-video.html','',
'NOTE','  Video native Android screenrecord uniquement.','  Analyse visuelle et pixel-delta dans le navigateur.','  Aucun frame n est automatiquement branche dans Layer0.'
])+'\n','utf-8')
print('FORMATION_RUNTIME_VIDEO_OK',f'bytes={size}',f'video={video}')
print('FORMATION_RUNTIME_VIDEO_META',meta)
print('FORMATION_RUNTIME_VIDEO_REPORT',report)
PY

echo "=== FORMATION RUNTIME VIDEO TERMINEE ==="
echo "Preview : http://127.0.0.1:8877/lab/lastwar-formation-transition-video.html"
echo "Rapport : $REPORT"
echo "main non modifiee."
