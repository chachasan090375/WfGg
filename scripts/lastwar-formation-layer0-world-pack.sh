#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — exact Formation LAYER 0 world pack.
# Extracts the authoritative World/Terrain roots, their dependency closure and
# the environment prop families required to reconstruct the blurred background.
# CODE ONLY · OFFLINE installed game data · no generated landscape.

PKG="com.fun.lastwar.gp"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
CONTRACT="$ROOT/frontend/lab/master-assets-v2/meta/formation-layer0-contract-v1.json"
OUT="$ROOT/frontend/lab/local_assets/lastwar-formation-layer0-world-v1"
MANIFEST="$ROOT/frontend/lab/master-assets-v2/meta/formation-layer0-world-pack-v1.json"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_FORMATION_LAYER0_WORLD_PACK.txt"
PY="${TMPDIR:-$HOME/.cache}/wfgg-layer0-world-pack.py"
UNITY_VERSION="2019.4.41f1"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
[[ -s "$CONTRACT" ]] || fail "contrat Layer0 absent"
command -v python >/dev/null 2>&1 || fail "python absent"
command -v cmd >/dev/null 2>&1 || fail "commande Android cmd absente"

mapfile -t APK_PATHS < <(cmd package path "$PKG" 2>/dev/null | sed -n 's/^package://p')
[[ ${#APK_PATHS[@]} -gt 0 ]] || fail "APK Last War introuvable"

rm -rf "$OUT"
mkdir -p "$OUT/bundles" "$OUT/meshes" "$OUT/textures" "$(dirname "$MANIFEST")" "$(dirname "$REPORT")" "$(dirname "$PY")"

cat > "$PY" <<'PYEOF'
from pathlib import Path
from collections import Counter, defaultdict
import hashlib, json, re, struct, sys, zipfile, traceback

out=Path(sys.argv[1]); contractp=Path(sys.argv[2]); manifestp=Path(sys.argv[3]); reportp=Path(sys.argv[4]); unity_version=sys.argv[5]; apks=sys.argv[6:]
contract=json.loads(contractp.read_text(encoding='utf-8'))
WANTED={'gameres':'assets/AssetBundles/gameres','bundleOffsets':'assets/AssetBundles/BundleOffsetTable.bytes','aliasOffsets':'assets/AssetBundles/AliasOffsetTable.bytes','fragment':'assets/AssetBundles/BundleFragment0.bytes'}
raw={}; src={}
for apk in apks:
    try:
        with zipfile.ZipFile(apk) as z:
            names=set(z.namelist())
            for k,e in WANTED.items():
                if k in raw or e not in names: continue
                info=z.getinfo(e)
                if k=='fragment': raw[k]=None; src[k]={'apk':apk,'entry':e,'bytes':info.file_size}
                else:
                    b=z.read(e); raw[k]=b; src[k]={'apk':apk,'entry':e,'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
    except Exception: pass
for k in WANTED:
    if k not in raw: raise SystemExit('missing installed component: '+k)

text=raw['gameres'].decode('utf-8','strict')
def section(name):
    m=re.search(rf'^\[{re.escape(name)}\]\s*$',text,re.M)
    if not m:return []
    s=m.end(); n=re.search(r'^\[[^\]]+\]\s*$',text[s:],re.M); e=s+n.start() if n else len(text)
    return [x for x in text[s:e].splitlines() if x.strip()]

dirs={}
for ln in section('Directories'):
    try:i,p=ln.split(',',1);dirs[int(i)]=p
    except:pass
paths={}
for ln in section('Paths'):
    try:pid,did,name=ln.split(',',2);paths[int(pid)]=dirs[int(did)].rstrip('/')+'/'+name
    except:pass
bundles={}
for ln in section('Bundles'):
    p=ln.split(',')
    if len(p)<8:continue
    try:
        bid=int(p[0]); bundles[bid]={'bundleId':bid,'logicalName':p[1],'crc':p[2],'declaredBytes':int(p[3]),'assetPathIds':[int(x) for x in p[4].split('|') if x],'dependencyBundleIds':[int(x) for x in p[5].split('|') if x],'groups':p[6].split('|') if p[6] else [],'aliasName':p[7]}
    except:pass

# Verify the five authoritative root ids against the installed gameres namespace.
root_ids={int(x['pathId']) for x in contract['authoritativeRoots']}
root_paths={pid:paths.get(pid) for pid in sorted(root_ids)}
missing_roots=[pid for pid,p in root_paths.items() if not p]
if missing_roots: raise SystemExit('missing authoritative gameres root ids: '+repr(missing_roots))

# Root bundles + exact environment families. The prop families are deliberately
# selected by authoritative gameres path prefix, never by filename similarity.
selected_ids=set()
for bid,b in bundles.items():
    if any(pid in root_ids for pid in b['assetPathIds']): selected_ids.add(bid)
family_hits={}
for pref in contract['environmentFamilies']:
    pids={pid for pid,p in paths.items() if p.lower().startswith(pref.lower())}
    hits=[]
    for bid,b in bundles.items():
        if any(pid in pids for pid in b['assetPathIds']): selected_ids.add(bid); hits.append(bid)
    family_hits[pref]=sorted(set(hits))

# Include complete recursive dependencies of every selected exact bundle.
stack=list(selected_ids)
while stack:
    bid=stack.pop()
    b=bundles.get(bid)
    if not b:continue
    for dep in b['dependencyBundleIds']:
        if dep not in selected_ids:
            selected_ids.add(dep);stack.append(dep)

# Parse BundleFragment0 offsets.
def read7(buf,pos):
    r=0;s=0
    while True:
        x=buf[pos];pos+=1;r|=(x&0x7f)<<s
        if not (x&0x80):return r,pos
        s+=7

def offsets(buf):
    pos=0;fc=struct.unpack_from('<I',buf,pos)[0];pos+=4;rows=[]
    for _ in range(fc):
        ln,pos=read7(buf,pos);frag=buf[pos:pos+ln].decode();pos+=ln
        payload=struct.unpack_from('<I',buf,pos)[0];pos+=4
        count=struct.unpack_from('<I',buf,pos)[0];pos+=4
        rec=[]
        for _ in range(count):
            ln,pos=read7(buf,pos);name=buf[pos:pos+ln].decode();pos+=ln;off=struct.unpack_from('<Q',buf,pos)[0];pos+=8
            rec.append({'name':name,'offset':off})
        rows.append({'fragment':frag,'payloadBytes':payload,'records':rec})
    return rows
bo=offsets(raw['bundleOffsets']);ao=offsets(raw['aliasOffsets'])
if len(bo)!=1 or bo[0]['fragment']!='BundleFragment0.bytes':raise SystemExit('unexpected BundleOffsetTable layout')
installed={x['name']:int(x['offset']) for x in bo[0]['records']}; aliases={x['name']:int(x['offset']) for x in ao[0]['records']}
ordered=sorted((int(x['offset']),x['name']) for x in bo[0]['records']); fragbytes=int(src['fragment']['bytes'])
size={}
for i,(off,nm) in enumerate(ordered):size[off]=(ordered[i+1][0] if i+1<len(ordered) else fragbytes)-off

rows=[]
for bid in sorted(selected_ids):
    b=bundles.get(bid)
    if not b:continue
    off=installed.get(b['logicalName']); exact=off is not None and aliases.get(b['aliasName'])==off
    rows.append({**b,'assetPaths':[paths.get(pid) for pid in b['assetPathIds'] if paths.get(pid)],'installedExact':exact,'fragmentOffset':off,'fragmentBytes':size.get(off) if off is not None else None})

# Extract installed exact segments in ascending fragment order.
segments=[]
for r in rows:
    if r['installedExact']:
        dest=out/'bundles'/r['aliasName'];r['_dest']=dest;segments.append((int(r['fragmentOffset']),int(r['fragmentBytes']),r))
segments.sort(key=lambda x:x[0])
fragment_apk=None
for ap in apks:
    try:
        with zipfile.ZipFile(ap) as z:
            if WANTED['fragment'] in z.namelist():fragment_apk=Path(ap);break
    except:pass
if fragment_apk is None:raise SystemExit('BundleFragment0 source APK not found')
with zipfile.ZipFile(fragment_apk) as z,z.open(WANTED['fragment'],'r') as f:
    pos=0
    for off,n,r in segments:
        skip=off-pos
        while skip:
            b=f.read(min(skip,1024*1024))
            if not b:raise SystemExit('EOF seeking fragment')
            skip-=len(b);pos+=len(b)
        h=hashlib.sha256();left=n
        with r['_dest'].open('wb') as o:
            while left:
                b=f.read(min(left,1024*1024))
                if not b:raise SystemExit('EOF extracting fragment')
                o.write(b);h.update(b);left-=len(b);pos+=len(b)
        r['localFile']='bundles/'+r['_dest'].name;r['actualBytes']=r['_dest'].stat().st_size;r['sha256']=h.hexdigest();r['staged']=True

# Structural export. Meshes are exported directly with MeshHandler, avoiding
# UnityPy's Android-incompatible high-level exporter. Texture2D uses its image
# converter when available; failures are explicit in the report, never replaced.
try:
    import UnityPy
    from UnityPy.helpers.MeshHelper import MeshHandler
    UnityPy.config.FALLBACK_UNITY_VERSION=unity_version
except Exception as e:raise SystemExit('UnityPy import failed: '+repr(e))
try:from PIL import Image
except Exception as e:raise SystemExit('Pillow import failed: '+repr(e))

def safe(s):return re.sub(r'[^A-Za-z0-9._-]+','_',str(s or 'asset')).strip('._')[:140] or 'asset'
def tname(o):
    try:return o.type.name
    except:return str(getattr(o,'type',''))
def read(o):
    try:return o.read()
    except:
        try:return o.parse_as_object()
        except:return None
def name(d):return str(getattr(d,'m_Name','') or getattr(d,'name','') or '')
def objkey(o):return f"{getattr(getattr(o,'assets_file',None),'name','')}:{getattr(o,'path_id',0)}"
def ptrkey(p):
    try:
        if not p or int(getattr(p,'m_PathID',0) or 0)==0:return None
        af=getattr(getattr(p,'reader',None),'assets_file',None)
        return f"{getattr(af,'name','')}:{int(getattr(p,'m_PathID',0))}"
    except:return None

def mesh_obj(m):
    mh=MeshHandler(m);mh.process();verts=mh.m_Vertices or [];uvs=mh.m_UV0 or [];norms=mh.m_Normals or []
    if not verts:raise ValueError('no vertices')
    lines=[]
    for v in verts:lines.append(f"v {-float(v[0]):.9g} {float(v[1]):.9g} {float(v[2]):.9g}\n")
    for u in uvs:lines.append(f"vt {float(u[0]):.9g} {float(u[1]):.9g}\n")
    for n in norms:lines.append(f"vn {-float(n[0]):.9g} {float(n[1]):.9g} {float(n[2]):.9g}\n")
    huv=len(uvs)>=len(verts);hn=len(norms)>=len(verts);faces=0
    for gi,tris in enumerate(mh.get_triangles()):
        lines.append(f'g part_{gi}\n')
        for a,b,c in tris:
            ids=(int(c)+1,int(b)+1,int(a)+1)
            if huv and hn:lines.append('f {0}/{0}/{0} {1}/{1}/{1} {2}/{2}/{2}\n'.format(*ids))
            elif huv:lines.append('f {0}/{0} {1}/{1} {2}/{2}\n'.format(*ids))
            elif hn:lines.append('f {0}//{0} {1}//{1} {2}//{2}\n'.format(*ids))
            else:lines.append('f {} {} {}\n'.format(*ids))
            faces+=1
    if not faces:raise ValueError('no triangles')
    return ''.join(lines),len(verts),faces

bundle_files=[out/r['localFile'] for r in rows if r.get('staged')]
env=UnityPy.load(*[str(p) for p in bundle_files])
objects=[];seen=set();counts=Counter();names=defaultdict(set);exports={'meshes':[],'textures':[]};errors=[]
for o in env.objects:
    k=(tname(o),objkey(o))
    if k in seen:continue
    seen.add(k);typ=tname(o);counts[typ]+=1;d=read(o)
    if d is None:continue
    nm=name(d)
    if nm:names[typ].add(nm)
    if typ=='Mesh':
        item={'objectKey':objkey(o),'name':nm,'exported':False}
        try:
            txt,v,f=mesh_obj(d);fn=f"{len(exports['meshes'])+1:04d}_{safe(nm)}.obj";p=out/'meshes'/fn;p.write_text(txt,encoding='utf-8');item.update({'exported':True,'file':'meshes/'+fn,'vertices':v,'faces':f})
        except Exception as e:item['error']=repr(e)
        exports['meshes'].append(item)
    elif typ=='Texture2D':
        item={'objectKey':objkey(o),'name':nm,'exported':False,'width':getattr(d,'m_Width',None),'height':getattr(d,'m_Height',None),'format':str(getattr(d,'m_TextureFormat',''))}
        try:
            im=d.image;fn=f"{len(exports['textures'])+1:04d}_{safe(nm)}.png";p=out/'textures'/fn;im.save(p,'PNG');item.update({'exported':True,'file':'textures/'+fn})
        except Exception as e:item['error']=repr(e)
        exports['textures'].append(item)
    elif typ in {'GameObject','Transform','MeshRenderer','SkinnedMeshRenderer','Material','Terrain','MonoBehaviour'}:
        rec={'objectKey':objkey(o),'type':typ,'name':nm}
        if typ=='Transform':rec.update({'gameObject':ptrkey(getattr(d,'m_GameObject',None)),'parent':ptrkey(getattr(d,'m_Father',None))})
        elif typ in {'MeshRenderer','SkinnedMeshRenderer'}:rec.update({'gameObject':ptrkey(getattr(d,'m_GameObject',None)),'materials':[ptrkey(x) for x in (getattr(d,'m_Materials',[]) or [])]})
        elif typ=='Material':rec.update({'shader':ptrkey(getattr(d,'m_Shader',None))})
        objects.append(rec)

for r in rows:r.pop('_dest',None)
summary={
 'format':'WFGG_LASTWAR_FORMATION_LAYER0_WORLD_PACK_V1','networkUsed':False,'generatedArtwork':False,'unityFallback':unity_version,
 'contract':contract['bake'],'authoritativeRootPaths':root_paths,'familyBundleIds':family_hits,
 'selectedBundleCount':len(rows),'stagedBundleCount':sum(bool(r.get('staged')) for r in rows),'missingInstalledBundleCount':sum(not r['installedExact'] for r in rows),
 'bundles':rows,'objectTypeCounts':dict(counts),'namedObjects':{k:sorted(v) for k,v in names.items()},'sceneObjects':objects,'exports':exports,
 'meshExported':sum(x['exported'] for x in exports['meshes']),'textureExported':sum(x['exported'] for x in exports['textures']),
 'guardrails':{'exactGameresRoots':True,'recursiveDependencies':True,'exactEnvironmentPathPrefixes':True,'noSimilarityFallback':True,'noGeneratedLandscape':True,'noLastWarNetwork':True}
}
manifestp.write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
lines=['WfGg Last War — FORMATION LAYER0 WORLD PACK','exact gameres roots + exact environment path families · offline only',f"bundles={summary['stagedBundleCount']}/{summary['selectedBundleCount']} missingInstalled={summary['missingInstalledBundleCount']}",f"meshes={summary['meshExported']}/{len(exports['meshes'])} textures={summary['textureExported']}/{len(exports['textures'])}",f"bakeMaster={contract['bake']['masterWidth']}x{contract['bake']['masterHeight']} gaussianSigmaPx={contract['bake']['gaussianSigmaPx']} runtimeDynamicBlur={contract['bake']['runtimeDynamicBlur']}",'']
for pid,p in root_paths.items():lines.append(f'ROOT {pid} {p}')
lines.append('')
for fam,bids in family_hits.items():lines.append(f'FAMILY {fam} bundles={len(bids)} ids={"|".join(map(str,bids))}')
lines += ['', 'OBJECT TYPES '+json.dumps(dict(counts),sort_keys=True), '']
for typ in ('GameObject','Terrain','Mesh','Material','Texture2D','MonoBehaviour'):
    vals=sorted(names.get(typ,set()));lines.append(f'{typ} count={len(vals)}');lines.extend('  '+x for x in vals[:180]);lines.append('')
for x in exports['meshes']:
    if not x['exported']:lines.append('MESH_FAIL '+x['name']+' :: '+x.get('error',''))
for x in exports['textures']:
    if not x['exported']:lines.append('TEX_FAIL '+x['name']+' :: '+x.get('error',''))
lines += ['','BAKE CONTRACT','  runtime_blur=false',f"  master={contract['bake']['masterWidth']}x{contract['bake']['masterHeight']}",f"  gaussian_sigma_px={contract['bake']['gaussianSigmaPx']}",'  output='+contract['bake']['output'],'','GUARDRAILS','  no_fake_css_landscape=true','  no_generated_substitute_artwork=true','  no_similarity_fallback=true','  no_lastwar_network=true']
reportp.write_text('\n'.join(lines)+'\n',encoding='utf-8')
print('LAYER0_WORLD_PACK_OK',f"bundles={summary['stagedBundleCount']}/{summary['selectedBundleCount']}",f"mesh={summary['meshExported']}/{len(exports['meshes'])}",f"tex={summary['textureExported']}/{len(exports['textures'])}")
print('LAYER0_WORLD_PACK_REPORT',reportp)
PYEOF

python "$PY" "$OUT" "$CONTRACT" "$MANIFEST" "$REPORT" "$UNITY_VERSION" "${APK_PATHS[@]}"
rm -f "$PY"

git add "$MANIFEST" scripts/lastwar-formation-layer0-world-pack.sh frontend/lab/master-assets-v2/meta/formation-layer0-contract-v1.json scripts/lastwar-formation-layer0-bake.py
if ! git diff --cached --quiet; then
  git commit -m "lab: extract exact Formation world layer0 pack"
  git push origin "$BRANCH"
fi

echo "=== LAYER0 WORLD PACK TERMINE ==="
echo "Rapport : $REPORT"
echo "Assets locaux : frontend/lab/local_assets/lastwar-formation-layer0-world-v1"
echo "Le flou n'est PAS appliqué au runtime."
echo "main non modifiée."
