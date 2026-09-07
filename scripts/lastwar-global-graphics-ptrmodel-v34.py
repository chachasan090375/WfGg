#!/usr/bin/env python3
from __future__ import annotations

"""Exact Unity prefab -> Mesh resolver for the WfGg V33 mobile LAB.

This module deliberately does not guess meshes by name. It anchors the selected catalogue
asset in Unity's AssetBundle container (exact asset path when available), walks the real
GameObject/Transform/component PPtr graph and exports only Mesh objects reached from that graph.
A conservative strong GameObject-name anchor is allowed only when the container does not expose
the asset path. The caller keeps the previous strict renderer as fallback.
"""

from pathlib import Path
from urllib.parse import quote
import gc, json, math, re, shutil

SCHEMA=3401
MAX_DEP_BUNDLES=16
MAX_DEPTH=3
MAX_GAMEOBJECTS=320
MAX_MESHES=48

class PtrGraphUnavailable(RuntimeError):
    pass


def _safe(s):
    return re.sub(r'[^a-zA-Z0-9_.-]+','_',str(s or ''))[:100] or 'asset'


def _norm_path(s):
    return str(s or '').replace('\\','/').strip().lower()


def _type_name(reader):
    try:return str(getattr(reader.type,'name',reader.type))
    except Exception:return ''


def _obj_name(reader):
    try:
        n=reader.peek_name()
        if n:return str(n)
    except Exception:pass
    try:return str(getattr(reader.read(),'m_Name','') or '')
    except Exception:return ''


def _reader_from(value):
    if value is None:return None
    if hasattr(value,'type') and hasattr(value,'read'):
        return value
    for meth in ('get_obj','get_object'):
        fn=getattr(value,meth,None)
        if callable(fn):
            try:
                r=fn()
                if r is not None and hasattr(r,'type') and hasattr(r,'read'):return r
            except Exception:pass
    for attr in ('object_reader','reader','asset'):
        try:
            r=getattr(value,attr,None)
            if r is not None and hasattr(r,'type') and hasattr(r,'read'):return r
        except Exception:pass
    return None


def _vec3(v,default):
    if v is None:return default
    try:return (float(v.x),float(v.y),float(v.z))
    except Exception:pass
    if isinstance(v,(tuple,list)) and len(v)>=3:
        try:return (float(v[0]),float(v[1]),float(v[2]))
        except Exception:pass
    return default


def _quat(v):
    if v is None:return (0.0,0.0,0.0,1.0)
    try:return (float(v.x),float(v.y),float(v.z),float(v.w))
    except Exception:pass
    if isinstance(v,(tuple,list)) and len(v)>=4:
        try:return tuple(float(x) for x in v[:4])
        except Exception:pass
    return (0.0,0.0,0.0,1.0)


def _identity():
    return ((1.,0.,0.,0.),(0.,1.,0.,0.),(0.,0.,1.,0.),(0.,0.,0.,1.))


def _mul(a,b):
    return tuple(tuple(sum(a[r][k]*b[k][c] for k in range(4)) for c in range(4)) for r in range(4))


def _local_matrix(transform):
    p=_vec3(getattr(transform,'m_LocalPosition',None),(0.,0.,0.))
    s=_vec3(getattr(transform,'m_LocalScale',None),(1.,1.,1.))
    x,y,z,w=_quat(getattr(transform,'m_LocalRotation',None))
    qn=math.sqrt(x*x+y*y+z*z+w*w) or 1.0;x/=qn;y/=qn;z/=qn;w/=qn
    xx,yy,zz=x*x,y*y,z*z;xy,xz,yz=x*y,x*z,y*z;wx,wy,wz=w*x,w*y,w*z
    r00=1-2*(yy+zz);r01=2*(xy-wz);r02=2*(xz+wy)
    r10=2*(xy+wz);r11=1-2*(xx+zz);r12=2*(yz-wx)
    r20=2*(xz-wy);r21=2*(yz+wx);r22=1-2*(xx+yy)
    return ((r00*s[0],r01*s[1],r02*s[2],p[0]),
            (r10*s[0],r11*s[1],r12*s[2],p[1]),
            (r20*s[0],r21*s[1],r22*s[2],p[2]),
            (0.,0.,0.,1.))


