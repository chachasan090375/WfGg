#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — extract exact WorldCityGrass prefab from installed APK.
# Read-only. No Last War network. No generated artwork. main untouched.

PKG="com.fun.lastwar.gp"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
UNITY_VERSION="2019.4.41f1"
TARGET="Assets/Main/Prefabs/World/WorldCityGrass.prefab"
GAMERES="$ROOT/frontend/lab/local_assets/lastwar-formation-native-recipe-v1/gameres"
OUT="$ROOT/frontend/lab/master-assets-v2/meta/worldcitygrass-apk-composition-v1.json"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_WORLDCITYGRASS_APK_COMPOSITION.txt"
LOCAL="$ROOT/frontend/lab/local_assets/lastwar-worldcitygrass-apk-v1"
PY="${TMPDIR:-$HOME/.cache}/wfgg-worldcitygrass-apk.py"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
[[ -s "$GAMERES" ]] || fail "gameres local absent — relancer la recipe native"
command -v python >/dev/null 2>&1 || fail "python absent"
python - <<'PY' >/dev/null 2>&1 || fail "UnityPy absent"
import UnityPy
PY
mapfile -t APKS < <(cmd package path "$PKG" 2>/dev/null | sed -n 's/^package://p')
[[ ${#APKS[@]} -gt 0 ]] || fail "APK Last War introuvable"
mkdir -p "$LOCAL" "$(dirname "$OUT")" "$(dirname "$REPORT")" "$(dirname "$PY")"
rm -f "$LOCAL"/*.bundle "$LOCAL"/WorldCityGrass.bundle 2>/dev/null || true

cat > "$PY" <<'PYEOF'
from __future__ import annotations
from pathlib import Path
from collections import Counter,defaultdict
import json,re,struct,sys,zipfile,contextlib,io

root=Path(sys.argv[1]); gameres=Path(sys.argv[2]); outp=Path(sys.argv[3]); reportp=Path(sys.argv[4]); target=sys.argv[5]; unity=sys.argv[6]; apks=sys.argv[7:]
import UnityPy
UnityPy.config.FALLBACK_UNITY_VERSION=unity
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
pid=next((i for i,p in paths.items() if p.lower()==target.lower()),None)
if pid is None:raise SystemExit('TARGET_PATH_NOT_FOUND')
b=next((x for x in bundles.values() if pid in x['assetPathIds']),None)
if not b:raise SystemExit('TARGET_BUNDLE_NOT_FOUND')

def read7(buf,pos):
    out=0;shift=0
    while True:
        x=buf[pos];pos+=1;out|=(x&0x7f)<<shift
        if not x&0x80:return out,pos
        shift+=7

def parse_offsets(buf):
    pos=0;fc=struct.unpack_from('<I',buf,pos)[0];pos+=4;out=[]
    for _ in range(fc):
        ln,pos=read7(buf,pos);frag=buf[pos:pos+ln].decode();pos+=ln
        payload=struct.unpack_from('<I',buf,pos)[0];pos+=4
        cnt=struct.unpack_from('<I',buf,pos)[0];pos+=4;rows=[]
        for _ in range(cnt):
            ln,pos=read7(buf,pos);name=buf[pos:pos+ln].decode();pos+=ln
            off=struct.unpack_from('<Q',buf,pos)[0];pos+=8;rows.append((name,off))
        out.append((frag,payload,rows))
    return out

logical_offsets={};alias_offsets={};fragment=None;fragment_size=None
for apk in apks:
    try:
        with zipfile.ZipFile(apk) as z:
            ns=set(z.namelist());bo='assets/AssetBundles/BundleOffsetTable.bytes';ao='assets/AssetBundles/AliasOffsetTable.bytes';fr='assets/AssetBundles/BundleFragment0.bytes'
            if bo in ns and not logical_offsets:
                rr=parse_offsets(z.read(bo));
                if rr:logical_offsets={n:o for n,o in rr[0][2]}
            if ao in ns and not alias_offsets:
                rr=parse_offsets(z.read(ao));
                if rr:alias_offsets={n:o for n,o in rr[0][2]}
            if fr in ns and fragment is None:
                fragment=(apk,fr);fragment_size=z.getinfo(fr).file_size
    except Exception:pass

off=logical_offsets.get(b['logicalName'])
if off is None:raise SystemExit('TARGET_LOGICAL_OFFSET_NOT_FOUND')
if alias_offsets.get(b['aliasName']) not in (None,off):raise SystemExit('ALIAS_OFFSET_MISMATCH')
ordered=sorted((o,n) for n,o in logical_offsets.items());sizes={}
for i,(o,n) in enumerate(ordered):sizes[o]=(ordered[i+1][0] if i+1<len(ordered) else fragment_size)-o
n=sizes.get(off)
if not fragment or not n or n<=0:raise SystemExit('FRAGMENT_RANGE_NOT_FOUND')
apk,entry=fragment;dest=root/'WorldCityGrass.bundle'
with zipfile.ZipFile(apk) as z,z.open(entry) as f:
    left=off
    while left:
        c=f.read(min(left,1024*1024))
        if not c:raise SystemExit('FRAGMENT_SEEK_FAILED')
        left-=len(c)
    data=f.read(n)
if len(data)!=n:raise SystemExit(f'FRAGMENT_SHORT_READ {len(data)}/{n}')
dest.write_bytes(data)

sink=io.StringIO()
with contextlib.redirect_stderr(sink),contextlib.redirect_stdout(sink):env=UnityPy.load(str(dest));readers=list(env.objects)

def typ(r):
    try:return r.type.name
    except:return str(getattr(r,'type',''))
def read(r):
    try:return r.read()
    except:
        try:return r.parse_as_object()
        except:return None
def pidof(x):
    if x is None:return None
    for o in (x,getattr(x,'object_reader',None),getattr(x,'reader',None)):
        if o is None:continue
        for k in ('path_id','m_PathID'):
            try:
                v=getattr(o,k,None)
                if v is not None:return int(v)
            except:pass
    return None
def pobj(p):
    if p is None:return None
    try:return p.read()
    except:return None
def name(o):
    if o is None:return ''
    return str(getattr(o,'m_Name','') or getattr(o,'name','') or '')
def pname(p):return name(pobj(p))
def vec(v,ns):
    if v is None:return None
    try:return [float(getattr(v,k)) for k in ns]
    except:return None

counts=Counter(typ(r) for r in readers);gos={};trs={};comps=defaultdict(list);monos=[]
for r in readers:
    t=typ(r);o=read(r)
    if o is None:continue
    rp=pidof(r)
    if t=='GameObject':gos[rp]=name(o)
    elif t in ('Transform','RectTransform'):
        gp=getattr(o,'m_GameObject',None);father=getattr(o,'m_Father',None);kids=getattr(o,'m_Children',[]) or []
        trs[rp]={'pathId':rp,'gameObjectPathId':pidof(gp),'name':pname(gp),'parent':pidof(father),'children':[pidof(x) for x in kids if pidof(x) is not None],'localPosition':vec(getattr(o,'m_LocalPosition',None),('x','y','z')),'localRotation':vec(getattr(o,'m_LocalRotation',None),('x','y','z','w')),'localScale':vec(getattr(o,'m_LocalScale',None),('x','y','z'))}
    elif t in ('MeshFilter','MeshRenderer','SkinnedMeshRenderer','SpriteRenderer','Terrain','Light','Camera'):
        gp=getattr(o,'m_GameObject',None);row={'type':t,'pathId':rp,'gameObjectPathId':pidof(gp),'gameObject':pname(gp)}
        if t=='MeshFilter':
            mp=getattr(o,'m_Mesh',None);row['meshPathId']=pidof(mp);row['mesh']=pname(mp)
        if t=='SkinnedMeshRenderer':
            mp=getattr(o,'m_Mesh',None);row['meshPathId']=pidof(mp);row['mesh']=pname(mp)
        if t in ('MeshRenderer','SkinnedMeshRenderer','SpriteRenderer'):
            row['materials']=[{'pathId':pidof(x),'name':pname(x)} for x in (getattr(o,'m_Materials',[]) or [])]
        comps[row['gameObjectPathId']].append(row)
    elif t=='MonoBehaviour':
        gp=getattr(o,'m_GameObject',None);sp=getattr(o,'m_Script',None)
        monos.append({'pathId':rp,'gameObjectPathId':pidof(gp),'gameObject':pname(gp),'scriptPathId':pidof(sp),'script':pname(sp)})
for tr in trs.values():
    if not tr['name']:tr['name']=gos.get(tr['gameObjectPathId'],'')
roots=[x for x in trs.values() if x['parent'] in (None,0)]
roots.sort(key=lambda x:(x['name']!='WorldCityGrass',x['name']))
sel=next((x for x in roots if x['name']=='WorldCityGrass'),roots[0] if roots else None)
hier=[];seen=set()
def walk(tid,d=0):
    if tid in seen or tid not in trs:return
    seen.add(tid);x=trs[tid];gp=x['gameObjectPathId'];hier.append({**x,'depth':d,'components':comps.get(gp,[]),'monoBehaviours':[m for m in monos if m['gameObjectPathId']==gp]})
    for c in x['children']:walk(c,d+1)
if sel:walk(sel['pathId'])
keywords=re.compile(r'rock|stone|shitou|grass|cao|tree|shu|plant|shadow|terrain|ground',re.I)
interesting=[]
for x in hier:
    blob=' '.join([x.get('name','')]+[c.get('mesh','') for c in x.get('components',[])]+[m.get('script','') for m in x.get('monoBehaviours',[])])
    if keywords.search(blob):interesting.append(x)
summary={'format':'WFGG_LASTWAR_WORLDCITYGRASS_APK_COMPOSITION_V1','networkUsed':False,'generatedArtwork':False,'target':target,'bundle':b,'apkFragment':{'entry':entry,'offset':off,'bytes':n},'objectTypeCounts':dict(counts),'rootCount':len(roots),'roots':[{'pathId':x['pathId'],'name':x['name']} for x in roots],'selectedRoot':sel,'hierarchyCount':len(hier),'hierarchy':hier,'interestingCount':len(interesting),'interesting':interesting,'guardrails':{'apkReadOnly':True,'mainUntouched':True,'previewUntouched':True}}
outp.write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n','utf-8')
lines=['WfGg Last War — WORLDCITYGRASS APK COMPOSITION','',f"bundle={b['bundleId']} alias={b['aliasName']} bytes={n}",f"objects={sum(counts.values())} roots={len(roots)} hierarchy={len(hier)} interesting={len(interesting)}",'','OBJECT TYPES']
for k,v in counts.most_common():lines.append(f'  {k}={v}')
lines+=['','ROOTS']+[f"  {x['name']} pathId={x['pathId']}" for x in roots]
lines+=['','INTERESTING NODES']
for x in interesting[:120]:
    lines.append(f"  depth={x['depth']} name={x['name']} pos={x['localPosition']} scale={x['localScale']}")
    for c in x.get('components',[]):lines.append(f"    {c['type']} mesh={c.get('mesh','')} materials={[m['name'] for m in c.get('materials',[])]}")
reportp.write_text('\n'.join(lines)+'\n','utf-8')
print('WORLDCITYGRASS_APK_OK',f"bundle={b['bundleId']}",f"objects={sum(counts.values())}",f"hierarchy={len(hier)}",f"interesting={len(interesting)}")
for x in interesting[:20]:print('WORLD_NODE',f"depth={x['depth']}",f"name={x['name']}",f"pos={x['localPosition']}")
print('WORLDCITYGRASS_APK_JSON',outp)
print('WORLDCITYGRASS_APK_REPORT',reportp)
PYEOF

python "$PY" "$LOCAL" "$GAMERES" "$OUT" "$REPORT" "$TARGET" "$UNITY_VERSION" "${APKS[@]}"
rm -f "$PY"

git add scripts/lastwar-worldcitygrass-apk-extract.sh "$OUT"
if ! git diff --cached --quiet; then
  git commit -m "lab: extract WorldCityGrass composition from APK"
  git push origin "$BRANCH"
fi

echo "=== WORLDCITYGRASS APK EXTRACTION TERMINEE ==="
echo "JSON: $OUT"
echo "Rapport: $REPORT"
echo "Preview inchangée. main non modifiée."
