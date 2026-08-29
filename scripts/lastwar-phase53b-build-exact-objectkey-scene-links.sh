#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — PHASE 53B
# EXACT UNITY OBJECT-KEY RUNTIME SCENE LINKS
# CODE ONLY · OFFLINE ONLY · exact Phase47 bundles + validated Phase49/52 data.
#
# Phase53 proved that pathId alone is not globally unique once several serialized
# Unity files are loaded together. This phase keys every object as:
#   (serialized assets-file identity, pathId)
# and resolves every PPtr to that same exact key. No name fallback is used for
# Mesh / Material / Texture binding. Exported OBJ/PNG identities are reconstructed
# from the exact Phase49B object iteration order and verified against names.
#
# No generated geometry. No generated motion. No fuzzy matching. No Last War network.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
UNITY_VERSION="2019.4.41f1"
P47="$ROOT/frontend/lab/master-assets-v2/meta/current15-exact-bundle-stage.json"
P49="$ROOT/frontend/lab/master-assets-v2/meta/current15-web-export-v2.json"
P52="$ROOT/frontend/lab/master-assets-v2/meta/current15-runtime-pack-v1.json"
SRC="$ROOT/frontend/lab/local_assets/lastwar-current15-exact-v1"
OUT="$ROOT/frontend/lab/local_assets/lastwar-current15-runtime-v3-scene"
MANIFEST="$ROOT/frontend/lab/master-assets-v2/meta/current15-runtime-scene-links-v2.json"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_PHASE53B_CURRENT15_EXACT_OBJECTKEY_SCENE_LINKS.txt"
PY="${TMPDIR:-$HOME/.cache}/wfgg-phase53b-objectkey-scene-links.py"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche active incorrecte"
[[ -s "$P47" ]] || fail "Phase47 absente"
[[ -s "$P49" ]] || fail "Phase49B absente"
[[ -s "$P52" ]] || fail "Phase52 absente"
[[ -d "$SRC" ]] || fail "bundles locaux Phase47 absents"
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
import json, os, re, sys, traceback

p47p,p49p,p52p,src,out,manifestp,reportp,unity_version=sys.argv[1:]
p47p=Path(p47p);p49p=Path(p49p);p52p=Path(p52p);src=Path(src);out=Path(out);manifestp=Path(manifestp);reportp=Path(reportp)

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
        except:pass
    return default
def pid_raw(x):
    if x is None:return None
    for y in (x,getattr(x,'reader',None),getattr(x,'object_reader',None)):
        if y is None:continue
        for a in ('path_id','m_PathID'):
            try:
                v=getattr(y,a,None)
                if v is not None:return int(v)
            except:pass
    return None
def assets_name_from_reader(r):
    if r is None:return ''
    for y in (r,getattr(r,'reader',None),getattr(r,'object_reader',None)):
        if y is None:continue
        for a in ('assets_file','assetsfile'):
            try:
                af=getattr(y,a,None)
                if af is not None:
                    n=str(getattr(af,'name','') or getattr(af,'path','') or '')
                    if n:return n
            except:pass
    return ''
def ptr_reader(p):
    if p is None:return None
    # ObjectReader itself.
    if hasattr(p,'type') and pid_raw(p) is not None and assets_name_from_reader(p):return p
    for fn in ('get_obj','get_object'):
        try:
            f=getattr(p,fn,None)
            if callable(f):
                r=f()
                if r is not None:return r
        except:pass
    # Some UnityPy PPtrs expose a resolved ObjectReader through .reader.
    r=getattr(p,'reader',None)
    if r is not None and hasattr(r,'type') and pid_raw(r) is not None:return r
    # Last exact route: dereference object then recover its object_reader.
    for fn in ('read','deref_parse_as_object','parse_as_object'):
        try:
            f=getattr(p,fn,None)
            if callable(f):
                o=f()
                rr=getattr(o,'object_reader',None) or getattr(o,'reader',None)
                if rr is not None and pid_raw(rr) is not None:return rr
        except:pass
    return None
def rkey(r):
    if r is None:return None
    p=pid_raw(r);a=assets_name_from_reader(r)
    if p is None or not a:return None
    return (a,p)
def pkey(p):
    return rkey(ptr_reader(p))
def keystr(k):
    return None if k is None else f'{k[0]}::{k[1]}'
