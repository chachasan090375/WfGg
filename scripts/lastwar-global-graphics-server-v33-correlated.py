#!/usr/bin/env python3
from __future__ import annotations

"""V33 correlated mobile runtime.

Fixes two user-visible problems:
1. Search/result correlation: every search has its own paged result set and the local-renderable
   filter is enforced server-side. Previous/next can traverse beyond the first 100 rows.
2. Render/object correlation: a selected catalogue row is never allowed to display an arbitrary
   Sprite/Texture2D from the same bundle. A real decoded object must strongly match the selected
   asset identity/name, otherwise the LAB reports a correlation error instead of a misleading image.

The same principle is applied to 3D: manifests containing only unrelated meshes are rejected.
"""

from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs
import hashlib, importlib.util, json, re, sqlite3, sys

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
BASE_RENDER=core.v31.render_asset
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
    best='none'
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
    return False,best


def strict_render(a):
    sid=a['stable_id']
    png=core.v31.RENDER_CACHE/(sid+'-unified.png')
    proof=core.v31.RENDER_CACHE/(sid+'-correlation.json')
    if png.is_file() and proof.is_file():
        try:
            meta=json.loads(proof.read_text('utf-8'))
            if meta.get('accepted') and meta.get('stableId')==sid:
                return png,meta
        except Exception:pass
    # Old V33 caches had no proof and may contain an arbitrary decodable object from a bundle.
    try:png.unlink(missing_ok=True)
    except Exception:pass
    try:proof.unlink(missing_ok=True)
    except Exception:pass
    p,meta=BASE_RENDER(a)
    ok,why=correlation(meta.get('objectName',''),a,meta.get('matchScore'))
    if not ok:
        try:Path(p).unlink(missing_ok=True)
        except Exception:pass
        raise RuntimeError(
            'RUNTIME_ASSET_OBJECT_MISMATCH: asset='+sid+
            '; objet='+str(meta.get('objectName') or 'sans-nom')+
            '; score='+str(meta.get('matchScore'))+
            '; le LAB refuse d’afficher une image décodable mais non corrélée à la ligne sélectionnée'
        )
    meta=dict(meta);meta.update({'accepted':True,'stableId':sid,'correlation':why,'correlationPolicy':'exact/substring/token>=60%/score>=75'})
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
        # A direct geometry row may legitimately use a generic mesh name; only accept geometry
        # from the selected bundle slot b0 in that narrow case.
        direct_geometry=str(a.get('model_role') or '') in {'geometry','geometry-candidate'}
        b0=[x for x in (m.get('objects') or []) if re.search(r'(?:^|/)mesh-b0-',str(x.get('path') or ''))]
        if direct_geometry and b0:
            m=dict(m);m['objects']=b0;m['correlation']='selected-bundle-direct-geometry';return m
        raise RuntimeError(
            'RUNTIME_3D_OBJECT_MISMATCH: des meshes ont été extraits, mais aucun n’est suffisamment corrélé à l’asset sélectionné; rendu 3D arbitraire refusé'
        )
    # Keep only OBJ files whose safe mesh name corresponds to one of the accepted mesh names.
    accepted=[]
    for obj,why in strong:
        s=exact.safe(obj.get('name') or 'mesh')
        accepted.extend([x for x in (m.get('objects') or []) if str(x.get('path') or '').endswith('-'+s+'.obj')])
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
    if rav=='local-renderable':
        conditions.append("a.render_availability IN ('local-exact','local-resolved')")
    elif rav and rav!='all':
        conditions.append('a.render_availability=?');params.append(rav)
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


def search_page(qs):
    q,conditions,params=_query_parts(qs)
    limit=max(1,min(120,int(q1(qs,'limit','60') or 60)));offset=max(0,int(q1(qs,'offset','0') or 0))
    con=core.dbcon();fts=core.v31.fts_expr(q)
    rows=[];total=0
    if fts:
        base=' FROM asset_fts f JOIN assets a ON a.stable_id=f.stable_id WHERE asset_fts MATCH ?'
        p=[fts]
        if conditions:base+=' AND '+' AND '.join(conditions);p+=params
        try:
            total=con.execute('SELECT count(*)'+base,p).fetchone()[0]
            rows=con.execute('SELECT a.*'+base+' ORDER BY a.confidence DESC,a.row_no LIMIT ? OFFSET ?',p+[limit,offset]).fetchall()
        except sqlite3.OperationalError:
            c=list(conditions)+['lower(a.search_text) LIKE ?'];pp=params+['%'+q.lower()+'%']
            where=' WHERE '+' AND '.join(c)
            total=con.execute('SELECT count(*) FROM assets a'+where,pp).fetchone()[0]
            rows=con.execute('SELECT a.* FROM assets a'+where+' ORDER BY a.confidence DESC,a.row_no LIMIT ? OFFSET ?',pp+[limit,offset]).fetchall()
    else:
        where=(' WHERE '+' AND '.join(conditions)) if conditions else ''
        total=con.execute('SELECT count(*) FROM assets a'+where,params).fetchone()[0]
        rows=con.execute('SELECT a.* FROM assets a'+where+' ORDER BY a.row_no LIMIT ? OFFSET ?',params+[limit,offset]).fetchall()
    out=[]
    for r in rows:
        d=core.rowdict(r);d['event_links']=core.event_links(con,d['stable_id']);out.append(d)
    con.close()
    signature='&'.join(f'{k}={q1(qs,k)}' for k in sorted(qs))
    token=hashlib.sha1(signature.encode('utf-8')).hexdigest()[:12]
    return {'items':out,'total':total,'offset':offset,'limit':limit,'hasMore':offset+len(out)<total,'queryToken':token}


class CorrelatedHandler(mobile.MobileLabHandler):
    def do_GET(self):
        u=urlparse(self.path)
        if u.path=='/api/v33/search':
            try:return self.send_json(search_page(parse_qs(u.query)))
            except Exception as e:return self.send_json({'error':'search-failed','message':str(e)},500)
        if u.path=='/lab/lastwar-global-graphics-viewer-v33.html':
            raw=VIEWER.read_text('utf-8')
            tag='<script src="./global-graphics-v33/search-correlation-v33.js"></script>'
            if 'search-correlation-v33.js' not in raw:raw=raw.replace('</body>',tag+'</body>')
            data=raw.encode('utf-8')
            self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(data)));self.send_header('Cache-Control','no-store, no-cache, must-revalidate, max-age=0');self.end_headers();self.wfile.write(data);return
        return super().do_GET()


if __name__=='__main__':
    print('=== WFGG LAST WAR GLOBAL GRAPHICS V33 — SEARCH / RENDER CORRELATED ===',flush=True)
    print('V33_SEARCH paging=ON pageSize<=120 local-renderable=SERVER-SIDE query-token=ON',flush=True)
    print('V33_RENDER_CORRELATION arbitrary-bundle-object=REJECTED strong-match=REQUIRED',flush=True)
    print('V33_3D_CORRELATION unrelated-meshes=REJECTED',flush=True)
    print(f'http://127.0.0.1:{core.PORT}/lab/lastwar-global-graphics-viewer-v33.html',flush=True)
    ThreadingHTTPServer(('127.0.0.1',core.PORT),CorrelatedHandler).serve_forever()
