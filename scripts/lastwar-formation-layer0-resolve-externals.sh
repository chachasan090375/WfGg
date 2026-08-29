#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — FORMATION LAYER0 EXTERNAL RESOLUTION
# Resolves the exact external references already exposed by the native panel:
#   FormationRT.m_Material and FormationContent/Bg.m_Texture.
# It searches only direct dependencies of UIHeroPVPFormationPanel.

PKG="com.fun.lastwar.gp"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
UNITY_VERSION="2019.4.41f1"
CACHE_ROOT="/sdcard/Android/data/$PKG/files/AssetBundles"
LOCAL="$ROOT/frontend/lab/local_assets/lastwar-formation-native-recipe-v1"
SRC_RECIPE="$ROOT/frontend/lab/master-assets-v2/meta/formation-native-recipe-v1.json"
SRC_LINKS="$ROOT/frontend/lab/master-assets-v2/meta/formation-layer0-native-links-v1.json"
OUT="$ROOT/frontend/lab/master-assets-v2/meta/formation-layer0-external-resolution-v1.json"
EXPORT="$ROOT/frontend/lab/master-assets-v2/ui/formation-layer0-exact-external.png"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_FORMATION_LAYER0_EXTERNAL_RESOLUTION.txt"
PY="${TMPDIR:-$HOME/.cache}/wfgg-formation-layer0-resolve-externals.py"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
[[ -s "$SRC_RECIPE" ]] || fail "recipe absente: $SRC_RECIPE"
[[ -s "$SRC_LINKS" ]] || fail "native links absents: $SRC_LINKS"
[[ -s "$LOCAL/gameres" ]] || fail "gameres local absent; relancer d'abord lastwar-formation-native-recipe.sh"
command -v python >/dev/null 2>&1 || fail "python absent"
python - <<'PY' >/dev/null 2>&1 || fail "UnityPy absent"
import UnityPy
PY
mkdir -p "$(dirname "$OUT")" "$(dirname "$EXPORT")" "$(dirname "$REPORT")" "$(dirname "$PY")"

