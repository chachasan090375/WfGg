#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — PHASE 39B
# Recover the remaining hero->vehicle identities without generic fallback.
# CODE ONLY. OFFLINE ONLY. No Last War network connection.

PKG="com.fun.lastwar.gp"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
SEED="$ROOT/frontend/lab/master-assets-v2/meta/hero-vehicle-catalog-seed.json"
OUT="$ROOT/frontend/lab/master-assets-v2/meta/hero-vehicle-catalog-seed-v2.json"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_PHASE39B_ALL31_VEHICLE_IDENTITIES_STRICT.txt"
PY="${TMPDIR:-${HOME}/.cache}/wfgg-phase39b-vehicle-identities.py"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
command -v python >/dev/null 2>&1 || fail "python absent"
command -v pm >/dev/null 2>&1 || fail "commande Android pm absente"
[[ -s "$SEED" ]] || fail "Phase 39 seed absent: $SEED"
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche active incorrecte"

mapfile -t APK_PATHS < <(pm path "$PKG" 2>/dev/null | sed -n 's/^package://p')
if [[ ${#APK_PATHS[@]} -eq 0 ]]; then
  mapfile -t APK_PATHS < <(cmd package path "$PKG" 2>/dev/null | sed -n 's/^package://p')
fi
[[ ${#APK_PATHS[@]} -gt 0 ]] || fail "installation Last War introuvable ($PKG)"

mkdir -p "$(dirname "$OUT")" "$(dirname "$PY")"
cat > "$PY" <<'PYEOF'
from pathlib import Path
import json, os, re, sys, zipfile

seedp=Path(sys.argv[1]); outp=Path(sys.argv[2]); reportp=Path(sys.argv[3]); apk_paths=sys.argv[4:]
seed=json.loads(seedp.read_text(encoding='utf-8'))
heroes=seed.get('heroes') or []
if len(heroes)!=31: raise SystemExit(f'expected 31 heroes in seed, got {len(heroes)}')

# Seven Phase-39 low-confidence cases need broader vehicle-path discovery.
# Aliases below are grounded in authoritative portrait names / prior static-path evidence.
RECOVERY_ALIASES={
  30005:['gump','gump3'],
  50013:['mcgregor','ewan_mcgregor','ewan'],
  50014:['fiona'],
  50018:['schuyler','sally_ride','sally'],
  50019:['carlie','carly'],
  50023:['mason','david_stirling','david'],
  50025:['violet','doctor_poison','doctorpoison','poison'],
}

def norm(s): return re.sub(r'[^a-z0-9]+','_',str(s or '').lower()).strip('_')
def flat(s): return norm(s).replace('_','')

def has_alias(text, aliases):
    f=flat(text)
    return sorted({a for a in aliases if flat(a) and flat(a) in f},key=len,reverse=True)

# Source catalogue surfaces where real vehicle/display prefabs have already been observed.
ENTRY_NAMES=(
  'assets/AssetBundles/BundleOffsetTable.bytes',
  'assets/AssetBundles/AliasOffsetTable.bytes',
  'assets/AssetBundles/gameres',
)
printable=re.compile(rb'[ -~]{18,}')
raw_strings=set(); sources=[]
for apk in apk_paths:
    try:
        with zipfile.ZipFile(apk) as z:
            for entry in ENTRY_NAMES:
                try: raw=z.read(entry)
                except KeyError: continue
                sources.append({'apk':os.path.basename(apk),'entry':entry,'bytes':len(raw)})
                for m in printable.finditer(raw):
                    s=m.group().decode('ascii','ignore')
                    # Preserve explicit Assets paths.
                    for x in re.findall(r'Assets/[A-Za-z0-9_./ -]{8,}',s,re.I): raw_strings.add(x.strip())
                    # Preserve bundle names, including flattened paths.
                    for x in re.findall(r'[A-Za-z0-9_./-]{8,}\.bundle',s,re.I): raw_strings.add(x)
    except Exception:
        pass

# Broad but still vehicle/display-specific filter. HeroUniqueWeapon is deliberately excluded:
# it can share hero aliases but is not the formation vehicle prefab.
def relevant(s):
    low=s.lower(); n=norm(s)
    if 'a_hero_' not in low: return False
    if 'herouniqueweapon' in low: return False
    return any(k in low or k in n for k in (
      'models/cars','models_new/cars','models_new/cars','character/vehicle',
      'inspecialdir','lwbattle/hero','_dir_cars_','_models_cars_','_models_new_cars_',
      '_character_vehicle_','_inspecialdir_','_lwbattle_hero_'
    ))

candidates=[s for s in raw_strings if relevant(s)]

# Extract plausible vehicle roots from slash and flattened bundle forms.
def roots(s):
    low=s.lower(); out=[]
    # Slash path segments beginning with A_Hero_. Keep each such segment separately.
    for seg in re.split(r'[/\\]',low):
        if seg.startswith('a_hero_'):
            seg=re.sub(r'\.(prefab|fbx)$','',seg)
            if len(seg)>=8: out.append(norm(seg))
    # Flattened bundle names: stop before asset-kind markers.
    for m in re.finditer(r'(a_hero_[a-z0-9_]+?)(?=_(?:animation|animator|material|mesh|prefab|texture|camera|timeline)(?:_|\.)|\.bundle)',low):
        out.append(norm(m.group(1)))
    # InSpecialDir often uses ...a_hero_david_01_prefab_a_hero_david_01...
    for m in re.finditer(r'(a_hero_[a-z0-9_]+?)_prefab_',low): out.append(norm(m.group(1)))
    # Drop clearly nested duplicated variants only when a shorter exact prefix is present.
    return sorted({x for x in out if x})

ASSET_KIND=('animation','animator','material','mesh','prefab','texture','camera','timeline')

def score_path(path, root, aliases):
    rh=has_alias(root,aliases); ph=has_alias(path,aliases)
    if not rh and not ph: return None
    low=path.lower(); score=0; evidence=[]
    if rh:
        score += 8000 + max(len(flat(a)) for a in rh)*30
        evidence.extend('root:'+a for a in rh)
    elif ph:
        score += 2600 + max(len(flat(a)) for a in ph)*15
        evidence.extend('path:'+a for a in ph)
    if 'character/vehicle' in low or '_character_vehicle_' in norm(path): score+=2200
    if 'models/cars' in low or 'models_new/cars' in low or '_dir_cars_' in norm(path) or '_models_' in norm(path) and '_cars_' in norm(path): score+=1800
    if 'inspecialdir' in low: score+=1100
    if 'lwbattle/hero' in low: score+=700
    for k in ASSET_KIND:
        if k in low: score+=120
    if 'effect' in low or '_eff_' in norm(path): score-=1800
    return score,evidence

recovered={}
for hid,als0 in RECOVERY_ALIASES.items():
    aliases=[norm(x) for x in als0]
    byroot={}
    for path in candidates:
        for root in roots(path):
            got=score_path(path,root,aliases)
            if not got: continue
            score,evidence=got
            row=byroot.setdefault(root,{'vehicleRoot':root,'score':0,'paths':[],'evidence':set(),'assetKinds':set(),'sourceFamilies':set()})
            row['score']=max(row['score'],score)
            row['paths'].append(path); row['evidence'].update(evidence)
            low=path.lower()
            for k in ASSET_KIND:
                if k in low: row['assetKinds'].add(k)
            if 'character/vehicle' in low or '_character_vehicle_' in norm(path): row['sourceFamilies'].add('Character/Vehicle')
            if 'models/cars' in low or 'models_new/cars' in low or '_dir_cars_' in norm(path): row['sourceFamilies'].add('Models/Cars')
            if 'inspecialdir' in low: row['sourceFamilies'].add('InSpecialDir')
            if 'lwbattle/hero' in low: row['sourceFamilies'].add('LWBattle/Hero')
    rows=[]
    for r in byroot.values():
        r['paths']=sorted(set(r['paths']))[:100]
        r['evidence']=sorted(r['evidence'])
        r['assetKinds']=sorted(r['assetKinds'])
        r['sourceFamilies']=sorted(r['sourceFamilies'])
        r['score'] += len(r['assetKinds'])*180 + len(r['sourceFamilies'])*400
        if 'prefab' in r['assetKinds']: r['score']+=600
        if 'mesh' in r['assetKinds']: r['score']+=500
        rows.append(r)
    rows.sort(key=lambda x:(x['score'],len(x['assetKinds']),len(x['paths'])),reverse=True)
    recovered[hid]=rows

# Preserve only Phase-39 medium/high results. All low/no-evidence rows are discarded.
out_heroes=[]
for h in heroes:
    hid=int(h.get('heroId') or 0)
    old_conf=h.get('selectionConfidence') or 'none'
    old_sel=h.get('selected')
    old_has_evidence=bool((old_sel or {}).get('evidence'))
    if old_conf in ('high','medium') and old_sel and old_has_evidence:
        row=dict(h)
        row['resolutionSource']='phase39_models_cars'
        out_heroes.append(row)
        continue

    rows=recovered.get(hid,[])
    sel=rows[0] if rows else None
    conf='none'
    if sel:
        second=rows[1]['score'] if len(rows)>1 else 0
        ratio=sel['score']/max(1,second)
        if sel['score']>=10500 and ('Character/Vehicle' in sel['sourceFamilies'] or 'Models/Cars' in sel['sourceFamilies']) and ratio>=1.05:
            conf='high'
        elif sel['score']>=7000:
            conf='medium'
        else:
            conf='low'
    row={k:v for k,v in h.items() if k not in ('selected','alternates','selectionConfidence')}
    row['selectionConfidence']=conf
    row['selected']=sel if conf in ('high','medium') else None
    row['alternates']=rows[1:6] if rows else []
    row['recoveryCandidates']=rows[:6]
    row['resolutionSource']='phase39b_broad_vehicle_paths' if row['selected'] else 'unresolved'
    out_heroes.append(row)

out={
  'format':'WFGG_LASTWAR_HERO_VEHICLE_CATALOG_SEED_V2',
  'networkUsed':False,
  'source':'Phase39 strict + broad Character/Vehicle/Models/Cars recovery',
  'heroContractCount':31,
  'catalogSourceFiles':sources,
  'broadCandidatePathCount':len(candidates),
  'heroes':out_heroes,
}
out['selectedCount']=sum(1 for x in out_heroes if x.get('selected'))
out['highConfidenceCount']=sum(1 for x in out_heroes if x.get('selectionConfidence')=='high')
out['mediumOrHighCount']=sum(1 for x in out_heroes if x.get('selectionConfidence') in ('high','medium'))
out['unresolvedHeroIds']=[x['heroId'] for x in out_heroes if not x.get('selected')]
outp.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')

lines=[
 'WfGg Last War LAB — PHASE 39B STRICT ALL-31 VEHICLE IDENTITIES',
 'OFFLINE ONLY · no generic fallback · alias evidence required',
 f"selected={out['selectedCount']}/31 high={out['highConfidenceCount']}/31 mediumOrHigh={out['mediumOrHighCount']}/31 unresolved={len(out['unresolvedHeroIds'])}",
 ''
]
for h in out_heroes:
    lines.append(f"HERO {h['heroId']} {h['name']} confidence={h['selectionConfidence']} source={h['resolutionSource']}")
    s=h.get('selected')
    if s:
        lines.append(f"  vehicleRoot={s.get('vehicleRoot')} score={s.get('score')} families={','.join(s.get('sourceFamilies') or []) or '-'} kinds={','.join(s.get('assetKinds') or []) or '-'}")
        lines.append('  evidence='+','.join(s.get('evidence') or []))
        for p in (s.get('paths') or [])[:8]: lines.append('  path='+p)
    else:
        lines.append('  UNRESOLVED_NO_AUTHENTIC_ALIAS_MATCH')
        for c in (h.get('recoveryCandidates') or [])[:3]:
            lines.append(f"  candidate root={c.get('vehicleRoot')} score={c.get('score')} evidence={','.join(c.get('evidence') or [])}")
    lines.append('')
lines.append('unresolvedHeroIds='+','.join(map(str,out['unresolvedHeroIds'])))
reportp.write_text('\n'.join(lines)+'\n',encoding='utf-8')
print('PHASE39B_OK',f"selected={out['selectedCount']}/31",f"high={out['highConfidenceCount']}/31",f"mediumOrHigh={out['mediumOrHighCount']}/31",f"unresolved={len(out['unresolvedHeroIds'])}")
PYEOF

python "$PY" "$SEED" "$OUT" "$REPORT" "${APK_PATHS[@]}"
rm -f "$PY"

git add -f frontend/lab/master-assets-v2/meta/hero-vehicle-catalog-seed-v2.json scripts/lastwar-phase39b-recover-unresolved-vehicle-identities.sh
if git diff --cached --quiet -- frontend/lab/master-assets-v2/meta/hero-vehicle-catalog-seed-v2.json scripts/lastwar-phase39b-recover-unresolved-vehicle-identities.sh; then
  echo "Aucun changement à committer."
else
  git commit -m "lab: recover unresolved hero vehicle identities strictly"
fi
git push origin "$BRANCH"

echo "=== PHASE 39B TERMINEE ==="
echo "Référentiel strict: frontend/lab/master-assets-v2/meta/hero-vehicle-catalog-seed-v2.json"
echo "Rapport: Téléchargements/WFGG_LASTWAR_PHASE39B_ALL31_VEHICLE_IDENTITIES_STRICT.txt"
echo "Ne lance pas encore la page Escouades."
echo "main non modifiée."
