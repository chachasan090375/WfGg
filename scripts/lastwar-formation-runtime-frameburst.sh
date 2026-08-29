#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — native FormationBg transition capture.
# Captures the REAL screen compositor during Formation opening and keeps the
# lowest-detail non-black frame as a candidate for the native blurred Layer0.
# No generated artwork. No Last War network. main untouched.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
OUTDIR="$ROOT/frontend/lab/local_assets/lastwar-formation-runtime-frameburst-v1"
FINAL="$ROOT/frontend/lab/master-assets-v2/background/formation-layer0-runtime-frame-v1.png"
META="$ROOT/frontend/lab/master-assets-v2/meta/formation-layer0-runtime-frame-v1.json"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_FORMATION_RUNTIME_FRAMEBURST.txt"
PY="${TMPDIR:-$HOME/.cache}/wfgg-runtime-frameburst.py"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
command -v adb >/dev/null 2>&1 || fail "adb absent"
command -v python >/dev/null 2>&1 || fail "python absent"
python - <<'PY' >/dev/null 2>&1 || fail "Pillow/numpy absents"
from PIL import Image
import numpy
PY

SERIAL="$(adb devices 2>/dev/null | awk 'NR>1 && $2=="device" {print $1; exit}')"
[[ -n "$SERIAL" ]] || fail "aucun appareil ADB connecte"
mkdir -p "$OUTDIR" "$(dirname "$FINAL")" "$(dirname "$META")" "$(dirname "$REPORT")" "$(dirname "$PY")"
rm -f "$OUTDIR"/frame_*.png "$FINAL" 2>/dev/null || true

printf '\n=== CAPTURE FORMATIONBG RUNTIME ===\n'
printf '1) Lance ce script puis bascule immediatement dans Last War.\n'
printf '2) Reste sur l ecran MONDE pendant quelques secondes.\n'
printf '3) A la vibration (ou environ 5 s), ouvre Formation UNE SEULE FOIS.\n'
printf '4) Ne touche plus a rien pendant environ 10 secondes.\n\n'

for n in 5 4 3 2 1; do printf 'Capture dans %s...\n' "$n"; sleep 1; done
if command -v termux-vibrate >/dev/null 2>&1; then termux-vibrate -d 250 >/dev/null 2>&1 || true; fi

printf 'FRAMEBURST_START\n'
# 36 real compositor captures. screencap cadence varies by device; this gives
# roughly 8-12 seconds on a modern Android phone.
for i in $(seq -w 1 36); do
  adb -s "$SERIAL" exec-out screencap -p > "$OUTDIR/frame_${i}.png" 2>/dev/null || true
  sleep 0.08
 done
printf 'FRAMEBURST_CAPTURED count=%s\n' "$(find "$OUTDIR" -name 'frame_*.png' -size +10k | wc -l)"

cat > "$PY" <<'PYEOF'
from pathlib import Path
from PIL import Image
import numpy as np, json, hashlib, shutil, sys, statistics

src=Path(sys.argv[1]); final=Path(sys.argv[2]); meta=Path(sys.argv[3]); report=Path(sys.argv[4])
rows=[]
for p in sorted(src.glob('frame_*.png')):
    try:
        im=Image.open(p).convert('RGB'); a=np.asarray(im,dtype=np.float32)
    except Exception:
        continue
    h,w=a.shape[:2]
    # Score the Formation-relevant central/top viewport and avoid Android nav area.
    y0=max(0,int(h*0.035)); y1=max(y0+20,int(h*0.78)); x0=int(w*0.025); x1=int(w*0.975)
    c=a[y0:y1,x0:x1]
    gray=0.2126*c[:,:,0]+0.7152*c[:,:,1]+0.0722*c[:,:,2]
    mean=float(gray.mean()); std=float(gray.std())
    gx=np.abs(np.diff(gray,axis=1)).mean(); gy=np.abs(np.diff(gray,axis=0)).mean(); edge=float((gx+gy)/2)
    # Strong edges/text/vehicles increase p95 gradient; blurred world stays low.
    dx=np.abs(np.diff(gray,axis=1)).ravel(); dy=np.abs(np.diff(gray,axis=0)).ravel()
    p95=float(np.percentile(np.concatenate([dx,dy]),95))
    # Reject black/white transition frames and near-static single-color frames.
    valid=(28.0 <= mean <= 225.0 and std >= 8.0)
    # Prefer blur: low edge/p95, while retaining enough tonal variance for rocks/shadows.
    score=(edge*1.0 + p95*0.34) - min(std,55.0)*0.055
    rows.append({'file':p.name,'width':w,'height':h,'mean':mean,'std':std,'edge':edge,'p95':p95,'score':score,'valid':valid})

valid=[r for r in rows if r['valid']]
if not valid:
    raise SystemExit('NO_VALID_RUNTIME_FRAMES')
valid.sort(key=lambda r:r['score'])
sel=valid[0]; chosen=src/sel['file']; shutil.copyfile(chosen,final)
sha=hashlib.sha256(final.read_bytes()).hexdigest()
summary={
  'format':'WFGG_LASTWAR_FORMATION_RUNTIME_FRAME_V1',
  'generatedArtwork':False,'networkUsed':False,'source':'adb-screencap-transition',
  'selection':'lowest high-frequency detail among valid transition frames',
  'selected':sel,'sha256':sha,'candidateTop5':valid[:5],
  'allFrameCount':len(rows),
  'guardrails':{'nativePixelsOnly':True,'noInpainting':True,'noGeneratedLandscape':True,'previewNotYetMutated':True}
}
meta.write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n','utf-8')
lines=['WfGg Last War — FORMATION RUNTIME FRAMEBURST','',f"frames={len(rows)} selected={sel['file']} size={sel['width']}x{sel['height']}",f"sha256={sha}",'','TOP 5 LOW-DETAIL TRANSITION FRAMES']
for r in valid[:5]:
    lines.append(f"  {r['file']} score={r['score']:.4f} mean={r['mean']:.2f} std={r['std']:.2f} edge={r['edge']:.4f} p95={r['p95']:.2f}")
lines += ['','NOTE','  Selected frame is native ADB screencap only. No generated pixels or inpainting.','  It must be visually validated before wiring it into Layer0.']
report.write_text('\n'.join(lines)+'\n','utf-8')
print('FORMATION_RUNTIME_FRAMEBURST_OK',f"frames={len(rows)}",f"selected={sel['file']}",f"score={sel['score']:.4f}",f"size={sel['width']}x{sel['height']}")
print('FORMATION_RUNTIME_FRAME',final)
print('FORMATION_RUNTIME_META',meta)
print('FORMATION_RUNTIME_REPORT',report)
PYEOF

python "$PY" "$OUTDIR" "$FINAL" "$META" "$REPORT"
rm -f "$PY"
# Raw burst frames stay local/ignored. Only the selected native frame + metadata are recorded.
git add scripts/lastwar-formation-runtime-frameburst.sh "$FINAL" "$META"
if ! git diff --cached --quiet; then
  git commit -m "lab: record native Formation background transition frame"
  git push origin "$BRANCH"
fi

echo "=== FORMATION RUNTIME FRAMEBURST TERMINE ==="
echo "Rapport : $REPORT"
echo "Frame native : $FINAL"
echo "Preview pas encore modifiee. main non modifiee."
