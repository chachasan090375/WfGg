#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — PHASE 39C
# Isolate the final 4 hero->vehicle identities by eliminating the 27 already
# claimed vehicle families, then measuring direct/proximity evidence in the
# installed asset catalog. CODE ONLY. OFFLINE ONLY.

PKG="com.fun.lastwar.gp"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
IN="$ROOT/frontend/lab/master-assets-v2/meta/hero-vehicle-catalog-seed-v2.json"
OUT="$ROOT/frontend/lab/master-assets-v2/meta/hero-vehicle-final-four-graph.json"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_PHASE39C_FINAL_FOUR_VEHICLE_GRAPH.txt"
PY="${TMPDIR:-${HOME}/.cache}/wfgg-phase39c-final-four.py"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
command -v python >/dev/null 2>&1 || fail "python absent"
command -v pm >/dev/null 2>&1 || fail "commande Android pm absente"
[[ -s "$IN" ]] || fail "Phase 39B stricte absente: $IN"
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
from collections import defaultdict
import json, os, re, sys, zipfile

inp=Path(sys.argv[1]); outp=Path(sys.argv[2]); reportp=Path(sys.argv[3]); apk_paths=sys.argv[4:]
data=json.loads(inp.read_text(encoding='utf-8'))

TARGETS={
  30005:{'name':'Gump','aliases':['gump','gump3']},
  50014:{'name':'Fiona','aliases':['fiona']},
  50019:{'name':'Carlie','aliases':['carlie','carly','carly_zw']},
  50025:{'name':'Violet','aliases':['violet','doctor','doctor_poison','doctorpoison','doctor_poison02','doctor_poison3_ur']},
}
ENTRY_NAMES=(
  'assets/AssetBundles/gameres',
  'assets/AssetBundles/BundleOffsetTable.bytes',
  'assets/AssetBundles/AliasOffsetTable.bytes',
)

def norm(s): return re.sub(r'[^a-z0-9]+','_',str(s or '').lower()).strip('_')
def flat(s): return norm(s).replace('_','')

def root_core(root):
    s=norm(root)
    if 'a_hero_' in s: s=s.split('a_hero_',1)[1]
    # Some flattened names contain a second a_hero_ segment.
    if '_a_hero_' in s: s=s.split('_a_hero_',1)[0]
    # Preserve meaningful two-token identities first.
    special=('blackwidow','japanmonica','misshot','sally','ewan','david','audie','katyusha','morrison','stetman','tesla','dva','nimitz','rick','tom','lucius','farhad','maxwell','richard','basilone','hager','lambo','elsa','cage','adam','sara','alex')
    fs=flat(s)
    for x in special:
        if x in fs: return x
    parts=[p for p in s.split('_') if p]
    stop={'zhuanwu','zhuangwu','awaken','wzsj','ur','ssr','sr','show','battle','lod','high','low','vfx'}
    clean=[]
    for p in parts:
        if p in stop or p.isdigit() or re.fullmatch(r'v\d+',p): break
        clean.append(p)
    return '_'.join(clean[:3]) if clean else s

def extract_roots(text):
    low=text.lower(); out=[]
    # Slash paths.
    for m in re.finditer(r'a_hero_[a-z0-9_]+',low):
        x=m.group(0)
        x=re.split(r'_(?:animation|animator|material|mesh|prefab|texture|camera|timeline|effect|eff)(?:_|$)',x,1)[0]
        if len(x)>=8: out.append(norm(x))
    return sorted(set(out))

def is_vehicle_context(s):
    low=s.lower(); n=norm(s)
    if 'a_hero_' not in low:return False
    if 'herouniqueweapon' in low:return False
    return any(k in low or k in n for k in (
      'models/cars','models_new/cars','character/vehicle','inspecialdir','lwbattle/hero',
      '_dir_cars_','_models_cars_','_models_new_cars_','_character_vehicle_','_inspecialdir_','_lwbattle_hero_'
    ))

