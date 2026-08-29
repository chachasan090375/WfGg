#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — PHASE 39B
# Resolve the seven low-confidence hero->vehicle identities from authoritative
# static hero/config tables before any 31/31 3D extraction.
# CODE ONLY. OFFLINE ONLY. No Last War network connection.

PKG="com.fun.lastwar.gp"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
SEED="$ROOT/frontend/lab/master-assets-v2/meta/hero-vehicle-catalog-seed.json"
OUT="$ROOT/frontend/lab/master-assets-v2/meta/hero-vehicle-seven-resolution.json"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_PHASE39B_SEVEN_VEHICLE_ALIASES.txt"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
command -v python >/dev/null 2>&1 || fail "python absent"
command -v pm >/dev/null 2>&1 || fail "commande Android pm absente"
[[ -s "$SEED" ]] || fail "Phase 39 absente: $SEED"
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche active incorrecte"

mapfile -t APK_PATHS < <(pm path "$PKG" 2>/dev/null | sed -n 's/^package://p')
if [[ ${#APK_PATHS[@]} -eq 0 ]]; then
  mapfile -t APK_PATHS < <(cmd package path "$PKG" 2>/dev/null | sed -n 's/^package://p')
fi
[[ ${#APK_PATHS[@]} -gt 0 ]] || fail "installation Last War introuvable ($PKG)"

python - "$SEED" "$OUT" "$REPORT" "${APK_PATHS[@]}" <<'PY'
from pathlib import Path
import csv, io, json, os, re, sys, zipfile
from collections import defaultdict

seedp=Path(sys.argv[1]); outp=Path(sys.argv[2]); reportp=Path(sys.argv[3]); apk_paths=sys.argv[4:]
seed=json.loads(seedp.read_text(encoding='utf-8'))
TARGETS={30005:'Gump',50013:'McGregor',50014:'Fiona',50018:'Schuyler',50019:'Carlie',50023:'Mason',50025:'Violet'}

# Known display/icon aliases are evidence inputs, never enough by themselves to accept a vehicle.
BASE_ALIASES={
  30005:['gump','gump3'],
  50013:['mcgregor','ewan_mcgregor'],
  50014:['fiona'],
  50018:['schuyler','sally_ride','sallyride'],
  50019:['carlie','carly'],
  50023:['mason','david_stirling','davidstirling'],
  50025:['violet','doctor_poison','doctorpoison'],
}

def norm(s): return re.sub(r'[^a-z0-9]+','_',str(s or '').lower()).strip('_')
def flatnorm(s): return norm(s).replace('_','')
def scalar(v): return isinstance(v,(str,int,float,bool)) or v is None

def flatten(d,prefix=''):
    out={}
    if isinstance(d,dict):
        for k,v in d.items():
            key=f'{prefix}.{k}' if prefix else str(k)
            if scalar(v): out[key]=v
            elif isinstance(v,dict): out.update(flatten(v,key))
    return out

def decode_text(b):
    for enc in ('utf-8-sig','utf-16-le','utf-16-be'):
        try:
            s=b.decode(enc)
            if s and sum(ch.isprintable() or ch in '\r\n\t' for ch in s)/len(s)>.82:return s
        except Exception: pass
    return None

def parse_rows(b):
    s=decode_text(b)
    if not s:return [],'binary'
    st=s.lstrip('\ufeff\x00 \r\n\t')
    if st.startswith(('{','[')):
        try:
            obj=json.loads(st); rows=[]
            def walk(x):
                if isinstance(x,dict):
                    if len(x)>=2: rows.append(x)
                    for v in x.values():walk(v)
                elif isinstance(x,list):
                    for v in x:walk(v)
            walk(obj); return rows,'json'
        except Exception: pass
    lines=[x for x in s.splitlines() if x.strip()]
    if not lines:return [],'text'
    sample='\n'.join(lines[:25]); ds=['\t',',','|',';']; delim=max(ds,key=sample.count)
    if sample.count(delim)<2:return [],'text'
    try:t=list(csv.reader(lines,delimiter=delim))
    except Exception:return [],'text'
    if len(t)<2:return [],'text'
    hdr=[x.strip() for x in t[0]]
    if sum(bool(re.search(r'[A-Za-z_]',x)) for x in hdr)<max(2,len(hdr)//3):return [],'text'
    rows=[]
    for r in t[1:]:
        if not r:continue
        rows.append({hdr[i] if i<len(hdr) and hdr[i] else f'c{i}':v for i,v in enumerate(r)})
    return rows,'delimited'

def row_id_score(row,hid):
    f=flatten(row); best=-1
    for k,v in f.items():
        try:eq=int(v)==hid
        except Exception:eq=str(v).strip()==str(hid)
        if not eq:continue
        nk=norm(k); sc=1
        if nk in ('id','hero_id','heroid','cfgid','configid','metaid'):sc+=20
        if 'hero' in nk and 'id' in nk:sc+=15
        if nk.endswith('id'):sc+=5
        best=max(best,sc)
    return best

def exact_rows(rows,hid):
    z=[(row_id_score(r,hid),r) for r in rows]
    z=[x for x in z if x[0]>=0]; z.sort(key=lambda x:x[0],reverse=True)
    return z

INTEREST_RX=re.compile(r'model|prefab|vehicle|car|queue|formation|show|battle|path|asset|appearance|type|icon|body|display|unit|army|class|quality',re.I)
def interesting(flat):
    return {k:v for k,v in flat.items() if v not in ('',None) and INTEREST_RX.search(k)}

def string_tokens(flat):
    toks=set()
    for k,v in flat.items():
        if not isinstance(v,str):continue
        s=v.strip()
        if not s or len(s)>180:continue
        for t in re.findall(r'[A-Za-z][A-Za-z0-9_]{2,}',s):
            n=norm(t)
            if len(n)>=4 and n not in {'hero','icon','model','prefab','asset','battle','appearance','default','normal','common'}:
                toks.add(n)
    return toks

# Find the table container proven in earlier phases.
container=None
for apk in apk_paths:
    try:z=zipfile.ZipFile(apk)
    except Exception:continue
    for zi in z.infolist():
        if not (zi.filename.startswith('assets/table/') and zi.filename.endswith('.data')):continue
        try:b=z.read(zi)
        except Exception:continue
        if not b.startswith(b'PK'):continue
        try:inner=zipfile.ZipFile(io.BytesIO(b)); names=inner.namelist()
        except Exception:continue
        if any(n.strip('/').lower()=='lw_hero' for n in names):
            container=(os.path.basename(apk),zi.filename,b,names); inner.close(); break
        inner.close()
    z.close()
    if container:break
if not container:raise SystemExit('table container with LW_Hero not found')
apk_name,container_name,container_bytes,member_names=container
inner=zipfile.ZipFile(io.BytesIO(container_bytes))

# Parse relevant config members. We intentionally include every textual member whose name
# may carry hero/model/appearance/formation data, not just LW_Hero.
member_cache={}
for name in member_names:
    low=name.lower()
    if not any(t in low for t in ('lw_hero','hero','appearance','formation','army','model')):continue
    try:b=inner.read(name)
    except Exception:continue
    rows,fmt=parse_rows(b)
    if rows:member_cache[name]=(rows,fmt)
inner.close()

# Extract the installed asset catalogue paths and canonical vehicle roots.
manifest=''
for apk in apk_paths:
    try:
        with zipfile.ZipFile(apk) as z:
            if 'assets/AssetBundles/gameres' in z.namelist():
                manifest=z.read('assets/AssetBundles/gameres').decode('utf-8','ignore');break
    except Exception:pass
if not manifest:raise SystemExit('gameres manifest not found')

paths=set()
for m in re.finditer(r'[A-Za-z0-9_./-]{8,}\.bundle',manifest,re.I):
    s=m.group(0)
    l=s.lower()
    if ('cars' in l or 'models_new_cars' in l) and 'a_hero_' in l:paths.add(s)
for m in re.finditer(r'Assets/[A-Za-z0-9_./ -]{8,}',manifest,re.I):
    s=m.group(0).strip();l=s.lower()
    if ('cars/' in l or 'models_new/cars/' in l) and 'a_hero_' in l:paths.add(s)

def roots(path):
    low=path.lower();out=[]
    for rx in (
      r'(a_hero_[a-z0-9_]+?)(?:/(?:animation|animator|material|mesh|prefab|texture)|\.(?:prefab|fbx)|$)',
      r'(a_hero_[a-z0-9_]+?)(?:_(?:animation|animator|material|mesh|prefab|texture)(?:_|\.)|\.bundle)'):
        out += re.findall(rx,low)
    return sorted(set(norm(x) for x in out if x))
root_paths=defaultdict(list)
for p in paths:
    for r in roots(p):root_paths[r].append(p)

# Roots already supported by medium/high Phase 39 are not candidates for a different hero
# unless authoritative table evidence explicitly points to the same root.
claimed={}
for h in seed.get('heroes',[]):
    if h.get('selectionConfidence') in ('medium','high') and h.get('selected'):
        claimed[norm(h['selected'].get('vehicleRoot'))]=int(h['heroId'])

results=[]
for hid,name in TARGETS.items():
    evidence_rows=[]; table_tokens=set(BASE_ALIASES[hid]); appearance_ids=set()
    for member,(rows,fmt) in member_cache.items():
        hits=exact_rows(rows,hid)
        for sc,row in hits[:4]:
            f=flatten(row); intr=interesting(f); toks=string_tokens(f)
            for k,v in f.items():
                if 'appearance' in norm(k):
                    try:appearance_ids.add(int(v))
                    except Exception:pass
            table_tokens.update(toks)
            evidence_rows.append({'member':member,'format':fmt,'idScore':sc,'interestingFields':intr,'stringTokens':sorted(toks)[:120]})

    # Follow explicit appearance IDs into appearance-related tables.
    for aid in sorted(appearance_ids):
        for member,(rows,fmt) in member_cache.items():
            if 'appearance' not in member.lower():continue
            hits=exact_rows(rows,aid)
            for sc,row in hits[:3]:
                f=flatten(row); intr=interesting(f); toks=string_tokens(f); table_tokens.update(toks)
                evidence_rows.append({'member':member,'appearanceId':aid,'format':fmt,'idScore':sc,'interestingFields':intr,'stringTokens':sorted(toks)[:120]})

    # Match table-derived strings to actual vehicle roots. This is deliberately stricter
    # than Phase 39: no candidate exists without a root/token match.
    cand=[]
    for root,plist in root_paths.items():
        rf=flatnorm(root); matches=[]; score=0
        for tok in table_tokens:
            tf=flatnorm(tok)
            if len(tf)<4:continue
            if tf in rf or rf in tf:
                # Direct display/icon aliases are useful but table-discovered aliases are stronger.
                base=tok in {norm(x) for x in BASE_ALIASES[hid]}
                points=(3500 if base else 6200)+min(len(tf),30)*30
                score+=points;matches.append({'token':tok,'basis':'base_alias' if base else 'table_row'})
        kinds=set()
        for p in plist:
            lp=p.lower()
            for k in ('animation','animator','material','mesh','prefab','texture'):
                if k in lp:kinds.add(k)
        score += len(kinds)*180
        if 'prefab' in kinds and 'mesh' in kinds:score+=900
        owner=claimed.get(root)
        if owner and owner!=hid:score-=9000
        if matches and score>0:
            cand.append({'vehicleRoot':root,'score':score,'matches':matches[:30],'assetKinds':sorted(kinds),'claimedByOtherHeroId':owner,'paths':sorted(set(plist))[:30]})
    cand.sort(key=lambda x:(x['score'],len(x['assetKinds'])),reverse=True)
    selected=cand[0] if cand else None
    confidence='none'
    if selected:
        second=cand[1]['score'] if len(cand)>1 else 0; ratio=selected['score']/max(1,second)
        table_match=any(x['basis']=='table_row' for x in selected['matches'])
        if table_match and selected['score']>=8000 and ratio>=1.18:confidence='high'
        elif selected['score']>=5000:confidence='medium'
        else:confidence='low'
    results.append({'heroId':hid,'name':name,'appearanceIds':sorted(appearance_ids),'selectionConfidence':confidence,'selected':selected,'alternates':cand[1:6],'tableEvidence':evidence_rows})

out={
 'format':'WFGG_LASTWAR_PHASE39B_SEVEN_VEHICLE_ALIASES_V1','networkUsed':False,
 'sourceTableContainer':f'{apk_name}:{container_name}','targets':results
}
out['resolvedCount']=sum(1 for x in results if x['selected'])
out['mediumOrHighCount']=sum(1 for x in results if x['selectionConfidence'] in ('medium','high'))
out['unresolvedHeroIds']=[x['heroId'] for x in results if not x['selected']]
outp.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')

lines=[
 'WfGg Last War LAB — PHASE 39B SEVEN VEHICLE ALIASES',
 'OFFLINE ONLY · authoritative table rows -> actual Models/Cars roots',
 f"targets=7 resolved={out['resolvedCount']}/7 mediumOrHigh={out['mediumOrHighCount']}/7",''
]
for x in results:
    lines.append(f"HERO {x['heroId']} {x['name']} confidence={x['selectionConfidence']} appearanceIds={','.join(map(str,x['appearanceIds'])) or '-'}")
    if x['selected']:
        s=x['selected'];lines.append(f"  vehicleRoot={s['vehicleRoot']} score={s['score']} kinds={','.join(s['assetKinds'])}")
        lines.append('  matches='+','.join(f"{m['token']}[{m['basis']}]" for m in s['matches']))
        for p in s['paths'][:6]:lines.append('  path='+p)
    else:lines.append('  UNRESOLVED')
    for ev in x['tableEvidence'][:10]:
        if ev.get('interestingFields'):
            lines.append(f"  TABLE {ev['member']} idScore={ev['idScore']} fields="+json.dumps(ev['interestingFields'],ensure_ascii=False,separators=(',',':')))
        toks=ev.get('stringTokens') or []
        if toks:lines.append('  TOKENS '+ev['member']+'='+','.join(toks[:30]))
    lines.append('')
lines.append('unresolvedHeroIds='+','.join(map(str,out['unresolvedHeroIds'])))
reportp.write_text('\n'.join(lines)+'\n',encoding='utf-8')
print('PHASE39B_OK',f"resolved={out['resolvedCount']}/7",f"mediumOrHigh={out['mediumOrHighCount']}/7",f"unresolved={len(out['unresolvedHeroIds'])}")
PY

git add -f frontend/lab/master-assets-v2/meta/hero-vehicle-seven-resolution.json scripts/lastwar-phase39b-resolve-seven-vehicle-aliases.sh
if git diff --cached --quiet -- frontend/lab/master-assets-v2/meta/hero-vehicle-seven-resolution.json scripts/lastwar-phase39b-resolve-seven-vehicle-aliases.sh; then
  echo "Aucun changement à committer."
else
  git commit -m "lab: resolve seven remaining vehicle aliases from hero tables"
fi
git push origin "$BRANCH"

echo "=== PHASE 39B TERMINEE ==="
echo "Rapport: Téléchargements/WFGG_LASTWAR_PHASE39B_SEVEN_VEHICLE_ALIASES.txt"
echo "Ne lance pas encore la page Escouades."
echo "main non modifiée."
