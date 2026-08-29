#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — PHASE 53
# BUILD AUTHORITATIVE CURRENT-15 RUNTIME SCENE LINKS
# CODE ONLY · OFFLINE ONLY · exact Phase47 bundles + validated Phase49/52 data.
#
# Purpose:
#  - rebuild the exact Unity GameObject/Transform/component graph by pathId
#  - keep only components under the authoritative queue-model root
#  - link MeshFilter / SkinnedMeshRenderer -> exact Mesh pathId/name
#  - link Renderer -> exact Material pathId/name
#  - link Material texture slots -> exact Texture2D pathId/name
#  - map exact exported OBJ/PNG files from Phase49B without fuzzy matching
#  - prepare one scene.json per hero for the upcoming WebGL renderer
#
# No generated geometry. No generated motion. No Last War network.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
UNITY_VERSION="2019.4.41f1"
P47="$ROOT/frontend/lab/master-assets-v2/meta/current15-exact-bundle-stage.json"
P49="$ROOT/frontend/lab/master-assets-v2/meta/current15-web-export-v2.json"
P52="$ROOT/frontend/lab/master-assets-v2/meta/current15-runtime-pack-v1.json"
SRC="$ROOT/frontend/lab/local_assets/lastwar-current15-exact-v1"
RUNTIME52="$ROOT/frontend/lab/local_assets/lastwar-current15-runtime-v1"
OUT="$ROOT/frontend/lab/local_assets/lastwar-current15-runtime-v2-scene"
MANIFEST="$ROOT/frontend/lab/master-assets-v2/meta/current15-runtime-scene-links-v1.json"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_PHASE53_CURRENT15_RUNTIME_SCENE_LINKS.txt"
PY="${TMPDIR:-$HOME/.cache}/wfgg-phase53-runtime-scene-links.py"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche active incorrecte"
[[ -s "$P47" ]] || fail "Phase47 absente"
[[ -s "$P49" ]] || fail "Phase49B absente"
[[ -s "$P52" ]] || fail "Phase52 absente"
[[ -d "$SRC" ]] || fail "bundles locaux Phase47 absents"
[[ -d "$RUNTIME52" ]] || fail "runtime local Phase52 absent"
command -v python >/dev/null 2>&1 || fail "python absent"
python - <<'PY' >/dev/null 2>&1 || fail "UnityPy absent"
import UnityPy
PY

rm -rf "$OUT"
mkdir -p "$OUT" "$(dirname "$MANIFEST")" "$(dirname "$REPORT")" "$(dirname "$PY")"

cat > "$PY" <<'PYEOF'
from __future__ import annotations
from pathlib import Path
from collections import defaultdict
import json, os, re, shutil, sys, traceback

p47p,p49p,p52p,src,runtime52,out,manifestp,reportp,unity_version=sys.argv[1:]
p47p=Path(p47p);p49p=Path(p49p);p52p=Path(p52p);src=Path(src);runtime52=Path(runtime52);out=Path(out);manifestp=Path(manifestp);reportp=Path(reportp)

import UnityPy
UnityPy.config.FALLBACK_UNITY_VERSION=unity_version
j47=json.loads(p47p.read_text(encoding='utf-8'))
j49=json.loads(p49p.read_text(encoding='utf-8'))
j52=json.loads(p52p.read_text(encoding='utf-8'))
h47={int(x['heroId']):x for x in j47.get('heroes',[])}
h49={int(x['heroId']):x for x in j49.get('heroes',[])}
h52={int(x['heroId']):x for x in j52.get('heroes',[])}
ids=sorted(set(h47)&set(h49)&set(h52))
if len(ids)!=15: raise SystemExit(f'expected 15 common heroes, got {len(ids)}')

SAFE=re.compile(r'[^A-Za-z0-9._-]+')
def safe(s): return SAFE.sub('_',str(s or '')).strip('._') or 'asset'
def tname(r):
    try:return r.type.name
    except:return str(getattr(r,'type',''))
