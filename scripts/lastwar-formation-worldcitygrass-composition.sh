#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — WORLD CITY GRASS COMPOSITION
# Purpose: recover the exact composition recipe behind the blurred Formation
# world layer instead of guessing rock/tree/grass placement from screenshots.
#
# LOCAL/OFFLINE ONLY:
#   - reads the already downloaded Last War AssetBundles cache through local ADB
#   - resolves WorldCityGrass.prefab by exact gameres path
#   - pulls that exact alias bundle only
#   - exports its Unity hierarchy + Transform values + renderer links
#   - dumps readable MonoBehaviour typetrees when available
#
# No Last War network. No generated artwork. No fuzzy asset matching.

PKG="com.fun.lastwar.gp"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
UNITY_VERSION="2019.4.41f1"
CACHE_ROOT="/sdcard/Android/data/$PKG/files/AssetBundles"
TARGET_PATH="Assets/Main/Prefabs/World/WorldCityGrass.prefab"
LOCAL="$ROOT/frontend/lab/local_assets/lastwar-worldcitygrass-v1"
MANIFEST="$ROOT/frontend/lab/master-assets-v2/meta/formation-worldcitygrass-composition-v1.json"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_WORLDCITYGRASS_COMPOSITION.txt"
PY="${TMPDIR:-$HOME/.cache}/wfgg-worldcitygrass-composition.py"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
command -v adb >/dev/null 2>&1 || fail "adb absent"
command -v python >/dev/null 2>&1 || fail "python absent"
python - <<'PY' >/dev/null 2>&1 || fail "UnityPy absent — relancer une phase Last War précédente ayant installé UnityPy"
import UnityPy
PY

SERIAL="$(adb devices 2>/dev/null | awk 'NR>1 && $2=="device" {print $1; exit}')"
[[ -n "$SERIAL" ]] || fail "aucun appareil ADB connecté — reconnecter le débogage sans fil local puis relancer"

