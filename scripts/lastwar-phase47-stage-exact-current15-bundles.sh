#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — PHASE 47
# STAGE EXACT FORMATION BUNDLES FOR THE 15 CURRENT HEROES
# CODE ONLY · OFFLINE ONLY · no root · no run-as · no Last War network.
#
# Sources are authoritative only:
#  - installed APK BundleFragment0 offsets from Phase 45
#  - exact hashed cache bundles recovered by Phase 46B
# No similarity matching, no fallback vehicle, no generated geometry.

PKG="com.fun.lastwar.gp"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
P45="$ROOT/frontend/lab/master-assets-v2/meta/formation-authoritative-bundle-map-31.json"
CACHE="$HOME/storage/downloads/WFGG_LASTWAR_PHASE46B_CACHE_INDEXES"
OUT="$ROOT/frontend/lab/local_assets/lastwar-current15-exact-v1"
MANIFEST="$ROOT/frontend/lab/master-assets-v2/meta/current15-exact-bundle-stage.json"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_PHASE47_CURRENT15_EXACT_STAGE.txt"
PY="${TMPDIR:-$HOME/.cache}/wfgg-phase47-stage-current15.py"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche active incorrecte"
[[ -s "$P45" ]] || fail "Phase45 absente: $P45"
[[ -d "$CACHE" ]] || fail "Cache Phase46B absent: $CACHE"
command -v python >/dev/null 2>&1 || fail "python absent"
command -v cmd >/dev/null 2>&1 || fail "commande Android cmd absente"