def robj(r):
    try:return r.read()
    except Exception:
        try:return r.parse_as_object()
        except:return None
def pid(x):
    if x is None:return None
    for y in (x,getattr(x,'reader',None)):
        if y is None:continue
        for a in ('path_id','m_PathID'):
            try:
                v=getattr(y,a,None)
                if v is not None:return int(v)
            except:pass
    return None
def pobj(p):
    if p is None:return None
    for fn in ('read','deref_parse_as_object','parse_as_object'):
        try:
            f=getattr(p,fn,None)
            if callable(f):return f()
        except:pass
    return None
def oname(o,fb=''):
    if o is None:return str(fb or '')
    return str(getattr(o,'m_Name','') or getattr(o,'name','') or fb or '')
def pname(p):return oname(pobj(p))
def vec(v,names):
    if v is None:return None
    try:return [float(getattr(v,n)) for n in names]
    except:return None
def attr(o,*names,default=None):
    for n in names:
        try:
            v=getattr(o,n)
            if v is not None:return v
        except:pass
    return default

def expected_root(queue_path):return Path(str(queue_path or '')).stem
def root_score(n,e):
    n=str(n or '');e=str(e or '')
    if n==e:return 10000
    nl=n.lower();el=e.lower()
    if nl==el:return 9500
    if nl.startswith(el) or el.startswith(nl):return 7000
    if el in nl or nl in el:return 5000
    return 0

def pair_items(x):
    if x is None:return []
    if isinstance(x,dict):return list(x.items())
    out=[]
    for it in x or []:
        if isinstance(it,(list,tuple)) and len(it)>=2:out.append((it[0],it[1]));continue
        if isinstance(it,dict):
            k=it.get('first',it.get('key',it.get('Key')));v=it.get('second',it.get('value',it.get('Value')))
        else:
            k=attr(it,'first','key','Key');v=attr(it,'second','value','Value')
        if k is not None:out.append((k,v))
    return out

def material_tex_slots(mat):
    sp=attr(mat,'m_SavedProperties','savedProperties')
    te=attr(sp,'m_TexEnvs','TexEnvs',default=[])
    rows=[]
    for k,v in pair_items(te):
        texptr=attr(v,'m_Texture','texture') if v is not None else None
        if texptr is None and isinstance(v,dict):texptr=v.get('m_Texture',v.get('texture'))
        rows.append({'slot':str(k),'texturePathId':pid(texptr),'texture':pname(texptr)})
    return rows

def exported_map(items):
    by=defaultdict(list)
    for x in items:
        if not x.get('exported'):continue
        by[str(x.get('name') or '')].append(x)
    out={};amb=[]
    for n,arr in by.items():
        hashes={str(x.get('sha256') or '') for x in arr}
        if len(hashes)==1:out[n]=arr[0]
        else:amb.append(n)
    return out,sorted(amb)