def _transform_obj(txt,m):
    out=[]
    for line in txt.splitlines():
        if line.startswith('v '):
            p=line[2:].strip().split()
            if len(p)>=3:
                try:
                    x,y,z=map(float,p[:3])
                    q=(m[0][0]*x+m[0][1]*y+m[0][2]*z+m[0][3],
                       m[1][0]*x+m[1][1]*y+m[1][2]*z+m[1][3],
                       m[2][0]*x+m[2][1]*y+m[2][2]*z+m[2][3])
                    line='v %.9g %.9g %.9g'%(q[0],q[1],q[2])
                except Exception:pass
        out.append(line)
    return '\n'.join(out)+'\n'


def _component_ptrs(go):
    for item in getattr(go,'m_Component',None) or []:
        ptr=getattr(item,'component',None) or getattr(item,'m_Component',None) or item
        r=_reader_from(ptr)
        if r is not None:yield r


def _mesh_ptrs(component):
    names=('m_Mesh','mesh','m_Mesh1','m_Mesh2','m_Mesh3','m_Mesh4')
    seen=set()
    for name in names:
        ptr=getattr(component,name,None)
        r=_reader_from(ptr)
        if r is not None and _type_name(r)=='Mesh':
            key=id(r)
            if key not in seen:seen.add(key);yield r,name
    for name in ('m_Meshes','meshes'):
        vals=getattr(component,name,None) or []
        try:it=list(vals)
        except Exception:continue
        for i,ptr in enumerate(it):
            r=_reader_from(ptr)
            if r is not None and _type_name(r)=='Mesh':
                key=id(r)
                if key not in seen:seen.add(key);yield r,f'{name}[{i}]'


def _container_reader(env,a,core):
    target=_norm_path(a.get('asset_path'))
    container=getattr(env,'container',None) or {}
    try:items=list(container.items())
    except Exception:items=[]
    if target:
        exact=[]
        for key,val in items:
            k=_norm_path(key)
            if k==target:exact.append((key,val))
        if len(exact)==1:
            r=_reader_from(exact[0][1])
            if r:return r,'assetbundle-container-exact:'+str(exact[0][0])
        suffix=[(key,val) for key,val in items if _norm_path(key).endswith('/'+target) or target.endswith('/'+_norm_path(key))]
        if len(suffix)==1:
            r=_reader_from(suffix[0][1])
            if r:return r,'assetbundle-container-suffix:'+str(suffix[0][0])

    terms=core.target_terms(a);cands=[]
    for obj in env.objects:
        if _type_name(obj)!='GameObject':continue
        name=_obj_name(obj);score=core.score_name(name,terms)
        if score>=75:cands.append((score,len(name),name,obj))
    cands.sort(reverse=True,key=lambda x:(x[0],x[1]))
    if cands:
        top=cands[0]
        ties=[x for x in cands if x[0]==top[0] and x[2]==top[2]]
        if len(ties)==1:return top[3],'gameobject-strong-name:'+top[2]+':'+str(top[0])
    return None,'no-exact-root'


def _root_gameobject(reader):
    typ=_type_name(reader)
    if typ=='GameObject':return reader
    try:data=reader.read()
    except Exception:return None
    ptr=getattr(data,'m_GameObject',None)
    r=_reader_from(ptr)
    if r is not None and _type_name(r)=='GameObject':return r
    for name in ('m_RootGameObject','rootGameObject'):
        r=_reader_from(getattr(data,name,None))
        if r is not None and _type_name(r)=='GameObject':return r
    return None


