#!/usr/bin/env python3
from __future__ import annotations

from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from collections import OrderedDict
import gc, json, mimetypes, os, re, sqlite3, subprocess, sys, zipfile

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
PORT = int(os.environ.get('WFGG_LAB_PORT','8788'))
CACHE = Path.home() / '.cache/wfgg-lastwar-v31'
DB = CACHE / 'graphics-catalog-v31.sqlite3'
BUNDLE_CACHE = CACHE / 'bundles'
RENDER_CACHE = CACHE / 'renders'
TAXONOMY = ROOT / 'frontend/lab/global-graphics-v31/taxonomy-v31.json'
FRONTEND = ROOT / 'frontend'
for p in [CACHE,BUNDLE_CACHE,RENDER_CACHE]: p.mkdir(parents=True, exist_ok=True)

if not DB.is_file():
    print('Catalogue absent. Construction V31...', flush=True)
    subprocess.run([sys.executable, str(ROOT/'scripts/lastwar-global-graphics-catalog-v31.py'), str(ROOT)], check=True)

TAX = json.loads(TAXONOMY.read_text('utf-8'))
ALIASES = {re.sub(r'\s+',' ',k.lower()).strip():v for k,v in TAX.get('searchAliases',{}).items()}
BUNDLE_LRU = OrderedDict()
RENDER_LRU = OrderedDict()
MAX_BUNDLES = 3
MAX_RENDERS = 18
_fragment_index = None
_apk_index = None

FIELDS = [
 'stable_id','row_no','bundle_id','offset_bytes','span_bytes','fragment_entry','table_fragment','asset_path','logical_name','alias_name',
 'family','subfamily','subject','visual_role','context','tech_kind','state','variant','language','scope_kind','scope_id','scope_name','scope_period',
 'family_conf','role_conf','context_conf','scope_conf','confidence','evidence_json','search_text'
]


def dbcon():
    con=sqlite3.connect(DB); con.row_factory=sqlite3.Row; return con


def rowdict(row):
    if not row: return None
    d=dict(row)
    try: d['evidence']=json.loads(d.pop('evidence_json') or '{}')
    except Exception: d['evidence']={}
    d.pop('search_text',None)
    return d


def q1(qs,name,default=''):
    return (qs.get(name) or [default])[0]


def fts_expr(q):
    q=re.sub(r'[^a-zA-Z0-9À-ÿ_ -]+',' ',q).lower().strip()
    if not q: return ''
    groups=[q]+list(ALIASES.get(re.sub(r'\s+',' ',q),[]))
    outs=[]
    stop={'de','du','des','le','la','les','the','a','an','of','et','and'}
    for g in groups:
        toks=[t for t in re.findall(r'[a-z0-9]+',g.lower()) if len(t)>1 and t not in stop]
        if toks: outs.append(' AND '.join('"'+t+'"' for t in toks))
    return ' OR '.join('('+x+')' for x in outs)


def search_assets(qs):
    q=q1(qs,'q').strip(); limit=max(1,min(200,int(q1(qs,'limit','60') or 60))); offset=max(0,int(q1(qs,'offset','0') or 0))
    filters=[]; params=[]
    for key in ['family','subfamily','visual_role','context','tech_kind','scope_kind','scope_id','language']:
        val=q1(qs,key).strip()
        if val and val!='all': filters.append('a.'+key+'=?'); params.append(val)
    min_conf=q1(qs,'min_confidence').strip()
    if min_conf:
        try: filters.append('a.confidence>=?'); params.append(float(min_conf))
        except Exception: pass
    where=(' WHERE '+' AND '.join(filters)) if filters else ''
    con=dbcon(); fts=fts_expr(q)
    if fts:
        sql='SELECT a.* FROM asset_fts f JOIN assets a ON a.stable_id=f.stable_id WHERE asset_fts MATCH ?'
        p=[fts]
        if filters: sql+=' AND '+' AND '.join(filters); p+=params
        sql+=' ORDER BY a.confidence DESC,a.row_no LIMIT ? OFFSET ?'; p += [limit,offset]
        try: rows=con.execute(sql,p).fetchall()
        except sqlite3.OperationalError:
            like='%'+q.lower()+'%'; sql='SELECT a.* FROM assets a'+((' WHERE '+' AND '.join(filters)+' AND ') if filters else ' WHERE ')+'lower(a.search_text) LIKE ? ORDER BY confidence DESC,row_no LIMIT ? OFFSET ?'; rows=con.execute(sql,params+[like,limit,offset]).fetchall()
    else:
        rows=con.execute('SELECT a.* FROM assets a'+where+' ORDER BY row_no LIMIT ? OFFSET ?',params+[limit,offset]).fetchall()
    con.close(); return [rowdict(x) for x in rows]


def get_asset(sid):
    con=dbcon(); row=con.execute('SELECT * FROM assets WHERE stable_id=?',(sid,)).fetchone(); con.close(); return rowdict(row)