# 1) Read raw catalog surfaces.
sources=[]; blobs=[]; printable_runs=[]
printable=re.compile(rb'[ -~]{16,}')
for apk in apk_paths:
    try:
        with zipfile.ZipFile(apk) as z:
            for entry in ENTRY_NAMES:
                try: raw=z.read(entry)
                except KeyError: continue
                sources.append({'apk':os.path.basename(apk),'entry':entry,'bytes':len(raw)})
                blobs.append((os.path.basename(apk),entry,raw))
                for m in printable.finditer(raw):
                    s=m.group().decode('ascii','ignore')
                    if 'a_hero_' in s.lower() or any(a in s.lower() for t in TARGETS.values() for a in t['aliases']):
                        printable_runs.append((os.path.basename(apk),entry,m.start(),s))
    except Exception:
        pass
if not blobs: raise SystemExit('asset catalog surfaces unavailable')

# 2) Vehicle root inventory + asset kinds / source families.
root_info={}
for apk,entry,pos,s in printable_runs:
    # A long printable run can contain many records. Extract path/bundle fragments separately.
    frags=[]
    frags += re.findall(r'Assets/[A-Za-z0-9_./ -]{8,}',s,re.I)
    frags += re.findall(r'[A-Za-z0-9_./-]{8,}\.bundle',s,re.I)
    if not frags and 'a_hero_' in s.lower(): frags=[s]
    for frag in frags:
        if not is_vehicle_context(frag): continue
        for root in extract_roots(frag):
            row=root_info.setdefault(root,{
              'root':root,'core':root_core(root),'paths':set(),'assetKinds':set(),'sourceFamilies':set(),'occurrences':0
            })
            row['occurrences']+=1; row['paths'].add(frag.strip())
            low=frag.lower()
            for k in ('animation','animator','material','mesh','prefab','texture','camera','timeline'):
                if k in low: row['assetKinds'].add(k)
            if 'character/vehicle' in low or '_character_vehicle_' in norm(frag): row['sourceFamilies'].add('Character/Vehicle')
            if 'models/cars' in low or 'models_new/cars' in low or '_dir_cars_' in norm(frag) or ('_models_' in norm(frag) and '_cars_' in norm(frag)): row['sourceFamilies'].add('Models/Cars')
            if 'inspecialdir' in low or '_inspecialdir_' in norm(frag): row['sourceFamilies'].add('InSpecialDir')
            if 'lwbattle/hero' in low or '_lwbattle_hero_' in norm(frag): row['sourceFamilies'].add('LWBattle/Hero')

# 3) Remove families already authentically claimed by the 27 selected heroes.
claimed_cores=set(); claimed=[]
for h in data.get('heroes',[]):
    s=h.get('selected') or {}
    if not s: continue
    root=norm(s.get('vehicleRoot') or '')
    if not root: continue
    core=root_core(root); claimed_cores.add(core)
    claimed.append({'heroId':h.get('heroId'),'name':h.get('name'),'root':root,'core':core})

unclaimed={r:info for r,info in root_info.items() if info['core'] not in claimed_cores}

# 4) Direct evidence: target alias and unclaimed A_Hero root in the same printable run.
direct=defaultdict(lambda: defaultdict(list))
for apk,entry,pos,s in printable_runs:
    sl=s.lower()
    present=[]
    for hid,t in TARGETS.items():
        hits=[a for a in t['aliases'] if flat(a) in flat(sl)]
        if hits: present.append((hid,hits))
    if not present: continue
    roots=[r for r in extract_roots(s) if r in unclaimed]
    if not roots: continue
    for hid,hits in present:
        for r in roots:
            direct[hid][r].append({'apk':apk,'entry':entry,'offset':pos,'aliases':hits,'context':s[:700]})

