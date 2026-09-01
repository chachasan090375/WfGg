#!/usr/bin/env python3
from __future__ import annotations

from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs, quote
import gc, importlib.util, json, mimetypes, os, re, shutil, sqlite3, subprocess, sys

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv)>1 else Path(__file__).resolve().parents[1]
PORT = int(os.environ.get('WFGG_LAB_PORT','8788'))
V32_SERVER = ROOT/'scripts/lastwar-global-graphics-server-v32.py'
ENRICH33 = ROOT/'scripts/lastwar-global-graphics-enrich-v33.py'
CACHE = Path.home()/'.cache/wfgg-lastwar-v31'
MODEL_CACHE = CACHE/'models-v33'
MODEL_CACHE.mkdir(parents=True,exist_ok=True)

spec=importlib.util.spec_from_file_location('wfgg_v32_server',V32_SERVER)
v32=importlib.util.module_from_spec(spec);spec.loader.exec_module(v32)
v31=v32.v31
DB=v32.DB

MODEL_DIMENSIONS={'3D','Composant 3D','Mixte 2D/3D'}
MODEL_ROLES={'geometry','geometry-candidate','prefab','material','texture','shader','animation','component'}
MAX_ASSEMBLY_ASSETS=240
MAX_MODEL_BUNDLES=12
MAX_RENDERERS=16
MAX_MESHES=24
MAX_TEXTURES=64


def dbcon():
    con=sqlite3.connect(DB);con.row_factory=sqlite3.Row;return con


def has_v33():
    con=dbcon();cols={r[1] for r in con.execute('pragma table_info(assets)')};con.close()
    return {'dimension_class','model_role','asset_folder'}.issubset(cols)

if not has_v33():
    print('Enrichissement V33 absent. Construction...',flush=True)
    subprocess.run([sys.executable,str(ENRICH33),str(ROOT)],check=True)


def q1(qs,name,default=''):
    return (qs.get(name) or [default])[0]


def rowdict(row):
    if not row:return None
    d=dict(row)
    for src,dst,default in [
        ('evidence_json','evidence','{}'),
        ('graphic_evidence_json','graphic_evidence','[]'),
        ('dimension_evidence_json','dimension_evidence','[]')
    ]:
        raw=d.pop(src,None)
        try:d[dst]=json.loads(raw or default)
        except Exception:d[dst]=json.loads(default)
    d.pop('search_text',None)
    return d


def event_links(con,sid):
    return v32.event_links(con,sid)


def search_assets(qs):
    q=q1(qs,'q').strip();limit=max(1,min(250,int(q1(qs,'limit','100') or 100)));offset=max(0,int(q1(qs,'offset','0') or 0))
    conditions=[];params=[]
    for key in ['family','subfamily','visual_role','context','tech_kind','scope_kind','scope_id','language','graphic_class','dimension_class','model_role']:
        val=q1(qs,key).strip()
        if val and val!='all':conditions.append('a.'+key+'=?');params.append(val)
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

    con=dbcon();fts=v31.fts_expr(q)
    if fts:
        sql='SELECT a.* FROM asset_fts f JOIN assets a ON a.stable_id=f.stable_id WHERE asset_fts MATCH ?';p=[fts]
        if conditions:sql+=' AND '+' AND '.join(conditions);p+=params
        sql+=' ORDER BY a.confidence DESC,a.row_no LIMIT ? OFFSET ?';p += [limit,offset]
        try:rows=con.execute(sql,p).fetchall()
        except sqlite3.OperationalError:
            c2=list(conditions)+['lower(a.search_text) LIKE ?'];p2=params+['%'+q.lower()+'%']
            rows=con.execute('SELECT a.* FROM assets a WHERE '+' AND '.join(c2)+' ORDER BY a.confidence DESC,a.row_no LIMIT ? OFFSET ?',p2+[limit,offset]).fetchall()
    else:
        sql='SELECT a.* FROM assets a'
        if conditions:sql+=' WHERE '+' AND '.join(conditions)
        sql+=' ORDER BY a.row_no LIMIT ? OFFSET ?';rows=con.execute(sql,params+[limit,offset]).fetchall()
    out=[]
    for r in rows:
        d=rowdict(r);d['event_links']=event_links(con,d['stable_id']);out.append(d)
    con.close();return out


def get_asset(sid):
    con=dbcon();r=con.execute('SELECT * FROM assets WHERE stable_id=?',(sid,)).fetchone();d=rowdict(r)
    if d:d['event_links']=event_links(con,sid)
    con.close();return d


