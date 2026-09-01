#!/usr/bin/env python3
from __future__ import annotations

"""V33 correlated mobile runtime.

Search pages are correlated to one logical query and raster/model rendering is correlated to the
selected catalogue row.  For 2D, the runtime now searches the exact selected Sprite/Texture2D in
the whole local dependency closure instead of decoding an arbitrary object from the same bundle.
When UnityPy cannot resolve a Sprite PPtr by itself, a conservative manual PathID/file resolver is
used before the LAB gives up.  A deeper exact-only closure is retried only for difficult assets.
"""

from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs
import gc, hashlib, importlib.util, json, re, sqlite3, sys

ROOT=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else Path(__file__).resolve().parents[1]
MOBILE=ROOT/'scripts/lastwar-global-graphics-server-v33-mobile.py'
VIEWER=ROOT/'frontend/lab/lastwar-global-graphics-viewer-v33.html'
PATCH_JS=ROOT/'frontend/lab/global-graphics-v33/search-correlation-v33.js'


def load_module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod

mobile=load_module('wfgg_v33_mobile_correlated',MOBILE)
core=mobile.core
u=mobile.u
exact=mobile.exact
BASE_MODEL=core.build_model


def norm(s):
    return re.sub(r'[^a-z0-9]+','',str(s or '').lower())


def tokens(s):
    return {x for x in re.findall(r'[a-z0-9]+',str(s or '').lower()) if len(x)>1}


def asset_terms(a):
    vals=[]
    for k in ('asset_path','logical_name','alias_name','subject'):
        raw=str(a.get(k) or '').replace('\\','/')
        tail=raw.rsplit('/',1)[-1]
        tail=re.sub(r'\.(bundle|prefab|asset|mat|material|shader|png|jpg|jpeg|tga|dds|psd|spriteatlas|fbx|obj|mesh)$','',tail,flags=re.I)
        if tail:vals.append(tail)
    return list(dict.fromkeys(vals))


def correlation(name,a,score=None):
    n=norm(name)
    if not n:return False,'empty-object-name'
    for term in asset_terms(a):
        t=norm(term)
        if not t:continue
        if n==t:return True,'exact-name'
        if min(len(n),len(t))>=5 and (n in t or t in n):return True,'substring-name'
        nt=tokens(name);tt=tokens(term);inter=nt&tt
        if len(inter)>=2 and len(inter)/max(1,min(len(nt),len(tt)))>=0.6:
            return True,'token-overlap'
    if score is not None and float(score)>=75:
        return True,'score>=75'
    return False,'none'


def _object_name(obj):
    try:
        n=obj.peek_name()
        if n:return str(n)
    except Exception:pass
    try:return str(getattr(obj.read(),'m_Name','') or '')
    except Exception:return ''


def _int_attr(obj,*names):
    for name in names:
        try:
            value=getattr(obj,name)
            if value is not None:return int(value)
        except Exception:pass
    return None


def _path_id(reader):
    return _int_attr(reader,'path_id','m_PathID')


def _file_key(reader):
    af=getattr(reader,'assets_file',None)
    vals=[]
    for name in ('name','path','file_name','m_Name'):
        try:
            v=getattr(af,name,None)
            if v:vals.append(str(v))
        except Exception:pass
    try:vals.append(str(af))
    except Exception:pass
    return norm(' '.join(vals))


def _external_key(sprite_reader,file_id):
    if not file_id or file_id<=0:return ''
    af=getattr(sprite_reader,'assets_file',None)
    externals=getattr(af,'externals',None) or getattr(af,'m_Externals',None) or []
    try:ext=externals[file_id-1]
    except Exception:return ''
    vals=[]
    for name in ('path','name','m_PathName','file_name'):
        try:
            v=getattr(ext,name,None)
            if v:vals.append(str(v))
        except Exception:pass
    return norm(' '.join(vals))


def _manual_ptr_read(ptr,sprite_reader,texture_readers):
    """Resolve one unresolved Texture2D PPtr conservatively from PathID and source file.

    PathID is only trusted when the candidate is unique in the expected serialized file.  We never
    pick the first Texture2D with the same integer from another file because PathIDs can collide.
    """
    pid=_int_attr(ptr,'path_id','m_PathID')
    fid=_int_attr(ptr,'file_id','m_FileID') or 0
    if pid is None:return None,'no-path-id'
    matches=[r for r in texture_readers if _path_id(r)==pid]
    if not matches:return None,'path-id-not-found'

    source_af=getattr(sprite_reader,'assets_file',None)
    if fid==0:
        same=[r for r in matches if getattr(r,'assets_file',None) is source_af]
        if len(same)==1:matches=same
        elif len(same)>1:return None,'same-file-path-id-ambiguous'
    else:
        ext=_external_key(sprite_reader,fid)
        if ext:
            by_file=[r for r in matches if ext in _file_key(r) or _file_key(r) in ext]
            if len(by_file)==1:matches=by_file
            elif len(by_file)>1:return None,'external-path-id-ambiguous'

    if len(matches)!=1:return None,'path-id-ambiguous-'+str(len(matches))
    try:
        tex=matches[0].read()
        if tex is not None and hasattr(tex,'m_Width'):return tex,'manual-pathid'
    except Exception:return None,'manual-read-failed'
    return None,'manual-not-texture'


