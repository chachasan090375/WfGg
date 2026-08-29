#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — BACKGROUND LAYER 1
# Recover the exact installed environment assets behind the Formation screen.
# CODE ONLY · OFFLINE ONLY · no Last War network · no generated artwork.
#
# This deliberately separates the future screen into real layers:
#   L1 background environment: A_build_ground + trees + rocks
#   L2 Formation platform:      A_build_formation (staged here, rendered later)
#   L3 vehicles / drone
#   L4 labels / UI

PKG="com.fun.lastwar.gp"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
OUT="$ROOT/frontend/lab/local_assets/lastwar-formation-background-v1"
MANIFEST="$ROOT/frontend/lab/master-assets-v2/meta/formation-background-exact-v1.json"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_BACKGROUND_LAYER1_EXACT.txt"
PY="${TMPDIR:-$HOME/.cache}/wfgg-lastwar-background-layer1.py"
UNITY_VERSION="2019.4.41f1"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche active incorrecte"
command -v python >/dev/null 2>&1 || fail "python absent"
command -v cmd >/dev/null 2>&1 || fail "commande Android cmd absente"

mapfile -t APK_PATHS < <(cmd package path "$PKG" 2>/dev/null | sed -n 's/^package://p')
[[ ${#APK_PATHS[@]} -gt 0 ]] || fail "APK Last War introuvable"

rm -rf "$OUT"
mkdir -p "$OUT/bundles" "$(dirname "$MANIFEST")" "$(dirname "$REPORT")" "$(dirname "$PY")"

cat > "$PY" <<'PYEOF'
from pathlib import Path
from collections import defaultdict, Counter
import hashlib, json, os, re, struct, sys, zipfile

out=Path(sys.argv[1]); manifestp=Path(sys.argv[2]); reportp=Path(sys.argv[3]); unity_version=sys.argv[4]; apks=sys.argv[5:]
PKG='com.fun.lastwar.gp'
WANTED={
 'gameres':'assets/AssetBundles/gameres',
 'bundleOffsets':'assets/AssetBundles/BundleOffsetTable.bytes',
 'aliasOffsets':'assets/AssetBundles/AliasOffsetTable.bytes',
 'fragment':'assets/AssetBundles/BundleFragment0.bytes',
}
raw={}; src={}
for apk in apks:
    try:
        with zipfile.ZipFile(apk) as z:
            names=set(z.namelist())
            for k,e in WANTED.items():
                if k in raw or e not in names: continue
                info=z.getinfo(e)
                if k=='fragment':
                    raw[k]=None; src[k]={'apk':apk,'entry':e,'bytes':info.file_size}
                else:
                    b=z.read(e); raw[k]=b; src[k]={'apk':apk,'entry':e,'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
    except Exception:
        pass
for k in WANTED:
    if k not in raw: raise SystemExit('missing installed component: '+k)

text=raw['gameres'].decode('utf-8','strict')
def section(name):
    m=re.search(rf'^\[{re.escape(name)}\]\s*$',text,re.M)
    if not m:return []
    s=m.end(); n=re.search(r'^\[[^\]]+\]\s*$',text[s:],re.M); e=s+n.start() if n else len(text)
    return [x for x in text[s:e].splitlines() if x.strip()]

directories={}
for ln in section('Directories'):
    try:i,p=ln.split(',',1);directories[int(i)]=p
    except:pass
paths={}
for ln in section('Paths'):
    try:
        pid,did,name=ln.split(',',2);pid=int(pid);did=int(did)
        paths[pid]=directories[did].rstrip('/')+'/'+name
    except:pass
bundles={}
for ln in section('Bundles'):
    p=ln.split(',')
    if len(p)<8:continue
    try:
        bid=int(p[0]); assets=[int(x) for x in p[4].split('|') if x]; deps=[int(x) for x in p[5].split('|') if x]
        bundles[bid]={'bundleId':bid,'logicalName':p[1],'crc':p[2],'declaredBytes':int(p[3]),'assetPathIds':assets,'dependencyBundleIds':deps,'groups':p[6].split('|') if p[6] else [],'aliasName':p[7]}
    except:pass

def read7(buf,pos):
    r=0;s=0
    while True:
        x=buf[pos];pos+=1;r|=(x&0x7f)<<s
        if not (x&0x80):return r,pos
        s+=7

def parse_offsets(buf):
    pos=0; fc=struct.unpack_from('<I',buf,pos)[0];pos+=4; out=[]
    for _ in range(fc):
        ln,pos=read7(buf,pos); frag=buf[pos:pos+ln].decode();pos+=ln
        payload=struct.unpack_from('<I',buf,pos)[0];pos+=4; count=struct.unpack_from('<I',buf,pos)[0];pos+=4
        rec=[]
        for _ in range(count):
            ln,pos=read7(buf,pos); name=buf[pos:pos+ln].decode();pos+=ln; off=struct.unpack_from('<Q',buf,pos)[0];pos+=8
            rec.append({'name':name,'offset':off})
        out.append({'fragment':frag,'payloadBytes':payload,'records':rec})
    return out
bo=parse_offsets(raw['bundleOffsets']); ao=parse_offsets(raw['aliasOffsets'])
if len(bo)!=1 or bo[0]['fragment']!='BundleFragment0.bytes': raise SystemExit('unexpected BundleOffsetTable')
installed={x['name']:int(x['offset']) for x in bo[0]['records']}
alias_installed={x['name']:int(x['offset']) for x in ao[0]['records']}
ordered=sorted((int(x['offset']),x['name']) for x in bo[0]['records'])
fragment_bytes=int(src['fragment']['bytes'])
size_by_offset={}
for i,(off,name) in enumerate(ordered):
    nxt=ordered[i+1][0] if i+1<len(ordered) else fragment_bytes
    size_by_offset[off]=nxt-off

FAMILIES={
 'ground':'Assets/_Art_LastWar/Models/Environment/Build/A_build_ground/',
 'trees':'Assets/_Art_LastWar/Models/Environment/Prop/O_Prop_tree/',
 'rocks':'Assets/_Art_LastWar/Models/Environment/Prop/Rock/',
 'formation':'Assets/_Art_LastWar/Models/Environment/Build/Formation/',
}
pids_by_family={k:{pid for pid,p in paths.items() if p.lower().startswith(prefix.lower())} for k,prefix in FAMILIES.items()}
selected=[]
for bid,b in bundles.items():
    fams=[]; hitpaths=[]
    for fam,pids in pids_by_family.items():
        hits=[pid for pid in b['assetPathIds'] if pid in pids]
        if hits:
            fams.append(fam);hitpaths.extend(paths[pid] for pid in hits)
    if not fams:continue
    off=installed.get(b['logicalName']); aoff=alias_installed.get(b['aliasName'])
    selected.append({**b,'families':fams,'assetPaths':sorted(hitpaths),'installedExact':off is not None and aoff==off,'fragmentOffset':off,'fragmentBytes':size_by_offset.get(off) if off is not None else None})

# Only installed authoritative bundles are usable in this first background layer.
segments=[]
for r in selected:
    if not r['installedExact']:continue
    dest=out/'bundles'/r['aliasName']
    r['_dest']=dest
    segments.append((int(r['fragmentOffset']),int(r['fragmentBytes']),r))
segments.sort(key=lambda x:x[0])

fragment_apk=None
for ap in apks:
    try:
        with zipfile.ZipFile(ap) as z:
            if WANTED['fragment'] in z.namelist(): fragment_apk=Path(ap);break
    except:pass
if fragment_apk is None:raise SystemExit('BundleFragment0 APK source not found')

with zipfile.ZipFile(fragment_apk) as z, z.open(WANTED['fragment'],'r') as f:
    pos=0
    for off,n,row in segments:
        if off<pos:raise SystemExit(f'non-monotonic fragment offset {off} < {pos}')
        skip=off-pos
        while skip:
            b=f.read(min(skip,1024*1024))
            if not b:raise SystemExit('fragment EOF while seeking')
            skip-=len(b);pos+=len(b)
        left=n; h=hashlib.sha256(); dest=row['_dest']
        with dest.open('wb') as o:
            while left:
                b=f.read(min(left,1024*1024))
                if not b:raise SystemExit('fragment EOF while extracting')
                o.write(b);h.update(b);left-=len(b);pos+=len(b)
        row['localFile']='bundles/'+dest.name;row['actualBytes']=dest.stat().st_size;row['sha256']=h.hexdigest();row['staged']=True

# Structural inventory with UnityPy only. No rendering and no generated assets.
try:
    import UnityPy
    UnityPy.config.FALLBACK_UNITY_VERSION=unity_version
    unitypy_error=None
except Exception as e:
    UnityPy=None;unitypy_error=repr(e)

inventory={}
if UnityPy is not None:
    for fam in FAMILIES:
        files=[out/r['localFile'] for r in selected if r.get('staged') and fam in r['families']]
        names=defaultdict(list);counts=Counter();errors=[]
        try:
            env=UnityPy.load(*[str(p) for p in files]) if files else None
            if env:
                seen=set()
                for obj in env.objects:
                    typ=getattr(getattr(obj,'type',None),'name',str(getattr(obj,'type','')))
                    key=(typ,getattr(obj,'path_id',None),str(getattr(getattr(obj,'assets_file',None),'name','')))
                    if key in seen:continue
                    seen.add(key);counts[typ]+=1
                    if typ in {'GameObject','Transform','Mesh','Material','Texture2D'}:
                        try:
                            d=obj.read(); nm=str(getattr(d,'m_Name','') or getattr(d,'name','') or '')
                            if nm:names[typ].append(nm)
                        except Exception as e:errors.append(repr(e))
        except Exception as e:errors.append(repr(e))
        inventory[fam]={'bundleCount':len(files),'objectTypes':dict(counts),'names':{k:sorted(set(v)) for k,v in names.items()},'errors':errors[:20]}
else:
    inventory={'unityPyError':unitypy_error}

for r in selected:r.pop('_dest',None)
summary={
 'format':'WFGG_LASTWAR_FORMATION_BACKGROUND_EXACT_V1','networkUsed':False,'generatedArtwork':False,
 'source':src,'families':FAMILIES,'selectedBundleCount':len(selected),'stagedBundleCount':sum(bool(r.get('staged')) for r in selected),
 'missingInstalledBundles':[{'bundleId':r['bundleId'],'aliasName':r['aliasName'],'families':r['families']} for r in selected if not r['installedExact']],
 'bundles':selected,'inventory':inventory,
 'layerContract':{'layer1':['ground','trees','rocks'],'layer2':['formation'],'layer3':['vehicles','drone'],'layer4':['labels','icons','controls']},
 'guardrails':{'exactGameresPaths':True,'exactInstalledFragmentOffsets':True,'noSimilarityMatching':True,'noGeneratedArtwork':True,'noLastWarNetwork':True}
}
manifestp.write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')

lines=['WfGg Last War — BACKGROUND LAYER 1 EXACT','OFFLINE ONLY · exact gameres paths + installed fragment offsets',f"selectedBundles={summary['selectedBundleCount']} stagedBundles={summary['stagedBundleCount']} missingInstalled={len(summary['missingInstalledBundles'])}",'']
for fam,prefix in FAMILIES.items():
    fr=[r for r in selected if fam in r['families']]
    lines.append(f'FAMILY {fam} prefix={prefix} bundles={len(fr)} staged={sum(bool(x.get("staged")) for x in fr)}')
    inv=inventory.get(fam,{})
    lines.append('  objectTypes='+json.dumps(inv.get('objectTypes',{}),ensure_ascii=False,sort_keys=True))
    for typ,nms in (inv.get('names') or {}).items():
        lines.append(f'  {typ}: '+', '.join(nms[:80]))
    for r in fr:
        lines.append(f"  bundle installed={r['installedExact']} staged={bool(r.get('staged'))} offset={r.get('fragmentOffset')} bytes={r.get('actualBytes') or r.get('fragmentBytes')} alias={r['aliasName']}")
    lines.append('')
lines += ['LAYER CONTRACT','  L1 = exact ground + exact tree props + exact rock props','  L2 = exact Formation platform (separate; do not stack team variants)','  L3 = exact animated vehicles + drone','  L4 = labels + icons + controls','','GUARDRAILS','  no_fake_css_environment=true','  no_generated_background=true','  no_similarity_fallback=true','  no_lastwar_network=true']
reportp.write_text('\n'.join(lines)+'\n',encoding='utf-8')
print('BACKGROUND_LAYER1_OK',f"staged={summary['stagedBundleCount']}/{summary['selectedBundleCount']}",f"missing={len(summary['missingInstalledBundles'])}")
print('BACKGROUND_LAYER1_REPORT',reportp)
PYEOF

python "$PY" "$OUT" "$MANIFEST" "$REPORT" "$UNITY_VERSION" "${APK_PATHS[@]}"
rm -f "$PY"

git add scripts/lastwar-background-layer1-exact.sh "$MANIFEST"
if ! git diff --cached --quiet; then
  git commit -m "lab: record exact Formation background asset layer"
  git push origin "$BRANCH"
fi

echo "=== BACKGROUND LAYER 1 TERMINE ==="
echo "Assets locaux : frontend/lab/local_assets/lastwar-formation-background-v1"
echo "Manifest : frontend/lab/master-assets-v2/meta/formation-background-exact-v1.json"
echo "Rapport : $REPORT"
echo "main non modifiée."