def facets_v33():
    con=dbcon();rows=con.execute('SELECT axis,value,count FROM facets ORDER BY axis,count DESC').fetchall()
    names={r['event_id']:r['event_name'] for r in con.execute('SELECT event_id,event_name FROM event_registry_v32')}
    labels={
        'Graphique':'Oui — graphique','Composant graphique':'Composant graphique','Non graphique':'Non — non graphique','Indéterminé':'Indéterminé',
        '2D':'2D','3D':'3D — modèle/géométrie','Composant 3D':'3D — composant','Mixte 2D/3D':'Mixte 2D / 3D','Non visuel':'Non visuel'
    }
    out={}
    for r in rows:
        item={'value':r['value'],'count':r['count']}
        if r['axis']=='event_id':item['label']=names.get(r['value'],r['value'])
        elif r['axis']=='event_relation':item['label']={'belongs-to':'Appartient à','used-by':'Utilisé par','candidate':'Candidat'}.get(r['value'],r['value'])
        else:item['label']=labels.get(r['value'],r['value'])
        out.setdefault(r['axis'],[]).append(item)
    con.close();return out


def safe_name(s):
    s=re.sub(r'[^a-zA-Z0-9_.-]+','_',str(s or ''))
    return s[:100] or 'asset'


def target_terms(a):
    out=[]
    for k in ('asset_path','logical_name','alias_name','subject'):
        raw=str(a.get(k) or '').replace('\\','/').rsplit('/',1)[-1]
        raw=re.sub(r'\.(bundle|prefab|asset|mat|png|jpg|jpeg|tga|dds|fbx|obj)$','',raw,flags=re.I).lower()
        if raw:out.append(raw)
    return list(dict.fromkeys(out))


def score_name(name,terms):
    n=(name or '').lower();score=0
    for t in terms:
        if n==t:score=max(score,100)
        elif n and (n in t or t in n):score=max(score,75)
        else:
            nw=set(re.findall(r'[a-z0-9]+',n));tw=set(re.findall(r'[a-z0-9]+',t));score=max(score,10*len(nw&tw))
    return score


def assembly_assets(a):
    con=dbcon();folder=str(a.get('asset_folder') or '')
    order="CASE model_role WHEN 'geometry' THEN 0 WHEN 'geometry-candidate' THEN 1 WHEN 'prefab' THEN 2 WHEN 'material' THEN 3 WHEN 'texture' THEN 4 WHEN 'shader' THEN 5 WHEN 'animation' THEN 6 ELSE 7 END"
    if folder:
        rows=con.execute(f'SELECT * FROM assets WHERE asset_folder=? ORDER BY {order},confidence DESC,row_no LIMIT ?',(folder,MAX_ASSEMBLY_ASSETS)).fetchall()
    else:
        rows=con.execute(f'SELECT * FROM assets WHERE bundle_id=? ORDER BY {order},confidence DESC,row_no LIMIT ?',(a.get('bundle_id'),MAX_ASSEMBLY_ASSETS)).fetchall()
    con.close();items=[rowdict(r) for r in rows]
    if not any(x['stable_id']==a['stable_id'] for x in items):items.insert(0,a)
    relevant=[x for x in items if x.get('model_role') in MODEL_ROLES or x.get('dimension_class') in MODEL_DIMENSIONS or x['stable_id']==a['stable_id']]
    return relevant or [a]


def choose_bundles(a,components):
    ordered=[];seen=set()
    for x in [a]+components:
        try:bid=int(x.get('bundle_id'))
        except Exception:continue
        if bid in seen:continue
        seen.add(bid);ordered.append(x)
        if len(ordered)>=MAX_MODEL_BUNDLES:break
    return ordered


def object_name(obj):
    try:
        n=obj.peek_name()
        if n:return str(n)
    except Exception:pass
    try:return str(getattr(obj.read(),'m_Name','') or '')
    except Exception:return ''