def _sprite_texture(sprite,sprite_reader,texture_readers):
    rd=getattr(sprite,'m_RD',None) or getattr(sprite,'m_RenderData',None)
    if rd is None:return None,'no-render-data'
    errors=[]
    for key in ('texture','m_Texture','alphaTexture','m_AlphaTexture'):
        ptr=getattr(rd,key,None)
        if ptr is None:continue
        try:
            tex=ptr.read() if hasattr(ptr,'read') else ptr
            if tex is not None and hasattr(tex,'m_Width'):return tex,key+':unitypy'
        except Exception as exc:errors.append(key+':'+type(exc).__name__)
        tex,mode=_manual_ptr_read(ptr,sprite_reader,texture_readers)
        if tex is not None:return tex,key+':'+mode
        errors.append(key+':'+mode)
    return None,';'.join(errors[:6]) or 'no-texture-pointer'


def _correlation_rank(why,score,typ,a):
    base={'exact-name':500,'substring-name':400,'token-overlap':300,'score>=75':200}.get(why,0)
    tech=str(a.get('tech_kind') or '').lower()
    role=str(a.get('visual_role') or '').lower()
    prefer_sprite=tech=='sprite' or 'sprite' in role
    if typ=='Sprite' and prefer_sprite:base+=40
    if typ=='Texture2D' and not prefer_sprite:base+=20
    return base+min(100,int(score or 0))


def _render_target_pass(a,deep=False):
    sid=a['stable_id']
    if deep:mobile._DEEP_RASTER_IDS.add(sid)
    env=None
    try:
        paths,sources=mobile.materialize_raster_closure(a)
        if not paths:raise RuntimeError('RUNTIME_NO_LOCAL_BUNDLE: aucune fermeture locale matérialisable')
        try:import UnityPy
        except Exception as exc:raise RuntimeError('RUNTIME_UNITYPY_MISSING: '+str(exc)) from exc
        env=UnityPy.load(*[str(p) for p in paths])
        terms=core.target_terms(a)
        texture_readers=[];candidates=[];observed=[]
        for obj in env.objects:
            typ=getattr(obj.type,'name',str(obj.type))
            if typ not in {'Sprite','Texture2D'}:continue
            if typ=='Texture2D':texture_readers.append(obj)
            name=_object_name(obj)
            score=core.score_name(name,terms)
            ok,why=correlation(name,a,score)
            observed.append((score,name,typ))
            if ok:candidates.append((_correlation_rank(why,score,typ,a),score,why,name,typ,obj))
        candidates.sort(key=lambda x:(x[0],x[1],len(x[3])),reverse=True)
        observed.sort(key=lambda x:(x[0],len(x[1])),reverse=True)
        if not candidates:
            top=', '.join((n or '<sans nom>')+':'+str(s) for s,n,_ in observed[:6])
            raise RuntimeError(
                'RUNTIME_TARGET_OBJECT_NOT_FOUND: asset='+sid+'; bundles='+str(len(paths))+
                '; cible='+('|'.join(asset_terms(a))[:240])+'; meilleurs='+top
            )

        errors=[]
        out=core.v31.RENDER_CACHE/(sid+'-target.png')
        for rank,score,why,name,typ,obj in candidates[:120]:
            try:
                if typ=='Texture2D':
                    tex=obj.read();img,fmt=u.codec.decode_texture2d(tex);resolver='direct-texture'
                else:
                    sprite=obj.read();tex,resolver=_sprite_texture(sprite,obj,texture_readers)
                    if tex is None:raise ValueError('Texture2D unresolved: '+resolver)
                    img,fmt=u.codec.decode_texture2d(tex);img=exact.crop_sprite(img,sprite)
                out.parent.mkdir(parents=True,exist_ok=True);img.save(out,'PNG')
                return out,{
                    'accepted':True,'stableId':sid,'objectName':name,'objectType':typ,'matchScore':score,
                    'correlation':why,'correlationRank':rank,'correlationPolicy':'target-object-first',
                    'textureFormat':fmt,'textureResolver':resolver,'closureMode':'deep' if deep else 'shallow',
                    'closureBundles':len(paths),'closureSources':sources[:12],
                }
            except Exception as exc:
                errors.append(typ+':'+name+':'+type(exc).__name__+':'+str(exc))
        raise RuntimeError(
            'RUNTIME_TARGET_OBJECT_UNRESOLVED: asset='+sid+'; correlated='+str(len(candidates))+
            '; bundles='+str(len(paths))+'; '+' | '.join(errors[:8])
        )
    finally:
        if deep:mobile._DEEP_RASTER_IDS.discard(sid)
        try:del env
        except Exception:pass
        gc.collect()


