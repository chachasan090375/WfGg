#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — robust WorldCityGrass extractor V2
# Reads ALL BundleOffsetTable/AliasOffsetTable groups and ALL installed APK fragments.
# Offline/read-only against Last War. Preview and main untouched.

PKG="com.fun.lastwar.gp"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
UNITY_VERSION="2019.4.41f1"
TARGET="Assets/Main/Prefabs/World/WorldCityGrass.prefab"
GAMERES="$ROOT/frontend/lab/local_assets/lastwar-formation-native-recipe-v1/gameres"
LOCAL="$ROOT/frontend/lab/local_assets/lastwar-worldcitygrass-apk-v2"
OUT="$ROOT/frontend/lab/master-assets-v2/meta/worldcitygrass-apk-composition-v2.json"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_WORLDCITYGRASS_APK_COMPOSITION_V2.txt"
PY="${TMPDIR:-$HOME/.cache}/wfgg-worldcitygrass-apk-v2.py"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
[[ -s "$GAMERES" ]] || fail "gameres local absent"
command -v python >/dev/null 2>&1 || fail "python absent"
python - <<'PY' >/dev/null 2>&1 || fail "UnityPy absent"
import UnityPy
PY
mapfile -t APKS < <(cmd package path "$PKG" 2>/dev/null | sed -n 's/^package://p')
[[ ${#APKS[@]} -gt 0 ]] || fail "APK Last War introuvable"
mkdir -p "$LOCAL" "$(dirname "$OUT")" "$(dirname "$REPORT")" "$(dirname "$PY")"
rm -f "$LOCAL"/WorldCityGrass.bundle

cat > "$PY" <<'PYEOF'
from __future__ import annotations
from pathlib import Path
from collections import Counter,defaultdict
import contextlib,io,json,re,struct,sys,zipfile

local=Path(sys.argv[1]); gameres=Path(sys.argv[2]); outp=Path(sys.argv[3]); reportp=Path(sys.argv[4]); target=sys.argv[5]; unity=sys.argv[6]; apks=sys.argv[7:]
import UnityPy
UnityPy.config.FALLBACK_UNITY_VERSION=unity
text=gameres.read_text('utf-8')

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
    try:pid,did,n=ln.split(',',2);paths[int(pid)]=dirs[int(did)].rstrip('/')+'/'+n
    except:pass
bundles={}
for ln in section('Bundles'):
    p=ln.split(',')
    if len(p)<8:continue
    try:
        bid=int(p[0]); bundles[bid]={
            'bundleId':bid,'logicalName':p[1],'declaredBytes':int(p[3]),
            'assetPathIds':[int(x) for x in p[4].split('|') if x],
            'dependencyBundleIds':[int(x) for x in p[5].split('|') if x],
            'groups':p[6].split('|') if p[6] else [],'aliasName':p[7]}
    except:pass
pid=next((i for i,p in paths.items() if p.lower()==target.lower()),None)
if pid is None:raise SystemExit('TARGET_PATH_NOT_FOUND')
b=next((x for x in bundles.values() if pid in x['assetPathIds']),None)
if not b:raise SystemExit('TARGET_BUNDLE_NOT_FOUND')
print('TARGET_RESOLVED',f"bundle={b['bundleId']}",f"logical={b['logicalName']}",f"alias={b['aliasName']}")

def read7(buf,pos):
    out=0;shift=0
    while True:
        if pos>=len(buf):raise ValueError('7bit EOF')
        x=buf[pos];pos+=1;out|=(x&0x7f)<<shift
        if not x&0x80:return out,pos
        shift+=7

def parse_offsets(buf):
    pos=0;fc=struct.unpack_from('<I',buf,pos)[0];pos+=4;groups=[]
    for gi in range(fc):
        ln,pos=read7(buf,pos);frag=buf[pos:pos+ln].decode('utf-8','replace');pos+=ln
        payload=struct.unpack_from('<I',buf,pos)[0];pos+=4
        cnt=struct.unpack_from('<I',buf,pos)[0];pos+=4;rows=[]
        for _ in range(cnt):
            ln,pos=read7(buf,pos);name=buf[pos:pos+ln].decode('utf-8','replace');pos+=ln
            off=struct.unpack_from('<Q',buf,pos)[0];pos+=8;rows.append((name,off))
        groups.append({'group':gi,'fragment':frag,'payload':payload,'rows':rows})
    return groups

# Collect tables and physical fragment entries across every installed APK.
table_groups={'logical':[],'alias':[]}; physical=[]
for apk in apks:
    try:
        with zipfile.ZipFile(apk) as z:
            names=z.namelist();ns=set(names)
            for kind,entry in [('logical','assets/AssetBundles/BundleOffsetTable.bytes'),('alias','assets/AssetBundles/AliasOffsetTable.bytes')]:
                if entry in ns:
                    try:
                        for g in parse_offsets(z.read(entry)):
                            table_groups[kind].append({**g,'tableApk':apk,'tableEntry':entry})
                    except Exception as e:print('TABLE_PARSE_WARNING',kind,Path(apk).name,repr(e))
            for n in names:
                low=n.lower()
                if 'assets/assetbundles/' in low and 'bundlefragment' in low and low.endswith('.bytes'):
                    physical.append({'apk':apk,'entry':n,'base':Path(n).name,'stem':Path(n).stem,'size':z.getinfo(n).file_size})
    except Exception as e:print('APK_SCAN_WARNING',Path(apk).name,repr(e))

if not physical:raise SystemExit('NO_BUNDLE_FRAGMENTS_FOUND')

def hits(kind,name):
    out=[]
    for g in table_groups[kind]:
        for rn,off in g['rows']:
            if rn==name:out.append({**g,'rowName':rn,'offset':off,'kind':kind})
    return out
lh=hits('logical',b['logicalName']); ah=hits('alias',b['aliasName'])
print('OFFSET_HITS',f'logical={len(lh)}',f'alias={len(ah)}',f'logicalGroups={len(table_groups["logical"])}',f'aliasGroups={len(table_groups["alias"])}',f'physicalFragments={len(physical)}')
if not lh and not ah:
    # Diagnostic near-matches, never used as extraction fallback.
    needle='worldcitygrass'
    near=[]
    for kind,gs in table_groups.items():
        for g in gs:
            for rn,off in g['rows']:
                if needle in rn.lower():near.append((kind,g['group'],g['fragment'],rn,off))
    print('OFFSET_NEAR_MATCHES',json.dumps(near[:20],ensure_ascii=False))
    raise SystemExit('TARGET_OFFSET_NOT_FOUND_ALL_GROUPS')

# Alias is strongest identity; otherwise logical name.
hit=(ah or lh)[0]

def norm(s):return re.sub(r'[^a-z0-9]','',str(s).lower())
def match_fragment(hit):
    frag=hit.get('fragment','');nf=norm(frag)
    # 1 exact basename/stem-ish match from table metadata.
    ranked=[]
    for p in physical:
        nb=norm(p['base']);ns=norm(p['stem']);score=0
        if nf and (nf==nb or nf==ns):score=100
        elif nf and (nf in nb or nb in nf or nf in ns or ns in nf):score=80
        # 2 group number in filename.
        if re.search(rf'fragment0*{hit["group"]}(?:\D|$)',p['base'],re.I):score=max(score,60)
        ranked.append((score,p))
    ranked.sort(key=lambda x:(-x[0],x[1]['base']))
    if ranked and ranked[0][0]>0:return ranked[0][1],ranked[0][0]
    # 3 positional fallback only when table/physical counts make this unambiguous enough.
    ps=sorted(physical,key=lambda p:p['base'])
    gi=int(hit['group'])
    if 0<=gi<len(ps):return ps[gi],20
    return None,0

phys,matchscore=match_fragment(hit)
if not phys:raise SystemExit('TARGET_FRAGMENT_FILE_NOT_RESOLVED')
print('OFFSET_SELECTED',f"kind={hit['kind']}",f"group={hit['group']}",f"tableFragment={hit['fragment']}",f"offset={hit['offset']}",f"physical={phys['entry']}",f"matchScore={matchscore}")

# Determine end from all row offsets of the same group/fragment; union logical+alias is safe.
off=int(hit['offset']); offsets={off}
for kind,gs in table_groups.items():
    for g in gs:
        if int(g['group'])==int(hit['group']) and norm(g.get('fragment',''))==norm(hit.get('fragment','')):
            offsets.update(int(o) for _,o in g['rows'])
nexts=sorted(x for x in offsets if x>off)
end=nexts[0] if nexts else int(phys['size'])
n=end-off
# Sanity against declared size: exact fragment range can include padding, but must not be smaller.
if n<=0:raise SystemExit(f'INVALID_FRAGMENT_RANGE off={off} end={end}')
if off+n>phys['size']:raise SystemExit(f'FRAGMENT_RANGE_OVERFLOW off={off} bytes={n} fragment={phys["size"]}')
print('FRAGMENT_RANGE',f'offset={off}',f'bytes={n}',f'declared={b["declaredBytes"]}',f'fragmentSize={phys["size"]}')

dest=local/'WorldCityGrass.bundle'
with zipfile.ZipFile(phys['apk']) as z,z.open(phys['entry']) as f:
    left=off
    while left:
        c=f.read(min(left,1024*1024))
        if not c:raise SystemExit('FRAGMENT_SEEK_FAILED')
        left-=len(c)
    data=f.read(n)
if len(data)!=n:raise SystemExit(f'FRAGMENT_SHORT_READ {len(data)}/{n}')
dest.write_bytes(data)

sink=io.StringIO()
with contextlib.redirect_stdout(sink),contextlib.redirect_stderr(sink):
    env=UnityPy.load(str(dest)); readers=list(env.objects)

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
    try:return p.read() if p is not None else None
    except:return None
def name(o):return '' if o is None else str(getattr(o,'m_Name','') or getattr(o,'name','') or '')
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
        gp=getattr(o,'m_GameObject',None);fa=getattr(o,'m_Father',None);kids=getattr(o,'m_Children',[]) or []
        trs[rp]={'pathId':rp,'gameObjectPathId':pidof(gp),'name':pname(gp),'parent':pidof(fa),'children':[pidof(x) for x in kids if pidof(x) is not None],'localPosition':vec(getattr(o,'m_LocalPosition',None),('x','y','z')),'localRotation':vec(getattr(o,'m_LocalRotation',None),('x','y','z','w')),'localScale':vec(getattr(o,'m_LocalScale',None),('x','y','z'))}
    elif t in ('MeshFilter','MeshRenderer','SkinnedMeshRenderer','SpriteRenderer','Terrain','Light','Camera'):
        gp=getattr(o,'m_GameObject',None);row={'type':t,'pathId':rp,'gameObjectPathId':pidof(gp),'gameObject':pname(gp)}
        if t in ('MeshFilter','SkinnedMeshRenderer'):
            mp=getattr(o,'m_Mesh',None);row.update({'meshPathId':pidof(mp),'mesh':pname(mp)})
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
kw=re.compile(r'rock|stone|shitou|grass|cao|tree|shu|plant|shadow|terrain|ground|env',re.I)
interesting=[]
for x in hier:
    blob=' '.join([x.get('name','')]+[c.get('mesh','') or '' for c in x.get('components',[])]+[m.get('script','') or '' for m in x.get('monoBehaviours',[])])
    if kw.search(blob):interesting.append(x)

summary={'format':'WFGG_LASTWAR_WORLDCITYGRASS_APK_COMPOSITION_V2','target':target,'bundle':b,'resolution':{'offsetKind':hit['kind'],'tableGroup':hit['group'],'tableFragment':hit['fragment'],'physicalApk':Path(phys['apk']).name,'physicalEntry':phys['entry'],'matchScore':matchscore,'offset':off,'bytes':n},'objectTypeCounts':dict(counts),'rootCount':len(roots),'roots':[{'pathId':x['pathId'],'name':x['name']} for x in roots],'selectedRoot':sel,'hierarchyCount':len(hier),'hierarchy':hier,'interestingCount':len(interesting),'interesting':interesting,'guardrails':{'offline':True,'apkReadOnly':True,'previewUntouched':True,'mainUntouched':True}}
outp.write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n','utf-8')
lines=['WfGg Last War — WORLDCITYGRASS APK COMPOSITION V2','',f"bundle={b['bundleId']} alias={b['aliasName']}",f"offsetKind={hit['kind']} group={hit['group']} tableFragment={hit['fragment']}",f"physical={Path(phys['apk']).name}:{phys['entry']}",f"offset={off} bytes={n} declared={b['declaredBytes']}",f"objects={sum(counts.values())} roots={len(roots)} hierarchy={len(hier)} interesting={len(interesting)}",'','OBJECT TYPES']
for k,v in counts.most_common():lines.append(f'  {k}={v}')
lines+=['','ROOTS']+[f"  {x['name']} pathId={x['pathId']}" for x in roots]
lines+=['','INTERESTING NODES']
for x in interesting[:160]:
    lines.append(f"  depth={x['depth']} name={x['name']} pos={x['localPosition']} scale={x['localScale']}")
    for c in x.get('components',[]):lines.append(f"    {c['type']} mesh={c.get('mesh','')} materials={[m['name'] for m in c.get('materials',[])]}")
reportp.write_text('\n'.join(lines)+'\n','utf-8')
print('WORLDCITYGRASS_APK_V2_OK',f"bundle={b['bundleId']}",f"objects={sum(counts.values())}",f"hierarchy={len(hier)}",f"interesting={len(interesting)}")
for x in interesting[:24]:print('WORLD_NODE',f"depth={x['depth']}",f"name={x['name']}",f"pos={x['localPosition']}")
print('WORLDCITYGRASS_APK_V2_JSON',outp)
print('WORLDCITYGRASS_APK_V2_REPORT',reportp)
PYEOF

python "$PY" "$LOCAL" "$GAMERES" "$OUT" "$REPORT" "$TARGET" "$UNITY_VERSION" "${APKS[@]}"
rm -f "$PY"

git add scripts/lastwar-worldcitygrass-apk-extract-v2.sh "$OUT"
if ! git diff --cached --quiet; then
  git commit -m "lab: record robust WorldCityGrass APK composition"
  git push origin "$BRANCH"
fi

echo "=== WORLDCITYGRASS APK V2 TERMINEE ==="
echo "JSON: $OUT"
echo "Rapport: $REPORT"
echo "Preview inchangée. main non modifiée."