# 5) Binary proximity evidence: locate aliases and inspect +/- 1600 bytes for unclaimed roots.
prox=defaultdict(lambda: defaultdict(list))
for apk,entry,raw in blobs:
    low=raw.lower()
    for hid,t in TARGETS.items():
        seen_positions=set()
        for alias in t['aliases']:
            pat=alias.lower().encode()
            if len(pat)<4: continue
            p=0; n=0
            while n<80:
                p=low.find(pat,p)
                if p<0: break
                if p in seen_positions: p+=1; continue
                seen_positions.add(p); n+=1
                a=max(0,p-1600); b=min(len(raw),p+1600)
                window=raw[a:b]
                txt=' '.join(m.group().decode('ascii','ignore') for m in printable.finditer(window))
                roots=[r for r in extract_roots(txt) if r in unclaimed]
                for r in roots:
                    # Find approximate textual root distance when possible.
                    rf=r.encode(); rp=low.find(rf,a,b)
                    dist=abs(rp-p) if rp>=0 else 1600
                    prox[hid][r].append({'apk':apk,'entry':entry,'alias':alias,'aliasOffset':p,'distance':dist,'context':txt[:700]})
                p+=len(pat)

# 6) Candidate scoring. Completeness alone can NEVER resolve identity.
results=[]
for hid,t in TARGETS.items():
    rows=[]
    for r,info in unclaimed.items():
        de=direct[hid].get(r,[]); pe=prox[hid].get(r,[])
        evidence_score=0
        if de: evidence_score += 12000 + min(4,len(de))*1800
        if pe:
            mind=min(x['distance'] for x in pe)
            if mind<=180:evidence_score+=8000
            elif mind<=500:evidence_score+=5000
            elif mind<=1000:evidence_score+=2600
            else:evidence_score+=900
            evidence_score+=min(5,len(pe))*250
        completeness=len(info['assetKinds'])*260 + len(info['sourceFamilies'])*450
        if 'prefab' in info['assetKinds']: completeness+=500
        if 'mesh' in info['assetKinds']: completeness+=500
        score=evidence_score+completeness
        if evidence_score<=0: continue
        rows.append({
          'vehicleRoot':r,'core':info['core'],'score':score,'evidenceScore':evidence_score,
          'assetKinds':sorted(info['assetKinds']),'sourceFamilies':sorted(info['sourceFamilies']),
          'occurrences':info['occurrences'],'directEvidence':de[:8],'proximityEvidence':sorted(pe,key=lambda x:x['distance'])[:12],
          'paths':sorted(info['paths'])[:20]
        })
    rows.sort(key=lambda x:(x['score'],x['evidenceScore'],len(x['assetKinds'])),reverse=True)
    sel=rows[0] if rows else None; conf='none'
    if sel:
        second=rows[1]['score'] if len(rows)>1 else 0
        ratio=sel['score']/max(1,second)
        direct_ok=bool(sel['directEvidence'])
        near=min((x['distance'] for x in sel['proximityEvidence']),default=999999)
        if direct_ok and sel['evidenceScore']>=12000 and ratio>=1.10: conf='high'
        elif (direct_ok or near<=500) and sel['evidenceScore']>=5000 and ratio>=1.05: conf='medium'
        else: conf='low'
    results.append({'heroId':hid,'name':t['name'],'aliases':t['aliases'],'selectionConfidence':conf,'selected':sel if conf in ('high','medium') else None,'candidates':rows[:12]})

# Rank unclaimed families globally for manual inspection if a target remains unresolved.
family_rows=[]
bycore=defaultdict(list)
for r,info in unclaimed.items(): bycore[info['core']].append(info)
for core,arr in bycore.items():
    kinds=set(); fam=set(); paths=set(); occ=0; roots=[]
    for x in arr:
        roots.append(x['root']); kinds.update(x['assetKinds']); fam.update(x['sourceFamilies']); paths.update(x['paths']); occ+=x['occurrences']
    family_rows.append({'core':core,'roots':sorted(set(roots))[:30],'assetKinds':sorted(kinds),'sourceFamilies':sorted(fam),'occurrences':occ,'paths':sorted(paths)[:20]})
family_rows.sort(key=lambda x:(len(x['assetKinds']),len(x['sourceFamilies']),x['occurrences']),reverse=True)