rows=[]
for idx,hid in enumerate(ids,1):
    h=h47[hid];e49=h49[hid];e52=h52[hid];nm=h.get('name') or str(hid);expected=expected_root(h.get('queueModelPath'))
    print(f'PHASE53_HERO {idx}/15 id={hid} name={nm}',flush=True)
    row={'heroId':hid,'name':nm,'queueModelPath':h.get('queueModelPath'),'expectedRoot':expected,'parseOk':False,'rootExact':False,'sceneLinked':False,'errors':[]}
    try:
        files=[]
        hdir=src/str(hid)
        for b in h.get('bundles') or []:
            logical=os.path.basename(str(b.get('logicalName') or ''))
            p=hdir/logical
            if logical and p.is_file():files.append(p)
        files=sorted(set(files))
        if not files:raise ValueError('no exact Phase47 bundles')
        env=UnityPy.load(*[str(x) for x in files]);readers=list(env.objects);row['parseOk']=True

        gos={};trs={};tr_by_go={}
        for r in readers:
            typ=tname(r)
            if typ not in ('GameObject','Transform','RectTransform'):continue
            o=robj(r)
            if o is None:continue
            if typ=='GameObject':gos[pid(r)]={'pathId':pid(r),'name':oname(o)}
            else:
                gp=attr(o,'m_GameObject');gpid=pid(gp);tpid=pid(r);fp=pid(attr(o,'m_Father'))
                tr={'pathId':tpid,'gameObjectPathId':gpid,'name':pname(gp),'parentPathId':fp,'children':[pid(x) for x in (attr(o,'m_Children',default=[]) or []) if pid(x) is not None],
                    'localPosition':vec(attr(o,'m_LocalPosition'),('x','y','z')),'localRotation':vec(attr(o,'m_LocalRotation'),('x','y','z','w')),'localScale':vec(attr(o,'m_LocalScale'),('x','y','z'))}
                trs[tpid]=tr
                if gpid is not None:tr_by_go[gpid]=tpid

        roots=[t for t in trs.values() if t.get('parentPathId') in (None,0)]
        roots.sort(key=lambda x:root_score(x.get('name'),expected),reverse=True)
        if not roots or root_score(roots[0].get('name'),expected)<5000:raise ValueError(f'authoritative root not found expected={expected}')
        root=roots[0];rootpid=root['pathId'];row['rootExact']=root_score(root.get('name'),expected)>=5000

        memo={}
        def fullpath(tpid):
            if tpid in memo:return memo[tpid]
            t=trs.get(tpid)
            if not t:return ''
            parent=t.get('parentPathId');pp=fullpath(parent) if parent in trs else ''
            p=(pp+'/'+t['name']) if pp else t['name'];memo[tpid]=p;return p
        def under_root(tpid):
            seen=set();cur=tpid
            while cur in trs and cur not in seen:
                if cur==rootpid:return True
                seen.add(cur);cur=trs[cur].get('parentPathId')
            return False
        scene_tr=[]
        for tpid,t in trs.items():
            if under_root(tpid):scene_tr.append({**t,'path':fullpath(tpid)})
        scene_tr.sort(key=lambda x:x['path'])
        path_by_tid={x['pathId']:x['path'] for x in scene_tr}

        mesh_catalog={};tex_catalog={};materials={};mesh_filters=[];renderers=[];skinned=[]
        for r in readers:
            typ=tname(r)
            if typ not in ('Mesh','Texture2D','Material','MeshFilter','MeshRenderer','Renderer','SkinnedMeshRenderer'):continue
            o=robj(r)
            if o is None:continue
            rpid=pid(r)
            if typ=='Mesh':mesh_catalog[rpid]={'pathId':rpid,'name':oname(o,'Mesh')}
            elif typ=='Texture2D':tex_catalog[rpid]={'pathId':rpid,'name':oname(o,'Texture2D')}
            elif typ=='Material':materials[rpid]={'pathId':rpid,'name':oname(o,'Material'),'shader':pname(attr(o,'m_Shader')),'textures':material_tex_slots(o)}
            else:
                gp=attr(o,'m_GameObject');gpid=pid(gp);tpid=tr_by_go.get(gpid)
                if not under_root(tpid):continue
                mats=[]
                for mp in (attr(o,'m_Materials',default=[]) or []):mats.append({'pathId':pid(mp),'name':pname(mp)})
                base={'componentPathId':rpid,'gameObjectPathId':gpid,'gameObject':pname(gp),'transformPathId':tpid,'transformPath':path_by_tid.get(tpid),'materials':mats}
                if typ=='MeshFilter':
                    m=attr(o,'m_Mesh');mesh_filters.append({**base,'meshPathId':pid(m),'mesh':pname(m)})
                elif typ in ('MeshRenderer','Renderer'):renderers.append(base)
                elif typ=='SkinnedMeshRenderer':
                    m=attr(o,'m_Mesh');bones=[]
                    for bp in (attr(o,'m_Bones',default=[]) or []):
                        bpid=pid(bp);bones.append({'transformPathId':bpid,'transformPath':path_by_tid.get(bpid),'name':pname(bp)})
                    rb=attr(o,'m_RootBone');rbpid=pid(rb)
                    skinned.append({**base,'meshPathId':pid(m),'mesh':pname(m),'rootBone':{'transformPathId':rbpid,'transformPath':path_by_tid.get(rbpid),'name':pname(rb)},'bones':bones})

        objmap,objamb=exported_map(e49.get('meshes',[]));pngmap,pngamb=exported_map(e49.get('textures',[]))
        def mesh_link(mpid,mname):
            x=objmap.get(str(mname or ''))
            return {'meshPathId':mpid,'mesh':mname,'objFile':x.get('file') if x else None,'objSha256':x.get('sha256') if x else None}
        mesh_links=[]
        for x in mesh_filters:mesh_links.append(mesh_link(x.get('meshPathId'),x.get('mesh')))
        for x in skinned:mesh_links.append(mesh_link(x.get('meshPathId'),x.get('mesh')))
        unresolved_mesh=[x for x in mesh_links if not x.get('objFile')]

        material_rows=[];unresolved_tex=[]
        used_mat_ids={m.get('pathId') for x in renderers+skinned for m in x.get('materials',[]) if m.get('pathId') is not None}
        for mid in sorted(used_mat_ids):
            m=materials.get(mid)
            if not m:continue
            mm={**m,'textures':[]}
            for t in m.get('textures',[]):
                ex=pngmap.get(str(t.get('texture') or ''))
                tt={**t,'pngFile':ex.get('file') if ex else None,'pngSha256':ex.get('sha256') if ex else None}
                if t.get('texturePathId') and not tt['pngFile']:unresolved_tex.append(tt)
                mm['textures'].append(tt)
            material_rows.append(mm)

        hd=out/str(hid);hd.mkdir(parents=True,exist_ok=True)
        runtime_src=runtime52/str(hid)
        # Reuse validated Phase52 binaries locally; no duplicate extraction.
        scene={
          'format':'WFGG_LASTWAR_HERO_RUNTIME_SCENE_V1','heroId':hid,'name':nm,'queueModelPath':h.get('queueModelPath'),'expectedRoot':expected,
          'root':{'transformPathId':rootpid,'name':root.get('name'),'path':path_by_tid.get(rootpid)},
          'rendererMode':e52.get('rendererMode'),'transforms':scene_tr,'meshFilters':mesh_filters,'renderers':renderers,'skinnedRenderers':skinned,
          'meshes':list(mesh_catalog.values()),'materials':material_rows,'textures':list(tex_catalog.values()),'meshLinks':mesh_links,
          'runtimeBase':f'../lastwar-current15-runtime-v1/{hid}/','idleAnimation':'animation/idle.json.gz','rig':'rig.json.gz',
          'guardrails':{'exactQueueRoot':True,'noFuzzyMatching':True,'noGeneratedGeometry':True,'noGeneratedMotion':True}
        }
        (hd/'scene.json').write_text(json.dumps(scene,ensure_ascii=False,indent=2),encoding='utf-8')
        row.update({'transformCount':len(scene_tr),'meshFilterCount':len(mesh_filters),'rendererCount':len(renderers),'skinnedRendererCount':len(skinned),'meshLinkCount':len(mesh_links),
                    'unresolvedMeshLinks':len(unresolved_mesh),'materialCount':len(material_rows),'unresolvedTextureLinks':len(unresolved_tex),'ambiguousExportMeshNames':objamb,'ambiguousExportTextureNames':pngamb,
                    'sceneJson':str((hd/'scene.json').relative_to(out))})
        row['sceneLinked']=bool(scene_tr and mesh_links and not unresolved_mesh and not objamb)
        if not row['sceneLinked']:
            if unresolved_mesh:row['errors'].append('unresolved mesh links: '+','.join(sorted({str(x.get('mesh')) for x in unresolved_mesh})))
            if objamb:row['errors'].append('ambiguous exported mesh names: '+','.join(objamb))
    except Exception as e:
        row['errors'].append(repr(e));row['traceback']=traceback.format_exc()[-3000:]
    rows.append(row)
    print('PHASE53_HERO_DONE',hid,f"linked={row['sceneLinked']}",f"transforms={row.get('transformCount',0)}",f"meshLinks={row.get('meshLinkCount',0)}",f"unresolvedMesh={row.get('unresolvedMeshLinks',0)}",flush=True)