def _render_target_exact(a):
    sid=a['stable_id'];first=''
    try:return _render_target_pass(a,False)
    except RuntimeError as exc:first=str(exc)
    print('V33_TARGET_DEEP_RETRY',sid,'reason='+first.split(':',1)[0],flush=True)
    try:return _render_target_pass(a,True)
    except RuntimeError as deep_exc:
        raise RuntimeError(str(deep_exc)+' | shallow='+first[:600]) from deep_exc


def strict_render(a):
    sid=a['stable_id']
    png=core.v31.RENDER_CACHE/(sid+'-target.png')
    proof=core.v31.RENDER_CACHE/(sid+'-target-proof.json')
    if png.is_file() and proof.is_file():
        try:
            meta=json.loads(proof.read_text('utf-8'))
            if meta.get('accepted') and meta.get('stableId')==sid:return png,meta
        except Exception:pass
    try:png.unlink(missing_ok=True)
    except Exception:pass
    try:proof.unlink(missing_ok=True)
    except Exception:pass
    p,meta=_render_target_exact(a)
    try:proof.write_text(json.dumps(meta,ensure_ascii=False,separators=(',',':')),'utf-8')
    except Exception:pass
    return p,meta


def strict_model(a):
    m=BASE_MODEL(a)
    exported=m.get('exportedObjects') or []
    strong=[]
    for obj in exported:
        if str(obj.get('type') or '')!='Mesh':continue
        ok,why=correlation(obj.get('name',''),a,obj.get('score'))
        if ok:strong.append((obj,why))
    if not strong:
        direct_geometry=str(a.get('model_role') or '') in {'geometry','geometry-candidate'}
        b0=[x for x in (m.get('objects') or []) if re.search(r'(?:^|/)mesh-b0-',str(x.get('path') or ''))]
        if direct_geometry and b0:
            m=dict(m);m['objects']=b0;m['correlation']='selected-bundle-direct-geometry';return m
        raise RuntimeError('RUNTIME_3D_OBJECT_MISMATCH: aucun Mesh suffisamment corrélé à l’asset sélectionné')
    accepted=[]
    for obj,why in strong:
        safe=exact.safe(obj.get('name') or 'mesh')
        accepted.extend([x for x in (m.get('objects') or []) if str(x.get('path') or '').endswith('-'+safe+'.obj')])
    if accepted:
        seen=set();uniq=[]
        for x in accepted:
            p=x.get('path')
            if p in seen:continue
            seen.add(p);uniq.append(x)
        m=dict(m);m['objects']=uniq;m['correlation']='strong-mesh-name';m['correlatedMeshCount']=len(uniq)
    return m


core.v31.render_asset=strict_render
core.build_model=strict_model


def q1(qs,name,default=''):
    return (qs.get(name) or [default])[0]


def _query_parts(qs):
    q=q1(qs,'q').strip();conditions=[];params=[]
    for key in ['family','subfamily','visual_role','context','tech_kind','scope_kind','scope_id','language','graphic_class','dimension_class','model_role']:
        val=q1(qs,key).strip()
        if val and val!='all':conditions.append('a.'+key+'=?');params.append(val)
    rav=q1(qs,'render_availability').strip()
    if rav=='local-renderable':conditions.append("a.render_availability IN ('local-exact','local-resolved')")
    elif rav and rav!='all':conditions.append('a.render_availability=?');params.append(rav)
    mc=q1(qs,'min_confidence').strip()
    if mc:
        try:conditions.append('a.confidence>=?');params.append(float(mc))
        except Exception:pass
    event_id=q1(qs,'event_id').strip();relation=q1(qs,'event_relation').strip()
    if (event_id and event_id!='all') or (relation and relation!='all'):
        sub=['l.stable_id=a.stable_id'];subp=[]
        if event_id and event_id!='all':sub.append('l.event_id=?');subp.append(event_id)
        if relation and relation!='all':sub.append('l.relation=?');subp.append(relation)
        conditions.append('EXISTS (SELECT 1 FROM event_asset_links_v32 l WHERE '+' AND '.join(sub)+')');params+=subp
    return q,conditions,params