def export_bundle_objects(UnityPy,bundle,outdir,bi,terms,exported,errors):
    env=None
    try:
        env=UnityPy.load(str(bundle))
        renderers=[];meshes=[];textures=[]
        for obj in env.objects:
            typ=getattr(obj.type,'name',str(obj.type))
            if typ not in {'Renderer','MeshRenderer','SkinnedMeshRenderer','Mesh','Texture2D','Sprite'}:continue
            name=object_name(obj);score=score_name(name,terms);rec=(score,name,typ,obj)
            if typ in {'Renderer','MeshRenderer','SkinnedMeshRenderer'}:renderers.append(rec)
            elif typ=='Mesh':meshes.append(rec)
            else:textures.append(rec)
        renderers.sort(key=lambda x:(x[0],len(x[1])),reverse=True);meshes.sort(key=lambda x:(x[0],len(x[1])),reverse=True);textures.sort(key=lambda x:(x[0],len(x[1])),reverse=True)

        for oi,(score,name,typ,obj) in enumerate(renderers[:MAX_RENDERERS]):
            try:
                data=obj.read();dest=outdir/f'renderer-b{bi}-{oi}-{safe_name(name or typ)}';dest.mkdir(parents=True,exist_ok=True)
                data.export(str(dest));exported.append({'type':typ,'name':name,'score':score,'sourceBundle':bundle.name,'mode':'renderer-export'})
            except Exception as e:errors.append(f'{typ}:{name}: {e}')

        for oi,(score,name,typ,obj) in enumerate(meshes[:MAX_MESHES]):
            try:
                data=obj.read();txt=data.export();fp=outdir/f'mesh-b{bi}-{oi}-{safe_name(name or "mesh")}.obj';fp.write_text(txt,encoding='utf-8',newline='')
                exported.append({'type':'Mesh','name':name,'score':score,'sourceBundle':bundle.name,'mode':'mesh-export'})
            except Exception as e:errors.append(f'Mesh:{name}: {e}')

        texdir=outdir/'textures';texdir.mkdir(exist_ok=True)
        for oi,(score,name,typ,obj) in enumerate(textures[:MAX_TEXTURES]):
            try:
                data=obj.read();image=getattr(data,'image',None)
                if image is None:continue
                fp=texdir/f'b{bi}-{oi}-{safe_name(name or typ)}.png';image.save(fp)
            except Exception:continue
        return True
    except Exception as e:
        errors.append('load '+bundle.name+': '+str(e));return False
    finally:
        try:del env
        except Exception:pass
        gc.collect()


def build_model(a):
    sid=a['stable_id'];outdir=MODEL_CACHE/sid;manifest_path=outdir/'manifest.json'
    if manifest_path.is_file():
        try:
            m=json.loads(manifest_path.read_text('utf-8'))
            if m.get('schemaVersion')==33 and m.get('objects'):return m
        except Exception:pass
    if outdir.exists():shutil.rmtree(outdir,ignore_errors=True)
    outdir.mkdir(parents=True,exist_ok=True)
    components=assembly_assets(a);bundle_assets=choose_bundles(a,components)
    try:import UnityPy
    except Exception as e:raise RuntimeError('UnityPy indisponible : '+str(e))

    terms=target_terms(a);exported=[];errors=[];bundle_ids=[];bundle_sources=[];loaded=0
    # Materialize -> decode -> export immediately. The V31 mobile bundle cache intentionally
    # keeps only a tiny LRU, so V33 never assumes 12 materialized bundle files coexist.
    for bi,x in enumerate(bundle_assets):
        bundle_ids.append(x.get('bundle_id'))
        try:p,source=v31.materialize_bundle(x)
        except Exception as e:
            bundle_sources.append('error:'+str(e));continue
        bundle_sources.append(source)
        if export_bundle_objects(UnityPy,p,outdir,bi,terms,exported,errors):loaded+=1
    if not loaded:raise RuntimeError('Aucun bundle du modèle n’est matérialisable/décodable sur le téléphone')

    files=[]
    for fp in sorted(outdir.rglob('*')):
        if not fp.is_file() or fp.name=='manifest.json':continue
        rel=fp.relative_to(outdir).as_posix();ext=fp.suffix.lower()
        if ext not in {'.obj','.mtl','.png','.jpg','.jpeg','.webp'}:continue
        files.append({'path':rel,'kind':ext.lstrip('.'),'bytes':fp.stat().st_size,'url':'/api/v33/model-file?id='+quote(sid)+'&file='+quote(rel,safe='/')})
    objects=[f for f in files if f['kind']=='obj']
    if not objects:raise RuntimeError('Aucune géométrie OBJ décodable dans les bundles assemblés')
    m={
        'schemaVersion':33,'stableId':sid,'dimensionClass':a.get('dimension_class'),'assetFolder':a.get('asset_folder') or '',
        'assemblyAssetCount':len(components),'assemblyAssets':[{'id':x['stable_id'],'role':x.get('model_role'),'tech':x.get('tech_kind'),'path':x.get('asset_path')} for x in components],
        'bundleIds':bundle_ids,'bundleSources':bundle_sources,'exportedObjects':exported,'objects':objects,'files':files,'errors':errors[:80],
        'policy':'selected asset + compatible assets from the same logical subfolder; bundles are streamed through the mobile cache; real Unity Renderer/Mesh/Texture exports only'
    }
    manifest_path.write_text(json.dumps(m,ensure_ascii=False,indent=2),'utf-8')
    return m


