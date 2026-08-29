#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — PHASE 39
# DISCOVER AUTHENTIC VEHICLE IDENTITIES FOR ALL 31 HEROES
# CODE ONLY. OFFLINE ONLY. Reads installed static asset catalog only.
# No Last War network connection. No gameplay automation.

PKG="com.fun.lastwar.gp"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
HERO_MAP="$ROOT/frontend/lab/lastwar-hero-authoritative-map.js"
OUT="$ROOT/frontend/lab/master-assets-v2/meta/hero-vehicle-catalog-seed.json"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_PHASE39_ALL31_VEHICLE_IDENTITIES.txt"
PY="${TMPDIR:-${HOME}/.cache}/wfgg-phase39-all31-vehicle-identities.py"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
command -v python >/dev/null 2>&1 || fail "python absent"
command -v pm >/dev/null 2>&1 || fail "commande Android pm absente"
[[ -s "$HERO_MAP" ]] || fail "mapping 31 héros absent: $HERO_MAP"
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

hero_map_path=Path(sys.argv[1]); outp=Path(sys.argv[2]); reportp=Path(sys.argv[3]); apk_paths=sys.argv[4:]
text=hero_map_path.read_text(encoding='utf-8')

# Authoritative 31-hero contract from the decoded LW_Hero/LW_Hero_Appearance mapping.
rx=re.compile(r"\{heroId:(\d+),name:'([^']+)'[^}]*?appearance:(\d+)[^}]*?queueIcon:'([^']+)'",re.S)
heroes=[]
for m in rx.finditer(text):
    heroes.append({'heroId':int(m.group(1)),'name':m.group(2),'appearance':int(m.group(3)),'queueIcon':m.group(4)})
if len(heroes)!=31:
    raise SystemExit(f'expected 31 heroes, parsed {len(heroes)}')

# Known internal vehicle aliases already established by portrait names, catalogue paths,
# and previous extraction work. These are identity hints only; Phase 39 still requires a
# real Models/Cars path from the installed asset catalogue before accepting a vehicle root.
SPECIAL={
  30002:['loki','black_widow','blackwidow'],
  30003:['kane','basilone'],
  30004:['ambolt','hager'],
  30005:['gump','gump3'],
  40007:['elsa'],
  40008:['farhad'],
  40009:['richard'],
  40013:['braz','lambo'],
  40015:['cage'],
  40016:['maxwell','cruzo'],
  40020:['monica','japanmonica'],
  50006:['murphy','audie','audie_murphy'],
  50007:['williams','rick'],
  50008:['marshall','nimitz'],
  50009:['kimberly','katyusha'],
  50010:['stetmann','stetman'],
  50013:['mcgregor','ewan_mcgregor'],
  50014:['fiona'],
  50015:['swift','tom'],
  50016:['tesla'],
  50017:['dva','d_va'],
  50018:['schuyler','sally_ride','sallyride'],
  50019:['carlie','carly'],
  50020:['morrison'],
  50021:['lucius'],
  50022:['adam'],
  50023:['mason','david_stirling','davidstirling'],
  50025:['violet','doctor_poison','doctorpoison'],
  50026:['scarlett','misshot','miss_hot'],
  50027:['sarah','sara'],
  50028:['venom','alex'],
}

def norm(s):
    return re.sub(r'[^a-z0-9]+','_',str(s or '').lower()).strip('_')

def icon_alias(icon):
    s=norm(icon)
    s=re.sub(r'^hero_icon_','',s)
    for suff in ('_ur','_ssr','_sr','02','03','2','3'):
        if s.endswith(suff): s=s[:-len(suff)].rstrip('_')
    return s

for h in heroes:
    vals={norm(h['name']),icon_alias(h['queueIcon'])}
    vals.update(norm(x) for x in SPECIAL.get(h['heroId'],[]))
    h['aliases']=sorted(x for x in vals if x)

# Gather printable bundle/path strings from the installed static catalogue files.
ENTRY_NAMES=(
  'assets/AssetBundles/BundleOffsetTable.bytes',
  'assets/AssetBundles/AliasOffsetTable.bytes',
  'assets/AssetBundles/gameres',
)
strings=set(); sources=[]
printable=re.compile(rb'[ -~]{20,}')
for apk in apk_paths:
    try:
        with zipfile.ZipFile(apk) as z:
            for entry in ENTRY_NAMES:
                try: raw=z.read(entry)
                except KeyError: continue
                sources.append({'apk':os.path.basename(apk),'entry':entry,'bytes':len(raw)})
                for m in printable.finditer(raw):
                    s=m.group().decode('ascii','ignore')
                    # A printable run can contain separators/control remnants; split around .bundle.
                    for hit in re.findall(r'[A-Za-z0-9_./-]{8,}\.bundle',s,re.I):
                        strings.add(hit)
                    for hit in re.findall(r'Assets/[A-Za-z0-9_./ -]{8,}',s,re.I):
                        strings.add(hit.strip())
    except Exception:
        pass