def facets():
    con=dbcon(); rows=con.execute('SELECT axis,value,count FROM facets ORDER BY axis,count DESC').fetchall(); con.close()
    out={}
    for r in rows: out.setdefault(r['axis'],[]).append({'value':r['value'],'count':r['count']})
    return out


def local_fragments():
    global _fragment_index
    if _fragment_index is not None: return _fragment_index
    roots=[ROOT,Path.home()/'.cache',Path.home()/'storage/downloads',Path.home()/'storage/shared/Download',Path('/sdcard/Download'),Path('/storage/emulated/0/Download')]
    idx={}; seen=set()
    for base in roots:
        if not base.exists(): continue
        try: key=str(base.resolve())
        except Exception: key=str(base)
        if key in seen: continue
        seen.add(key)
        try:
            for dp,dirs,files in os.walk(base):
                dirs[:] = [d for d in dirs if d not in {'.git','node_modules','bundles','renders'}]
                for fn in files:
                    low=fn.lower()
                    if low.startswith('bundlefragment') and low.endswith('.bytes') and low not in idx: idx[low]=Path(dp)/fn
        except (OSError,PermissionError): pass
    _fragment_index=idx
    print('V31_LOCAL_FRAGMENTS',len(idx),flush=True)
    return idx


def apk_paths():
    global _apk_index
    if _apk_index is not None: return _apk_index
    out=[]; cached=ROOT/'frontend/lab/master-assets-v2/meta/lastwar-installed-apk-paths-v1.txt'
    if cached.is_file():
        for line in cached.read_text('utf-8','replace').splitlines():
            p=line.strip().replace('package:','',1) if line.strip().startswith('package:') else line.strip()
            if p and Path(p).is_file() and p not in out: out.append(p)
    for cmd in (['pm','path','com.fun.lastwar.gp'],['cmd','package','path','com.fun.lastwar.gp']):
        try:
            cp=subprocess.run(cmd,capture_output=True,text=True,timeout=10)
            for line in (cp.stdout or '').splitlines():
                if line.startswith('package:'):
                    p=line.split(':',1)[1].strip()
                    if Path(p).is_file() and p not in out: out.append(p)
        except Exception: pass
    _apk_index=out; return out


def good_bundle(p):
    try: return p.is_file() and p.open('rb').read(16).startswith((b'UnityFS',b'UnityWeb',b'UnityRaw'))
    except Exception: return False


def trim_lru(cache,limit,delete_files=False):
    while len(cache)>limit:
        _,p=cache.popitem(last=False)
        if delete_files:
            try: Path(p).unlink(missing_ok=True)
            except Exception: pass


def materialize_bundle(a):
    bid=int(a.get('bundle_id') or -1); span=int(a.get('span_bytes') or -1); off=int(a.get('offset_bytes') or -1)
    if bid<0 or span<=0 or off<0: raise RuntimeError('Position physique du bundle absente de l’index')
    out=BUNDLE_CACHE/f'bundle-{bid}.bundle'
    if good_bundle(out) and out.stat().st_size==span:
        BUNDLE_LRU[bid]=str(out); BUNDLE_LRU.move_to_end(bid); trim_lru(BUNDLE_LRU,MAX_BUNDLES,True); return out,'cache'
    frag=(a.get('table_fragment') or '').split('/')[-1].lower()
    local=local_fragments().get(frag)
    if local and local.is_file():
        with local.open('rb') as f: f.seek(off); raw=f.read(span)
        if len(raw)==span and raw.startswith((b'UnityFS',b'UnityWeb',b'UnityRaw')):
            out.write_bytes(raw); BUNDLE_LRU[bid]=str(out); BUNDLE_LRU.move_to_end(bid); trim_lru(BUNDLE_LRU,MAX_BUNDLES,True); return out,'local:'+str(local)
    entry=(a.get('fragment_entry') or '').replace('\\','/')
    if entry:
        for apk in apk_paths():
            try:
                with zipfile.ZipFile(apk,'r') as z:
                    if entry not in z.namelist(): continue
                    with z.open(entry,'r') as f: f.seek(off); raw=f.read(span)
                if len(raw)==span and raw.startswith((b'UnityFS',b'UnityWeb',b'UnityRaw')):
                    out.write_bytes(raw); BUNDLE_LRU[bid]=str(out); BUNDLE_LRU.move_to_end(bid); trim_lru(BUNDLE_LRU,MAX_BUNDLES,True); return out,'apk:'+Path(apk).name
            except Exception: continue
    raise RuntimeError('Bundle non matérialisable : fragment local/APK introuvable ou inaccessible')


def target_terms(a):
    vals=[]
    for key in ['asset_path','alias_name','logical_name','subject']:
        raw=str(a.get(key) or '').replace('\\','/')
        tail=raw.rsplit('/',1)[-1]
        tail=re.sub(r'\.(bundle|png|jpg|jpeg|tga|psd|prefab|asset)$','',tail,flags=re.I)
        if tail: vals.append(tail.lower())
    return list(dict.fromkeys(vals))


