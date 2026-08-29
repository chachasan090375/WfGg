#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — global gameres scan for Formation runtime scene/prefab candidates.
# Read-only catalog analysis. No Last War network. No preview mutation. main untouched.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
GAMERES="$ROOT/frontend/lab/local_assets/lastwar-formation-native-recipe-v1/gameres"
OUT="$ROOT/frontend/lab/master-assets-v2/meta/formation-global-scene-catalog-v1.json"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_FORMATION_GLOBAL_SCENE_CATALOG.txt"
PY="${TMPDIR:-$HOME/.cache}/wfgg-formation-global-scene-catalog.py"

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
        bid=int(p[0]);bundles[bid]={'bundleId':bid,'logicalName':p[1],'declaredBytes':int(p[3]),'assetPathIds':[int(x) for x in p[4].split('|') if x],'dependencyBundleIds':[int(x) for x in p[5].split('|') if x],'groups':p[6].split('|') if p[6] else [],'aliasName':p[7]}
    except:pass
for b in bundles.values():b['assetPaths']=[paths.get(x) for x in b['assetPathIds'] if paths.get(x)]

# Runtime-loaded scenes/prefabs can be absent from the UI prefab dependency graph,
# so scan every catalog path. Broad enough to catch Chinese/legacy naming families.
rx=re.compile(r'(formation|pvp|hero.?show|show.?hero|heroshow|showhero|formationbg|formationrt|biandui|bian.?dui|team.?show|squad|deploy|lineup|battle.?array|hero.*camera|camera.*hero)',re.I)
sceneish=re.compile(r'\.(unity|prefab|fbx|asset|mat)$',re.I)
noise=re.compile(r'(buff|cell|text|icon|sprite|atlas|language|audio|sound|localization)',re.I)
rows=[]
for b in bundles.values():
    hits=[p for p in b['assetPaths'] if rx.search(p)]
    if not hits:continue
    score=0
    for p in hits:
        pl=p.lower()
        if pl.endswith('.unity'):score+=180
        elif pl.endswith('.prefab'):score+=90
        elif pl.endswith('.fbx'):score+=50
        elif pl.endswith('.asset'):score+=25
        if re.search(r'hero.?show|show.?hero|heroshow',pl):score+=120
        if re.search(r'formation.*(scene|camera|world|bg)|(?:scene|camera|world|bg).*formation',pl):score+=140
        if 'uiheropvpformationpanel' in pl:score-=120
        if noise.search(pl):score-=20
    if any(sceneish.search(p) for p in hits):score+=20
    rows.append({**b,'matchedAssetPaths':hits,'score':score})
rows.sort(key=lambda x:(-x['score'],x['bundleId']))

summary={'format':'WFGG_LASTWAR_FORMATION_GLOBAL_SCENE_CATALOG_V1','networkUsed':False,'generatedArtwork':False,'catalogPathCount':len(paths),'bundleCount':len(bundles),'candidateCount':len(rows),'candidates':rows,'guardrails':{'globalCatalogOnly':True,'previewUntouched':True,'mainUntouched':True}}
outp.write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n','utf-8')
lines=['WfGg Last War — FORMATION GLOBAL SCENE CATALOG','',f'paths={len(paths)} bundles={len(bundles)} candidates={len(rows)}','']
for r in rows[:120]:
    lines.append(f"CANDIDATE score={r['score']} bundle={r['bundleId']} bytes={r['declaredBytes']} logical={r['logicalName']}")
    for p in r['matchedAssetPaths'][:40]:lines.append('  '+p)
reportp.write_text('\n'.join(lines)+'\n','utf-8')
print('FORMATION_GLOBAL_SCENE_CATALOG_OK',f'paths={len(paths)}',f'bundles={len(bundles)}',f'candidates={len(rows)}')
for r in rows[:20]:
    print('GLOBAL_SCENE_CANDIDATE',f"score={r['score']}",f"bundle={r['bundleId']}",(r['matchedAssetPaths'] or [''])[0])
print('FORMATION_GLOBAL_SCENE_CATALOG_JSON',outp)
print('FORMATION_GLOBAL_SCENE_CATALOG_REPORT',reportp)
PYEOF

python "$PY" "$GAMERES" "$OUT" "$REPORT"
rm -f "$PY"

git add scripts/lastwar-formation-global-scene-catalog.sh "$OUT"
if ! git diff --cached --quiet; then
  git commit -m "lab: scan global Formation scene catalog"
  git push origin "$BRANCH"
fi

echo "=== FORMATION GLOBAL SCENE CATALOG TERMINE ==="
echo "JSON: $OUT"
echo "Rapport: $REPORT"
echo "Preview inchangée. main non modifiée."
