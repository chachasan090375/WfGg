#!/usr/bin/env python3
from __future__ import annotations

from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote
import gc, importlib.util, json, re, shutil, subprocess, sys

ROOT=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else Path(__file__).resolve().parents[1]
RESOLVED=ROOT/'scripts/lastwar-global-graphics-server-v33-resolved.py'
DEPS_SCRIPT=ROOT/'scripts/lastwar-global-graphics-dependencies-v33.py'
CODEC_PATH=ROOT/'scripts/lastwar-global-graphics-android-codec-v33.py'
CACHE=Path.home()/'.cache/wfgg-lastwar-v31'
MODEL_CACHE=CACHE/'models-v33-exact'
MODEL_CACHE.mkdir(parents=True,exist_ok=True)
MAX_DEP_BUNDLES=36
MAX_MESHES=80
MAX_TEXTURES=120


def load_module(name,path):
    spec=importlib.util.spec_from_file_location(name,path); mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); return mod

resolved=load_module('wfgg_v33_resolved',RESOLVED)
core=resolved.core
codec=load_module('wfgg_v33_android_codec',CODEC_PATH)


def ensure_dependencies():
    con=core.dbcon(); tables={r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}; con.close()
    if 'bundle_dependencies_v33' not in tables:
        print('V33_DEP_MAP_MISSING construction...',flush=True)
        subprocess.run([sys.executable,str(DEPS_SCRIPT),str(ROOT)],check=True)

ensure_dependencies()


def safe(s): return re.sub(r'[^a-zA-Z0-9_.-]+','_',str(s or ''))[:100] or 'asset'


def object_name(obj):
    try:
        n=obj.peek_name()
        if n:return str(n)
    except Exception: pass
    try:return str(getattr(obj.read(),'m_Name','') or '')
    except Exception:return ''


def physical_row_for_bundle(con,bid):
    row=con.execute("""
      SELECT * FROM assets
      WHERE bundle_id=? AND render_availability IN ('local-exact','local-resolved')
      ORDER BY CASE render_availability WHEN 'local-exact' THEN 0 ELSE 1 END,
               CASE WHEN offset_bytes>=0 AND span_bytes>0 THEN 0 ELSE 1 END,row_no LIMIT 1
    """,(bid,)).fetchone()
    return core.rowdict(row) if row else None


def dependency_rows(a,max_bundles=MAX_DEP_BUNDLES,max_depth=2):
    try:start=int(a.get('bundle_id'))
    except Exception:return []
    con=core.dbcon(); out=[]; seen={start}; frontier=[start]
    for depth in range(max_depth):
        nxt=[]
        for src in frontier:
            for r in con.execute('SELECT target_bundle_id FROM bundle_dependencies_v33 WHERE source_bundle_id=? ORDER BY ordinal',(src,)):
                bid=int(r[0])
                if bid in seen:continue
                seen.add(bid);nxt.append(bid)
                row=physical_row_for_bundle(con,bid)
                if row:
                    row['_dependency_depth']=depth+1;row['_dependency_from']=src;out.append(row)
                    if len(out)>=max_bundles:break
            if len(out)>=max_bundles:break
        if len(out)>=max_bundles or not nxt:break
        frontier=nxt
    con.close()
    def rank(x):
        t=' '.join(str(x.get(k) or '').lower() for k in ('logical_name','asset_path','alias_name'))
        if 'mesh' in t:return 0
        if 'material' in t:return 1
        if 'texture' in t:return 2
        if 'prefab' in t:return 3
        if 'animation' in t or 'animator' in t:return 4
        return 5
    out.sort(key=lambda x:(rank(x),x.get('_dependency_depth',9),x.get('bundle_id',999999)))
    return out[:max_bundles]


def _score(name,terms): return core.score_name(name,terms)


