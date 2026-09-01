#!/usr/bin/env python3
from __future__ import annotations

from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs
import importlib.util, json, os, re, sqlite3, subprocess, sys

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv)>1 else Path(__file__).resolve().parents[1]
PORT = int(os.environ.get('WFGG_LAB_PORT','8788'))
V31_SERVER = ROOT/'scripts/lastwar-global-graphics-server-v31.py'
V31_VIEWER = ROOT/'frontend/lab/lastwar-global-graphics-viewer-v31.html'
ENRICH = ROOT/'scripts/lastwar-global-graphics-enrich-v32.py'

spec=importlib.util.spec_from_file_location('wfgg_v31_server',V31_SERVER)
v31=importlib.util.module_from_spec(spec); spec.loader.exec_module(v31)
DB=v31.DB


def has_v32():
    con=sqlite3.connect(DB)
    cols={r[1] for r in con.execute('pragma table_info(assets)')}
    tables={r[0] for r in con.execute("select name from sqlite_master where type='table'")}
    con.close()
    return 'graphic_class' in cols and 'event_asset_links_v32' in tables

if not has_v32():
    print('Enrichissement V32 absent. Construction...',flush=True)
    subprocess.run([sys.executable,str(ENRICH),str(ROOT)],check=True)


def dbcon():
    con=sqlite3.connect(DB); con.row_factory=sqlite3.Row; return con


def q1(qs,name,default=''):
    return (qs.get(name) or [default])[0]


def fts_expr(q): return v31.fts_expr(q)


def rowdict(row):
    if not row:return None
    d=dict(row)
    for src,dst,default in [('evidence_json','evidence','{}'),('graphic_evidence_json','graphic_evidence','[]')]:
        raw=d.pop(src,None)
        try:d[dst]=json.loads(raw or default)
        except Exception:d[dst]=json.loads(default)
    d.pop('search_text',None)
    return d


def event_links(con,sid):
    rows=con.execute('''
      SELECT l.event_id,r.event_name,r.kind,r.phase,r.category,r.cadence,l.relation,l.confidence,l.evidence_json
      FROM event_asset_links_v32 l LEFT JOIN event_registry_v32 r ON r.event_id=l.event_id
      WHERE l.stable_id=? ORDER BY l.confidence DESC,r.event_name
    ''',(sid,)).fetchall()
    out=[]
    for x in rows:
        d=dict(x)
        try:d['evidence']=json.loads(d.pop('evidence_json') or '{}')
        except Exception:d['evidence']={}
        out.append(d)
    return out


def search_assets(qs):
    q=q1(qs,'q').strip(); limit=max(1,min(250,int(q1(qs,'limit','100') or 100))); offset=max(0,int(q1(qs,'offset','0') or 0))
    conditions=[]; params=[]
    for key in ['family','subfamily','visual_role','context','tech_kind','scope_kind','scope_id','language','graphic_class']:
        val=q1(qs,key).strip()
        if val and val!='all': conditions.append('a.'+key+'=?'); params.append(val)
    mc=q1(qs,'min_confidence').strip()
    if mc:
        try: conditions.append('a.confidence>=?'); params.append(float(mc))
        except Exception: pass
    event_id=q1(qs,'event_id').strip(); relation=q1(qs,'event_relation').strip()
    if (event_id and event_id!='all') or (relation and relation!='all'):
        sub=['l.stable_id=a.stable_id']; subp=[]
        if event_id and event_id!='all': sub.append('l.event_id=?'); subp.append(event_id)
        if relation and relation!='all': sub.append('l.relation=?'); subp.append(relation)
        conditions.append('EXISTS (SELECT 1 FROM event_asset_links_v32 l WHERE '+' AND '.join(sub)+')'); params+=subp

    con=dbcon(); fts=fts_expr(q)
    if fts:
        sql='SELECT a.* FROM asset_fts f JOIN assets a ON a.stable_id=f.stable_id WHERE asset_fts MATCH ?'
        p=[fts]
        if conditions: sql+=' AND '+' AND '.join(conditions); p+=params
        sql+=' ORDER BY a.confidence DESC,a.row_no LIMIT ? OFFSET ?'; p += [limit,offset]
        try: rows=con.execute(sql,p).fetchall()
        except sqlite3.OperationalError:
            conditions2=list(conditions)+['lower(a.search_text) LIKE ?']; p2=params+['%'+q.lower()+'%']
            rows=con.execute('SELECT a.* FROM assets a WHERE '+' AND '.join(conditions2)+' ORDER BY a.confidence DESC,a.row_no LIMIT ? OFFSET ?',p2+[limit,offset]).fetchall()
    else:
        sql='SELECT a.* FROM assets a'
        if conditions:sql+=' WHERE '+' AND '.join(conditions)
        sql+=' ORDER BY a.row_no LIMIT ? OFFSET ?'
        rows=con.execute(sql,params+[limit,offset]).fetchall()
    out=[]
    for r in rows:
        d=rowdict(r); d['event_links']=event_links(con,d['stable_id']); out.append(d)
    con.close(); return out


def get_asset(sid):
    con=dbcon(); row=con.execute('SELECT * FROM assets WHERE stable_id=?',(sid,)).fetchone(); d=rowdict(row)
    if d:d['event_links']=event_links(con,sid)
    con.close(); return d


