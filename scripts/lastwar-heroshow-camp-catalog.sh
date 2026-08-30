#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — locate the HeroShow Camp_<level> assets referenced by HeroShowSetting.
# Read-only catalog analysis. No preview mutation. main untouched.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
GAMERES="$ROOT/frontend/lab/local_assets/lastwar-formation-native-recipe-v1/gameres"
OUT="$ROOT/frontend/lab/master-assets-v2/meta/heroshow-camp-catalog-v1.json"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_HEROSHOW_CAMP_CATALOG.txt"
PY="${TMPDIR:-$HOME/.cache}/wfgg-heroshow-camp-catalog.py"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
[[ -s "$GAMERES" ]] || fail "gameres local absent"
command -v python >/dev/null 2>&1 || fail "python absent"
mkdir -p "$(dirname "$OUT")" "$(dirname "$REPORT")" "$(dirname "$PY")"

cat > "$PY" <<'PYEOF'
from pathlib import Path
import json,re,sys

gameres=Path(sys.argv[1]);outp=Path(sys.argv[2]);reportp=Path(sys.argv[3])
text=gameres.read_text('utf-8')
def section(name):
    m=re.search(rf'^\[{re.escape(name)}\]\s*$',text,re.M)
    if not m:return []
    s=m.end();n=re.search(r'^\[[^\]]+\]\s*$',text[s:],re.M);e=s+n.start() if n else len(text)
    return [x for x in text[s:e].splitlines() if x.strip()]

dirs={}
for ln in section('Directories'):
    try:i,p=ln.split(',',1);dirs[int(i)]=p
    except:pass
paths={}
for ln in section('Paths'):
    try:pid,did,n=ln.split(',',2);paths[int(pid)]=dirs[int(did)].rstrip('/')+'/'+n
    except:pass
bundles={}
for ln in section('Bundles'):
    p=ln.split(',')
    if len(p)<8:continue
    try:
        bid=int(p[0]);bundles[bid]={
            'bundleId':bid,'logicalName':p[1],'declaredBytes':int(p[3]),
            'assetPathIds':[int(x) for x in p[4].split('|') if x],
            'dependencyBundleIds':[int(x) for x in p[5].split('|') if x],
            'groups':p[6].split('|') if p[6] else [],'aliasName':p[7]
        }
    except:pass
for b in bundles.values():
    b['assetPaths']=[paths.get(x) for x in b['assetPathIds'] if paths.get(x)]

# HeroShowSetting.Update() does GameObject.Find("Camp_" + level).
# Search exact Camp_* naming first, then nearby camp/heroshow scene-ish assets.
exact_rx=re.compile(r'(^|[/_])Camp_[A-Za-z0-9-]*',re.I)
related_rx=re.compile(r'(hero.?show|show.?hero|camp)',re.I)
sceneish=re.compile(r'\.(unity|prefab|fbx|asset|mat)$',re.I)
rows=[]
for b in bundles.values():
    exact=[p for p in b['assetPaths'] if exact_rx.search(p)]
    related=[p for p in b['assetPaths'] if related_rx.search(p)]
    if not exact and not related:continue
    score=0
    for p in exact:
        score+=300
        if p.lower().endswith('.unity'):score+=250
        elif p.lower().endswith('.prefab'):score+=180
        elif p.lower().endswith('.fbx'):score+=100
        elif p.lower().endswith('.asset'):score+=60
    for p in related:
        pl=p.lower()
        if 'heroshow' in pl or re.search(r'hero.?show',pl):score+=90
        if sceneish.search(pl):score+=20
    rows.append({**b,'exactCampPaths':exact,'relatedPaths':related,'score':score})
rows.sort(key=lambda x:(-x['score'],x['bundleId']))

# Reverse parents: bundles depending on a Camp bundle can reveal the loader/scene family.
parents={bid:[] for bid in bundles}
for b in bundles.values():
    for d in b['dependencyBundleIds']:
        parents.setdefault(d,[]).append(b['bundleId'])
for r in rows:
    r['parentBundleIds']=parents.get(r['bundleId'],[])
    r['dependencyBundles']=[{
        'bundleId':d,
        'logicalName':bundles[d]['logicalName'],
        'assetPaths':bundles[d]['assetPaths'][:40]
    } for d in r['dependencyBundleIds'] if d in bundles]
    r['parentBundles']=[{
        'bundleId':p,
        'logicalName':bundles[p]['logicalName'],
        'assetPaths':bundles[p]['assetPaths'][:40]
    } for p in r['parentBundleIds'] if p in bundles]

summary={
 'format':'WFGG_LASTWAR_HEROSHOW_CAMP_CATALOG_V1',
 'evidence':{'heroShowSettingFindPattern':'Camp_<level>','source':'Assembly-CSharp CLR IL'},
 'pathCount':len(paths),'bundleCount':len(bundles),'candidateCount':len(rows),
 'candidates':rows,
 'guardrails':{'catalogReadOnly':True,'previewUntouched':True,'mainUntouched':True}
}
outp.write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n','utf-8')
lines=['WfGg Last War — HEROSHOW CAMP CATALOG','',f'paths={len(paths)} bundles={len(bundles)} candidates={len(rows)}','']
for r in rows[:100]:
    lines.append(f"CAMP_CANDIDATE score={r['score']} bundle={r['bundleId']} bytes={r['declaredBytes']} logical={r['logicalName']} parents={len(r['parentBundleIds'])} deps={len(r['dependencyBundleIds'])}")
    for p in r['exactCampPaths'][:30]:lines.append('  EXACT '+p)
    for p in r['relatedPaths'][:30]:
        if p not in r['exactCampPaths']:lines.append('  RELATED '+p)
    for d in r['dependencyBundles'][:12]:lines.append(f"  DEP bundle={d['bundleId']} logical={d['logicalName']}")
    for p in r['parentBundles'][:12]:lines.append(f"  PARENT bundle={p['bundleId']} logical={p['logicalName']}")
reportp.write_text('\n'.join(lines)+'\n','utf-8')
print('HEROSHOW_CAMP_CATALOG_OK',f'paths={len(paths)}',f'bundles={len(bundles)}',f'candidates={len(rows)}')
for r in rows[:30]:
    best=(r['exactCampPaths'] or r['relatedPaths'] or [''])[0]
    print('CAMP_CANDIDATE',f"score={r['score']}",f"bundle={r['bundleId']}",best)
    for d in r['dependencyBundles'][:5]:print('  CAMP_DEP',d['bundleId'],d['logicalName'])
    for p in r['parentBundles'][:5]:print('  CAMP_PARENT',p['bundleId'],p['logicalName'])
print('HEROSHOW_CAMP_CATALOG_JSON',outp)
print('HEROSHOW_CAMP_CATALOG_REPORT',reportp)
PYEOF

python "$PY" "$GAMERES" "$OUT" "$REPORT"
rm -f "$PY"

git add scripts/lastwar-heroshow-camp-catalog.sh "$OUT"
if ! git diff --cached --quiet; then
  git commit -m "lab: locate HeroShow Camp runtime assets"
  git push origin "$BRANCH"
fi

echo "=== HEROSHOW CAMP CATALOG TERMINE ==="
echo "JSON: $OUT"
echo "Rapport: $REPORT"
echo "Preview inchangée. main non modifiée."