def export_bundle_android(bundle,outdir,bi,terms,stats,errors):
    import UnityPy
    env=None
    try:
        env=UnityPy.load(str(bundle)); meshes=[]; textures=[]
        for obj in env.objects:
            typ=getattr(obj.type,'name',str(obj.type)); name=object_name(obj); score=_score(name,terms)
            if typ=='Mesh':meshes.append((score,name,obj))
            elif typ=='Texture2D':textures.append((score,name,obj))
        meshes.sort(key=lambda x:(x[0],len(x[1])),reverse=True);textures.sort(key=lambda x:(x[0],len(x[1])),reverse=True)
        for oi,(score,name,obj) in enumerate(meshes[:MAX_MESHES]):
            try:
                data=obj.read(); txt=codec.export_mesh_obj(data)
                fp=outdir/f'mesh-b{bi}-{oi}-{safe(name or "mesh")}.obj';fp.write_text(txt,'utf-8')
                stats['meshes']+=1;stats['objects'].append({'type':'Mesh','name':name,'score':score,'sourceBundle':bundle.name,'mode':'android-meshhandler'})
            except Exception as e:errors.append(f'Mesh {name}: {e}')
        texdir=outdir/'textures';texdir.mkdir(exist_ok=True)
        for oi,(score,name,obj) in enumerate(textures[:MAX_TEXTURES]):
            try:
                data=obj.read();img,fmt=codec.decode_texture2d(data)
                fp=texdir/f'b{bi}-{oi}-{safe(name or "texture")}.png';img.save(fp)
                stats['textures']+=1;stats['formats'][fmt]=stats['formats'].get(fmt,0)+1
            except Exception as e:errors.append(f'Texture2D {name}: {e}')
        stats['bundles']+=1;return True
    except Exception as e:
        errors.append('load '+bundle.name+': '+str(e));return False
    finally:
        try:del env
        except Exception:pass
        gc.collect()


def build_model_exact(a):
    sid=a['stable_id'];outdir=MODEL_CACHE/sid;mp=outdir/'manifest.json'
    if mp.is_file():
        try:
            m=json.loads(mp.read_text('utf-8'))
            if m.get('schemaVersion')==3302 and m.get('objects'):return m
        except Exception:pass
    if outdir.exists():shutil.rmtree(outdir,ignore_errors=True)
    outdir.mkdir(parents=True,exist_ok=True)

    deps=dependency_rows(a); candidates=[a]+deps
    # Same logical folder remains a secondary source, but exact dependency bundles are first.
    candidate_ids={y.get('stable_id') for y in candidates}
    for x in core.assembly_assets(a):
        if x.get('stable_id') not in candidate_ids and str(x.get('render_availability') or '')!='global-index-only':
            candidates.append(x); candidate_ids.add(x.get('stable_id'))
        if len(candidates)>=MAX_DEP_BUNDLES:break

    seen=set();bundle_rows=[]
    for x in candidates:
        try:bid=int(x.get('bundle_id'))
        except Exception:continue
        if bid in seen:continue
        seen.add(bid);bundle_rows.append(x)
        if len(bundle_rows)>=MAX_DEP_BUNDLES:break

    terms=core.target_terms(a);errors=[];stats={'bundles':0,'meshes':0,'textures':0,'formats':{},'objects':[]};sources=[];bundle_ids=[]
    for bi,x in enumerate(bundle_rows):
        bundle_ids.append(x.get('bundle_id'))
        try:p,source=core.v31.materialize_bundle(x)
        except Exception as e:
            errors.append('materialize b'+str(x.get('bundle_id'))+': '+str(e));continue
        sources.append({'bundleId':x.get('bundle_id'),'source':source,'dependencyDepth':x.get('_dependency_depth',0)})
        export_bundle_android(p,outdir,bi,terms,stats,errors)

    files=[]
    for fp in sorted(outdir.rglob('*')):
        if not fp.is_file() or fp.name=='manifest.json':continue
        rel=fp.relative_to(outdir).as_posix();ext=fp.suffix.lower()
        if ext not in {'.obj','.png','.jpg','.jpeg','.webp'}:continue
        files.append({'path':rel,'kind':ext.lstrip('.'),'bytes':fp.stat().st_size,'url':'/api/v33/model-file?id='+quote(sid)+'&file='+quote(rel,safe='/')})
    objects=[f for f in files if f['kind']=='obj']
    if not objects:
        raise RuntimeError(f'Aucune géométrie Mesh décodable dans le bundle sélectionné et ses {len(deps)} dépendances locales exactes')
    m={'schemaVersion':3302,'stableId':sid,'dimensionClass':a.get('dimension_class'),'assetFolder':a.get('asset_folder') or '',
       'dependencyPolicy':'TSV exact depends_on, depth<=2; candidate edges excluded','exactDependencyBundles':len(deps),
       'assemblyAssetCount':len(candidates),'bundleIds':bundle_ids,'bundleSources':sources,'exportedObjects':stats['objects'],
       'objects':objects,'files':files,'androidSafe':True,'meshCount':stats['meshes'],'textureCount':stats['textures'],'textureFormats':stats['formats'],'errors':errors[:120]}
    mp.write_text(json.dumps(m,ensure_ascii=False,indent=2),'utf-8');return m


