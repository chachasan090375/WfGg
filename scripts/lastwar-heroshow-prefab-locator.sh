#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — locate the exact AssetBundle carrying HeroShowSetting.
# Strategy: search physical BundleFragment*.bytes for the CLR class name, map the
# physical offset back through BundleOffsetTable/AliasOffsetTable, extract only
# the containing bundle, then inspect its prefab hierarchy with UnityPy.
# Read-only on installed APKs. Preview/main untouched.

PKG="com.fun.lastwar.gp"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
UNITY_VERSION="2019.4.41f1"
GAMERES="$ROOT/frontend/lab/local_assets/lastwar-formation-native-recipe-v1/gameres"
LOCAL="$ROOT/frontend/lab/local_assets/lastwar-heroshow-prefab-v1"
OUT="$ROOT/frontend/lab/master-assets-v2/meta/heroshow-prefab-locator-v1.json"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_HEROSHOW_PREFAB_LOCATOR.txt"
PY="${TMPDIR:-$HOME/.cache}/wfgg-heroshow-prefab-locator.py"

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
rm -f "$LOCAL"/*.bundle

cat > "$PY" <<'PYEOF'
from __future__ import annotations
from pathlib import Path
from collections import Counter,defaultdict
import contextlib,io,json,re,struct,sys,zipfile

local=Path(sys.argv[1]); gameres=Path(sys.argv[2]); outp=Path(sys.argv[3]); reportp=Path(sys.argv[4]); unity=sys.argv[5]; apks=[Path(x) for x in sys.argv[6:]]
import UnityPy
UnityPy.config.FALLBACK_UNITY_VERSION=unity
text=gameres.read_text('utf-8',errors='replace')

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
by_logical={b['logicalName']:b for b in bundles.values()}; by_alias={b['aliasName']:b for b in bundles.values() if b['aliasName']}

def read7(buf,pos):
    out=0;shift=0
    while True:
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
            off=struct.unpack_from('<Q',buf,pos)[0];pos+=8;rows.append((name,int(off)))
        groups.append({'group':gi,'fragment':frag,'payload':payload,'rows':rows})
    return groups

def norm(s):return re.sub(r'[^a-z0-9]','',str(s).lower())

tables={'logical':[],'alias':[]}; physical=[]
for apk in apks:
    try:
        with zipfile.ZipFile(apk) as z:
            names=z.namelist(); ns=set(names)
            for kind,entry in [('logical','assets/AssetBundles/BundleOffsetTable.bytes'),('alias','assets/AssetBundles/AliasOffsetTable.bytes')]:
                if entry in ns:
                    try:
                        for g in parse_offsets(z.read(entry)): tables[kind].append({**g,'tableApk':str(apk),'tableEntry':entry})
                    except Exception as e: print('TABLE_WARNING',kind,apk.name,repr(e))
            for n in names:
                low=n.lower()
                if 'assets/assetbundles/' in low and 'bundlefragment' in low and low.endswith('.bytes'):
                    physical.append({'apk':str(apk),'entry':n,'base':Path(n).name,'stem':Path(n).stem,'size':z.getinfo(n).file_size})
    except Exception as e: print('APK_WARNING',apk.name,repr(e))

print('HEROSHOW_FRAGMENT_SCAN',f'apks={len(apks)}',f'fragments={len(physical)}',f'logicalGroups={len(tables["logical"])}',f'aliasGroups={len(tables["alias"])}')
needles=[b'HeroShowSetting',b'GrabCamera',b'Camp_']
hits=[]
for pi,p in enumerate(physical,1):
    try:
        with zipfile.ZipFile(p['apk']) as z:
            data=z.read(p['entry'])
        for needle in needles:
            start=0
            while True:
                off=data.find(needle,start)
                if off<0:break
                hits.append({'needle':needle.decode(),'apk':p['apk'],'entry':p['entry'],'fragmentBase':p['base'],'offset':off,'fragmentSize':len(data)})
                start=off+1
    except Exception as e: print('FRAGMENT_SCAN_WARNING',p['base'],repr(e))
    if pi%5==0: print('HEROSHOW_FRAGMENT_PROGRESS',f'{pi}/{len(physical)}')

print('HEROSHOW_STRING_HITS',f'total={len(hits)}',f'hero={sum(h["needle"]=="HeroShowSetting" for h in hits)}',f'grab={sum(h["needle"]=="GrabCamera" for h in hits)}',f'camp={sum(h["needle"]=="Camp_" for h in hits)}')
for h in hits[:40]:print('HEROSHOW_STRING_HIT',h['needle'],Path(h['apk']).name,h['fragmentBase'],h['offset'])

# Map each physical hit to the most plausible table group and containing bundle interval.
def frag_match_score(fragment_name,physical_base,group):
    nf=norm(fragment_name); nb=norm(physical_base); score=0
    if nf and (nf==nb or nf==norm(Path(physical_base).stem)):score=100
    elif nf and (nf in nb or nb in nf):score=80
    if re.search(rf'fragment0*{group}(?:\D|$)',physical_base,re.I):score=max(score,60)
    return score

mapped=[]
for h in hits:
    candidates=[]
    for kind,gs in tables.items():
        for g in gs:
            sc=frag_match_score(g['fragment'],h['fragmentBase'],g['group'])
            if sc<=0:continue
            rows=sorted(g['rows'],key=lambda x:x[1])
            for i,(name,off) in enumerate(rows):
                end=rows[i+1][1] if i+1<len(rows) else h['fragmentSize']
                if off<=h['offset']<end:
                    b=(by_alias.get(name) if kind=='alias' else by_logical.get(name))
                    candidates.append({'score':sc,'kind':kind,'group':g['group'],'tableFragment':g['fragment'],'rowName':name,'start':off,'end':end,'bundle':b})
                    break
    candidates.sort(key=lambda x:(-x['score'],x['kind']!='alias',x['start']))
    if candidates:
        c=candidates[0]; mapped.append({**h,**c})

hero_mapped=[m for m in mapped if m['needle']=='HeroShowSetting']
print('HEROSHOW_MAPPED',f'total={len(mapped)}',f'hero={len(hero_mapped)}')
for m in hero_mapped[:20]:
    b=m.get('bundle') or {}
    print('HEROSHOW_BUNDLE_CANDIDATE',f"bundle={b.get('bundleId','?')}",f"logical={b.get('logicalName',m['rowName'])}",f"alias={b.get('aliasName','')}",f"offset={m['start']}",f"bytes={m['end']-m['start']}",f"score={m['score']}")

# Extract unique HeroShowSetting-containing intervals and inspect with UnityPy.
inspected=[]; seen=set()
for idx,m in enumerate(hero_mapped[:8],1):
    key=(m['apk'],m['entry'],m['start'],m['end'])
    if key in seen:continue
    seen.add(key)
    n=m['end']-m['start']
    if n<=0 or n>300_000_000:continue
    dest=local/f'heroshow_candidate_{idx:02d}.bundle'
    try:
        with zipfile.ZipFile(m['apk']) as z,z.open(m['entry']) as f:
            left=m['start']
            while left:
                c=f.read(min(left,1024*1024))
                if not c:raise RuntimeError('seek EOF')
                left-=len(c)
            blob=f.read(n)
        if len(blob)!=n:raise RuntimeError(f'short read {len(blob)}/{n}')
        dest.write_bytes(blob)
        sink=io.StringIO()
        with contextlib.redirect_stdout(sink),contextlib.redirect_stderr(sink): env=UnityPy.load(str(dest)); readers=list(env.objects)
    except Exception as e:
        inspected.append({'candidate':m,'file':str(dest),'unityError':repr(e)});continue

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

    counts=Counter(typ(r) for r in readers); scripts={}; gos={}; trs={}; comps=defaultdict(list); monos=[]
    for r in readers:
        t=typ(r);o=read(r)
        if o is None:continue
        rp=pidof(r)
        if t=='MonoScript':
            scripts[rp]={'pathId':rp,'name':name(o),'className':str(getattr(o,'m_ClassName','') or ''),'namespace':str(getattr(o,'m_Namespace','') or ''),'assembly':str(getattr(o,'m_AssemblyName','') or '')}
        elif t=='GameObject':gos[rp]=name(o)
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
            gp=getattr(o,'m_GameObject',None);sp=getattr(o,'m_Script',None);sid=pidof(sp)
            monos.append({'pathId':rp,'gameObjectPathId':pidof(gp),'gameObject':pname(gp),'scriptPathId':sid})
    for tr in trs.values():
        if not tr['name']:tr['name']=gos.get(tr['gameObjectPathId'],'')
    for mo in monos:
        mo['script']=scripts.get(mo['scriptPathId'],{})
    roots=[x for x in trs.values() if x['parent'] in (None,0)]
    hierarchy=[];seen_tr=set()
    def walk(tid,d=0):
        if tid in seen_tr or tid not in trs:return
        seen_tr.add(tid);x=trs[tid];gp=x['gameObjectPathId']
        hierarchy.append({**x,'depth':d,'components':comps.get(gp,[]),'monoBehaviours':[mm for mm in monos if mm['gameObjectPathId']==gp]})
        for c in x['children']:walk(c,d+1)
    for r in sorted(roots,key=lambda x:x['name']):walk(r['pathId'])
    hero_scripts=[s for s in scripts.values() if s.get('className')=='HeroShowSetting' or s.get('name')=='HeroShowSetting']
    hero_monos=[mo for mo in monos if mo.get('script',{}).get('className')=='HeroShowSetting' or mo.get('script',{}).get('name')=='HeroShowSetting']
    keynodes=[x for x in hierarchy if re.search(r'(^Camp_|GrabCamera|HeroShow|Formation|Ground|Grass|Rock|Stone|shitou|tree|shadow)',x.get('name',''),re.I)]
    b=m.get('bundle') or {}
    asset_paths=[paths.get(pid,'') for pid in b.get('assetPathIds',[]) if paths.get(pid)]
    inspected.append({'candidate':m,'bundle':b,'assetPaths':asset_paths,'file':str(dest),'objectTypeCounts':dict(counts),'scripts':list(scripts.values()),'heroScripts':hero_scripts,'heroMonoBehaviours':hero_monos,'roots':[{'pathId':r['pathId'],'name':r['name']} for r in roots],'hierarchyCount':len(hierarchy),'keyNodes':keynodes[:1000],'hierarchy':hierarchy[:3000]})
    print('HEROSHOW_UNITY_OK',f"bundle={b.get('bundleId','?')}",f'objects={len(readers)}',f'roots={len(roots)}',f'heroScripts={len(hero_scripts)}',f'heroMonos={len(hero_monos)}',f'keyNodes={len(keynodes)}')
    for x in keynodes[:50]: print('HEROSHOW_NODE',f"depth={x['depth']}",f"name={x['name']}",f"pos={x.get('localPosition')}")

summary={'format':'WFGG_LASTWAR_HEROSHOW_PREFAB_LOCATOR_V1','needles':[x.decode() for x in needles],'physicalFragmentCount':len(physical),'stringHits':hits[:500],'mappedHits':mapped[:500],'heroMappedCount':len(hero_mapped),'inspected':inspected,'guardrails':{'apkReadOnly':True,'previewUntouched':True,'mainUntouched':True}}
outp.write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n','utf-8')
lines=['WfGg Last War — HEROSHOW PREFAB LOCATOR','',f'fragments={len(physical)} stringHits={len(hits)} heroMapped={len(hero_mapped)} inspected={len(inspected)}','']
for m in hero_mapped[:20]:
    b=m.get('bundle') or {};lines.append(f"BUNDLE bundle={b.get('bundleId','?')} logical={b.get('logicalName',m['rowName'])} alias={b.get('aliasName','')} offset={m['start']} bytes={m['end']-m['start']}")
for r in inspected:
    if r.get('unityError'):lines.append('UNITY_ERROR '+r['unityError']);continue
    b=r.get('bundle') or {};lines.append(f"UNITY bundle={b.get('bundleId','?')} assets={r.get('assetPaths',[])} roots={r.get('roots',[])} heroScripts={len(r.get('heroScripts',[]))} heroMonos={len(r.get('heroMonoBehaviours',[]))}")
    for x in r.get('keyNodes',[])[:100]:lines.append(f"  NODE depth={x['depth']} name={x['name']} pos={x.get('localPosition')}")
reportp.write_text('\n'.join(lines)+'\n','utf-8')
print('HEROSHOW_PREFAB_LOCATOR_OK',f'heroMapped={len(hero_mapped)}',f'inspected={len(inspected)}')
print('HEROSHOW_PREFAB_JSON',outp)
print('HEROSHOW_PREFAB_REPORT',reportp)
PYEOF

python "$PY" "$LOCAL" "$GAMERES" "$OUT" "$REPORT" "$UNITY_VERSION" "${APKS[@]}"
rm -f "$PY"

git add scripts/lastwar-heroshow-prefab-locator.sh "$OUT"
if ! git diff --cached --quiet; then
  git commit -m "lab: locate HeroShowSetting prefab bundle"
  git push origin "$BRANCH"
fi

echo "=== HEROSHOW PREFAB LOCATOR TERMINE ==="
echo "JSON: $OUT"
echo "Rapport: $REPORT"
echo "Preview inchangée. main non modifiée."
