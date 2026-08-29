#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — audit des prefabs/scenes 3D qui sont des dependances
# DIRECTES du vrai UIHeroPVPFormationPanel. Aucune modification de preview.

PKG="com.fun.lastwar.gp"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
UNITY_VERSION="2019.4.41f1"
LOCAL="$ROOT/frontend/lab/local_assets/lastwar-formation-native-recipe-v1"
RECIPE="$ROOT/frontend/lab/master-assets-v2/meta/formation-native-recipe-v1.json"
OUT="$ROOT/frontend/lab/master-assets-v2/meta/formation-direct-prefab-audit-v1.json"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_FORMATION_DIRECT_PREFAB_AUDIT.txt"
TMPPY="${TMPDIR:-$HOME/.cache}/wfgg-formation-direct-prefab-audit.py"
CACHE_ROOT="/sdcard/Android/data/$PKG/files/AssetBundles"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
[[ -s "$LOCAL/gameres" ]] || fail "gameres local absent"
[[ -s "$RECIPE" ]] || fail "recipe absente"
command -v python >/dev/null 2>&1 || fail "python absent"
python - <<'PY' >/dev/null 2>&1 || fail "UnityPy absent"
import UnityPy
PY
mkdir -p "$(dirname "$OUT")" "$(dirname "$REPORT")" "$(dirname "$TMPPY")"