def crop_sprite(img,sprite):
    try:
        r=getattr(sprite,'m_Rect',None)
        if r is None:return img
        x=int(round(float(r.x)));y=int(round(float(r.y)));w=int(round(float(r.width)));h=int(round(float(r.height)))
        if w<=0 or h<=0:return img
        top=max(0,img.height-(y+h));left=max(0,x);right=min(img.width,x+w);bottom=min(img.height,img.height-y)
        if right>left and bottom>top:return img.crop((left,top,right,bottom))
    except Exception:pass
    return img


def render_asset_android(a):
    sid=a['stable_id'];cached=core.v31.RENDER_CACHE/(sid+'.png')
    if cached.is_file() and cached.stat().st_size>64:
        return cached,{'source':'render-cache-v33'}
    bundle,source=core.v31.materialize_bundle(a)
    try:import UnityPy
    except Exception as e:raise RuntimeError('UnityPy indisponible: '+str(e))
    env=None;terms=core.v31.target_terms(a);cands=[];errs=[]
    try:
        env=UnityPy.load(str(bundle))
        for obj in env.objects:
            typ=getattr(obj.type,'name',str(obj.type))
            if typ not in {'Texture2D','Sprite'}:continue
            name=object_name(obj);score=core.score_name(name,terms)+(5 if typ=='Sprite' else 0);cands.append((score,name,typ,obj))
        cands.sort(key=lambda x:(x[0],len(x[1])),reverse=True)
        for score,name,typ,obj in cands[:40]:
            try:
                data=obj.read()
                if typ=='Texture2D':img,fmt=codec.decode_texture2d(data)
                else:
                    rd=getattr(data,'m_RD',None);ptr=getattr(rd,'texture',None) if rd is not None else None
                    tex=ptr.read() if ptr is not None else None
                    if tex is None:raise ValueError('Sprite sans Texture2D résolue')
                    img,fmt=codec.decode_texture2d(tex);img=crop_sprite(img,data)
                img.save(cached)
                return cached,{'source':source,'objectName':name,'objectType':typ,'matchScore':score,'bundleId':a.get('bundle_id'),'codec':'android-direct','textureFormat':fmt}
            except Exception as e:errs.append(f'{typ}:{name}:{e}')
        if not cands:raise RuntimeError('Aucun Sprite/Texture2D dans ce bundle')
        raise RuntimeError('Sprite/Texture2D trouvés mais décodage Android impossible: '+(' | '.join(errs[:4]) or 'cause inconnue'))
    finally:
        try:del env
        except Exception:pass
        gc.collect()

# Install exact dependency + Android-safe pipelines into the existing V33 handler.
core.build_model=build_model_exact
core.v31.render_asset=render_asset_android

if __name__=='__main__':
    con=core.dbcon();edges=con.execute('SELECT count(*) FROM bundle_dependencies_v33').fetchone()[0];con.close()
    url=f'http://127.0.0.1:{core.PORT}/lab/lastwar-global-graphics-viewer-v33.html'
    print('=== WFGG LAST WAR GLOBAL GRAPHICS V33 — EXACT DEPENDENCIES + ANDROID CODEC ===',flush=True)
    print('V33_EXACT_DEP_EDGES',edges,flush=True)
    print(url,flush=True)
    ThreadingHTTPServer(('127.0.0.1',core.PORT),core.Handler).serve_forever()
