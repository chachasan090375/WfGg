#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — fixed Layer 0 baker.
# Uses the supplied/native 1316x1536 Formation capture as the pixel reference,
# removes foreground/UI by deterministic masks, diffuses only the hidden areas,
# and preserves the already-blurred visible world pixels.
# Runtime applies NO blur. Output is a fixed WebP used by every device.
# Pillow-only: no NumPy dependency, Android/Termux safe.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
OUTDIR="$ROOT/frontend/lab/master-assets-v2/background"
OUT="$OUTDIR/formation-layer0-world-baked.webp"
META="$ROOT/frontend/lab/master-assets-v2/meta/formation-layer0-baked-v1.json"
REF="${1:-}"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
command -v python >/dev/null 2>&1 || fail "python absent"

if [[ -z "$REF" ]]; then
  for p in \
    "$HOME/storage/pictures/Screenshots/Screenshot_20260829_171043_Last War.jpg" \
    "$HOME/storage/dcim/Screenshots/Screenshot_20260829_171043_Last War.jpg" \
    "$HOME/storage/downloads/Screenshot_20260829_171043_Last War.jpg"
  do
    [[ -f "$p" ]] && REF="$p" && break
  done
fi

if [[ -z "$REF" ]]; then
  REF="$(find "$HOME/storage" -type f \( -iname '*20260829*171043*Last*War*.jpg' -o -iname '*171043*Last*War*.jpg' \) 2>/dev/null | head -n 1 || true)"
fi
[[ -n "$REF" && -f "$REF" ]] || fail "capture native introuvable; passe son chemin en argument"

mkdir -p "$OUTDIR" "$(dirname "$META")"

python - "$REF" "$OUT" "$META" <<'PY'
from pathlib import Path
import hashlib, json, sys
from PIL import Image, ImageDraw, ImageFilter, ImageOps, ImageStat

ref=Path(sys.argv[1]); out=Path(sys.argv[2]); meta=Path(sys.argv[3])
im=Image.open(ref).convert('RGB')
if im.size != (1316,1536):
    raise SystemExit(f'expected native 1316x1536 reference, got {im.size[0]}x{im.size[1]}')

W,H=im.size
mask=Image.new('L',(W,H),0)
d=ImageDraw.Draw(mask)

# Foreground masks measured on the native Formation reference.
# They cover platform, units, labels and controls. Visible outer-world pixels
# remain untouched and therefore preserve the game's already-rendered blur.
rects=[
    (420,22,892,145),       # power badge
    (84,175,224,340),       # left rank badge
    (0,1015,330,1536),      # lower-left controls
    (500,1190,1316,1536),   # lower-right team controls
]
for r in rects:
    d.rectangle(r,fill=255)

main=[
    (0,350),(82,330),(172,360),(255,326),(322,245),(420,175),
    (735,150),(820,120),(1030,130),(1316,145),(1316,930),(1240,930),
    (1160,1010),(1030,1035),(930,1115),(720,1160),(525,1135),(400,1080),
    (260,1070),(120,1010),(0,930)
]
d.polygon(main,fill=255)
d.ellipse((0,610,180,820),fill=255)
d.rectangle((1120,865,1316,1110),fill=255)

# Feather only the foreground boundary. Visible world remains the source image.
feather=mask.filter(ImageFilter.GaussianBlur(18))

# Pillow-only harmonic-style diffusion at quarter resolution.
# Known/world pixels are restored after every blur pass; only hidden pixels are
# allowed to evolve. This is the same boundary-condition principle as the old
# NumPy Laplacian loop, without requiring NumPy on Android.
SW,SH=W//4,H//4
small=im.resize((SW,SH),Image.Resampling.LANCZOS)
smask=mask.resize((SW,SH),Image.Resampling.NEAREST)
known_mask=ImageOps.invert(smask)

stats=ImageStat.Stat(small,known_mask)
mean=tuple(max(0,min(255,round(v))) for v in stats.mean[:3])
fill_small=Image.new('RGB',(SW,SH),mean)
fill_small=Image.composite(small,fill_small,known_mask)

# Multi-scale diffusion converges quickly on this deliberately blurred layer.
# Large radii propagate the boundary field inward; smaller radii settle edges.
for radius,passes in ((18,14),(11,18),(7,24),(4,28),(2,32)):
    for _ in range(passes):
        blurred=fill_small.filter(ImageFilter.GaussianBlur(radius))
        fill_small=Image.composite(small,blurred,known_mask)

fill=fill_small.resize((W,H),Image.Resampling.BICUBIC)
fill=fill.filter(ImageFilter.GaussianBlur(6))
result=Image.composite(fill,im,feather)

out.parent.mkdir(parents=True,exist_ok=True)
result.save(out,'WEBP',quality=96,method=6)

def sha256(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):
            h.update(b)
    return h.hexdigest()

info={
  'format':'WFGG_LASTWAR_FORMATION_LAYER0_BAKED_V1',
  'sourceCapture':ref.name,
  'sourceSize':[W,H],
  'output':'master-assets-v2/background/formation-layer0-world-baked.webp',
  'outputBytes':out.stat().st_size,
  'sha256':sha256(out),
  'visibleWorldPixelsPreserved':True,
  'foregroundRemovedByDeterministicMask':True,
  'hiddenPixelsMethod':'Pillow multiscale boundary diffusion; known world pixels fixed each pass',
  'runtimeDynamicBlur':False,
  'measuredNativeGaussianSigmaPx':11.8,
  'important':'11.8 px documents the blur already present in the native capture; it is NOT applied again during this bake',
  'masterSize':[1316,1536],
  'runtimeFit':'cover',
  'runtimePosition':'center',
  'numpyRequired':False,
  'generatedSubstituteProps':False,
  'mainUntouched':True
}
meta.write_text(json.dumps(info,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('LAYER0_BAKE_OK',out)
print('LAYER0_SHA256',info['sha256'])
print('LAYER0_BYTES',info['outputBytes'])
print('LAYER0_NUMPY_REQUIRED false')
PY

git add "$OUT" "$META"
if ! git diff --cached --quiet; then
  git commit -m "lab: bake fixed native Formation world background"
  git push origin "$BRANCH"
fi

echo "=== LAYER0 BAKE TERMINE ==="
echo "Source : $REF"
echo "Sortie : $OUT"
echo "Runtime blur : AUCUN"
echo "NumPy : NON REQUIS"
echo "main non modifiee."
