#!/data/data/com.termux/files/usr/bin/python
from pathlib import Path
import json, math, re, sys

ROOT = Path(sys.argv[1]).resolve()
SRC = ROOT / 'frontend/lab/audie-assembly-2d-v14-data/manifest.json'
OUT = ROOT / 'frontend/lab/audie-assembly-strict-v15-data'
MAN = OUT / 'manifest.json'
META = ROOT / 'frontend/lab/master-assets-v2/meta/audie-assembly-strict-v15.json'
OUT.mkdir(parents=True, exist_ok=True)

if not SRC.is_file():
    raise SystemExit('ERROR: V14 manifest absent; run lastwar-audie-assembly-2d-v14.sh first')

src = json.loads(SRC.read_text('utf-8'))

def low(*xs):
    return ' '.join(str(x or '') for x in xs).lower()

def is_audie_part(p):
    s = low(p.get('meshName'), p.get('meshBundle'), p.get('gameObject'), p.get('meshSerializedFile'))
    return ('audie' in s) or ('a_hero_audie_01' in s)

def assembly_score(a, anchors):
    clue_n = len(a.get('clues') or [])
    v = int(a.get('vertexTotal') or 0)
    parts = int(a.get('partCount') or 0)
    root = low(a.get('rootName'))
    score = len(anchors) * 100 + clue_n * 20 + min(parts, 40) * 2 + min(40, int(math.log10(max(v, 1)) * 10))
    if any(k in root for k in ('recruit_', 'recruit ', 'uiroot', 'canvas')):
        score -= 80
    if v < 500:
        score -= 35
    return score

rows = []
rejected = []
for a in src.get('assemblies') or []:
    parts = a.get('parts') or []
    anchors = [p for p in parts if is_audie_part(p)]
    if not anchors:
        rejected.append({
            'rootName': a.get('rootName'),
            'bundle': a.get('bundle'),
            'partCount': a.get('partCount'),
            'vertexTotal': a.get('vertexTotal'),
            'reason': 'NO_AUDIE_MESH_ANCHOR',
        })
        continue
    r = dict(a)
    r['audieAnchorCount'] = len(anchors)
    r['siblingPartCount'] = max(0, len(parts) - len(anchors))
    r['audieAnchors'] = [{
        'meshName': p.get('meshName'),
        'gameObject': p.get('gameObject'),
        'meshBundle': p.get('meshBundle'),
        'transformID': p.get('transformID'),
        'clue': p.get('clue'),
    } for p in anchors]
    r['score'] = assembly_score(r, anchors)
    r['strictReason'] = 'DIRECT_AUDIE_MESH_IN_HIERARCHY'
    rows.append(r)

# Deduplicate exact part/transform compositions after strict filtering.
uniq = {}
for a in rows:
    sig = tuple(sorted((str(p.get('src') or ''), str(p.get('transformID') or '')) for p in (a.get('parts') or [])))
    old = uniq.get(sig)
    if old is None or int(a.get('score') or 0) > int(old.get('score') or 0):
        uniq[sig] = a
rows = list(uniq.values())
rows.sort(key=lambda a: (-int(a.get('score') or 0), -int(a.get('audieAnchorCount') or 0), -int(a.get('vertexTotal') or 0), str(a.get('rootName') or '').lower()))

verdict = 'STRICT_AUDIE_ASSEMBLIES_FOUND' if rows else 'NO_STRICT_AUDIE_ASSEMBLY_IN_V14'
res = {
    'format': 'WFGG_LASTWAR_AUDIE_ASSEMBLY_STRICT_V15',
    'verdict': verdict,
    'counts': {
        'v14Assemblies': len(src.get('assemblies') or []),
        'strictAssemblies': len(rows),
        'rejectedAssemblies': len(rejected),
        'strictMultiPart': sum(1 for a in rows if int(a.get('partCount') or 0) >= 2),
        'audieAnchors': sum(int(a.get('audieAnchorCount') or 0) for a in rows),
    },
    'assemblies': rows,
    'rejected': rejected,
    'rules': [
        'V15 never accepts an assembly merely because it has multiple parts.',
        'At least one resolved Mesh/GameObject/bundle in the hierarchy must contain the Audie identity.',
        'Once anchored to Audie, sibling mesh parts under the same Transform root are preserved because they may be generically named vehicle components.',
        'Assemblies such as recruit_100 without any Audie mesh anchor are rejected.',
        'This pass reuses V14 data and performs no heavy bundle rescan.',
    ],
}
META.parent.mkdir(parents=True, exist_ok=True)
META.write_text(json.dumps(res, ensure_ascii=False, indent=2) + '\n', 'utf-8')
MAN.write_text(json.dumps(res, ensure_ascii=False, indent=2) + '\n', 'utf-8')

print('AUDIE_ASSEMBLY_STRICT_V15_READY', f'verdict={verdict}', f'strict={len(rows)}', f'rejected={len(rejected)}', flush=True)
for i, a in enumerate(rows[:30], 1):
    print('V15_ASSEMBLY', i, a.get('rootName'), f"score={a.get('score')}", f"anchors={a.get('audieAnchorCount')}", f"parts={a.get('partCount')}", f"v={a.get('vertexTotal')}", a.get('bundle'), flush=True)
print('JSON=' + str(META), flush=True)
print('VIEWER=http://127.0.0.1:8788/lab/lastwar-audie-assembly-strict-v15.html?v=15', flush=True)