out={
 'format':'WFGG_LASTWAR_FINAL_FOUR_VEHICLE_GRAPH_V1','networkUsed':False,
 'sourceFiles':sources,'claimedVehicleFamilies':claimed,'claimedCoreCount':len(claimed_cores),
 'allVehicleRoots':len(root_info),'unclaimedVehicleRoots':len(unclaimed),'unclaimedFamilyCount':len(bycore),
 'targets':results,'unclaimedFamilies':family_rows[:120]
}
out['resolvedCount']=sum(1 for x in results if x['selected'])
out['mediumOrHighCount']=sum(1 for x in results if x['selectionConfidence'] in ('medium','high'))
out['unresolvedHeroIds']=[x['heroId'] for x in results if not x['selected']]
outp.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')

lines=[
 'WfGg Last War LAB — PHASE 39C FINAL FOUR VEHICLE GRAPH',
 'OFFLINE ONLY · 27 claimed families eliminated · direct/proximity evidence required',
 f"vehicleRoots={len(root_info)} claimedCores={len(claimed_cores)} unclaimedRoots={len(unclaimed)} unclaimedFamilies={len(bycore)}",
 f"resolved={out['resolvedCount']}/4 mediumOrHigh={out['mediumOrHighCount']}/4 unresolved={len(out['unresolvedHeroIds'])}",''
]
for x in results:
    lines.append(f"HERO {x['heroId']} {x['name']} confidence={x['selectionConfidence']}")
    s=x.get('selected')
    if s:
        lines.append(f"  SELECTED root={s['vehicleRoot']} core={s['core']} score={s['score']} evidenceScore={s['evidenceScore']}")
    else: lines.append('  UNRESOLVED')
    for c in x['candidates'][:8]:
        mind=min((p['distance'] for p in c['proximityEvidence']),default=-1)
        lines.append(f"  CAND root={c['vehicleRoot']} core={c['core']} score={c['score']} evidence={c['evidenceScore']} direct={len(c['directEvidence'])} prox={len(c['proximityEvidence'])} minDist={mind} kinds={','.join(c['assetKinds']) or '-'} families={','.join(c['sourceFamilies']) or '-'}")
        for e in c['directEvidence'][:2]: lines.append(f"    DIRECT {e['entry']}@{e['offset']} aliases={','.join(e['aliases'])}")
        for e in c['proximityEvidence'][:2]: lines.append(f"    PROX {e['entry']} alias={e['alias']} dist={e['distance']}")
        for p in c['paths'][:3]: lines.append('    path='+p)
    lines.append('')
lines.append('TOP_UNCLAIMED_FAMILIES')
for f in family_rows[:60]:
    lines.append(f"  core={f['core']} roots={','.join(f['roots'][:6])} kinds={','.join(f['assetKinds']) or '-'} families={','.join(f['sourceFamilies']) or '-'} occurrences={f['occurrences']}")
    for p in f['paths'][:2]: lines.append('    path='+p)
lines.append('')
lines.append('unresolvedHeroIds='+','.join(map(str,out['unresolvedHeroIds'])))
reportp.write_text('\n'.join(lines)+'\n',encoding='utf-8')
print('PHASE39C_OK',f"resolved={out['resolvedCount']}/4",f"mediumOrHigh={out['mediumOrHighCount']}/4",f"unresolved={len(out['unresolvedHeroIds'])}",f"unclaimedFamilies={len(bycore)}")
PYEOF

python "$PY" "$IN" "$OUT" "$REPORT" "${APK_PATHS[@]}"
rm -f "$PY"

git add -f frontend/lab/master-assets-v2/meta/hero-vehicle-final-four-graph.json scripts/lastwar-phase39c-four-unclaimed-vehicle-graph.sh
if git diff --cached --quiet -- frontend/lab/master-assets-v2/meta/hero-vehicle-final-four-graph.json scripts/lastwar-phase39c-four-unclaimed-vehicle-graph.sh; then
  echo "Aucun changement à committer."
else
  git commit -m "lab: isolate final four hero vehicle identities"
fi
git push origin "$BRANCH"

echo "=== PHASE 39C TERMINEE ==="
echo "Graphe: frontend/lab/master-assets-v2/meta/hero-vehicle-final-four-graph.json"
echo "Rapport: Téléchargements/WFGG_LASTWAR_PHASE39C_FINAL_FOUR_VEHICLE_GRAPH.txt"
echo "Ne lance pas encore la page Escouades."
echo "main non modifiée."