def _go_transform(go_reader):
    try:go=go_reader.read()
    except Exception:return None,None
    components=list(_component_ptrs(go))
    for r in components:
        if _type_name(r) in {'Transform','RectTransform'}:
            try:return r,r.read()
            except Exception:return r,None
    return None,None


def _walk(root_go):
    queue=[(root_go,_identity(),'root')];visited=set();meshes=[];nodes=0
    while queue and nodes<MAX_GAMEOBJECTS and len(meshes)<MAX_MESHES:
        go_reader,parent_world,route=queue.pop(0)
        key=(_type_name(go_reader),getattr(go_reader,'path_id',id(go_reader)))
        if key in visited:continue
        visited.add(key);nodes+=1
        try:go=go_reader.read()
        except Exception:continue
        tr_reader,tr=_go_transform(go_reader)
        world=_mul(parent_world,_local_matrix(tr)) if tr is not None else parent_world
        for comp_reader in _component_ptrs(go):
            typ=_type_name(comp_reader)
            if typ in {'Transform','RectTransform'}:continue
            try:comp=comp_reader.read()
            except Exception:continue
            for mesh_reader,field in _mesh_ptrs(comp):
                meshes.append((mesh_reader,world,route+'/'+typ+'.'+field,_obj_name(go_reader)))
                if len(meshes)>=MAX_MESHES:break
        if tr is None:continue
        for i,ptr in enumerate(getattr(tr,'m_Children',None) or []):
            child_tr_reader=_reader_from(ptr)
            if child_tr_reader is None:continue
            try:child_tr=child_tr_reader.read()
            except Exception:continue
            child_go=_reader_from(getattr(child_tr,'m_GameObject',None))
            if child_go is not None and _type_name(child_go)=='GameObject':
                queue.append((child_go,world,route+f'/child[{i}]'))
    return meshes,nodes


def _materialize(core,dependency_rows,a,cache):
    sid=a['stable_id'];base=cache/'closure'/sid
    if base.exists():shutil.rmtree(base,ignore_errors=True)
    base.mkdir(parents=True,exist_ok=True)
    rows=[a]+dependency_rows(a,max_bundles=MAX_DEP_BUNDLES,max_depth=MAX_DEPTH)
    seen=set();paths=[];sources=[]
    for row in rows:
        try:bid=int(row.get('bundle_id'))
        except Exception:continue
        if bid in seen:continue
        seen.add(bid)
        try:src,source=core.v31.materialize_bundle(row)
        except Exception as exc:
            sources.append({'bundleId':bid,'ok':False,'error':str(exc)[:220]});continue
        dst=base/f'bundle-{bid}.bundle'
        try:shutil.copy2(src,dst)
        except Exception as exc:
            sources.append({'bundleId':bid,'ok':False,'error':'copy:'+str(exc)[:220]});continue
        paths.append(dst);sources.append({'bundleId':bid,'ok':True,'source':source,'depth':row.get('_dependency_depth',0)})
    return paths,sources


