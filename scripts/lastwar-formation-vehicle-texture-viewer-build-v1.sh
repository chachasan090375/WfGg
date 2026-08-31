#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail
ROOT="${HOME}/wfgg-lastwar-preview"
LAB="$ROOT/frontend/lab"
OUT="$LAB/master-assets-v2/formation-vehicle-texture-viewer-data"
mkdir -p "$OUT"
python - "$LAB" "$OUT" <<'PY'
import json, os, sys
from pathlib import Path
lab=Path(sys.argv[1]); out=Path(sys.argv[2])
roots=[
 lab/'formation-texture-review',
 lab/'formation-texture-review-v2',
 lab/'formation-bridge-bundle-viewer-data',
 lab/'bundle-reconstruction-data',
 lab/'master-assets-v2',
]
img_ext={'.png','.jpg','.jpeg','.webp'}
items=[]; seen=set()
for root in roots:
    if not root.exists(): continue
    for p in root.rglob('*'):
        if not p.is_file() or p.suffix.lower() not in img_ext: continue
        # avoid recursively indexing the output viewer itself
        try:
            p.relative_to(out)
            continue
        except Exception:
            pass
        rel=p.relative_to(lab).as_posix()
        if rel in seen: continue
        seen.add(rel)
        name=p.stem
        low=(name+' '+rel).lower()
        # Keep broad corpus but score likely formation/vehicle images first.
        score=0
        for kw,w in [('formation',6),('hero',5),('vehicle',6),('tank',6),('aircraft',6),('missile',6),('car',4),('audie',8),('murphy',8),('slot',3),('unit',2),('texture',1),('sprite',2),('atlas',2)]:
            if kw in low: score+=w
        w=h=None
        try:
            from PIL import Image
            with Image.open(p) as im: w,h=im.size
        except Exception: pass
        bundle=None; role=None
        # Pull bundle ids/roles heuristically from path segments produced by earlier viewers.
        import re
        m=re.search(r'(?<!\d)(\d{4,6})(?!\d)', rel)
        if m: bundle=m.group(1)
        if 'murphy' in low: role='Murphy'
        elif 'formation' in low: role='Formation'
        elif 'background' in low: role='Background'
        typ='Texture2D'
        if 'spriteatlas' in low or 'sprite-atlas' in low: typ='SpriteAtlas'
        elif 'sprite' in low: typ='Sprite'
        items.append({'name':name,'type':typ,'width':w,'height':h,'bundleId':bundle,'bundleRole':role,'source':rel,'path':rel,'url':'./'+rel,'score':score})
items.sort(key=lambda x:(-x['score'],-((x['width'] or 0)*(x['height'] or 0)),x['name'].lower()))
out.joinpath('manifest.json').write_text(json.dumps({'generatedBy':'lastwar-formation-vehicle-texture-viewer-build-v1','count':len(items),'items':items},ensure_ascii=False,indent=2),encoding='utf-8')
print(f'FORMATION_VEHICLE_TEXTURE_VIEWER_V1_READY images={len(items)}')
print('MANIFEST='+str(out/'manifest.json'))
PY
printf 'VIEWER=http://127.0.0.1:8788/lab/lastwar-formation-vehicle-texture-viewer.html?v=1\n'