mapfile -t APK_PATHS < <(cmd package path "$PKG" 2>/dev/null | sed -n 's/^package://p')
[[ ${#APK_PATHS[@]} -gt 0 ]] || fail "APK Last War introuvable"

rm -rf "$OUT"
mkdir -p "$OUT" "$(dirname "$MANIFEST")" "$(dirname "$PY")"

cat > "$PY" <<'PYEOF'
from pathlib import Path
from collections import defaultdict
import hashlib, json, os, shutil, sys, zipfile

p45p=Path(sys.argv[1]); cache=Path(sys.argv[2]); outdir=Path(sys.argv[3]); manifestp=Path(sys.argv[4]); reportp=Path(sys.argv[5]); apk_paths=sys.argv[6:]
data=json.loads(p45p.read_text(encoding='utf-8'))
rows=[r for r in (data.get('rows') or []) if r.get('current15')]
if len(rows)!=15:
    raise SystemExit(f'expected 15 current heroes, got {len(rows)}')

fragment_entry=((data.get('source') or {}).get('fragment') or {}).get('entry') or 'assets/AssetBundles/BundleFragment0.bytes'
fragment_apk=None
for ap in apk_paths:
    try:
        with zipfile.ZipFile(ap) as z:
            if fragment_entry in z.namelist():
                fragment_apk=Path(ap);break
    except Exception:
        pass
if fragment_apk is None:
    raise SystemExit(f'installed fragment entry not found: {fragment_entry}')

# Phase46B stores exact cache aliases as exact__<aliasName>.
def cache_file(alias):
    if not alias:return None
    p=cache/f'exact__{alias}'
    return p if p.is_file() else None

def sha256_file(p,chunk=1024*1024):
    h=hashlib.sha256()
    with p.open('rb') as f:
        while True:
            b=f.read(chunk)
            if not b:break
            h.update(b)
    return h.hexdigest()

def sanitize(name):
    # Manifest names are already safe bundle basenames; keep exact logical spelling.
    return os.path.basename(str(name or '')).replace('..','_')

# Build one authoritative asset row per queue/dependency bundle.
hero_entries=[]
installed_segments=[]
for r in rows:
    hid=int(r['heroId']); hdir=outdir/str(hid); hdir.mkdir(parents=True,exist_ok=True)
    entries=[]
    seen=set()

    def add(src, role):
        if not src:return
        logical=src.get('logicalName') or src.get('aliasName')
        if not logical:return
        key=(src.get('bundleId'),logical)
        if key in seen:return
        seen.add(key)
        dest=hdir/sanitize(logical)
        row={
          'heroId':hid,'heroName':r.get('name'),'role':role,
          'kind':src.get('kind') or ('queue' if role=='queue' else 'dependency'),
          'bundleId':src.get('bundleId'),'logicalName':src.get('logicalName'),
          'aliasName':src.get('aliasName'),'declaredBytes':src.get('declaredBytes'),
          'fragmentOffset':src.get('fragmentOffset'),'fragmentBytes':src.get('fragmentBytes'),
          'dest':dest,'source':None,'staged':False,'sizeOk':None,'sha256':None,
        }
        off=src.get('fragmentOffset'); n=src.get('fragmentBytes') or src.get('declaredBytes')
        if off is not None and n is not None:
            row['source']='installedFragment'
            installed_segments.append((int(off),int(n),row))
        else:
            cf=cache_file(src.get('aliasName'))
            if cf is not None:
                row['source']='adbCacheExactAlias'
                shutil.copyfile(cf,dest)
                actual=dest.stat().st_size
                expected=src.get('declaredBytes')
                row['staged']=True;row['actualBytes']=actual
                row['sizeOk']=(expected is None or actual==int(expected))
                row['sha256']=sha256_file(dest)
            else:
                row['source']='missing'
        entries.append(row)

    add(r.get('queueBundle') or {},'queue')
    for d in r.get('installedSameModelDependencies') or []:add(d,'sameModelDependency')
    for d in r.get('missingSameModelDependencies') or []:add(d,'sameModelDependency')
    hero_entries.append((r,entries))

# Extract all installed fragment slices in ONE forward stream. This avoids loading
# the 534 MB fragment in RAM and avoids re-decompressing it once per bundle.
installed_segments.sort(key=lambda x:(x[0],x[1]))
if installed_segments:
    with zipfile.ZipFile(fragment_apk) as z, z.open(fragment_entry,'r') as f:
        pos=0
        for off,n,row in installed_segments:
            if off < pos:
                # Offsets should be disjoint/increasing. Duplicate offset is allowed only
                # if already staged through another identical segment.
                raise SystemExit(f'non-monotonic fragment segment hero={row["heroId"]} off={off} pos={pos}')
            remain=off-pos
            while remain:
                b=f.read(min(remain,1024*1024))
                if not b:raise SystemExit(f'fragment EOF while seeking to {off}')
                remain-=len(b);pos+=len(b)
            buf=bytearray()
            left=n
            while left:
                b=f.read(min(left,1024*1024))
                if not b:raise SystemExit(f'fragment EOF while reading {off}+{n}')
                buf.extend(b);left-=len(b);pos+=len(b)
            row['dest'].write_bytes(buf)
            actual=len(buf);expected=row.get('declaredBytes') or n
            row['staged']=True;row['actualBytes']=actual
            row['sizeOk']=(actual==int(expected))
            row['sha256']=hashlib.sha256(buf).hexdigest()

# Finalize relative paths, readiness and strict completeness.
outrows=[]
for r,entries in hero_entries:
    kinds=defaultdict(int);missing=[];bad=[]
    for e in entries:
        if e['staged']:
            kinds[e['kind']]+=1
        else:missing.append(e['logicalName'] or e['aliasName'])
        if e['staged'] and e['sizeOk'] is False:bad.append(e['logicalName'] or e['aliasName'])
        try:e['localRel']=str(e['dest'].relative_to(outdir.parent.parent.parent.parent))
        except Exception:e['localRel']=str(e['dest'])
        e.pop('dest',None)
    declared_kinds=sorted(set(e['kind'] for e in entries))
    staged_kinds=sorted(k for k,v in kinds.items() if v)
    has_queue=kinds.get('queue',0)>=1
    has_mesh=kinds.get('mesh',0)>=1
    has_material=kinds.get('material',0)>=1
    has_texture=kinds.get('texture',0)>=1
    geometry_ready=has_queue and has_mesh and has_material and has_texture
    all_exact=(not missing and not bad and all(e['staged'] for e in entries))
    animation_present=kinds.get('animation',0)>=1
    animator_present=kinds.get('animator',0)>=1
    outrows.append({
      'heroId':r['heroId'],'name':r.get('name'),'formationKind':r.get('formationKind'),
      'queueModelPath':r.get('queueModelPath'),'phase45InstalledExact':r.get('installedExact'),
      'bundleCount':len(entries),'stagedBundleCount':sum(e['staged'] for e in entries),
      'declaredKinds':declared_kinds,'stagedKinds':staged_kinds,
      'queueReady':has_queue,'geometryReady':geometry_ready,
      'animationPresent':animation_present,'animatorPresent':animator_present,
      'allExactBundlesStaged':all_exact,'missing':missing,'sizeMismatches':bad,
      'bundles':entries,
    })

complete=sum(x['allExactBundlesStaged'] for x in outrows)
geom=sum(x['geometryReady'] for x in outrows)
anim=sum(x['animationPresent'] for x in outrows)
from_apk=sum(e['source']=='installedFragment' and e['staged'] for x in outrows for e in x['bundles'])
from_cache=sum(e['source']=='adbCacheExactAlias' and e['staged'] for x in outrows for e in x['bundles'])
missing_count=sum(len(x['missing']) for x in outrows)

manifest={
 'format':'WFGG_LASTWAR_CURRENT15_EXACT_BUNDLE_STAGE_V1','networkUsed':False,
 'sources':{'phase45':'frontend/lab/master-assets-v2/meta/formation-authoritative-bundle-map-31.json','installedFragmentEntry':fragment_entry,'cache':'WFGG_LASTWAR_PHASE46B_CACHE_INDEXES'},
 'heroCount':15,'completeHeroCount':complete,'geometryReadyHeroCount':geom,'animationHeroCount':anim,
 'stagedFromInstalledFragment':from_apk,'stagedFromAdbCache':from_cache,'missingBundleCount':missing_count,
 'heroes':outrows,
}
manifestp.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')

lines=[
 'WfGg Last War LAB — PHASE 47 CURRENT15 EXACT BUNDLE STAGE',
 'OFFLINE ONLY · exact gameres mapping only · no similarity fallback',
 f'heroes=15 complete={complete}/15 geometryReady={geom}/15 animationPresent={anim}/15',
 f'fromInstalledFragment={from_apk} fromAdbCache={from_cache} missingBundles={missing_count}',
 f'fragmentApk={fragment_apk.name} fragmentEntry={fragment_entry}',
 ''
]
for h in outrows:
    lines.append(f"HERO {h['heroId']} {h['name']} complete={h['allExactBundlesStaged']} geometry={h['geometryReady']} animation={h['animationPresent']} animator={h['animatorPresent']} bundles={h['stagedBundleCount']}/{h['bundleCount']}")
    lines.append('  model='+str(h['queueModelPath']))
    for e in h['bundles']:
        lines.append(f"  {e['kind']} staged={e['staged']} source={e['source']} bytes={e.get('actualBytes')} sizeOk={e['sizeOk']} logical={e['logicalName']} alias={e['aliasName']}")
    for m in h['missing']:lines.append('  MISSING '+str(m))
    for m in h['sizeMismatches']:lines.append('  SIZE_MISMATCH '+str(m))
    lines.append('')
lines+=['GUARDRAILS','  queue_model_path_authoritative=true','  exact_manifest_bundle_only=true','  installed_offsets_from_phase45_only=true','  cache_aliases_from_phase46b_only=true','  no_similarity_fallback=true','  no_generated_geometry=true','  no_lastwar_network=true','  raw_bundles_not_committed=true']
reportp.write_text('\n'.join(lines)+'\n',encoding='utf-8')

print('PHASE47_OK',f'complete={complete}/15',f'geometry={geom}/15',f'animation={anim}/15',f'apkBundles={from_apk}',f'cacheBundles={from_cache}',f'missingBundles={missing_count}')
PYEOF

python "$PY" "$P45" "$CACHE" "$OUT" "$MANIFEST" "$REPORT" "${APK_PATHS[@]}"
rm -f "$PY"

git add scripts/lastwar-phase47-stage-exact-current15-bundles.sh frontend/lab/master-assets-v2/meta/current15-exact-bundle-stage.json
if ! git diff --cached --quiet -- scripts/lastwar-phase47-stage-exact-current15-bundles.sh frontend/lab/master-assets-v2/meta/current15-exact-bundle-stage.json; then
  git commit -m "lab: stage exact current 15 bundle manifest"
fi
git push origin "$BRANCH"

echo "=== PHASE 47 TERMINEE ==="
echo "Assets locaux: frontend/lab/local_assets/lastwar-current15-exact-v1"
echo "Manifest: frontend/lab/master-assets-v2/meta/current15-exact-bundle-stage.json"
echo "Rapport: $REPORT"
echo "Ne lance pas encore la page Escouades."
echo "main non modifiée."