mapfile -t APK_PATHS < <(cmd package path "$PKG" 2>/dev/null | sed -n 's/^package://p')
[[ ${#APK_PATHS[@]} -gt 0 ]] || fail "APK Last War introuvable"
SERIAL=""
if command -v adb >/dev/null 2>&1; then
  SERIAL="$(adb devices 2>/dev/null | awk 'NR>1 && $2=="device" {print $1; exit}')"
fi

cat > "$TMPPY" <<'PYEOF'
from __future__ import annotations
from pathlib import Path
from collections import Counter
import json,sys,re,struct,subprocess,zipfile,tempfile,shutil,contextlib,io

local=Path(sys.argv[1]); recipep=Path(sys.argv[2]); outp=Path(sys.argv[3]); reportp=Path(sys.argv[4])
serial,cache_root,unity_version=sys.argv[5:8]; apks=sys.argv[8:]
import UnityPy
UnityPy.config.FALLBACK_UNITY_VERSION=unity_version
recipe=json.loads(recipep.read_text('utf-8'))
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
        bid=int(p[0]);bundles[bid]={
          'bundleId':bid,'logicalName':p[1],'declaredBytes':int(p[3]),
          'assetPathIds':[int(x) for x in p[4].split('|') if x],
          'dependencyBundleIds':[int(x) for x in p[5].split('|') if x],
          'groups':p[6].split('|') if p[6] else [],'aliasName':p[7]}
    except:pass
for b in bundles.values(): b['assetPaths']=[paths.get(x) for x in b['assetPathIds'] if paths.get(x)]

ui=recipe['uiPanel']; depids=[int(x) for x in ui.get('dependencyBundleIds') or [] if int(x) in bundles]
# On garde uniquement des bundles qui portent des prefabs/scenes/models pertinents.
RX=re.compile(r'(formation|world|terrain|grass|rock|tree|plant|map|scene|camera|hero.?show|show.?hero|environment|build)',re.I)
EXT=re.compile(r'\.(prefab|unity|fbx)$',re.I)
candidates=[]
for bid in depids:
    b=bundles[bid]; aps=b.get('assetPaths') or []
    strong=[p for p in aps if EXT.search(p) and RX.search(p)]
    weak=[p for p in aps if EXT.search(p)]
    if strong:
        q=dict(b);q['matchedAssetPaths']=strong;q['allModelAssetPaths']=weak;candidates.append(q)
# Les plus precis d'abord.
candidates.sort(key=lambda b:(0 if any(re.search(r'formation|worldcitygrass|terrain_0|scene_world',p,re.I) for p in b['matchedAssetPaths']) else 1,b['declaredBytes'],b['bundleId']))

# APK fragment tables.
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
                rr=parse_offsets(z.read(bo));
                if rr:idx={n:o for n,o in rr[0][2]}
            if ao in ns and not alias_idx:
                rr=parse_offsets(z.read(ao));
                if rr:alias_idx={n:o for n,o in rr[0][2]}
            if fr in ns and fragment_src is None:
                fragment_src=(apk,fr);fragment_size=z.getinfo(fr).file_size
    except Exception:pass
ordered=sorted((o,n) for n,o in idx.items());sizes={}
if fragment_size is not None:
    for i,(o,n) in enumerate(ordered):sizes[o]=(ordered[i+1][0] if i+1<len(ordered) else fragment_size)-o

def adb_readable(remote):
    if not serial:return False
    try:
        cp=subprocess.run(['adb','-s',serial,'shell',f'test -r {remote!r} && echo YES || echo NO'],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,timeout=8)
        return cp.returncode==0 and 'YES' in cp.stdout
    except:return False

tmp=Path(tempfile.mkdtemp(prefix='wfgg-fdirect-'))
def stage(b):
    alias=b['aliasName'];logical=b['logicalName'];dest=tmp/alias
    for p in (local/alias,local/'resolved-deps'/alias):
        if p.is_file():return p,'existing-local'
    remote=f'{cache_root}/{alias}'
    if re.fullmatch(r'[0-9a-fA-F]{64}\.bundle',alias) and adb_readable(remote):
        cp=subprocess.run(['adb','-s',serial,'pull',remote,str(dest)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=90)
        if cp.returncode==0 and dest.is_file():return dest,'cache'
    off=idx.get(logical)
    if off is not None and alias_idx.get(alias)==off and fragment_src and off in sizes:
        apk,entry=fragment_src;n=sizes[off]
        try:
            with zipfile.ZipFile(apk) as z,z.open(entry) as f:
                left=off
                while left:
                    c=f.read(min(left,1024*1024))
                    if not c:break
                    left-=len(c)
                data=f.read(n)
            if len(data)==n:
                dest.write_bytes(data);return dest,'apk-fragment'
        except Exception:pass
    return None,'missing'

def pidof(o):
    for n in ('path_id','m_PathID'):
        try:
            v=getattr(o,n,None)
            if v is not None:return int(v)
        except:pass
    return None

def objname(x):
    for n in ('m_Name','name'):
        try:
            v=getattr(x,n,None)
            if v:return str(v)
        except:pass
    return ''

results=[]
# Cap raisonnable: les 30 candidats les plus pertinents.
for b in candidates[:30]:
    p,source=stage(b)
    row={k:b.get(k) for k in ('bundleId','logicalName','aliasName','declaredBytes','assetPaths','matchedAssetPaths')};row['source']=source
    if not p:
        row['error']='bundle unavailable';results.append(row);continue
    try:
        # UnityPy emet beaucoup de warnings de fallback; ils sont captures ici.
        sink=io.StringIO()
        with contextlib.redirect_stderr(sink),contextlib.redirect_stdout(sink):
            env=UnityPy.load(str(p)); objs=list(env.objects)
        types=Counter()
        names=[]; cameras=[]; renderers=[]; transforms=[]; monos=[]
        for o in objs:
            try:typ=o.type.name
            except:typ=str(getattr(o,'type',''))
            types[typ]+=1
            if typ in {'GameObject','Camera','MeshRenderer','SkinnedMeshRenderer','MeshFilter','Transform','RectTransform','MonoBehaviour'}:
                try:
                    with contextlib.redirect_stderr(sink),contextlib.redirect_stdout(sink): x=o.read()
                except:continue
                nm=objname(x)
                if nm and nm not in names and len(names)<120:names.append(nm)
                if typ=='Camera':cameras.append({'pathId':pidof(o),'name':nm})
                elif typ in {'MeshRenderer','SkinnedMeshRenderer'}:renderers.append({'pathId':pidof(o),'name':nm,'type':typ})
                elif typ in {'Transform','RectTransform'} and len(transforms)<80:
                    pos=getattr(x,'m_LocalPosition',None);rot=getattr(x,'m_LocalRotation',None);sc=getattr(x,'m_LocalScale',None)
                    def xyz(v):
                        if v is None:return None
                        try:return [float(v.x),float(v.y),float(v.z)]
                        except:return None
                    transforms.append({'pathId':pidof(o),'name':nm,'position':xyz(pos),'scale':xyz(sc)})
                elif typ=='MonoBehaviour' and len(monos)<80:
                    monos.append({'pathId':pidof(o),'name':nm})
        row.update({'objectTypeCounts':dict(types),'names':names,'cameras':cameras,'rendererCount':len(renderers),'renderers':renderers[:80],'transforms':transforms,'monoCount':len(monos)})
        # Score post-parse : camera ou beaucoup de renderers = candidat scene/prefab visuel fort.
        row['sceneScore']=len(cameras)*100+min(len(renderers),50)*4+sum(10 for n in names if RX.search(n))
    except Exception as e:row['error']=repr(e)
    results.append(row)

results.sort(key=lambda x:(-int(x.get('sceneScore',0)),x.get('bundleId',0)))
summary={
 'format':'WFGG_LASTWAR_FORMATION_DIRECT_PREFAB_AUDIT_V1','networkUsed':False,'generatedArtwork':False,
 'uiPanelBundleId':ui['bundleId'],'directDependencyCount':len(depids),'candidateBundleCount':len(candidates),'auditedCount':len(results),
 'results':results,
 'guardrails':{'directUiDependenciesOnly':True,'previewUntouched':True,'mainUntouched':True}
}
outp.write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n','utf-8')
lines=['WfGg Last War — FORMATION DIRECT PREFAB AUDIT','DIRECT DEPENDENCIES DU VRAI UIHeroPVPFormationPanel','',f'directDeps={len(depids)} candidates={len(candidates)} audited={len(results)}','']
for r in results:
    lines.append(f"CANDIDATE score={r.get('sceneScore',0)} bundle={r.get('bundleId')} source={r.get('source')} renderers={r.get('rendererCount',0)} cameras={len(r.get('cameras') or [])}")
    for p in r.get('matchedAssetPaths') or []:lines.append('  '+p)
    if r.get('names'):lines.append('  NAMES '+', '.join(r['names'][:30]))
    if r.get('cameras'):lines.append('  CAMERAS '+json.dumps(r['cameras'],ensure_ascii=False))
    if r.get('error'):lines.append('  ERROR '+r['error'])
reportp.write_text('\n'.join(lines)+'\n','utf-8')
shutil.rmtree(tmp,ignore_errors=True)
print('FORMATION_DIRECT_PREFAB_AUDIT_OK',f'directDeps={len(depids)}',f'candidates={len(candidates)}',f'audited={len(results)}')
for r in results[:12]:
    print('DIRECT_3D_CANDIDATE',f"score={r.get('sceneScore',0)}",f"bundle={r.get('bundleId')}",f"renderers={r.get('rendererCount',0)}",f"cameras={len(r.get('cameras') or [])}", (r.get('matchedAssetPaths') or [''])[0])
print('FORMATION_DIRECT_PREFAB_AUDIT_JSON',outp)
print('FORMATION_DIRECT_PREFAB_AUDIT_REPORT',reportp)
PYEOF

python "$TMPPY" "$LOCAL" "$RECIPE" "$OUT" "$REPORT" "$SERIAL" "$CACHE_ROOT" "$UNITY_VERSION" "${APK_PATHS[@]}"
rm -f "$TMPPY"

git add scripts/lastwar-formation-direct-prefab-audit.sh "$OUT"
if ! git diff --cached --quiet; then
  git commit -m "lab: audit Formation direct 3D prefab dependencies"
  git push origin "$BRANCH"
fi

echo "=== FORMATION DIRECT PREFAB AUDIT TERMINE ==="
echo "JSON: $OUT"
echo "Rapport: $REPORT"
echo "main non modifiée."
