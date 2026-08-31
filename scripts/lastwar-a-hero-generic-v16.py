#!/usr/bin/env python3
import json, os, re, sys, hashlib
from pathlib import Path

ROOT = Path(os.environ.get('WFGG_ROOT', Path.home() / 'wfgg-lastwar-preview'))
LAB = ROOT / 'frontend' / 'lab'
MASTER = LAB / 'master-assets-v2'
OUT = MASTER / 'a-hero-generic-v16'
OUT.mkdir(parents=True, exist_ok=True)

# Reuse the durable generic index if it exists; otherwise harvest the already-built V11 inventory.
index_candidates = [
    MASTER / 'unity-asset-index-v1.json',
    MASTER / 'lastwar-unity-asset-index-v1.json',
    MASTER / 'audie-model-variants-v11.json',
]

def load_json(p):
    try:
        return json.loads(p.read_text(errors='ignore'))
    except Exception:
        return None

src = None
src_path = None
for p in index_candidates:
    if p.exists():
        d = load_json(p)
        if d:
            src, src_path = d, p
            break

if src is None:
    print('ERROR no reusable asset index found; run V11 or generic asset index first', file=sys.stderr)
    sys.exit(2)

# Flatten unknown JSON shapes into asset-like dicts.
items = []
def walk(x, inherited=None):
    inherited = inherited or {}
    if isinstance(x, dict):
        cur = dict(inherited)
        for k in ('bundle','bundlePath','sourceBundle','serialized','serializedFile','sourceSerialized','type','className'):
            if k in x and isinstance(x[k], (str,int,float,bool)):
                cur[k] = x[k]
        nm = None
        for k in ('name','assetName','meshName','objectName','m_Name'):
            if isinstance(x.get(k), str) and x.get(k):
                nm = x[k]; break
        if nm:
            rec = dict(cur); rec.update({k:v for k,v in x.items() if isinstance(v,(str,int,float,bool))})
            rec['name'] = nm
            items.append(rec)
        for v in x.values():
            walk(v, cur)
    elif isinstance(x, list):
        for v in x: walk(v, inherited)
walk(src)

# Strong generic naming pass. Do not require Audie.
rx = re.compile(r'(?i)(?:^|[^a-z0-9])a[_-]?hero(?:[_-]?\d+|[_-][a-z0-9]+)*')
rx_loose = re.compile(r'(?i)a[_-]?hero')
seen = set(); hits=[]
for r in items:
    n = str(r.get('name',''))
    hay = ' '.join(str(r.get(k,'')) for k in ('name','bundle','bundlePath','sourceBundle','serialized','serializedFile','sourceSerialized'))
    if not rx_loose.search(hay):
        continue
    key=(n, str(r.get('bundle') or r.get('bundlePath') or r.get('sourceBundle') or ''), str(r.get('pathID') or r.get('sourcePathID') or ''))
    if key in seen: continue
    seen.add(key)
    low=hay.lower()
    score=0
    if re.search(r'(?i)^a[_-]?hero[_-]?0?1(?:$|[_-])', n): score += 100
    if re.search(r'(?i)^a[_-]?hero(?:$|[_-])', n): score += 35
    if 'audie' not in low: score += 25
    if any(t in low for t in ('formation','board','pvp','uihero','hero_01','hero-01')): score += 30
    if any(t in low for t in ('low','lod','simple','lite')): score += 20
    if any(t in low for t in ('high','bullet','missile','effect','fx_')): score -= 15
    typ=str(r.get('type') or r.get('className') or '')
    if 'mesh' in typ.lower() or 'mesh' in n.lower(): score += 8
    rr=dict(r); rr['score']=score; rr['haystack']=hay
    hits.append(rr)

hits.sort(key=lambda r:(-int(r.get('score',0)), str(r.get('name','')).lower()))

# Group roots for fast nomenclature inspection.
def root_name(n):
    s=re.sub(r'(?i)(?:_high|_low|_lod\d*|_skin\d*|_d|_n|_s)$','',n)
    return s

groups={}
for r in hits:
    groups.setdefault(root_name(r['name']), []).append(r)

group_rows=[]
for root, rows in groups.items():
    group_rows.append({
        'root':root,
        'count':len(rows),
        'maxScore':max(int(x.get('score',0)) for x in rows),
        'names':sorted({x['name'] for x in rows}),
        'bundles':sorted({str(x.get('bundle') or x.get('bundlePath') or x.get('sourceBundle') or '') for x in rows if (x.get('bundle') or x.get('bundlePath') or x.get('sourceBundle'))})[:30],
    })
group_rows.sort(key=lambda g:(-g['maxScore'],-g['count'],g['root'].lower()))

out={
    'version':16,
    'sourceIndex':str(src_path),
    'query':'A_Hero generic, no Audie requirement',
    'hits':hits,
    'groups':group_rows,
    'summary':{
        'recordsScanned':len(items),
        'aHeroHits':len(hits),
        'groups':len(group_rows),
        'exactAHero01':sum(1 for r in hits if re.search(r'(?i)^a[_-]?hero[_-]?0?1(?:$|[_-])',r['name'])),
        'nonAudie':sum(1 for r in hits if 'audie' not in r['haystack'].lower()),
    }
}
(OUT/'manifest.json').write_text(json.dumps(out,ensure_ascii=False,indent=2))
print(f"A_HERO_GENERIC_V16_READY hits={len(hits)} groups={len(group_rows)} exactAHero01={out['summary']['exactAHero01']} nonAudie={out['summary']['nonAudie']}")
print(f"JSON={OUT/'manifest.json'}")