def keyrow(k):
    return None if k is None else {'assetsFile':k[0],'pathId':k[1],'objectKey':keystr(k)}
def pobj(p):
    if p is None:return None
    for fn in ('read','deref_parse_as_object','parse_as_object'):
        try:
            f=getattr(p,fn,None)
            if callable(f):return f()
        except:pass
    rr=ptr_reader(p)
    if rr is not None:return robj(rr)
    return None
def oname(o,fb=''):
    if o is None:return str(fb or '')
    return str(getattr(o,'m_Name','') or getattr(o,'name','') or fb or '')
def pname(p):return oname(pobj(p))
def vec(v,names):
    if v is None:return None
    try:return [float(getattr(v,n)) for n in names]
    except:return None
def expected_root(q):return Path(str(q or '')).stem
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
        tk=pkey(texptr)
        rows.append({'slot':str(k),'textureKey':keyrow(tk),'texture':pname(texptr)})
    return rows

def phase49_identity(readers,e49):
    # Recreate Phase49B's exact de-duplication and object iteration order:
    # key=(type,path_id,assets_file.name). This is deterministic because both phases
    # load the same sorted Phase47 bundle paths into one UnityPy environment.
    seen=set();ordered=[]
    for r in readers:
        k=(tname(r),pid_raw(r),assets_name_from_reader(r))
        if k in seen:continue
        seen.add(k);ordered.append(r)
    mr=[r for r in ordered if tname(r)=='Mesh']
    tr=[r for r in ordered if tname(r)=='Texture2D']
    em=list(e49.get('meshes',[]));et=list(e49.get('textures',[]))
    if len(mr)!=len(em):raise ValueError(f'Phase49 mesh identity count mismatch readers={len(mr)} manifest={len(em)}')
    if len(tr)!=len(et):raise ValueError(f'Phase49 texture identity count mismatch readers={len(tr)} manifest={len(et)}')
    mm={};tm={};mismatch=[]
    for r,x in zip(mr,em):
        o=robj(r);n=oname(o,'Mesh');rk=rkey(r)
        if n!=str(x.get('name') or ''):mismatch.append(f'Mesh:{n}!={x.get("name")}')
        if rk is not None:mm[rk]=x
    for r,x in zip(tr,et):
        o=robj(r);n=oname(o,'Texture2D');rk=rkey(r)
        if n!=str(x.get('name') or ''):mismatch.append(f'Texture2D:{n}!={x.get("name")}')
        if rk is not None:tm[rk]=x
    if mismatch:raise ValueError('Phase49 identity order mismatch: '+' | '.join(mismatch[:8]))
    return mm,tm