def query_token(qs):
    ignored={'offset','limit'};parts=[]
    for key in sorted(k for k in qs if k not in ignored):
        values=qs.get(key) or [''];parts.append(key+'='+'\x1f'.join(str(v) for v in values))
    return hashlib.sha1('&'.join(parts).encode('utf-8')).hexdigest()[:12]


def search_page(qs):
    q,conditions,params=_query_parts(qs)
    limit=max(1,min(120,int(q1(qs,'limit','60') or 60)));offset=max(0,int(q1(qs,'offset','0') or 0))
    con=core.dbcon();fts=core.v31.fts_expr(q);rows=[];total=0
    if fts:
        base=' FROM asset_fts f JOIN assets a ON a.stable_id=f.stable_id WHERE asset_fts MATCH ?';p=[fts]
        if conditions:base+=' AND '+' AND '.join(conditions);p+=params
        try:
            total=con.execute('SELECT count(*)'+base,p).fetchone()[0]
            rows=con.execute('SELECT a.*'+base+' ORDER BY a.confidence DESC,a.row_no LIMIT ? OFFSET ?',p+[limit,offset]).fetchall()
        except sqlite3.OperationalError:
            c=list(conditions)+['lower(a.search_text) LIKE ?'];pp=params+['%'+q.lower()+'%'];where=' WHERE '+' AND '.join(c)
            total=con.execute('SELECT count(*) FROM assets a'+where,pp).fetchone()[0]
            rows=con.execute('SELECT a.* FROM assets a'+where+' ORDER BY a.confidence DESC,a.row_no LIMIT ? OFFSET ?',pp+[limit,offset]).fetchall()
    else:
        where=(' WHERE '+' AND '.join(conditions)) if conditions else ''
        total=con.execute('SELECT count(*) FROM assets a'+where,params).fetchone()[0]
        rows=con.execute('SELECT a.* FROM assets a'+where+' ORDER BY a.row_no LIMIT ? OFFSET ?',params+[limit,offset]).fetchall()
    out=[]
    for r in rows:
        d=core.rowdict(r);d['event_links']=core.event_links(con,d['stable_id']);out.append(d)
    con.close();token=query_token(qs)
    return {'items':out,'total':total,'offset':offset,'limit':limit,'hasMore':offset+len(out)<total,'queryToken':token}


assert query_token({'family':['vehicles'],'offset':['0'],'limit':['120']}) == query_token({'family':['vehicles'],'offset':['120'],'limit':['120']})
assert query_token({'family':['vehicles'],'offset':['0']}) != query_token({'family':['ui'],'offset':['0']})


class CorrelatedHandler(mobile.MobileLabHandler):
    def do_GET(self):
        u=urlparse(self.path)
        if u.path=='/api/v33/search':
            try:return self.send_json(search_page(parse_qs(u.query)))
            except Exception as e:return self.send_json({'error':'search-failed','message':str(e)},500)
        if u.path=='/lab/lastwar-global-graphics-viewer-v33.html':
            raw=VIEWER.read_text('utf-8');tag='<script src="./global-graphics-v33/search-correlation-v33.js"></script>'
            if 'search-correlation-v33.js' not in raw:raw=raw.replace('</body>',tag+'</body>')
            data=raw.encode('utf-8')
            self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(data)));self.send_header('Cache-Control','no-store, no-cache, must-revalidate, max-age=0');self.end_headers();self.wfile.write(data);return
        return super().do_GET()


if __name__=='__main__':
    print('=== WFGG LAST WAR GLOBAL GRAPHICS V33 — EXACT TARGET RASTER ===',flush=True)
    print('V33_SEARCH paging=ON pageSize<=120 query-token=STABLE-ACROSS-PAGES',flush=True)
    print('V33_RASTER target-object-first=ON whole-closure-scan=ON arbitrary-bundle-object=REJECTED',flush=True)
    print('V33_SPRITE_PTR unitypy+manual-pathid-resolver=ON deep-exact-retry=ON',flush=True)
    print('V33_3D_CORRELATION unrelated-meshes=REJECTED',flush=True)
    print(f'http://127.0.0.1:{core.PORT}/lab/lastwar-global-graphics-viewer-v33.html',flush=True)
    ThreadingHTTPServer(('127.0.0.1',core.PORT),CorrelatedHandler).serve_forever()