mapfile -t APK_PATHS < <(cmd package path "$PKG" 2>/dev/null | sed -n 's/^package://p')
[[ ${#APK_PATHS[@]} -gt 0 ]] || fail "APK Last War introuvable"
SERIAL=""
if command -v adb >/dev/null 2>&1; then
  SERIAL="$(adb devices 2>/dev/null | awk 'NR>1 && $2=="device" {print $1; exit}')"
fi

cat > "$PY" <<'PYEOF'
from __future__ import annotations
from pathlib import Path
from collections import defaultdict
import json,sys,re,struct,subprocess,zipfile,shutil,tempfile,hashlib

local=Path(sys.argv[1]); recipep=Path(sys.argv[2]); linksp=Path(sys.argv[3]); outp=Path(sys.argv[4]); exportp=Path(sys.argv[5]); reportp=Path(sys.argv[6])
serial,cache_root,unity_version=sys.argv[7:10]; apks=sys.argv[10:]
import UnityPy
UnityPy.config.FALLBACK_UNITY_VERSION=unity_version

recipe=json.loads(recipep.read_text('utf-8')); links=json.loads(linksp.read_text('utf-8'))
gameres=local/'gameres'; text=gameres.read_text('utf-8')

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

ui=recipe['uiPanel']; ui_alias=ui['aliasName']; ui_file=local/ui_alias
if not ui_file.is_file():raise SystemExit('bundle UI local absent: '+str(ui_file))
dep_ids=[int(x) for x in ui.get('dependencyBundleIds') or [] if int(x) in bundles]

# Exact non-zero external refs from the relevant RawImages only.
refs=[]
for m in links.get('targetMonoBehaviours') or []:
    if m.get('script')!='RawImage' or m.get('gameObject') not in {'FormationRT','FormationBg','Bg'}:continue
    for field in ('m_Material','m_Texture'):
        v=(m.get('fields') or {}).get(field)
        if not isinstance(v,dict):continue
        fid=v.get('m_FileID');pid=v.get('m_PathID')
        if isinstance(fid,int) and isinstance(pid,int) and fid>0 and pid!=0:
            refs.append({'ownerMonoPathId':m.get('pathId'),'gameObject':m.get('gameObject'),'field':field,'fileId':fid,'pathId':pid})
# Deduplicate exact refs.
uniq=[];seen=set()
for r in refs:
    k=(r['ownerMonoPathId'],r['field'],r['fileId'],r['pathId'])
    if k not in seen:seen.add(k);uniq.append(r)
refs=uniq
if not refs:raise SystemExit('aucune référence externe Layer0 non nulle')

# Helpers robust across UnityPy versions.
def pidof(x):
    for n in ('path_id','m_PathID'):
        try:
            v=getattr(x,n,None)
            if v is not None:return int(v)
        except:pass
    return None

def tname(r):
    try:return r.type.name
    except:return str(getattr(r,'type',''))
def readobj(r):
    try:return r.read()
    except:
        try:return r.parse_as_object()
        except:return None
def oname(o):
    for n in ('m_Name','name'):
        try:
            v=getattr(o,n,None)
            if v:return str(v)
        except:pass
    return ''
def js(v,depth=0):
    if depth>5:return '<max-depth>'
    if v is None or isinstance(v,(bool,int,float,str)):return v
    if isinstance(v,bytes):return {'bytes':len(v)}
    if isinstance(v,(list,tuple)):return [js(x,depth+1) for x in v[:120]]
    if isinstance(v,dict):return {str(k):js(x,depth+1) for k,x in list(v.items())[:120]}
    p=pidof(v)
    if p not in (None,0):return {'ptrPathId':p}
    try:return {str(k):js(x,depth+1) for k,x in list(vars(v).items())[:100] if not str(k).startswith('_')}
    except:return str(v)[:500]

# UI serialized-file external tables; this is the authoritative FileID map.
ui_env=UnityPy.load(str(ui_file))
ui_external_tables=[]
owner_external={}
for r in ui_env.objects:
    rp=pidof(r)
    af=getattr(r,'assets_file',None) or getattr(r,'serialized_file',None)
    if af is None:continue
    if any(rp==x['ownerMonoPathId'] for x in refs):
        exts=getattr(af,'externals',None) or getattr(af,'m_Externals',None) or []
        rows=[]
        for i,e in enumerate(exts,1):
            path=''
            for n in ('path','m_PathName','file_path','name'):
                try:
                    v=getattr(e,n,None)
                    if v:path=str(v);break
                except:pass
            rows.append({'fileId':i,'path':path,'repr':str(e)[:500]})
        owner_external[rp]=rows
        ui_external_tables.append({'ownerMonoPathId':rp,'entries':rows})
for r in refs:
    rows=owner_external.get(r['ownerMonoPathId']) or []
    r['externalEntry']=next((x for x in rows if x['fileId']==r['fileId']),None)

# APK fragment indexes (offline fallback).
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
idx={};alias_idx={};fragment_src=None;fragment_size=None
for apk in apks:
    try:
        with zipfile.ZipFile(apk) as z:
            ns=set(z.namelist());bo='assets/AssetBundles/BundleOffsetTable.bytes';ao='assets/AssetBundles/AliasOffsetTable.bytes';fr='assets/AssetBundles/BundleFragment0.bytes'
            if bo in ns and not idx:
                rows=parse_offsets(z.read(bo));
                if rows:idx={n:o for n,o in rows[0][2]}
            if ao in ns and not alias_idx:
                rows=parse_offsets(z.read(ao));
                if rows:alias_idx={n:o for n,o in rows[0][2]}
            if fr in ns and fragment_src is None:
                fragment_src=(apk,fr);fragment_size=z.getinfo(fr).file_size
    except Exception:pass
ordered=sorted((off,n) for n,off in idx.items());sizes={}
if fragment_size is not None:
    for i,(off,n) in enumerate(ordered):sizes[off]=(ordered[i+1][0] if i+1<len(ordered) else fragment_size)-off

def adb_readable(remote):
    if not serial:return False
    try:
        cp=subprocess.run(['adb','-s',serial,'shell',f'test -r {remote!r} && echo YES || echo NO'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=10)
        return cp.returncode==0 and 'YES' in cp.stdout
    except:return False

tmp=Path(tempfile.mkdtemp(prefix='wfgg-layer0-ext-'))
cache_used=False;apk_used=False

def stage(b):
    global cache_used,apk_used
    alias=b['aliasName'];logical=b['logicalName']
    # Reuse any already-staged local dependency first.
    for p in (local/alias,local/'resolved-deps'/alias):
        if p.is_file():return p,'existing-local',False
    dest=tmp/alias;remote=f'{cache_root}/{alias}'
    if re.fullmatch(r'[0-9a-fA-F]{64}\.bundle',alias) and adb_readable(remote):
        cp=subprocess.run(['adb','-s',serial,'pull',remote,str(dest)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=120)
        if cp.returncode==0 and dest.is_file():cache_used=True;return dest,'cache',True
    off=idx.get(logical)
    if off is not None and alias_idx.get(alias)==off and fragment_src and off in sizes:
        apk,entry=fragment_src;n=sizes[off]
        try:
            with zipfile.ZipFile(apk) as z,z.open(entry) as f:
                left=off
                while left:
                    chunk=f.read(min(left,1024*1024))
                    if not chunk:break
                    left-=len(chunk)
                data=f.read(n)
            if len(data)==n:
                dest.write_bytes(data);apk_used=True;return dest,'apk-fragment',True
        except Exception:pass
    return None,'missing',False

# Strong keyword candidates first, then smaller direct deps.
RX=re.compile(r'formation|render|blur|background|world|terrain|uihero',re.I)
def score(b):
    hay=' '.join([b['logicalName']]+b.get('assetPaths',[]));return (0 if RX.search(hay) else 1,b.get('declaredBytes',10**18),b['bundleId'])
deps=sorted((bundles[i] for i in dep_ids),key=score)
expected={'m_Material':{'Material'},'m_Texture':{'Texture2D','RenderTexture','Cubemap'}}
resolved=[];scanned=[]
unresolved={(r['ownerMonoPathId'],r['field'],r['fileId'],r['pathId']) for r in refs}

for b in deps:
    if not unresolved:break
    p,source,temporary=stage(b)
    if not p:
        scanned.append({'bundleId':b['bundleId'],'source':'missing','logicalName':b['logicalName']});continue
    row={'bundleId':b['bundleId'],'source':source,'logicalName':b['logicalName'],'aliasName':b['aliasName'],'declaredBytes':b['declaredBytes'],'assetPaths':b['assetPaths'],'matches':[]}
    try:
        env=UnityPy.load(str(p));objs=list(env.objects)
        bypid=defaultdict(list)
        for o in objs:bypid[pidof(o)].append(o)
        file_names=[]
        try:file_names=[str(x) for x in env.files.keys()]
        except:pass
        row['serializedFiles']=file_names
        for r in refs:
            k=(r['ownerMonoPathId'],r['field'],r['fileId'],r['pathId'])
            if k not in unresolved:continue
            hits=bypid.get(r['pathId'],[])
            for hit in hits:
                typ=tname(hit);obj=readobj(hit);nm=oname(obj) if obj is not None else ''
                rec={'target':r,'type':typ,'name':nm,'objectPathId':r['pathId'],'bundleId':b['bundleId'],'bundleSource':source,'bundleLogicalName':b['logicalName'],'bundleAliasName':b['aliasName'],'bundleAssetPaths':b['assetPaths'],'serializedFiles':file_names}
                # Keep compact object metadata, enough to resolve materials/textures.
                if obj is not None:
                    if typ=='Material':
                        rec['material']={'name':nm,'shader':js(getattr(obj,'m_Shader',None)),'savedProperties':js(getattr(obj,'m_SavedProperties',None))}
                    elif typ in {'Texture2D','RenderTexture','Cubemap'}:
                        rec['texture']={'name':nm,'width':getattr(obj,'m_Width',None),'height':getattr(obj,'m_Height',None),'format':str(getattr(obj,'m_TextureFormat',''))}
                        if typ=='Texture2D' and r['field']=='m_Texture':
                            try:
                                im=obj.image
                                im.save(exportp)
                                rec['exportedPng']=str(exportp)
                                rec['exportedBytes']=exportp.stat().st_size
                                rec['exportedSha256']=hashlib.sha256(exportp.read_bytes()).hexdigest()
                            except Exception as e:rec['exportError']=repr(e)
                row['matches'].append(rec);resolved.append(rec)
                if typ in expected.get(r['field'],set()):unresolved.discard(k)
        scanned.append(row)
    except Exception as e:
        row['error']=repr(e);scanned.append(row)
    finally:
        if temporary:
            try:p.unlink()
            except:pass

# Persist exact matched dependency bundles locally for subsequent targeted work.
keepdir=local/'resolved-deps';keepdir.mkdir(parents=True,exist_ok=True)
for rec in resolved:
    b=bundles.get(rec['bundleId']);
    if not b:continue
    dest=keepdir/b['aliasName']
    if dest.exists():continue
    p,source,temporary=stage(b)
    if p:
        try:shutil.copy2(p,dest)
        except:pass
        if temporary:
            try:p.unlink()
            except:pass

summary={
 'format':'WFGG_LASTWAR_FORMATION_LAYER0_EXTERNAL_RESOLUTION_V1',
 'networkUsed':False,'adbUsed':cache_used,'apkFragmentUsed':apk_used,
 'uiPanel':{'bundleId':ui['bundleId'],'aliasName':ui_alias,'assetPaths':ui.get('assetPaths')},
 'targetRefs':refs,'uiExternalTables':ui_external_tables,
 'directDependencyCount':len(dep_ids),'scannedCount':len(scanned),
 'resolved':resolved,'unresolved':[{'ownerMonoPathId':a,'field':b,'fileId':c,'pathId':d} for a,b,c,d in sorted(unresolved,key=str)],
 'exactTextureExport':str(exportp) if exportp.is_file() else None,
 'guardrails':{'directUiDependenciesOnly':True,'exactPathIdsOnly':True,'generatedArtwork':False,'mainUntouched':True,'previewUntouched':True}
}
outp.write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n','utf-8')

lines=['WfGg Last War — FORMATION LAYER0 EXTERNAL RESOLUTION','EXACT PPtr RESOLUTION · DIRECT UI DEPENDENCIES ONLY','',
 f"targets={len(refs)} directDeps={len(dep_ids)} scanned={len(scanned)} resolved={len(resolved)} unresolved={len(unresolved)}",
 f"adbUsed={cache_used} apkFragmentUsed={apk_used}",'','TARGET REFERENCES']
for r in refs:lines.append('  '+json.dumps(r,ensure_ascii=False))
lines+=['','RESOLVED OBJECTS']
for x in resolved:
    lines.append(f"  {x['target']['gameObject']}.{x['target']['field']} -> bundle={x['bundleId']} type={x['type']} name={x['name']} source={x['bundleSource']}")
    for ap in x.get('bundleAssetPaths') or []:lines.append('    '+ap)
    if x.get('exportedPng'):lines.append('    EXPORTED '+x['exportedPng']+' sha256='+x.get('exportedSha256',''))
if not resolved:lines.append('  none')
lines+=['','UNRESOLVED']
for x in summary['unresolved']:lines.append('  '+json.dumps(x,ensure_ascii=False))
if not summary['unresolved']:lines.append('  none')
reportp.write_text('\n'.join(lines)+'\n','utf-8')
shutil.rmtree(tmp,ignore_errors=True)
print('FORMATION_LAYER0_EXTERNAL_RESOLUTION_OK',f'targets={len(refs)}',f'resolved={len(resolved)}',f'unresolved={len(unresolved)}',f'scanned={len(scanned)}')
for x in resolved:print('RESOLVED',x['target']['gameObject']+'.'+x['target']['field'],'bundle='+str(x['bundleId']),'type='+x['type'],'name='+x['name'],'source='+x['bundleSource'])
if exportp.is_file():print('EXACT_TEXTURE_EXPORT',exportp)
print('FORMATION_LAYER0_EXTERNAL_RESOLUTION_JSON',outp)
print('FORMATION_LAYER0_EXTERNAL_RESOLUTION_REPORT',reportp)
PYEOF

python "$PY" "$LOCAL" "$SRC_RECIPE" "$SRC_LINKS" "$OUT" "$EXPORT" "$REPORT" "$SERIAL" "$CACHE_ROOT" "$UNITY_VERSION" "${APK_PATHS[@]}"
rm -f "$PY"

git add scripts/lastwar-formation-layer0-resolve-externals.sh "$OUT"
[[ -f "$EXPORT" ]] && git add "$EXPORT"
if ! git diff --cached --quiet; then
  git commit -m "lab: resolve Formation Layer0 exact externals"
  git push origin "$BRANCH"
fi

echo "=== FORMATION LAYER0 EXTERNAL RESOLUTION TERMINEE ==="
echo "JSON: $OUT"
echo "Rapport: $REPORT"
[[ -f "$EXPORT" ]] && echo "Texture exacte: $EXPORT"
echo "main non modifiée."