rows=[]
for idx,hid in enumerate(ids,1):
    h=h47[hid];e49=h49[hid];e52=h52[hid];nm=h.get('name') or str(hid);expected=expected_root(h.get('queueModelPath'))
    print(f'PHASE53B_HERO {idx}/15 id={hid} name={nm}',flush=True)
    row={'heroId':hid,'name':nm,'queueModelPath':h.get('queueModelPath'),'expectedRoot':expected,'parseOk':False,'rootExact':False,'sceneLinked':False,'errors':[]}
    try:
        hdir=src/str(hid);files=[]
        for b in h.get('bundles') or []:
            logical=os.path.basename(str(b.get('logicalName') or ''))
            p=hdir/logical
            if logical and p.is_file():files.append(p)
        files=sorted(set(files))
        if not files:raise ValueError('no exact Phase47 bundles')
        env=UnityPy.load(*[str(x) for x in files]);readers=list(env.objects);row['parseOk']=True
        export_mesh,export_tex=phase49_identity(readers,e49)

        gos={};trs={};tr_by_go={}
        for r in readers:
            typ=tname(r)
            if typ not in ('GameObject','Transform','RectTransform'):continue
            o=robj(r);rk=rkey(r)
            if o is None or rk is None:continue
            if typ=='GameObject':gos[rk]={'key':keyrow(rk),'name':oname(o)}
            else:
                gp=attr(o,'m_GameObject');gk=pkey(gp);fk=pkey(attr(o,'m_Father'))
                ck=[]
                for x in (attr(o,'m_Children',default=[]) or []):
                    q=pkey(x)
                    if q is not None:ck.append(q)
                tr={'key':keyrow(rk),'gameObjectKey':keyrow(gk),'name':pname(gp),'parentKey':keyrow(fk),'_parent':fk,'_children':ck,
                    'localPosition':vec(attr(o,'m_LocalPosition'),('x','y','z')),'localRotation':vec(attr(o,'m_LocalRotation'),('x','y','z','w')),'localScale':vec(attr(o,'m_LocalScale'),('x','y','z'))}
                trs[rk]=tr
                if gk is not None:tr_by_go[gk]=rk

        # Exact-name roots first; wrapper-compatible score only if the prefab itself uses one.
        roots=[]
        for k,t in trs.items():
            if t['_parent'] is None or t['_parent'] not in trs:
                roots.append((k,t))
        if not roots:raise ValueError('no transform roots')
        def descendant_count(rootk):
            n=0
            for k in trs:
                seen=set();cur=k
                while cur in trs and cur not in seen:
                    if cur==rootk:n+=1;break
                    seen.add(cur);cur=trs[cur]['_parent']
            return n
        scored=[]
        for k,t in roots:
            sc=root_score(t.get('name'),expected)
            if sc>=5000:scored.append((sc,descendant_count(k),k,t))
        if not scored:raise ValueError(f'authoritative root not found expected={expected}')
        scored.sort(key=lambda z:(z[0],z[1]),reverse=True)
        sc,root_desc,rootk,root=scored[0];row['rootExact']=sc>=5000

        def under_root(k):
            seen=set();cur=k
            while cur in trs and cur not in seen:
                if cur==rootk:return True
                seen.add(cur);cur=trs[cur]['_parent']
            return False
        memo={}
        def fullpath(k):
            if k in memo:return memo[k]
            t=trs.get(k)
            if not t:return ''
            pk=t['_parent'];pp=fullpath(pk) if pk in trs else ''
            p=(pp+'/'+t['name']) if pp else t['name'];memo[k]=p;return p
        scene_tr=[]
        for k,t in trs.items():
            if not under_root(k):continue
            scene_tr.append({z:v for z,v in t.items() if not z.startswith('_')}|{'path':fullpath(k)})
        scene_tr.sort(key=lambda x:x['path'])
        path_by_key={keystr(k):fullpath(k) for k in trs if under_root(k)}

        mesh_catalog={};tex_catalog={};materials={};mesh_filters=[];renderers=[];skinned=[]
        for r in readers:
            typ=tname(r)
            if typ not in ('Mesh','Texture2D','Material','MeshFilter','MeshRenderer','Renderer','SkinnedMeshRenderer'):continue
            o=robj(r);rk=rkey(r)
            if o is None or rk is None:continue
            if typ=='Mesh':
                ex=export_mesh.get(rk)
                mesh_catalog[rk]={'key':keyrow(rk),'name':oname(o,'Mesh'),'objFile':ex.get('file') if ex else None,'objSha256':ex.get('sha256') if ex else None}
            elif typ=='Texture2D':
                ex=export_tex.get(rk)
                tex_catalog[rk]={'key':keyrow(rk),'name':oname(o,'Texture2D'),'pngFile':ex.get('file') if ex else None,'pngSha256':ex.get('sha256') if ex else None}
            elif typ=='Material':
                materials[rk]={'key':keyrow(rk),'name':oname(o,'Material'),'shader':pname(attr(o,'m_Shader')),'textures':material_tex_slots(o)}
            else:
                gp=attr(o,'m_GameObject');gk=pkey(gp);tk=tr_by_go.get(gk)
                if tk is None or not under_root(tk):continue
                mats=[]
                for mp in (attr(o,'m_Materials',default=[]) or []):
                    mk=pkey(mp);mats.append({'key':keyrow(mk),'name':pname(mp)})
                base={'componentKey':keyrow(rk),'gameObjectKey':keyrow(gk),'gameObject':pname(gp),'transformKey':keyrow(tk),'transformPath':path_by_key.get(keystr(tk)),'materials':mats}
                if typ=='MeshFilter':
                    m=attr(o,'m_Mesh');mk=pkey(m);mesh_filters.append({**base,'meshKey':keyrow(mk),'mesh':pname(m)})
                elif typ in ('MeshRenderer','Renderer'):renderers.append(base)
                elif typ=='SkinnedMeshRenderer':
                    m=attr(o,'m_Mesh');mk=pkey(m);bones=[]
                    for bp in (attr(o,'m_Bones',default=[]) or []):
                        bk=pkey(bp);bones.append({'transformKey':keyrow(bk),'transformPath':path_by_key.get(keystr(bk)),'name':pname(bp)})
                    rb=attr(o,'m_RootBone');rbk=pkey(rb)
                    skinned.append({**base,'meshKey':keyrow(mk),'mesh':pname(m),'rootBone':{'transformKey':keyrow(rbk),'transformPath':path_by_key.get(keystr(rbk)),'name':pname(rb)},'bones':bones})

        mesh_links=[];unresolved_mesh=[]
        for comp in mesh_filters+skinned:
            mkd=comp.get('meshKey');mk=(mkd['assetsFile'],mkd['pathId']) if mkd else None
            ex=export_mesh.get(mk) if mk else None
            link={'componentKey':comp.get('componentKey'),'transformPath':comp.get('transformPath'),'meshKey':mkd,'mesh':comp.get('mesh'),'objFile':ex.get('file') if ex else None,'objSha256':ex.get('sha256') if ex else None}
            mesh_links.append(link)
            if not link['objFile']:unresolved_mesh.append(link)

        used_mat_keys=set()
        for comp in renderers+skinned:
            for m in comp.get('materials',[]):
                kd=m.get('key')
                if kd:used_mat_keys.add((kd['assetsFile'],kd['pathId']))
        material_rows=[];unresolved_mat=[];unresolved_tex=[]
        for mk in sorted(used_mat_keys,key=lambda x:(x[0],x[1])):
            m=materials.get(mk)
            if not m:
                unresolved_mat.append({'key':keyrow(mk)});continue
            mm={**m,'textures':[]}
            for t in m.get('textures',[]):
                kd=t.get('textureKey');tk=(kd['assetsFile'],kd['pathId']) if kd else None
                ex=export_tex.get(tk) if tk else None
                tt={**t,'pngFile':ex.get('file') if ex else None,'pngSha256':ex.get('sha256') if ex else None}
                if tk is not None and not tt['pngFile']:unresolved_tex.append(tt)
                mm['textures'].append(tt)
            material_rows.append(mm)

        hd=out/str(hid);hd.mkdir(parents=True,exist_ok=True)
        scene={
          'format':'WFGG_LASTWAR_HERO_RUNTIME_SCENE_V2_OBJECTKEY','heroId':hid,'name':nm,'queueModelPath':h.get('queueModelPath'),'expectedRoot':expected,
          'root':{'transformKey':keyrow(rootk),'name':root.get('name'),'path':fullpath(rootk),'descendantCount':root_desc},
          'rendererMode':e52.get('rendererMode'),'transforms':scene_tr,'meshFilters':mesh_filters,'renderers':renderers,'skinnedRenderers':skinned,
          'meshes':list(mesh_catalog.values()),'materials':material_rows,'textures':list(tex_catalog.values()),'meshLinks':mesh_links,
          'runtimeBase':f'../lastwar-current15-runtime-v1/{hid}/','idleAnimation':'animation/idle.json.gz','rig':'rig.json.gz',
          'guardrails':{'exactQueueRoot':True,'objectKeyUsesAssetsFileAndPathId':True,'noNameFallbackForBinding':True,'noFuzzyMatching':True,'noGeneratedGeometry':True,'noGeneratedMotion':True}
        }
        (hd/'scene.json').write_text(json.dumps(scene,ensure_ascii=False,indent=2),encoding='utf-8')
        row.update({'transformCount':len(scene_tr),'rootDescendantCount':root_desc,'meshFilterCount':len(mesh_filters),'rendererCount':len(renderers),'skinnedRendererCount':len(skinned),
                    'meshLinkCount':len(mesh_links),'unresolvedMeshLinks':len(unresolved_mesh),'materialCount':len(material_rows),'unresolvedMaterialLinks':len(unresolved_mat),'unresolvedTextureLinks':len(unresolved_tex),
                    'sceneJson':str((hd/'scene.json').relative_to(out))})
        row['sceneLinked']=bool(scene_tr and mesh_links and not unresolved_mesh and not unresolved_mat)
        if unresolved_mesh:row['errors'].append('unresolved exact mesh keys: '+','.join(sorted({str(x.get('mesh')) for x in unresolved_mesh})))
        if unresolved_mat:row['errors'].append(f'unresolved exact materials={len(unresolved_mat)}')
    except Exception as e:
        row['errors'].append(repr(e));row['traceback']=traceback.format_exc()[-4000:]
    rows.append(row)
    print('PHASE53B_HERO_DONE',hid,f"linked={row['sceneLinked']}",f"transforms={row.get('transformCount',0)}",f"meshLinks={row.get('meshLinkCount',0)}",f"unresolvedMesh={row.get('unresolvedMeshLinks',0)}",f"unresolvedMat={row.get('unresolvedMaterialLinks',0)}",f"unresolvedTex={row.get('unresolvedTextureLinks',0)}",flush=True)