if not strings:
    raise SystemExit('asset catalogue strings not found')

# Vehicle paths only. Accept both historical Art/Dir/Cars and newer _Art_LastWar/Models/Cars forms.
vehicle_strings=[]
for s in strings:
    n=norm(s)
    low=s.lower()
    if ('cars' in low or 'models_new_cars' in low or '_models_cars_' in n or '_dir_cars_' in n) and ('a_hero_' in low or 'hero_' in low):
        vehicle_strings.append(s)
vehicle_strings=sorted(set(vehicle_strings))

# Derive a canonical internal vehicle root, e.g. a_hero_farhad_01, a_hero_misshot_01,
# a_hero_katyusha_02, a_hero_monica_wzsj. Keep variants so later extraction can resolve skins.
def roots_from_path(s):
    low=s.lower()
    roots=[]
    # Slash-style source path.
    for m in re.finditer(r'(a_hero_[a-z0-9_]+?)(?:/(?:animation|animator|material|mesh|prefab|texture)|\.(?:prefab|fbx)|$)',low):
        roots.append(m.group(1))
    # Flattened bundle path.
    for m in re.finditer(r'(a_hero_[a-z0-9_]+?)(?:_(?:animation|animator|material|mesh|prefab|texture)(?:_|\.)|\.bundle)',low):
        roots.append(m.group(1))
    # Conservative fallback up to common version suffix.
    if not roots:
        m=re.search(r'(a_hero_[a-z0-9]+(?:_[a-z0-9]+){0,4})',low)
        if m: roots.append(m.group(1))
    return sorted(set(norm(x) for x in roots if x))

# Family terms used only as metadata; no family is invented when absent.
FAMILY_TERMS={
  'tank':('tank','tanke','track','turret','chassis'),
  'aircraft':('aircraft','plane','helic','rotor','feiji'),
  'missile':('missile','missle','rocket','launcher','daodan'),
}

def alias_match(root,path,alias):
    rf=norm(root).replace('_',''); pf=norm(path).replace('_',''); af=norm(alias).replace('_','')
    if not af:return False
    return af in rf or af in pf

def score_candidate(h,path,root):
    score=0; evidence=[]
    low=path.lower(); r=norm(root)
    for a in h['aliases']:
        if alias_match(root,path,a):
            # Root match is much stronger than arbitrary path-context match.
            if norm(a).replace('_','') in r.replace('_',''):
                score+=6000+len(a)*25; evidence.append('root:'+a)
            else:
                score+=1800+len(a)*10; evidence.append('path:'+a)
    if '/cars/' in low or '_dir_cars_' in low or 'models_new_cars' in low: score+=1200
    if '_prefab' in low or '/prefab' in low: score+=900
    if '_mesh' in low or '/mesh' in low: score+=350
    if '_texture' in low or '/texture' in low: score+=100
    if 'effect' in low or '/vfx/' in low: score-=1200
    return score,evidence

catalog=[]
for h in heroes:
    cand={}
    for path in vehicle_strings:
        for root in roots_from_path(path):
            score,evidence=score_candidate(h,path,root)
            if score<=0: continue
            row=cand.setdefault(root,{'vehicleRoot':root,'score':0,'paths':[],'evidence':set(),'familyEvidence':set()})
            row['score']=max(row['score'],score)
            row['paths'].append(path)
            row['evidence'].update(evidence)
            n=norm(path)+' '+root
            for family,terms in FAMILY_TERMS.items():
                if any(t in n for t in terms): row['familyEvidence'].add(family)
    rows=[]
    for row in cand.values():
        # Bundle diversity is useful evidence that this is a complete vehicle asset root.
        kinds=set()
        for p in row['paths']:
            lp=p.lower()
            for k in ('animation','animator','material','mesh','prefab','texture'):
                if k in lp:kinds.add(k)
        row['assetKinds']=sorted(kinds)
        row['score'] += len(kinds)*220
        if 'prefab' in kinds and 'mesh' in kinds: row['score']+=1000
        row['paths']=sorted(set(row['paths']))[:80]
        row['evidence']=sorted(row['evidence'])
        row['familyEvidence']=sorted(row['familyEvidence'])
        rows.append(row)
    rows.sort(key=lambda x:(x['score'],len(x['assetKinds']),len(x['paths'])),reverse=True)
    selected=rows[0] if rows else None
    confidence='none'
    if selected:
        second=rows[1]['score'] if len(rows)>1 else 0
        ratio=selected['score']/max(1,second)
        if selected['score']>=8500 and len(selected['assetKinds'])>=3 and ratio>=1.15: confidence='high'
        elif selected['score']>=5500 and len(selected['assetKinds'])>=2: confidence='medium'
        else: confidence='low'
    catalog.append({
      'heroId':h['heroId'],'name':h['name'],'appearance':h['appearance'],'queueIcon':h['queueIcon'],
      'aliases':h['aliases'],'selectionConfidence':confidence,'selected':selected,'alternates':rows[1:6]
    })