def render_asset(a):
    sid=a['stable_id']; cached=RENDER_CACHE/(sid+'.png')
    if cached.is_file() and cached.stat().st_size>32:
        RENDER_LRU[sid]=str(cached); RENDER_LRU.move_to_end(sid); trim_lru(RENDER_LRU,MAX_RENDERS,True); return cached,{'source':'render-cache'}
    bundle,source=materialize_bundle(a)
    try: import UnityPy
    except Exception as e: raise RuntimeError('UnityPy indisponible dans Termux: '+str(e))
    env=None; candidates=[]; terms=target_terms(a)
    try:
        env=UnityPy.load(str(bundle))
        for obj in env.objects:
            typ=getattr(obj.type,'name',str(obj.type))
            if typ not in {'Sprite','Texture2D'}: continue
            try:
                data=obj.read(); name=str(getattr(data,'name','') or '').lower()
                score=0
                for t in terms:
                    if name==t: score=max(score,100)
                    elif name and (name in t or t in name): score=max(score,70)
                    else:
                        words=set(re.findall(r'[a-z0-9]+',t)); nw=set(re.findall(r'[a-z0-9]+',name)); score=max(score,10*len(words & nw))
                if typ=='Sprite': score+=5
                candidates.append((score,name,typ,data,obj))
            except Exception: continue
        if not candidates: raise RuntimeError('Aucun Sprite/Texture2D décodable dans ce bundle')
        candidates.sort(key=lambda x:(x[0],len(x[1])),reverse=True)
        last_error=None
        for score,name,typ,data,obj in candidates[:20]:
            try:
                image=getattr(data,'image',None)
                if image is None: continue
                image.save(cached)
                if cached.is_file() and cached.stat().st_size>32:
                    meta={'source':source,'objectName':name,'objectType':typ,'matchScore':score,'bundleId':a.get('bundle_id')}
                    RENDER_LRU[sid]=str(cached); RENDER_LRU.move_to_end(sid); trim_lru(RENDER_LRU,MAX_RENDERS,True)
                    return cached,meta
            except Exception as e: last_error=e
        raise RuntimeError('Objets trouvés mais rendu PNG impossible'+((' : '+str(last_error)) if last_error else ''))
    finally:
        try: del env
        except Exception: pass
        gc.collect()


class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*args,**kwargs): super().__init__(*args,directory=str(FRONTEND),**kwargs)
    def log_message(self,fmt,*args): print('V31_HTTP',fmt%args,flush=True)
    def send_json(self,obj,status=200):
        raw=json.dumps(obj,ensure_ascii=False,separators=(',',':')).encode('utf-8'); self.send_response(status); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Content-Length',str(len(raw))); self.send_header('Cache-Control','no-store'); self.end_headers(); self.wfile.write(raw)
    def do_GET(self):
        u=urlparse(self.path)
        if not u.path.startswith('/api/v31/'): return super().do_GET()
        qs=parse_qs(u.query)
        try:
            if u.path=='/api/v31/status':
                con=dbcon(); n=con.execute('SELECT count(*) FROM assets').fetchone()[0]; con.close(); return self.send_json({'ok':True,'schemaVersion':31,'assets':n,'db':str(DB),'bundleCache':len(BUNDLE_LRU),'renderCache':len(RENDER_LRU)})
            if u.path=='/api/v31/facets': return self.send_json({'facets':facets(),'taxonomy':TAX})
            if u.path=='/api/v31/search': return self.send_json({'items':search_assets(qs)})
            if u.path=='/api/v31/asset':
                a=get_asset(q1(qs,'id')); return self.send_json({'asset':a},200 if a else 404)
            if u.path=='/api/v31/render':
                a=get_asset(q1(qs,'id'))
                if not a: return self.send_json({'error':'asset-not-found'},404)
                try: p,meta=render_asset(a)
                except Exception as e: return self.send_json({'error':'render-failed','message':str(e),'asset':a},422)
                raw=p.read_bytes(); self.send_response(200); self.send_header('Content-Type','image/png'); self.send_header('Content-Length',str(len(raw))); self.send_header('X-WfGg-Render-Meta',json.dumps(meta,ensure_ascii=True,separators=(',',':'))[:4000]); self.send_header('Cache-Control','no-store'); self.end_headers(); self.wfile.write(raw); return
            if u.path=='/api/v31/prefetch':
                ids=[x for x in q1(qs,'ids').split(',') if x][:2]; out=[]
                for sid in ids:
                    a=get_asset(sid)
                    if not a: continue
                    try: _,meta=render_asset(a); out.append({'id':sid,'ok':True,'meta':meta})
                    except Exception as e: out.append({'id':sid,'ok':False,'message':str(e)})
                return self.send_json({'items':out})
            return self.send_json({'error':'unknown-endpoint'},404)
        except Exception as e:
            return self.send_json({'error':'server-error','message':str(e)},500)


if __name__=='__main__':
    url=f'http://127.0.0.1:{PORT}/lab/lastwar-global-graphics-viewer-v31.html'
    print('=== WFGG LAST WAR GLOBAL GRAPHICS V31 ===',flush=True)
    print(url,flush=True)
    ThreadingHTTPServer(('127.0.0.1',PORT),Handler).serve_forever()