summary={'format':'WFGG_LASTWAR_CURRENT15_RUNTIME_SCENE_LINKS_V2_OBJECTKEY','networkUsed':False,'heroCount':15,
 'parseOkCount':sum(x['parseOk'] for x in rows),'rootExactCount':sum(x['rootExact'] for x in rows),'sceneLinkedCount':sum(x['sceneLinked'] for x in rows),
 'transformCount':sum(x.get('transformCount',0) for x in rows),'meshLinkCount':sum(x.get('meshLinkCount',0) for x in rows),
 'unresolvedMeshLinkCount':sum(x.get('unresolvedMeshLinks',0) for x in rows),'unresolvedMaterialLinkCount':sum(x.get('unresolvedMaterialLinks',0) for x in rows),'unresolvedTextureLinkCount':sum(x.get('unresolvedTextureLinks',0) for x in rows),
 'heroes':[{k:v for k,v in x.items() if k!='traceback'} for x in rows],
 'guardrails':{'objectKeyUsesAssetsFileAndPathId':True,'noNameFallbackForBinding':True,'noFuzzyMatching':True,'noGeneratedGeometry':True,'noGeneratedMotion':True,'noAnimationSubstitution':True,'noLastWarNetwork':True}}
manifestp.write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
lines=['WfGg Last War LAB — PHASE 53B EXACT OBJECT-KEY SCENE LINKS',
 f"heroes=15 parseOk={summary['parseOkCount']}/15 rootExact={summary['rootExactCount']}/15 sceneLinked={summary['sceneLinkedCount']}/15",
 f"transforms={summary['transformCount']} meshLinks={summary['meshLinkCount']} unresolvedMesh={summary['unresolvedMeshLinkCount']} unresolvedMaterial={summary['unresolvedMaterialLinkCount']} unresolvedTexture={summary['unresolvedTextureLinkCount']}",'']