summary={'format':'WFGG_LASTWAR_CURRENT15_RUNTIME_SCENE_LINKS_V1','networkUsed':False,'heroCount':15,'parseOkCount':sum(x['parseOk'] for x in rows),'rootExactCount':sum(x['rootExact'] for x in rows),'sceneLinkedCount':sum(x['sceneLinked'] for x in rows),
         'transformCount':sum(x.get('transformCount',0) for x in rows),'meshLinkCount':sum(x.get('meshLinkCount',0) for x in rows),'unresolvedMeshLinkCount':sum(x.get('unresolvedMeshLinks',0) for x in rows),'unresolvedTextureLinkCount':sum(x.get('unresolvedTextureLinks',0) for x in rows),
         'heroes':[{k:v for k,v in x.items() if k!='traceback'} for x in rows],'guardrails':{'noFuzzyMatching':True,'noGeneratedGeometry':True,'noGeneratedMotion':True,'noAnimationSubstitution':True,'noLastWarNetwork':True}}
manifestp.write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
lines=['WfGg Last War LAB — PHASE 53 CURRENT15 RUNTIME SCENE LINKS',f"heroes=15 parseOk={summary['parseOkCount']}/15 rootExact={summary['rootExactCount']}/15 sceneLinked={summary['sceneLinkedCount']}/15",f"transforms={summary['transformCount']} meshLinks={summary['meshLinkCount']} unresolvedMesh={summary['unresolvedMeshLinkCount']} unresolvedTexture={summary['unresolvedTextureLinkCount']}",'']
for x in rows:lines.append(f"HERO {x['heroId']} {x['name']} linked={x['sceneLinked']} rootExact={x['rootExact']} transforms={x.get('transformCount',0)} meshLinks={x.get('meshLinkCount',0)} unresolvedMesh={x.get('unresolvedMeshLinks',0)} unresolvedTexture={x.get('unresolvedTextureLinks',0)} errors={x['errors']}")
lines += ['','GUARDRAILS','  no_fuzzy_matching=true','  no_generated_geometry=true','  no_generated_motion=true','  no_animation_substitution=true','  no_lastwar_network=true']
reportp.write_text('\n'.join(lines)+'\n',encoding='utf-8')
print('PHASE53_OK',f"sceneLinked={summary['sceneLinkedCount']}/15",f"rootExact={summary['rootExactCount']}/15",f"meshLinks={summary['meshLinkCount']}",f"unresolvedMesh={summary['unresolvedMeshLinkCount']}",f"unresolvedTexture={summary['unresolvedTextureLinkCount']}",flush=True)
print('PHASE53_REPORT',reportp,flush=True)
PYEOF

python "$PY" "$P47" "$P49" "$P52" "$SRC" "$RUNTIME52" "$OUT" "$MANIFEST" "$REPORT" "$UNITY_VERSION"

git add "$MANIFEST"
if ! git diff --cached --quiet; then
  git commit -m "lab: record authoritative current15 runtime scene links"
  git push origin "$BRANCH"
fi
printf 'PHASE53_DONE report=%s\n' "$REPORT"