def build_ptr_model(a,core,exact,dependency_rows,model_cache):
    sid=a['stable_id'];outdir=model_cache/sid;mp=outdir/'manifest.json'
    if mp.is_file():
        try:
            m=json.loads(mp.read_text('utf-8'))
            if m.get('schemaVersion')==SCHEMA and m.get('objects'):return m
        except Exception:pass
    if outdir.exists():shutil.rmtree(outdir,ignore_errors=True)
    outdir.mkdir(parents=True,exist_ok=True)
    paths,sources=_materialize(core,dependency_rows,a,model_cache)
    if not paths:raise PtrGraphUnavailable('PTR3D_NO_LOCAL_CLOSURE')
    try:import UnityPy
    except Exception as exc:raise PtrGraphUnavailable('PTR3D_UNITYPY_MISSING: '+str(exc)) from exc
    env=None
    try:
        env=UnityPy.load(*[str(p) for p in paths])
        anchor,anchor_mode=_container_reader(env,a,core)
        if anchor is None:raise PtrGraphUnavailable('PTR3D_ROOT_NOT_FOUND: '+anchor_mode)
        root=_root_gameobject(anchor)
        if root is None:raise PtrGraphUnavailable('PTR3D_ROOT_NOT_GAMEOBJECT: '+_type_name(anchor))
        reached,nodes=_walk(root)
        if not reached:raise PtrGraphUnavailable('PTR3D_NO_MESH_POINTER: root='+_obj_name(root)+' nodes='+str(nodes))

        target=(core.target_terms(a) or [sid])[0]
        exported=[];files=[];objects=[];mesh_seen=set();errors=[]
        for i,(reader,world,route,go_name) in enumerate(reached[:MAX_MESHES]):
            pid=getattr(reader,'path_id',None)
            filekey=str(getattr(getattr(reader,'assets_file',None),'name',''))
            dedupe=(filekey,pid)
            if dedupe in mesh_seen:continue
            mesh_seen.add(dedupe)
            original=_obj_name(reader)
            try:
                data=reader.read();txt=exact.codec.export_mesh_obj(data);txt=_transform_obj(txt,world)
                fn=f'mesh-ptr-{len(objects):02d}-{_safe(target)}.obj';fp=outdir/fn;fp.write_text(txt,'utf-8')
                rec={'path':fn,'kind':'obj','bytes':fp.stat().st_size,'url':'/api/v33/model-file?id='+quote(sid)+'&file='+quote(fn,safe='/')}
                files.append(rec);objects.append(rec)
                exported.append({'type':'Mesh','name':target,'originalName':original,'score':100,'mode':'unity-ptr-graph','pointerRoute':route,'gameObject':go_name,'pathId':pid})
            except Exception as exc:errors.append((original or '<mesh>')+': '+type(exc).__name__+': '+str(exc))
        if not objects:raise PtrGraphUnavailable('PTR3D_MESH_EXPORT_FAILED: '+' | '.join(errors[:5]))
        m={'schemaVersion':SCHEMA,'stableId':sid,'dimensionClass':a.get('dimension_class'),'assetFolder':a.get('asset_folder') or '',
           'assemblyMode':'unity-ptr-graph-exact','correlation':'exact-unity-ptr-graph','rootAnchor':anchor_mode,'rootGameObject':_obj_name(root),
           'graphNodes':nodes,'meshPointerCount':len(reached),'meshCount':len(objects),'bundleIds':[x['bundleId'] for x in sources if x.get('ok')],
           'bundleSources':sources,'exportedObjects':exported,'objects':objects,'files':files,'errors':errors[:40],
           'policy':'Exact AssetBundle container/GameObject anchor; Transform/component PPtr traversal; only referenced Mesh objects; world TRS baked into OBJ vertices.'}
        mp.write_text(json.dumps(m,ensure_ascii=False,indent=2),'utf-8');return m
    finally:
        try:del env
        except Exception:pass
        gc.collect()


def install(core,correlated,model_cache,dependency_rows):
    """Install the exact graph builder ahead of the previous strict model path."""
    model_cache=Path(model_cache);model_cache.mkdir(parents=True,exist_ok=True)
    fallback=core.build_model;failed=set()
    core.MODEL_CACHE=model_cache
    try:correlated.exact.MODEL_CACHE=model_cache
    except Exception:pass

    def build(a):
        sid=a['stable_id']
        if sid not in failed:
            try:
                m=build_ptr_model(a,core,correlated.exact,dependency_rows,model_cache)
                print('V34_PTR3D_OK',sid,'meshes='+str(len(m.get('objects') or [])),'root='+str(m.get('rootGameObject') or ''),flush=True)
                return m
            except PtrGraphUnavailable as exc:
                failed.add(sid);print('V34_PTR3D_FALLBACK',sid,str(exc)[:500],flush=True)
            except Exception as exc:
                failed.add(sid);print('V34_PTR3D_ERROR',sid,type(exc).__name__,str(exc)[:500],flush=True)
        return fallback(a)
    core.build_model=build
    return build