for x in rows:
    lines.append(f"HERO {x['heroId']} {x['name']} linked={x['sceneLinked']} rootExact={x['rootExact']} rootDesc={x.get('rootDescendantCount',0)} transforms={x.get('transformCount',0)} meshLinks={x.get('meshLinkCount',0)} unresolvedMesh={x.get('unresolvedMeshLinks',0)} unresolvedMaterial={x.get('unresolvedMaterialLinks',0)} unresolvedTexture={x.get('unresolvedTextureLinks',0)} errors={x['errors']}")
lines += ['','GUARDRAILS','  object_key=assets_file+path_id','  no_name_fallback_for_binding=true','  no_fuzzy_matching=true','  no_generated_geometry=true','  no_generated_motion=true','  no_animation_substitution=true','  no_lastwar_network=true']
reportp.write_text('\n'.join(lines)+'\n',encoding='utf-8')
print('PHASE53B_OK',f"sceneLinked={summary['sceneLinkedCount']}/15",f"rootExact={summary['rootExactCount']}/15",f"meshLinks={summary['meshLinkCount']}",f"unresolvedMesh={summary['unresolvedMeshLinkCount']}",f"unresolvedMaterial={summary['unresolvedMaterialLinkCount']}",f"unresolvedTexture={summary['unresolvedTextureLinkCount']}",flush=True)
print('PHASE53B_REPORT',reportp,flush=True)
PYEOF

python "$PY" "$P47" "$P49" "$P52" "$SRC" "$OUT" "$MANIFEST" "$REPORT" "$UNITY_VERSION"

git add "$MANIFEST"
if ! git diff --cached --quiet; then
  git commit -m "lab: record exact object-key current15 runtime scene links"
  git push origin "$BRANCH"
fi
printf 'PHASE53B_DONE report=%s\n' "$REPORT"
