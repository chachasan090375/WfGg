#!/usr/bin/env python3
import json, os, re, sys
from pathlib import Path

ROOT = Path(os.environ.get('WFGG_ROOT', Path.home() / 'wfgg-lastwar-preview'))
LAB = ROOT / 'frontend' / 'lab'
MASTER = LAB / 'master-assets-v2'
META = MASTER / 'meta'
OUT = MASTER / 'a-hero-generic-v16'
OUT.mkdir(parents=True, exist_ok=True)

# Prefer the GLOBAL reusable name index. V11 is only a fallback and is Audie-scoped.
index_candidates = [
    META / 'unity-asset-name-index-v1.json',
    META / 'audie-model-variants-v11.json',
    LAB / 'audie-model-variants-v11-data' / 'manifest.json',
]

def load_json(p):
    try:
        return json.loads(p.read_text(encoding='utf-8', errors='ignore'))
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
    print('ERROR no reusable asset index found', file=sys.stderr)
    print('NEXT=python scripts/lastwar-unity-asset-index-v1.py "$HOME/wfgg-lastwar-preview"', file=sys.stderr)
    sys.exit(2)

# Flatten both the generic name index and older manifests into asset-like records.
items = []
def walk(x, inherited=None):
    inherited = inherited or {}
    if isinstance(x, dict):
        cur = dict(inherited)
        for k in ('bundle','bundlePath','sourceBundle','path','basename','serialized','serializedFile','sourceSerialized','type','className'):
            if k in x and isinstance(x[k], (str,int,float,bool)):
                cur[k] = x[k]
        nm = None
        for k in ('name','assetName','meshName','objectName','m_Name'):
            if isinstance(x.get(k), str) and x.get(k):
                nm = x[k]; break
        if nm:
            rec = dict(cur)
            rec.update({k:v for k,v in x.items() if isinstance(v,(str,int,float,bool))})
            rec['name'] = nm
            # Normalize the physical bundle field for the viewer / next resolver.
            rec['bundle'] = str(rec.get('bundle') or rec.get('bundlePath') or rec.get('sourceBundle') or rec.get('path') or rec.get('basename') or '')
            items.append(rec)
        for v in x.values():
            walk(v, cur)
    elif isinstance(x, list):
        for v in x:
            walk(v, inherited)
walk(src)

rx_loose = re.compile(r'(?i)a[_-]?hero')
seen = set(); hits=[]
for r in items:
    n = str(r.get('name',''))
    hay = ' '.join(str(r.get(k,'')) for k in ('name','bundle','path','basename','serialized','serializedFile','sourceSerialized'))
    if not rx_loose.search(hay):
        continue
    key=(n, str(r.get('bundle','')), str(r.get('pathID') or r.get('sourcePathID') or ''))
    if key in seen: continue
    seen.add(key)
    low=hay.lower(); score=0; reasons=[]
    if re.search(r'(?i)^a[_-]?hero[_-]?0?1(?:$|[_-])', n): score += 100; reasons.append('EXACT_A_HERO_01')
    if re.search(r'(?i)^a[_-]?hero(?:$|[_-])', n): score += 35; reasons.append('A_HERO_ROOT')
    if 'audie' not in low: score += 25; reasons.append('NON_AUDIE')
    if any(t in low for t in ('formation','board','pvp','uihero','hero_01','hero-01')): score += 30; reasons.append('FORMATION_CONTEXT_NAME')
    if any(t in low for t in ('low','lod','simple','lite','mobile')): score += 20; reasons.append('SIMPLIFIED_HINT')
    if any(t in low for t in ('high','bullet','missile','effect','fx_')): score -= 15
    typ=str(r.get('type') or r.get('className') or '')
    if typ.lower() == 'mesh': score += 12; reasons.append('MESH')
    elif 'mesh' in typ.lower() or 'mesh' in n.lower(): score += 8
    rr=dict(r); rr['score']=score; rr['reasons']=reasons; rr['haystack']=hay
    hits.append(rr)

hits.sort(key=lambda r:(-int(r.get('score',0)), str(r.get('name','')).lower(), str(r.get('bundle',''))))

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
        'bundles':sorted({str(x.get('bundle','')) for x in rows if x.get('bundle')})[:50],
        'types':sorted({str(x.get('type') or x.get('className') or '') for x in rows}),
    })
group_rows.sort(key=lambda g:(-g['maxScore'],-g['count'],g['root'].lower()))

exact=[r for r in hits if re.search(r'(?i)^a[_-]?hero[_-]?0?1(?:$|[_-])',r['name'])]
non_audie=[r for r in hits if 'audie' not in r['haystack'].lower()]
out={
    'version':16,
    'sourceIndex':str(src_path),
    'globalIndex':src_path.name == 'unity-asset-name-index-v1.json',
    'query':'A_Hero generic, no Audie requirement',
    'hits':hits,
    'groups':group_rows,
    'summary':{
        'recordsScanned':len(items),
        'aHeroHits':len(hits),
        'groups':len(group_rows),
        'exactAHero01':len(exact),
        'nonAudie':len(non_audie),
        'meshHits':sum(1 for r in hits if str(r.get('type','')).lower()=='mesh'),
    }
}
(OUT/'manifest.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
print(f"A_HERO_GENERIC_V16_READY globalIndex={out['globalIndex']} hits={len(hits)} groups={len(group_rows)} exactAHero01={len(exact)} nonAudie={len(non_audie)} meshHits={out['summary']['meshHits']}")
for i,r in enumerate(hits[:25],1):
    print('A_HERO_TOP', i, 'score='+str(r['score']), 'type='+str(r.get('type','?')), 'name='+r['name'], 'pathID='+str(r.get('pathID','?')), 'bundle='+str(r.get('bundle','')))
print(f"JSON={OUT/'manifest.json'}")