mkdir -p "$LOCAL" "$(dirname "$MANIFEST")" "$(dirname "$REPORT")" "$(dirname "$PY")"
rm -f "$LOCAL"/*

GAMERES="$LOCAL/gameres"
adb -s "$SERIAL" pull "$CACHE_ROOT/gameres" "$GAMERES" >/dev/null || fail "impossible de lire le gameres du cache Last War"
[[ -s "$GAMERES" ]] || fail "gameres cache vide"

cat > "$PY" <<'PYEOF'
from __future__ import annotations
from pathlib import Path
from collections import Counter, defaultdict
import json, math, os, re, subprocess, sys, traceback

root=Path(sys.argv[1]); gameres=Path(sys.argv[2]); manifestp=Path(sys.argv[3]); reportp=Path(sys.argv[4])
serial=sys.argv[5]; cache_root=sys.argv[6]; target_path=sys.argv[7]; unity_version=sys.argv[8]

import UnityPy
UnityPy.config.FALLBACK_UNITY_VERSION=unity_version

# ---------- exact gameres resolution ----------
text=gameres.read_text(encoding='utf-8')
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
        bid=int(p[0]);bundles[bid]={
          'bundleId':bid,'logicalName':p[1],'crc':p[2],'declaredBytes':int(p[3]),
          'assetPathIds':[int(x) for x in p[4].split('|') if x],
          'dependencyBundleIds':[int(x) for x in p[5].split('|') if x],
          'groups':p[6].split('|') if p[6] else [],'aliasName':p[7]
        }
    except:pass

pid=next((i for i,p in paths.items() if p.lower()==target_path.lower()),None)
if pid is None:raise SystemExit('WorldCityGrass exact path absent from current cache gameres')
row=next((b for b in bundles.values() if pid in b['assetPathIds']),None)
if row is None:raise SystemExit('WorldCityGrass exact bundle record absent')

# Recursive dependency closure is recorded for audit; only cached standalone files
# are pulled. The prefab itself is the composition source. Missing shader/material
# dependencies do not prevent Transform hierarchy extraction.
closure=set();stack=[row['bundleId']]
while stack:
    bid=stack.pop()
    if bid in closure:continue
    closure.add(bid)
    b=bundles.get(bid)
    if b:stack.extend(b['dependencyBundleIds'])
closure_rows=[bundles[x] for x in sorted(closure) if x in bundles]

# ---------- local ADB pull ----------
def adb_exists(remote):
    cp=subprocess.run(['adb','-s',serial,'shell',f'test -r {remote!r} && echo YES || echo NO'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=15)
    return cp.returncode==0 and 'YES' in cp.stdout

def pull_alias(b,required=False):
    alias=b.get('aliasName') or ''
    if not re.fullmatch(r'[0-9a-fA-F]{64}\.bundle',alias):
        return {'bundleId':b['bundleId'],'aliasName':alias,'cached':False,'reason':'alias-format'}
    remote=f'{cache_root}/{alias}'
    if not adb_exists(remote):
        if required:raise SystemExit('WorldCityGrass alias absent from local cache: '+remote)
        return {'bundleId':b['bundleId'],'logicalName':b['logicalName'],'aliasName':alias,'cached':False,'remote':remote}
    local=root/alias
    cp=subprocess.run(['adb','-s',serial,'pull',remote,str(local)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=90)
    if cp.returncode!=0 or not local.is_file():
        if required:raise SystemExit('WorldCityGrass pull failed: '+cp.stderr[-500:])
        return {'bundleId':b['bundleId'],'logicalName':b['logicalName'],'aliasName':alias,'cached':True,'pulled':False,'remote':remote}
    return {'bundleId':b['bundleId'],'logicalName':b['logicalName'],'aliasName':alias,'cached':True,'pulled':True,'remote':remote,'localFile':local.name,'bytes':local.stat().st_size}

pulls=[]
pulls.append(pull_alias(row,required=True))
for b in closure_rows:
    if b['bundleId']==row['bundleId']:continue
    pulls.append(pull_alias(b,required=False))

files=[root/x['localFile'] for x in pulls if x.get('pulled')]
if not files:raise SystemExit('aucun bundle WorldCityGrass local')

# ---------- Unity object helpers ----------
def tname(r):
    try:return r.type.name
    except:return str(getattr(r,'type',''))
def robj(r):
    try:return r.read()
    except Exception:
        try:return r.parse_as_object()
        except:return None
def attr(o,*names,default=None):
    for n in names:
        try:
            v=getattr(o,n)
            if v is not None:return v
        except Exception:pass
    return default
def oname(o,fb=''):
    if o is None:return str(fb or '')
    return str(getattr(o,'m_Name','') or getattr(o,'name','') or fb or '')
def afname(r):
    af=attr(r,'assets_file','assetsfile')
    return str(attr(af,'name','path',default='') or '')
def pidof(x):
    if x is None:return None
    for obj in (x,attr(x,'object_reader','reader')):
        if obj is None:continue
        for n in ('path_id','m_PathID'):
            try:
                v=getattr(obj,n,None)
                if v is not None:return int(v)
            except:pass
    return None
def ptr_reader(p):
    if p is None:return None
    for fn in ('get_obj','get_object'):
        try:
            f=getattr(p,fn,None)
            if callable(f):
                q=f()
                if q is not None:return q
        except:pass
    try:
        q=p.read();rr=attr(q,'object_reader','reader')
        if rr is not None:return rr
    except:pass
    return None
def pobj(p):
    if p is None:return None
    for fn in ('read','deref_parse_as_object','parse_as_object'):
        try:
            f=getattr(p,fn,None)
            if callable(f):return f()
        except:pass
    rr=ptr_reader(p);return robj(rr) if rr is not None else None
def pname(p):return oname(pobj(p))
def key(r):return {'assetsFile':afname(r),'pathId':pidof(r)}
def vec(v,names):
    if v is None:return None
    try:return [float(getattr(v,n)) for n in names]
    except:return None

def jsonsafe(v,depth=0):
    if depth>8:return '<max-depth>'
    if v is None or isinstance(v,(bool,int,float,str)):return v
    if isinstance(v,bytes):return {'bytes':len(v)}
    if isinstance(v,(list,tuple)):return [jsonsafe(x,depth+1) for x in v[:500]]
    if isinstance(v,dict):return {str(k):jsonsafe(x,depth+1) for k,x in list(v.items())[:500]}
    # PPtr-like
    rp=pidof(v)
    if rp not in (None,0):
        return {'ptrPathId':rp,'ptrName':pname(v)}
    # vectors/colors/quaternions
    for names in (('x','y','z','w'),('x','y','z'),('r','g','b','a'),('x','y')):
        vv=vec(v,names)
        if vv is not None:return vv
    # object __dict__ fallback, bounded
    try:
        d=vars(v)
        if d:return {str(k):jsonsafe(x,depth+1) for k,x in list(d.items())[:200] if not str(k).startswith('_')}
    except:pass
    return str(v)[:1000]

def typetree(reader):
    # UnityPy versions differ. Try object-reader typetree first, then parsed object.
    errs=[]
    for owner in (reader,):
        for fn in ('read_typetree','read_typetree_strict'):
            try:
                f=getattr(owner,fn,None)
                if callable(f):return jsonsafe(f()),None
            except Exception as e:errs.append(repr(e))
    d=robj(reader)
    if d is not None:
        try:return jsonsafe(d),None
        except Exception as e:errs.append(repr(e))
    return None,'; '.join(errs[-4:])

# ---------- load and map hierarchy ----------
env=UnityPy.load(*[str(p) for p in files])
readers=list(env.objects);counts=Counter(tname(r) for r in readers)

gos={};transforms={};go_to_tr={};components=defaultdict(list);monos=[]
for r in readers:
    typ=tname(r);d=robj(r)
    if d is None:continue
    rp=pidof(r)
    if typ=='GameObject':
        gos[rp]={'pathId':rp,'name':oname(d),'file':afname(r)}
    elif typ in ('Transform','RectTransform'):
        gp=attr(d,'m_GameObject');gpid=pidof(gp);father=attr(d,'m_Father');kids=attr(d,'m_Children',default=[]) or []
        transforms[rp]={
          'pathId':rp,'gameObjectPathId':gpid,'gameObject':pname(gp),'parentTransformPathId':pidof(father),
          'childTransformPathIds':[x for x in (pidof(k) for k in kids) if x is not None],
          'localPosition':vec(attr(d,'m_LocalPosition'),('x','y','z')),
          'localRotation':vec(attr(d,'m_LocalRotation'),('x','y','z','w')),
          'localScale':vec(attr(d,'m_LocalScale'),('x','y','z')),'file':afname(r)
        }
        if gpid is not None:go_to_tr[gpid]=rp
    elif typ in ('MeshFilter','MeshRenderer','SkinnedMeshRenderer','SpriteRenderer','Terrain','Light','Camera'):
        gp=attr(d,'m_GameObject');gpid=pidof(gp)
        rec={'type':typ,'pathId':rp,'gameObjectPathId':gpid,'gameObject':pname(gp),'file':afname(r)}
        if typ=='MeshFilter':
            mp=attr(d,'m_Mesh');rec.update({'meshPathId':pidof(mp),'mesh':pname(mp)})
        if typ in ('MeshRenderer','SkinnedMeshRenderer','SpriteRenderer'):
            rec['materials']=[{'pathId':pidof(x),'name':pname(x)} for x in (attr(d,'m_Materials',default=[]) or [])]
            rec['enabled']=bool(attr(d,'m_Enabled',default=1))
        if typ=='SkinnedMeshRenderer':
            mp=attr(d,'m_Mesh');rec.update({'meshPathId':pidof(mp),'mesh':pname(mp)})
        components[gpid].append(rec)
    elif typ=='MonoBehaviour':
        gp=attr(d,'m_GameObject');gpid=pidof(gp);sp=attr(d,'m_Script');tree,err=typetree(r)
        monos.append({
          'pathId':rp,'gameObjectPathId':gpid,'gameObject':pname(gp),
          'scriptPathId':pidof(sp),'script':pname(sp),'file':afname(r),
          'typetree':tree,'typetreeError':err
        })

for tr in transforms.values():
    if not tr['gameObject'] and tr['gameObjectPathId'] in gos:tr['gameObject']=gos[tr['gameObjectPathId']]['name']

roots=[t for t in transforms.values() if t['parentTransformPathId'] in (None,0)]
roots.sort(key=lambda x:(x['gameObject']!='WorldCityGrass',x['gameObject']))
selected=next((x for x in roots if x['gameObject']=='WorldCityGrass'),roots[0] if roots else None)
if selected is None:raise SystemExit('aucune Transform racine dans WorldCityGrass bundle')

# exact root descendant walk
hier=[];seen=set()
def walk(tid,depth=0):
    if tid in seen or tid not in transforms or depth>100:return
    seen.add(tid);t=transforms[tid];gpid=t['gameObjectPathId']
    hier.append({
      'depth':depth,'pathId':tid,'gameObjectPathId':gpid,'name':t['gameObject'],
      'localPosition':t['localPosition'],'localRotation':t['localRotation'],'localScale':t['localScale'],
      'components':components.get(gpid,[]),
      'monoBehaviours':[m for m in monos if m['gameObjectPathId']==gpid]
    })
    for c in t['childTransformPathIds']:walk(c,depth+1)
walk(selected['pathId'])

# Useful placement-like fields from MonoBehaviour typetrees. We do NOT infer values;
# this is just an exact-key filter to make arrays of positions/props easy to inspect.
PLACEMENT_RE=re.compile(r'position|rotation|scale|offset|coord|tile|grass|rock|tree|prop|prefab|model|asset|shadow',re.I)
def placement_hits(v,path=''):
    out=[]
    if isinstance(v,dict):
        for k,x in v.items():
            p=f'{path}.{k}' if path else str(k)
            if PLACEMENT_RE.search(str(k)):
                out.append({'path':p,'value':x})
            if isinstance(x,(dict,list)):out.extend(placement_hits(x,p))
    elif isinstance(v,list):
        for i,x in enumerate(v[:500]):
            if isinstance(x,(dict,list)):out.extend(placement_hits(x,f'{path}[{i}]'))
    return out[:2000]

mono_hits=[]
for m in monos:
    hs=placement_hits(m.get('typetree')) if m.get('typetree') is not None else []
    if hs:mono_hits.append({'gameObject':m['gameObject'],'script':m['script'],'pathId':m['pathId'],'hits':hs})

summary={
 'format':'WFGG_LASTWAR_WORLDCITYGRASS_COMPOSITION_V1','networkUsed':False,'generatedArtwork':False,
 'source':{'adbSerial':serial,'cacheRoot':cache_root,'gameresBytes':gameres.stat().st_size},
 'target':{'pathId':pid,'assetPath':target_path,'bundle':row},
 'dependencyClosure':[{'bundleId':b['bundleId'],'logicalName':b['logicalName'],'aliasName':b['aliasName'],'groups':b['groups']} for b in closure_rows],
 'pulls':pulls,'objectTypeCounts':dict(counts),'rootCandidates':roots,'selectedRoot':selected,
 'hierarchyNodeCount':len(hier),'hierarchy':hier,'monoBehaviourCount':len(monos),'monoBehaviours':monos,'placementFieldHits':mono_hits,
 'guardrails':{'exactGameresPath':True,'exactAliasOnly':True,'localCacheOnly':True,'noNameSimilarity':True,'noGeneratedArtwork':True,'noLastWarNetwork':True}
}
manifestp.write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')

lines=[
 'WfGg Last War — WORLDCITYGRASS COMPOSITION',
 'EXACT GAMERES PATH · LOCAL CACHE ONLY · NO GENERATED ARTWORK',
 f"targetPathId={pid}",f"logicalName={row['logicalName']}",f"aliasName={row['aliasName']}",
 f"bundleBytes={next((x.get('bytes') for x in pulls if x.get('bundleId')==row['bundleId']),None)}",
 f"objects={sum(counts.values())} transforms={len(transforms)} rootCandidates={len(roots)} hierarchyNodes={len(hier)} monoBehaviours={len(monos)} placementGroups={len(mono_hits)}",'',
 'ROOT CANDIDATES'
]
for r in roots:lines.append(f"  {r['gameObject']} pathId={r['pathId']} pos={r['localPosition']} scale={r['localScale']}")
lines += ['', 'SELECTED HIERARCHY']
for n in hier:
    pad='  '*n['depth']; comps=','.join(x['type'] for x in n['components']) or '-'; scripts=','.join(x['script'] or '?' for x in n['monoBehaviours']) or '-'
    lines.append(f"{pad}{n['name']} pos={n['localPosition']} rot={n['localRotation']} scale={n['localScale']} comps={comps} scripts={scripts}")
lines += ['', 'PLACEMENT-LIKE MONOBEHAVIOUR FIELDS']
for g in mono_hits:
    lines.append(f"  GO={g['gameObject']} script={g['script']} pathId={g['pathId']}")
    for h in g['hits'][:120]:lines.append(f"    {h['path']} = {json.dumps(h['value'],ensure_ascii=False)[:700]}")
if not mono_hits:lines.append('  none')
lines += ['', 'DEPENDENCY CACHE STATUS']
for p in pulls:lines.append(f"  bundleId={p['bundleId']} cached={p.get('cached')} pulled={p.get('pulled',False)} alias={p.get('aliasName')}")
lines += ['', 'GUARDRAILS','  exact_gameres_path=true','  exact_alias_only=true','  local_cache_only=true','  name_similarity=false','  generated_artwork=false','  lastwar_network=false']
reportp.write_text('\n'.join(lines)+'\n',encoding='utf-8')

print('WORLDCITYGRASS_COMPOSITION_OK',f'root={selected["gameObject"]}',f'hierarchy={len(hier)}',f'mono={len(monos)}',f'placementGroups={len(mono_hits)}',flush=True)
print('WORLDCITYGRASS_ALIAS',row['aliasName'],flush=True)
print('WORLDCITYGRASS_REPORT',reportp,flush=True)
PYEOF

python "$PY" "$LOCAL" "$GAMERES" "$MANIFEST" "$REPORT" "$SERIAL" "$CACHE_ROOT" "$TARGET_PATH" "$UNITY_VERSION"
rm -f "$PY"

# Never commit the pulled game bundle. Only exact structural metadata + script.
git add scripts/lastwar-formation-worldcitygrass-composition.sh "$MANIFEST"
if ! git diff --cached --quiet; then
  git commit -m "lab: record exact WorldCityGrass composition"
  git push origin "$BRANCH"
fi

echo "=== WORLDCITYGRASS COMPOSITION TERMINEE ==="
echo "Manifest: $MANIFEST"
echo "Rapport: $REPORT"
echo "Bundle local uniquement: $LOCAL"
echo "main non modifiée."