def facets_v32():
    con=dbcon(); rows=con.execute('SELECT axis,value,count FROM facets ORDER BY axis,count DESC').fetchall()
    names={r['event_id']:r['event_name'] for r in con.execute('SELECT event_id,event_name FROM event_registry_v32')}
    out={}
    for r in rows:
        item={'value':r['value'],'count':r['count']}
        if r['axis']=='event_id':item['label']=names.get(r['value'],r['value'])
        elif r['axis']=='event_relation':item['label']={'belongs-to':'Appartient à','used-by':'Utilisé par','candidate':'Candidat'}.get(r['value'],r['value'])
        else:item['label']=r['value']
        out.setdefault(r['axis'],[]).append(item)
    con.close(); return out


def viewer_v32():
    h=V31_VIEWER.read_text('utf-8')
    h=h.replace('Catalogue graphique global — V31','Catalogue graphique global — V32')
    h=h.replace('GLOBAL GRAPHICS V31','GLOBAL GRAPHICS V32')
    h=h.replace("const API='/api/v31'","const API='/api/v32'")
    extra='''<label>Graphique ?<select id="graphic_class"><option value="all">Tous</option></select></label>\n<label>Événement<select id="event_id"><option value="all">Tous</option></select></label>\n<label>Lien événement<select id="event_relation"><option value="all">Tous</option></select></label>\n'''
    if 'id="graphic_class"' not in h:
        h=h.replace('<label>Confiance<select id="min_confidence">',extra+'<label>Confiance<select id="min_confidence">')
    h=re.sub(r"const axes=\[[^;]+\];", "const axes=['family','visual_role','context','scope_kind','scope_id','tech_kind','graphic_class','event_id','event_relation'];", h, count=1)
    h=h.replace("['q','family','visual_role','context','scope_kind','scope_id','tech_kind','min_confidence']","['q','family','visual_role','context','scope_kind','scope_id','tech_kind','graphic_class','event_id','event_relation','min_confidence']")
    h=h.replace('o.textContent=`${x.value} (${x.count})`','o.textContent=`${x.label||x.value} (${x.count})`')
    h=h.replace("${kv('Technique',a.tech_kind)}", "${kv('Technique',a.tech_kind)}${kv('Graphique ?',a.graphic_class)}")
    h=h.replace("${kv('Périmètre',a.scope_name||a.scope_kind)}", "${kv('Périmètre',a.scope_name||a.scope_kind)}${kv('Événement',(a.event_links||[]).map(x=>x.event_name+' ['+x.relation+']').join(' · '))}")
    return h.encode('utf-8')


class Handler(v31.Handler):
    def do_GET(self):
        u=urlparse(self.path)
        if u.path=='/lab/lastwar-global-graphics-viewer-v32.html':
            raw=viewer_v32(); self.send_response(200); self.send_header('Content-Type','text/html; charset=utf-8'); self.send_header('Content-Length',str(len(raw))); self.send_header('Cache-Control','no-store'); self.end_headers(); self.wfile.write(raw); return
        if not u.path.startswith('/api/v32/'): return super().do_GET()
        qs=parse_qs(u.query)
        try:
            if u.path=='/api/v32/status':
                con=dbcon(); n=con.execute('select count(*) from assets').fetchone()[0]; eg=con.execute('select count(distinct stable_id) from event_asset_links_v32').fetchone()[0]; con.close()
                return self.send_json({'ok':True,'schemaVersion':32,'assets':n,'eventLinkedAssets':eg,'db':str(DB)})
            if u.path=='/api/v32/facets': return self.send_json({'facets':facets_v32(),'taxonomy':v31.TAX})
            if u.path=='/api/v32/search': return self.send_json({'items':search_assets(qs)})
            if u.path=='/api/v32/asset':
                a=get_asset(q1(qs,'id')); return self.send_json({'asset':a},200 if a else 404)
            if u.path=='/api/v32/render':
                a=get_asset(q1(qs,'id'))
                if not a:return self.send_json({'error':'asset-not-found'},404)
                try:p,meta=v31.render_asset(a)
                except Exception as e:return self.send_json({'error':'render-failed','message':str(e),'asset':a},422)
                raw=p.read_bytes(); self.send_response(200); self.send_header('Content-Type','image/png'); self.send_header('Content-Length',str(len(raw))); self.send_header('X-WfGg-Render-Meta',json.dumps(meta,ensure_ascii=True,separators=(',',':'))[:4000]); self.send_header('Cache-Control','no-store'); self.end_headers(); self.wfile.write(raw); return
            if u.path=='/api/v32/prefetch':
                ids=[x for x in q1(qs,'ids').split(',') if x][:2]; out=[]
                for sid in ids:
                    a=get_asset(sid)
                    if not a:continue
                    try:_,meta=v31.render_asset(a);out.append({'id':sid,'ok':True,'meta':meta})
                    except Exception as e:out.append({'id':sid,'ok':False,'message':str(e)})
                return self.send_json({'items':out})
            return self.send_json({'error':'unknown-endpoint'},404)
        except Exception as e:return self.send_json({'error':'server-error','message':str(e)},500)

if __name__=='__main__':
    url=f'http://127.0.0.1:{PORT}/lab/lastwar-global-graphics-viewer-v32.html'
    print('=== WFGG LAST WAR GLOBAL GRAPHICS V32 ===',flush=True); print(url,flush=True)
    ThreadingHTTPServer(('127.0.0.1',PORT),Handler).serve_forever()
