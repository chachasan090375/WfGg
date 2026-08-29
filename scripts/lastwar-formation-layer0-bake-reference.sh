#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — fixed Layer 0 baker.
# Uses the supplied/native 1316x1536 Formation capture as the pixel reference,
# removes foreground/UI by deterministic masks, diffuses only the hidden areas,
# and preserves the already-blurred visible world pixels.
# Runtime applies NO blur. Output is a fixed WebP used by every device.

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
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ref=Path(sys.argv[1]); out=Path(sys.argv[2]); meta=Path(sys.argv[3])
im=Image.open(ref).convert('RGB')
if im.size != (1316,1536):
    raise SystemExit(f'expected native 1316x1536 reference, got {im.size[0]}x{im.size[1]}')

W,H=im.size
mask=Image.new('L',(W,H),0)
d=ImageDraw.Draw(mask)

# Foreground masks measured on MASTER_SQUAD_SCREEN_LASTWAR_2026-08-29.
# They deliberately cover the formation platform, units, labels and controls.
# The visible outer world remains untouched and therefore pixel-authentic.
rects=[
    (420,22,892,145),       # power badge
    (84,175,224,340),       # left rank badge
    (0,1015,330,1536),      # drone/chip controls lower-left
    (500,1190,1316,1536),   # team controls lower-right
]
for r in rects:d.rectangle(r,fill=255)

# Main gameplay foreground: hero labels + units + platform + drone + overlord.
main=[
    (0,350),(82,330),(172,360),(255,326),(322,245),(420,175),
    (735,150),(820,120),(1030,130),(1316,145),(1316,930),(1240,930),
    (1160,1010),(1030,1035),(930,1115),(720,1160),(525,1135),(400,1080),
    (260,1070),(120,1010),(0,930)
]
d.polygon(main,fill=255)

# Extra small foreground islands outside the main polygon.
d.ellipse((0,610,180,820),fill=255)       # left rock/gorilla overlap
nd=(1120,865,1316,1110); d.rectangle(nd,fill=255) # right unit/rock overlap

# Feather the mask so preserved world pixels transition cleanly into reconstructed
# hidden regions. Hidden regions are later covered by Layer1/2 in normal use.
feather=mask.filter(ImageFilter.GaussianBlur(18))

# Solve the hidden field at 1/4 resolution with Laplacian diffusion from the
# actual visible world boundary. This does not invent props; it only fills pixels
# that are occluded by foreground in the reference capture.
small=im.resize((W//4,H//4),Image.Resampling.LANCZOS)
smask=mask.resize(small.size,Image.Resampling.NEAREST)
a=np.asarray(small,dtype=np.float32)
m=np.asarray(smask,dtype=np.uint8)>127
known=~m
mean=a[known].mean(axis=0) if known.any() else np.array([128,128,128],dtype=np.float32)
a[m]=mean

for _ in range(420):
    p=np.pad(a,((1,1),(1,1),(0,0)),mode='edge')
    avg=(p[:-2,1:-1]+p[2:,1:-1]+p[1:-1,:-2]+p[1:-1,2:])*0.25
    a[m]=avg[m]

fill=Image.fromarray(np.clip(a,0,255).astype(np.uint8),'RGB').resize((W,H),Image.Resampling.BICUBIC)
# A modest smoothing is used only on reconstructed hidden pixels. The native
# visible world already contains the game's blur and is never blurred again.
fill=fill.filter(ImageFilter.GaussianBlur(6))
result=Image.composite(fill,im,feather)

out.parent.mkdir(parents=True,exist_ok=True)
result.save(out,'WEBP',quality=96,method=6)

def sha256(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
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
  'hiddenPixelsMethod':'laplacian diffusion from visible world boundary',
  'runtimeDynamicBlur':False,
  'measuredNativeGaussianSigmaPx':11.8,
  'important':'11.8 px documents the blur already present in the native capture; it is NOT applied again during this bake',
  'masterSize':[1316,1536],
  'runtimeFit':'cover',
  'runtimePosition':'center',
  'generatedSubstituteProps':False,
  'mainUntouched':True
}
meta.write_text(json.dumps(info,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('LAYER0_BAKE_OK',out)
print('LAYER0_SHA256',info['sha256'])
print('LAYER0_BYTES',info['outputBytes'])
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
echo "main non modifiee."