def model_file(sid,rel):
    if not re.fullmatch(r'LWGA-[A-Z0-9]+',sid or ''):return None
    base=(MODEL_CACHE/sid).resolve();p=(base/rel).resolve()
    try:p.relative_to(base)
    except Exception:return None
    return p if p.is_file() else None


class Handler(v32.Handler):
    def do_GET(self):
        u=urlparse(self.path)
        if not u.path.startswith('/api/v33/'):return super().do_GET()
        qs=parse_qs(u.query)
        try:
            if u.path=='/api/v33/status':
                con=dbcon();n=con.execute('select count(*) from assets').fetchone()[0];dims=dict(con.execute('select dimension_class,count(*) from assets group by dimension_class'));linked=con.execute('select count(distinct stable_id) from event_asset_links_v32').fetchone()[0];con.close()
                return self.send_json({'ok':True,'schemaVersion':33,'assets':n,'dimensions':dims,'eventLinkedAssets':linked,'db':str(DB)})
            if u.path=='/api/v33/facets':return self.send_json({'facets':facets_v33(),'taxonomy':v31.TAX})
            if u.path=='/api/v33/search':return self.send_json({'items':search_assets(qs)})
            if u.path=='/api/v33/asset':
                a=get_asset(q1(qs,'id'));return self.send_json({'asset':a},200 if a else 404)
            if u.path=='/api/v33/render':
                a=get_asset(q1(qs,'id'))
                if not a:return self.send_json({'error':'asset-not-found'},404)
                try:p,meta=v31.render_asset(a)
                except Exception as e:return self.send_json({'error':'render-failed','message':str(e),'asset':a},422)
                raw=p.read_bytes();self.send_response(200);self.send_header('Content-Type','image/png');self.send_header('Content-Length',str(len(raw)));self.send_header('X-WfGg-Render-Meta',json.dumps(meta,ensure_ascii=True,separators=(',',':'))[:4000]);self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(raw);return
            if u.path=='/api/v33/model':
                a=get_asset(q1(qs,'id'))
                if not a:return self.send_json({'error':'asset-not-found'},404)
                if a.get('dimension_class') not in MODEL_DIMENSIONS and a.get('model_role') not in MODEL_ROLES:
                    return self.send_json({'error':'not-3d','message':'Asset non classé comme modèle/composant 3D','asset':a},422)
                try:m=build_model(a)
                except Exception as e:return self.send_json({'error':'model-build-failed','message':str(e),'asset':a},422)
                return self.send_json({'model':m})
            if u.path=='/api/v33/model-file':
                p=model_file(q1(qs,'id'),q1(qs,'file'))
                if not p:return self.send_json({'error':'model-file-not-found'},404)
                raw=p.read_bytes();ctype=mimetypes.guess_type(p.name)[0] or 'application/octet-stream';self.send_response(200);self.send_header('Content-Type',ctype);self.send_header('Content-Length',str(len(raw)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(raw);return
            if u.path=='/api/v33/prefetch':
                ids=[x for x in q1(qs,'ids').split(',') if x][:2];out=[]
                for sid in ids:
                    a=get_asset(sid)
                    if not a:continue
                    if a.get('dimension_class') in MODEL_DIMENSIONS:
                        out.append({'id':sid,'ok':True,'mode':'3d-deferred'});continue
                    try:_,meta=v31.render_asset(a);out.append({'id':sid,'ok':True,'mode':'2d','meta':meta})
                    except Exception as e:out.append({'id':sid,'ok':False,'message':str(e)})
                return self.send_json({'items':out})
            return self.send_json({'error':'unknown-endpoint'},404)
        except Exception as e:return self.send_json({'error':'server-error','message':str(e)},500)


if __name__=='__main__':
    url=f'http://127.0.0.1:{PORT}/lab/lastwar-global-graphics-viewer-v33.html'
    print('=== WFGG LAST WAR GLOBAL GRAPHICS V33 — 2D / 3D ===',flush=True);print(url,flush=True)
    ThreadingHTTPServer(('127.0.0.1',PORT),Handler).serve_forever()
