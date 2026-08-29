#!/usr/bin/env python3
from pathlib import Path
import json, sys
from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / 'frontend/lab/master-assets-v2/meta/formation-layer0-contract-v1.json'

if len(sys.argv) < 2:
    raise SystemExit('usage: lastwar-formation-layer0-bake.py <layer0-unblurred.png> [output.webp]')

src = Path(sys.argv[1]).expanduser().resolve()
if not src.is_file():
    raise SystemExit(f'source absent: {src}')

cfg = json.loads(CONTRACT.read_text(encoding='utf-8'))['bake']
w = int(cfg['masterWidth'])
h = int(cfg['masterHeight'])
sigma = float(cfg['gaussianSigmaPx'])
out = Path(sys.argv[2]).expanduser().resolve() if len(sys.argv) > 2 else ROOT / 'frontend/lab/master-assets-v2/background/formation-layer0-world-baked.webp'
out.parent.mkdir(parents=True, exist_ok=True)

im = Image.open(src).convert('RGB')
# Fixed master canvas. The source is cropped like CSS object-fit:cover, but all
# blur work happens here once; runtime never recomputes the blur.
scale = max(w / im.width, h / im.height)
rw = max(w, round(im.width * scale))
rh = max(h, round(im.height * scale))
im = im.resize((rw, rh), Image.Resampling.LANCZOS)
left = (rw - w) // 2
top = (rh - h) // 2
im = im.crop((left, top, left + w, top + h))
im = im.filter(ImageFilter.GaussianBlur(radius=sigma))
im.save(out, 'WEBP', quality=92, method=6)
print(f'LAYER0_BAKE_OK {out} {w}x{h} sigma={sigma}')
