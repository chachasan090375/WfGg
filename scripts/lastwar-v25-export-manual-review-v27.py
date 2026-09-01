#!/usr/bin/env python3
import json, sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
SRC = ROOT / 'frontend/lab/asset-name-derived-vehicles-v25/manifest.json'
OUT = ROOT / 'frontend/lab/manual-review-v27/inbox'
OUT.mkdir(parents=True, exist_ok=True)

if not SRC.exists():
    raise SystemExit(f'V25 manifest absent: {SRC}')

data = json.loads(SRC.read_text(encoding='utf-8'))
rows = [x for x in data.get('selected', []) if x.get('scope') == 'derived-outside']

# Keep every candidate exactly as V25 produced it. No filtering here.
compact = []
for i, x in enumerate(rows, 1):
    compact.append({
        'id': i,
        'assetPath': (x.get('examples') or [''])[0],
        'parent': x.get('parent',''),
        'name': x.get('pattern',''),
        'ext': x.get('ext',''),
        'logicalName': (x.get('logicalNames') or [''])[0],
        'aliasName': x.get('aliasName',''),
        'bundleId': x.get('bundleId',''),
        'declaredBytes': x.get('declaredBytes',''),
        'dependencies': x.get('dependencies',''),
        'evidenceFiles': x.get('evidenceFiles') or [],
    })

CHUNK = 250
chunks=[]
for n, start in enumerate(range(0, len(compact), CHUNK), 1):
    part=compact[start:start+CHUNK]
    fn=f'chunk-{n:03d}.json'
    (OUT/fn).write_text(json.dumps(part,ensure_ascii=False,indent=2),encoding='utf-8')
    chunks.append({'file':fn,'firstId':part[0]['id'],'lastId':part[-1]['id'],'count':len(part)})

idx={'version':27,'source':'V25 derived-outside','count':len(compact),'chunkSize':CHUNK,'chunks':chunks,'rule':'NO FILTERING DURING EXPORT — manual semantic review only'}
(OUT/'index.json').write_text(json.dumps(idx,ensure_ascii=False,indent=2),encoding='utf-8')
print(f'Exported {len(compact)} V25 names in {len(chunks)} chunks to {OUT}')