out={
  'format':'WFGG_LASTWAR_HERO_VEHICLE_CATALOG_SEED_V1',
  'networkUsed':False,
  'source':'installed AssetBundles catalog paths',
  'heroContractCount':31,
  'catalogSourceFiles':sources,
  'vehiclePathCount':len(vehicle_strings),
  'heroes':catalog,
}
out['selectedCount']=sum(1 for x in catalog if x['selected'])
out['highConfidenceCount']=sum(1 for x in catalog if x['selectionConfidence']=='high')
out['mediumOrHighCount']=sum(1 for x in catalog if x['selectionConfidence'] in ('high','medium'))
out['unresolvedHeroIds']=[x['heroId'] for x in catalog if not x['selected']]
outp.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')

lines=[
 'WfGg Last War LAB — PHASE 39 ALL 31 VEHICLE IDENTITIES',
 'OFFLINE ONLY · installed static asset catalogue · no generated artwork',
 f"heroContract=31 vehiclePaths={len(vehicle_strings)} selected={out['selectedCount']}/31 high={out['highConfidenceCount']}/31 mediumOrHigh={out['mediumOrHighCount']}/31",
 ''
]
for x in catalog:
    lines.append(f"HERO {x['heroId']} {x['name']} confidence={x['selectionConfidence']}")
    if x['selected']:
        s=x['selected']
        lines.append(f"  vehicleRoot={s['vehicleRoot']} score={s['score']} kinds={','.join(s['assetKinds']) or '-'} familyEvidence={','.join(s['familyEvidence']) or '-'}")
        lines.append(f"  evidence={','.join(s['evidence']) or '-'}")
        for p in s['paths'][:6]: lines.append(f"  path={p}")
        for alt in x['alternates'][:2]:
            lines.append(f"  ALT root={alt['vehicleRoot']} score={alt['score']} kinds={','.join(alt['assetKinds']) or '-'}")
    else:
        lines.append('  UNRESOLVED')
    lines.append('')
lines.append('unresolvedHeroIds='+','.join(map(str,out['unresolvedHeroIds'])))
reportp.write_text('\n'.join(lines)+'\n',encoding='utf-8')
print('PHASE39_OK',f"selected={out['selectedCount']}/31",f"high={out['highConfidenceCount']}/31",f"mediumOrHigh={out['mediumOrHighCount']}/31",f"unresolved={len(out['unresolvedHeroIds'])}")
PYEOF

python "$PY" "$HERO_MAP" "$OUT" "$REPORT" "${APK_PATHS[@]}"
rm -f "$PY"

git add -f frontend/lab/master-assets-v2/meta/hero-vehicle-catalog-seed.json scripts/lastwar-phase39-discover-all31-vehicle-identities.sh
if git diff --cached --quiet -- frontend/lab/master-assets-v2/meta/hero-vehicle-catalog-seed.json scripts/lastwar-phase39-discover-all31-vehicle-identities.sh; then
  echo "Aucun changement à committer."
else
  git commit -m "lab: discover vehicle identities for all 31 heroes"
fi
git push origin "$BRANCH"

echo "=== PHASE 39 TERMINEE ==="
echo "Référentiel 31 héros: frontend/lab/master-assets-v2/meta/hero-vehicle-catalog-seed.json"
echo "Rapport court: Téléchargements/WFGG_LASTWAR_PHASE39_ALL31_VEHICLE_IDENTITIES.txt"
echo "Ne lance pas encore la page Escouades."
echo "main non modifiée."
