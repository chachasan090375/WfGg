#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — NATIVE FORMATION RECIPE
# Exact/offline extraction of the real Formation panel and its native
# Environment/Build/Formation family. No generated artwork, no fuzzy matching.

PKG="com.fun.lastwar.gp"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
UNITY_VERSION="2019.4.41f1"
CACHE_ROOT="/sdcard/Android/data/$PKG/files/AssetBundles"
TARGET_UI="Assets/Main/Prefabs/UI/UIHero/LWHero/UIHeroPVPFormationPanel.prefab"
FORM_PREFIX="Assets/_Art_LastWar/Models/Environment/Build/Formation/"
LOCAL="$ROOT/frontend/lab/local_assets/lastwar-formation-native-recipe-v1"
MANIFEST="$ROOT/frontend/lab/master-assets-v2/meta/formation-native-recipe-v1.json"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_FORMATION_NATIVE_RECIPE.txt"
PY="${TMPDIR:-$HOME/.cache}/wfgg-formation-native-recipe.py"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
command -v adb >/dev/null 2>&1 || fail "adb absent"
command -v python >/dev/null 2>&1 || fail "python absent"
python - <<'PY' >/dev/null 2>&1 || fail "UnityPy absent"
import UnityPy
PY
SERIAL="$(adb devices 2>/dev/null | awk 'NR>1 && $2=="device" {print $1; exit}')"
[[ -n "$SERIAL" ]] || fail "aucun appareil ADB connecté"
mapfile -t APK_PATHS < <(cmd package path "$PKG" 2>/dev/null | sed -n 's/^package://p')
[[ ${#APK_PATHS[@]} -gt 0 ]] || fail "APK Last War introuvable"

rm -rf "$LOCAL"
mkdir -p "$LOCAL" "$(dirname "$MANIFEST")" "$(dirname "$REPORT")" "$(dirname "$PY")"
GAMERES="$LOCAL/gameres"
adb -s "$SERIAL" pull "$CACHE_ROOT/gameres" "$GAMERES" >/dev/null || fail "gameres cache illisible"

cat > "$PY" <<'PYEOF'
from __future__ import annotations
from pathlib import Path
from collections import Counter,defaultdict
import json,os,re,struct,subprocess,sys,zipfile,hashlib

local=Path(sys.argv[1]); gameres=Path(sys.argv[2]); manifestp=Path(sys.argv[3]); reportp=Path(sys.argv[4])
serial,cache_root,target_ui,form_prefix,unity_version=sys.argv[5:10]; apks=sys.argv[10:]
import UnityPy
UnityPy.config.FALLBACK_UNITY_VERSION=unity_version

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
for b in bundles.values():b['assetPaths']=[paths.get(pid) for pid in b['assetPathIds'] if paths.get(pid)]

ui_pid=next((pid for pid,p in paths.items() if p.lower()==target_ui.lower()),None)
if ui_pid is None:raise SystemExit('UIHeroPVPFormationPanel exact path absent')
ui=next((b for b in bundles.values() if ui_pid in b['assetPathIds']),None)
if ui is None:raise SystemExit('UIHeroPVPFormationPanel bundle absent')
form=[]
for b in bundles.values():
    if any(p.lower().startswith(form_prefix.lower()) for p in b['assetPaths']):form.append(b)
form.sort(key=lambda x:x['bundleId'])

# Direct dependencies that explain how the panel renders its world/background.
KEY=re.compile(r'formation|world|terrain|splat|grass|rock|tree|blur|camera|scene|environment|shadow',re.I)
interesting=[]
for bid in ui['dependencyBundleIds']:
    b=bundles.get(bid)
    if not b:continue
    hay=' '.join([b['logicalName']]+b['assetPaths'])
    if KEY.search(hay):interesting.append(b)

# Installed-APK fragment indexes, used only as an offline fallback when a bundle
# is not a standalone cache file.
def read7(buf,pos):
    r=0;s=0
    while True:
        x=buf[pos];pos+=1;r|=(x&0x7f)<<s
        if not (x&0x80):return r,pos
        s+=7
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
idx={};alias_idx={};fragment_src=None;fragment_size=None
for apk in apks:
    try:
        with zipfile.ZipFile(apk) as z:
            ns=set(z.namelist())
            bo='assets/AssetBundles/BundleOffsetTable.bytes';ao='assets/AssetBundles/AliasOffsetTable.bytes';fr='assets/AssetBundles/BundleFragment0.bytes'
            if bo in ns and not idx:
                rows=parse_offsets(z.read(bo));
                if rows:idx={n:o for n,o in rows[0][2]}
            if ao in ns and not alias_idx:
                rows=parse_offsets(z.read(ao));
                if rows:alias_idx={n:o for n,o in rows[0][2]}
            if fr in ns and fragment_src is None:
                fragment_src=(apk,fr);fragment_size=z.getinfo(fr).file_size
    except:pass
ordered=sorted((off,n) for n,off in idx.items());sizes={}
if fragment_size is not None:
    for i,(off,n) in enumerate(ordered):sizes[off]=(ordered[i+1][0] if i+1<len(ordered) else fragment_size)-off

def adb_readable(remote):
    cp=subprocess.run(['adb','-s',serial,'shell',f'test -r {remote!r} && echo YES || echo NO'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=12)
    return cp.returncode==0 and 'YES' in cp.stdout

def stage(b,required=False):
    alias=b['aliasName'];logical=b['logicalName'];dest=local/alias
    remote=f'{cache_root}/{alias}'
    if re.fullmatch(r'[0-9a-fA-F]{64}\.bundle',alias) and adb_readable(remote):
        cp=subprocess.run(['adb','-s',serial,'pull',remote,str(dest)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=90)
        if cp.returncode==0 and dest.is_file():return {'bundleId':b['bundleId'],'source':'cache','file':dest.name,'bytes':dest.stat().st_size,'aliasName':alias,'logicalName':logical}
    off=idx.get(logical)
    if off is not None and alias_idx.get(alias)==off and fragment_src and off in sizes:
        apk,entry=fragment_src
        with zipfile.ZipFile(apk) as z,z.open(entry) as f:
            left=off
            while left:
                chunk=f.read(min(left,1024*1024))
                if not chunk:break
                left-=len(chunk)
            n=sizes[off];data=f.read(n)
        if len(data)==n:
            dest.write_bytes(data);return {'bundleId':b['bundleId'],'source':'apk-fragment','file':dest.name,'bytes':n,'aliasName':alias,'logicalName':logical}
    if required:raise SystemExit('required Formation UI bundle unavailable locally: '+alias)
    return {'bundleId':b['bundleId'],'source':'missing','aliasName':alias,'logicalName':logical}

staged=[stage(ui,True)]
for b in form:staged.append(stage(b,False))
files=[local/x['file'] for x in staged if x.get('file')]

# Unity inspection of only the authoritative panel + native Formation family.
def tname(r):
    try:return r.type.name
    except:return str(getattr(r,'type',''))
def robj(r):
    try:return r.read()
    except:
        try:return r.parse_as_object()
        except:return None
def attr(o,*names,default=None):
    for n in names:
        try:
            v=getattr(o,n)
            if v is not None:return v
        except:pass
    return default
def name(o,fb=''):
    return str(attr(o,'m_Name','name',default=fb) or fb)
def pidof(x):
    if x is None:return None
    for n in ('path_id','m_PathID'):
        try:
            v=getattr(x,n,None)
            if v is not None:return int(v)
        except:pass
    try:
        rr=attr(x,'object_reader','reader')
        if rr is not None:return pidof(rr)
    except:pass
    return None
def deref(p):
    if p is None:return None
    for fn in ('read','deref_parse_as_object','parse_as_object'):
        try:
            f=getattr(p,fn,None)
            if callable(f):return f()
        except:pass
    return None
def pname(p):
    try:return name(deref(p))
    except:return ''
def vec(v,names):
    if v is None:return None
    try:return [float(getattr(v,n)) for n in names]
    except:return None
def js(v,depth=0):
    if depth>6:return '<max-depth>'
    if v is None or isinstance(v,(bool,int,float,str)):return v
    if isinstance(v,bytes):return {'bytes':len(v)}
    if isinstance(v,(list,tuple)):return [js(x,depth+1) for x in v[:300]]
    if isinstance(v,dict):return {str(k):js(x,depth+1) for k,x in list(v.items())[:300]}
    p=pidof(v)
    if p not in (None,0):return {'ptrPathId':p,'ptrName':pname(v)}
    for ns in (('x','y','z','w'),('x','y','z'),('r','g','b','a'),('x','y')):
        q=vec(v,ns)
        if q is not None:return q
    try:return {str(k):js(x,depth+1) for k,x in list(vars(v).items())[:120] if not str(k).startswith('_')}
    except:return str(v)[:800]

env=UnityPy.load(*[str(p) for p in files]);readers=list(env.objects);counts=Counter(tname(r) for r in readers)
gos={};trs={};go2tr={};components=defaultdict(list);monos=[]
for r in readers:
    typ=tname(r);d=robj(r);rp=pidof(r)
    if d is None:continue
    if typ=='GameObject':gos[rp]=name(d)
    elif typ in ('Transform','RectTransform'):
        gp=attr(d,'m_GameObject');gpid=pidof(gp);fa=attr(d,'m_Father');kids=attr(d,'m_Children',default=[]) or []
        trs[rp]={'pathId':rp,'gameObjectPathId':gpid,'name':pname(gp) or gos.get(gpid,''),'parent':pidof(fa),'children':[pidof(x) for x in kids if pidof(x) is not None],'localPosition':vec(attr(d,'m_LocalPosition'),('x','y','z')),'localRotation':vec(attr(d,'m_LocalRotation'),('x','y','z','w')),'localScale':vec(attr(d,'m_LocalScale'),('x','y','z'))}
        if gpid is not None:go2tr[gpid]=rp
    elif typ in ('MeshFilter','MeshRenderer','SkinnedMeshRenderer','SpriteRenderer','RawImage','Image','Camera','Light'):
        gp=attr(d,'m_GameObject');gpid=pidof(gp);rec={'type':typ,'pathId':rp,'gameObject':pname(gp)}
        if typ=='MeshFilter':rec['mesh']=pname(attr(d,'m_Mesh'))
        if typ in ('MeshRenderer','SkinnedMeshRenderer'):
            rec['materials']=[pname(x) for x in (attr(d,'m_Materials',default=[]) or [])]
        components[gpid].append(rec)
    elif typ=='MonoBehaviour':
        gp=attr(d,'m_GameObject');sp=attr(d,'m_Script');tree=None;err=None
        try:
            f=getattr(r,'read_typetree',None);tree=js(f()) if callable(f) else js(d)
        except Exception as e:err=repr(e);tree=js(d)
        monos.append({'pathId':rp,'gameObject':pname(gp),'script':pname(sp),'typetree':tree,'error':err})
for t in trs.values():
    if not t['name']:t['name']=gos.get(t['gameObjectPathId'],'')
roots=[t for t in trs.values() if t['parent'] in (None,0)]
roots.sort(key=lambda x:(x['name']!='UIHeroPVPFormationPanel',x['name']))
sel=next((x for x in roots if x['name']=='UIHeroPVPFormationPanel'),roots[0] if roots else None)
hier=[];seen=set()
def walk(pid,depth=0):
    if pid in seen or pid not in trs or depth>80:return
    seen.add(pid);t=trs[pid];hier.append({**t,'depth':depth,'components':components.get(t['gameObjectPathId'],[])})
    for c in t['children']:walk(c,depth+1)
if sel:walk(sel['pathId'])

# Exact keyword hits in serialized strings are useful even when MonoBehaviour type
# trees are stripped in the release build.
raw_hits=[]
for x in staged:
    if not x.get('file'):continue
    data=(local/x['file']).read_bytes()
    strings=[m.group().decode('ascii','ignore') for m in re.finditer(rb'[\x20-\x7e]{4,}',data)]
    hits=[]
    for s in strings:
        if KEY.search(s) and s not in hits:hits.append(s)
    if hits:raw_hits.append({'bundleId':x['bundleId'],'source':x['source'],'hits':hits[:500]})

mono_hits=[]
def scan(v,path=''):
    out=[]
    if isinstance(v,dict):
        for k,x in v.items():
            p=f'{path}.{k}' if path else str(k)
            if KEY.search(str(k)) or (isinstance(x,str) and KEY.search(x)):out.append({'path':p,'value':x})
            if isinstance(x,(dict,list)):out.extend(scan(x,p))
    elif isinstance(v,list):
        for i,x in enumerate(v[:300]):
            if isinstance(x,(dict,list)):out.extend(scan(x,f'{path}[{i}]'))
    return out[:1000]
for m in monos:
    h=scan(m['typetree'])
    if h:mono_hits.append({'gameObject':m['gameObject'],'script':m['script'],'hits':h})

summary={'format':'WFGG_LASTWAR_FORMATION_NATIVE_RECIPE_V1','networkUsed':False,'generatedArtwork':False,
 'source':{'gameresBytes':gameres.stat().st_size,'adbSerial':serial},
 'uiPanel':ui,'nativeFormationFamily':form,'staged':staged,
 'interestingDirectDependencies':interesting,
 'objectTypeCounts':dict(counts),'rootCandidates':roots,'selectedRoot':sel,'hierarchy':hier,
 'monoBehaviours':monos,'monoKeywordHits':mono_hits,'rawKeywordHits':raw_hits,
 'guardrails':{'exactPathsOnly':True,'cacheOrInstalledApkOnly':True,'noGeneratedArtwork':True,'noLastWarNetwork':True}}
manifestp.write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')

lines=['WfGg Last War — FORMATION NATIVE RECIPE','EXACT UI PANEL + NATIVE ENVIRONMENT/BUILD/FORMATION · OFFLINE ONLY',
 f"uiPath={target_ui}",f"uiBundleId={ui['bundleId']}",f"uiAlias={ui['aliasName']}",f"uiStage={staged[0]['source']}",
 f"formationFamilyBundles={len(form)} staged={sum(1 for x in staged[1:] if x.get('file'))}/{len(form)}",
 f"objects={sum(counts.values())} roots={len(roots)} hierarchyNodes={len(hier)} mono={len(monos)}",'', 'INTERESTING DIRECT DEPENDENCIES']
for b in interesting:
    lines.append(f"  {b['bundleId']} {b['logicalName']} alias={b['aliasName']}")
    for p in b['assetPaths'][:20]:lines.append('    '+p)
lines+=['','UI HIERARCHY']
for n in hier:
    lines.append('  '*n['depth']+f"{n['name']} pos={n['localPosition']} scale={n['localScale']} comps={','.join(c['type'] for c in n['components']) or '-'}")
lines+=['','MONOBEHAVIOUR KEYWORD HITS']
for g in mono_hits:
    lines.append(f"  GO={g['gameObject']} script={g['script']}")
    for h in g['hits'][:100]:lines.append('    '+h['path']+' = '+json.dumps(h['value'],ensure_ascii=False)[:500])
if not mono_hits:lines.append('  none')
lines+=['','RAW SERIALIZED STRING HITS']
for r in raw_hits:
    lines.append(f"  BUNDLE {r['bundleId']} source={r['source']}")
    for h in r['hits'][:150]:lines.append('    '+h[:500])
reportp.write_text('\n'.join(lines)+'\n',encoding='utf-8')
print('FORMATION_NATIVE_RECIPE_OK',f"ui={staged[0]['source']}",f"family={sum(1 for x in staged[1:] if x.get('file'))}/{len(form)}",f"hierarchy={len(hier)}",f"monoHits={len(mono_hits)}",flush=True)
print('FORMATION_NATIVE_RECIPE_REPORT',reportp,flush=True)
PYEOF

python "$PY" "$LOCAL" "$GAMERES" "$MANIFEST" "$REPORT" "$SERIAL" "$CACHE_ROOT" "$TARGET_UI" "$FORM_PREFIX" "$UNITY_VERSION" "${APK_PATHS[@]}"
rm -f "$PY"

git add scripts/lastwar-formation-native-recipe.sh "$MANIFEST"
if ! git diff --cached --quiet; then
  git commit -m "lab: record native Formation composition recipe"
  git push origin "$BRANCH"
fi

echo "=== FORMATION NATIVE RECIPE TERMINEE ==="
echo "Manifest: $MANIFEST"
echo "Rapport: $REPORT"
echo "main non modifiée."
