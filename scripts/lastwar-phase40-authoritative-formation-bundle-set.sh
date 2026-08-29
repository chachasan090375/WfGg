#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — PHASE 40
# Resolve the exact installed bundle-name set for the 31 authoritative
# HeroAppearance.queue_model_path entries decoded in Phase 39E.
# CODE ONLY. OFFLINE ONLY. No Last War network connection.

PKG="com.fun.lastwar.gp"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
MAP="$ROOT/frontend/lab/lastwar-hero-formation-unit-authoritative-map.js"
OUT="$ROOT/frontend/lab/master-assets-v2/meta/formation-unit-bundle-set-31.json"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_PHASE40_FORMATION_BUNDLE_SET_31.txt"
PY="${TMPDIR:-${HOME}/.cache}/wfgg-phase40-formation-bundles.py"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
command -v python >/dev/null 2>&1 || fail "python absent"
command -v pm >/dev/null 2>&1 || fail "commande Android pm absente"
[[ -s "$MAP" ]] || fail "référentiel 31/31 absent: $MAP"
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche active incorrecte"

mapfile -t APK_PATHS < <(cmd package path "$PKG" 2>/dev/null | sed -n 's/^package://p')
if [[ ${#APK_PATHS[@]} -eq 0 ]]; then
  mapfile -t APK_PATHS < <(pm path "$PKG" 2>/dev/null | sed -n 's/^package://p')
fi
[[ ${#APK_PATHS[@]} -gt 0 ]] || fail "installation Last War introuvable ($PKG)"

mkdir -p "$(dirname "$OUT")" "$(dirname "$PY")"
cat > "$PY" <<'PYEOF'
from pathlib import Path
import json, os, re, sys, zipfile

mapp=Path(sys.argv[1]); outp=Path(sys.argv[2]); reportp=Path(sys.argv[3]); apks=sys.argv[4:]
text=mapp.read_text(encoding='utf-8')
body=text.split('=',1)[1].rsplit(';',1)[0]
data=json.loads(body)
entries=data.get('entries') or []
if len(entries)!=31: raise SystemExit(f'expected 31 entries, got {len(entries)}')

# Installed catalog surfaces containing human-readable bundle names/asset paths.
CATALOG_ENTRIES=(
 'assets/AssetBundles/gameres',
 'assets/AssetBundles/BundleOffsetTable.bytes',
 'assets/AssetBundles/AliasOffsetTable.bytes',
)
printable=re.compile(rb'[ -~]{12,}')
fragments=[]; sources=[]
for apk in apks:
    try:
        with zipfile.ZipFile(apk) as z:
            for en in CATALOG_ENTRIES:
                try: raw=z.read(en)
                except KeyError: continue
                sources.append({'apk':os.path.basename(apk),'entry':en,'bytes':len(raw)})
                for m in printable.finditer(raw):
                    s=m.group().decode('ascii','ignore')
                    # Keep each bundle filename and each explicit Assets path separately.
                    for x in re.findall(r'[A-Za-z0-9_./-]{8,}\.bundle',s,re.I): fragments.append((en,m.start(),x))
                    for x in re.findall(r'Assets/[A-Za-z0-9_./ -]{8,}',s,re.I): fragments.append((en,m.start(),x.strip()))
    except Exception: pass
if not fragments: raise SystemExit('installed asset catalog strings unavailable')

# Some bundle name tables also live in base.apk assets/bin/Data. Scan only modest
# printable files likely to be indexes; no network and no account data.
for apk in apks:
    if not os.path.basename(apk).lower().startswith('base'): continue
    try:
        with zipfile.ZipFile(apk) as z:
            for zi in z.infolist():
                if not zi.filename.startswith('assets/bin/Data/') or zi.file_size>8*1024*1024: continue
                try: raw=z.read(zi)
                except Exception: continue
                if b'.bundle' not in raw: continue
                sources.append({'apk':os.path.basename(apk),'entry':zi.filename,'bytes':len(raw)})
                for m in printable.finditer(raw):
                    s=m.group().decode('ascii','ignore')
                    for x in re.findall(r'[A-Za-z0-9_./-]{8,}\.bundle',s,re.I): fragments.append((zi.filename,m.start(),x))
    except Exception: pass

def norm(s): return re.sub(r'[^a-z0-9]+','_',str(s or '').lower()).strip('_')
def flat(s): return norm(s).replace('_','')

def identity_tokens(e):
    path=e['queueModelPath']; low=path.lower()
    toks=[]
    # Prefer A_Hero identity segments from the authoritative path.
    for seg in re.split(r'[/\\]',path):
        if seg.lower().startswith('a_hero_'):
            x=re.sub(r'\.(?:prefab|fbx)$','',seg,flags=re.I)
            x=re.sub(r'_(?:city|battle|pve|pbr_zhanshi|zhanshi)$','',x,flags=re.I)
            toks.append(norm(x))
    # Gump is an explicit Soldier/bubing05 formation model rather than Models/Cars.
    m=re.search(r'/Soldier/([^/]+)/',path,re.I)
    if m: toks.extend([norm(m.group(1)), 'a_hero_'+norm(m.group(1))])
    # Longest/specific tokens first; generic prefixes excluded.
    out=[]
    for t in sorted(set(toks),key=len,reverse=True):
        if t and t not in ('a_hero','hero') and t not in out: out.append(t)
    return out

KINDS=('prefab','mesh','texture','material','matetial','materail','animation','animator','timeline','camera')
rows=[]
for e in entries:
    tokens=identity_tokens(e)
    matches=[]; seen=set()
    for source,off,s in fragments:
        fs=flat(s)
        hit=[t for t in tokens if flat(t) in fs]
        if not hit: continue
        # Require formation/model semantics, not portrait/UI-only bundles.
        ns=norm(s); ls=s.lower()
        if '.bundle' in ls:
            modelish=any(k in ns for k in ('models_cars','models_new_cars','character_vehicle','seasonres','soldier','art_dir_cars','art_lastwar_models'))
            if not modelish: continue
        key=s.lower()
        if key in seen: continue
        seen.add(key)
        kinds=sorted({k for k in KINDS if k in ns})
        matches.append({'source':source,'offset':off,'value':s,'tokens':hit,'kinds':kinds})
    # Stable priority: prefab/mesh first, then material/texture, then animation.
    def pr(m):
        kinds=set(m['kinds'])
        rank=0
        if 'prefab' in kinds: rank+=100
        if 'mesh' in kinds: rank+=90
        if 'material' in kinds or 'matetial' in kinds or 'materail' in kinds: rank+=70
        if 'texture' in kinds: rank+=60
        if 'animation' in kinds or 'animator' in kinds: rank+=50
        rank+=max((len(x) for x in m['tokens']),default=0)
        return (-rank,m['value'].lower())
    matches.sort(key=pr)
    bundle_matches=[m for m in matches if m['value'].lower().endswith('.bundle')]
    kinds=sorted({k for m in bundle_matches for k in m['kinds']})
    row={
      'heroId':e['heroId'],'name':e['name'],'appearance':e['appearance'],
      'formationKind':e['formationKind'],'queueModelPath':e['queueModelPath'],
      'identityTokens':tokens,'bundleCount':len(bundle_matches),'assetKinds':kinds,
      'bundleMatches':bundle_matches[:120]
    }
    # Complete enough for Phase41 extraction when a prefab plus geometry/texture family is present.
    row['hasPrefab']=('prefab' in kinds)
    row['hasGeometry']=('mesh' in kinds or e['formationKind']=='soldier')
    row['hasSurface']=any(k in kinds for k in ('material','matetial','materail','texture'))
    row['bundleSetReady']=bool(bundle_matches and row['hasPrefab'] and row['hasGeometry'] and row['hasSurface'])
    rows.append(row)
    print(f"UNIT {e['heroId']} {e['name']}: kind={e['formationKind']} bundles={len(bundle_matches)} kinds={','.join(kinds) or '-'} ready={row['bundleSetReady']}")

out={
 'format':'WFGG_LASTWAR_FORMATION_UNIT_BUNDLE_SET_31_V1','networkUsed':False,
 'sourceMap':'lastwar-hero-formation-unit-authoritative-map.js','catalogSources':sources,
 'heroCount':31,'rows':rows
}
out['resolvedBundleSets']=sum(1 for x in rows if x['bundleCount']>0)
out['readyBundleSets']=sum(1 for x in rows if x['bundleSetReady'])
out['unresolvedHeroIds']=[x['heroId'] for x in rows if x['bundleCount']==0]
out['notReadyHeroIds']=[x['heroId'] for x in rows if not x['bundleSetReady']]
outp.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')

lines=[
 'WfGg Last War LAB — PHASE 40 AUTHORITATIVE FORMATION BUNDLE SET 31',
 'OFFLINE ONLY · exact HeroAppearance.queue_model_path identities',
 f"heroes=31 resolvedBundleSets={out['resolvedBundleSets']}/31 readyBundleSets={out['readyBundleSets']}/31",
 ''
]
for x in rows:
    lines.append(f"HERO {x['heroId']} {x['name']} kind={x['formationKind']} bundles={x['bundleCount']} ready={x['bundleSetReady']}")
    lines.append('  queue_model_path='+x['queueModelPath'])
    lines.append('  identityTokens='+','.join(x['identityTokens']))
    lines.append('  kinds='+(','.join(x['assetKinds']) or '-'))
    for m in x['bundleMatches'][:20]: lines.append('  bundle='+m['value'])
    lines.append('')
lines.append('unresolvedHeroIds='+','.join(map(str,out['unresolvedHeroIds'])))
lines.append('notReadyHeroIds='+','.join(map(str,out['notReadyHeroIds'])))
reportp.write_text('\n'.join(lines)+'\n',encoding='utf-8')
print('PHASE40_OK',f"resolved={out['resolvedBundleSets']}/31",f"ready={out['readyBundleSets']}/31",f"unresolved={len(out['unresolvedHeroIds'])}")
PYEOF

python "$PY" "$MAP" "$OUT" "$REPORT" "${APK_PATHS[@]}"
rm -f "$PY"

git add -f frontend/lab/master-assets-v2/meta/formation-unit-bundle-set-31.json scripts/lastwar-phase40-authoritative-formation-bundle-set.sh
if git diff --cached --quiet -- frontend/lab/master-assets-v2/meta/formation-unit-bundle-set-31.json scripts/lastwar-phase40-authoritative-formation-bundle-set.sh; then
  echo "Aucun changement à committer."
else
  git commit -m "lab: resolve authoritative formation bundle sets for all 31 heroes"
fi
git push origin "$BRANCH"

echo "=== PHASE 40 TERMINEE ==="
echo "Rapport: $REPORT"
echo "Ne lance pas encore la page Escouades."
echo "main non modifiée."
