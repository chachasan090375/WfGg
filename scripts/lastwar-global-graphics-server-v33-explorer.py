#!/usr/bin/env python3
from __future__ import annotations

"""WfGg Last War LAB V33 explorer/runtime.

Adds the missing exploration layer without weakening the exact-render guardrails:
- persistent viewed/unviewed state in a separate SQLite DB;
- source/build date extracted from the installed APK ZIP entry (APK mtime fallback) + sorting;
- 31-hero registry with western names, game-internal aliases and IDs;
- hero direct/related crosswalk;
- keyword and exact folder/subfolder tree filters;
- perceptual visual fingerprints for successfully decoded PNGs and "similar images" search;
- source-identity/CAB-assisted Sprite -> Texture2D PPtr recovery;
- exact same-asset/same-folder raster bundle augmentation for PNG/Sprite failures.

The viewer remains local/offline and never substitutes an unrelated image for the selected asset.
"""

from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from datetime import datetime, timezone
import hashlib, importlib.util, json, math, os, re, shutil, sqlite3, subprocess, sys, threading, time, zipfile

ROOT=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else Path(__file__).resolve().parents[1]
CACHE=Path.home()/'.cache/wfgg-lastwar-v31'
CATALOG_DB=CACHE/'graphics-catalog-v31.sqlite3'
STATE_DB=CACHE/'viewer-state-v33.sqlite3'
IDENTITY_SCRIPT=ROOT/'scripts/lastwar-global-graphics-identity-enrich-v33.py'
BASE=ROOT/'scripts/lastwar-global-graphics-server-v33-sourcefixed-debug.py'
VIEWER=ROOT/'frontend/lab/lastwar-global-graphics-viewer-v33.html'
EXPLORER_JS=ROOT/'frontend/lab/global-graphics-v33/explorer-v33.js'
HERO_REGISTRY=ROOT/'data/lastwar/hero-registry-v1.json'


def load_module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod


def ensure_identity_column():
    if not CATALOG_DB.is_file():return
    con=sqlite3.connect(CATALOG_DB)
    cols={r[1] for r in con.execute('PRAGMA table_info(assets)')};con.close()
    if 'source_identity' not in cols:
        print('V33_EXPLORER identity-column=missing enrich=START',flush=True)
        subprocess.run([sys.executable,str(IDENTITY_SCRIPT),str(ROOT)],check=True)


ensure_identity_column()
base=load_module('wfgg_v33_sourcefixed_debug_explorer',BASE)
sf=base.m
c=sf.c
core=sf.core
v31=core.v31
mobile=c.mobile

STATE_DB.parent.mkdir(parents=True,exist_ok=True)
_tls=threading.local()
_external_env_hold=[]


def state_con():
    con=sqlite3.connect(STATE_DB,timeout=20)
    con.row_factory=sqlite3.Row
    con.execute('PRAGMA journal_mode=WAL')
    con.execute('PRAGMA synchronous=NORMAL')
    return con


def init_state_db():
    con=state_con()
    con.executescript('''
    CREATE TABLE IF NOT EXISTS seen(
      stable_id TEXT PRIMARY KEY,
      first_seen REAL NOT NULL,
      last_seen REAL NOT NULL,
      view_count INTEGER NOT NULL DEFAULT 1
    );
    CREATE INDEX IF NOT EXISTS idx_seen_last ON seen(last_seen);
    CREATE TABLE IF NOT EXISTS source_dates(
      stable_id TEXT PRIMARY KEY,
      epoch REAL,
      iso TEXT,
      kind TEXT,
      source TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_source_dates_epoch ON source_dates(epoch);
    CREATE TABLE IF NOT EXISTS visual_fingerprints(
      stable_id TEXT PRIMARY KEY,
      width INTEGER,height INTEGER,aspect REAL,
      dhash TEXT,alpha_hash TEXT,hist_json TEXT,edge REAL,
      rendered_file TEXT,updated_at REAL
    );
    CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT);
    ''')
    con.commit();con.close()


init_state_db()


def token_hit(hay,token):
    token=str(token or '').strip().lower()
    if not token:return False
    # underscore is intentionally a separator for game asset names.
    pattern=r'(?<![a-z0-9])'+re.escape(token)+r'(?![a-z0-9])'
    return re.search(pattern,hay,re.I) is not None


def load_heroes():
    data=json.loads(HERO_REGISTRY.read_text('utf-8'))
    return data.get('heroes') or []


HEROES=load_heroes()
HERO_BY_ID={str(h['hero_id']):h for h in HEROES}


def hero_registry_digest():
    return hashlib.sha1(HERO_REGISTRY.read_bytes()).hexdigest()


def ensure_hero_index():
    con=core.dbcon()
    con.executescript('''
    CREATE TABLE IF NOT EXISTS hero_registry_v33(
      hero_id TEXT PRIMARY KEY,western_name TEXT,aliases_json TEXT,internal_aliases_json TEXT,confidence TEXT
    );
    CREATE TABLE IF NOT EXISTS hero_asset_links_v33(
      hero_id TEXT NOT NULL,stable_id TEXT NOT NULL,relation TEXT NOT NULL,evidence TEXT,confidence REAL,
      PRIMARY KEY(hero_id,stable_id,relation)
    );
    CREATE INDEX IF NOT EXISTS idx_hero_links_asset ON hero_asset_links_v33(stable_id);
    CREATE INDEX IF NOT EXISTS idx_hero_links_hero ON hero_asset_links_v33(hero_id,relation);
    CREATE TABLE IF NOT EXISTS hero_index_meta_v33(key TEXT PRIMARY KEY,value TEXT);
    ''')
    asset_count=con.execute('SELECT count(*) FROM assets').fetchone()[0]
    sig=hero_registry_digest()+':'+str(asset_count)
    old=con.execute("SELECT value FROM hero_index_meta_v33 WHERE key='signature'").fetchone()
    links=con.execute('SELECT count(*) FROM hero_asset_links_v33').fetchone()[0]
    if old and old[0]==sig and links>0:
        con.close();print('V33_HERO_INDEX cached links='+str(links),flush=True);return

    started=time.time()
    con.execute('DELETE FROM hero_registry_v33');con.execute('DELETE FROM hero_asset_links_v33')
    con.executemany('INSERT INTO hero_registry_v33 VALUES(?,?,?,?,?)',[
        (str(h['hero_id']),h['western_name'],json.dumps(h.get('aliases') or [],ensure_ascii=False),json.dumps(h.get('internal_aliases') or [],ensure_ascii=False),h.get('confidence',''))
        for h in HEROES
    ])
    patterns=[]
    for h in HEROES:
        hid=str(h['hero_id']);western=h['western_name'].lower()
        aliases=list(dict.fromkeys([western]+[str(x).lower() for x in h.get('auto_link_aliases') or []]))
        patterns.append((hid,western,aliases))
    batch=[];rows=0;direct=0
    for r in con.execute('SELECT stable_id,asset_path,logical_name,alias_name,subject,search_text FROM assets'):
        rows+=1
        hay=' '.join(str(x or '') for x in r[1:]).lower()
        for hid,western,aliases in patterns:
            evidence=[]
            if token_hit(hay,hid):evidence.append('hero-id:'+hid)
            if token_hit(hay,western):evidence.append('western-name:'+western)
            for alias in aliases:
                if alias==western:continue
                if token_hit(hay,alias):evidence.append('internal-alias:'+alias)
            if evidence:
                batch.append((hid,r[0],'direct',';'.join(evidence[:6]),0.99 if evidence[0].startswith('hero-id') else 0.94))
                direct+=1
        if len(batch)>=5000:
            con.executemany('INSERT OR IGNORE INTO hero_asset_links_v33 VALUES(?,?,?,?,?)',batch);batch=[]
        if rows%30000==0:print('V33_HERO_INDEX_PROGRESS',rows,'direct='+str(direct),flush=True)
    if batch:con.executemany('INSERT OR IGNORE INTO hero_asset_links_v33 VALUES(?,?,?,?,?)',batch)

    # Exact logical-folder propagation is useful for skins, textures, materials and weapon/vehicle pieces
    # whose own filename does not repeat the hero name.
    con.execute('''
    INSERT OR IGNORE INTO hero_asset_links_v33(hero_id,stable_id,relation,evidence,confidence)
    SELECT d.hero_id,a.stable_id,'related-folder','same exact asset_folder as direct hero asset',0.86
    FROM hero_asset_links_v33 d
    JOIN assets src ON src.stable_id=d.stable_id
    JOIN assets a ON a.asset_folder=src.asset_folder
    WHERE d.relation='direct' AND coalesce(src.asset_folder,'')<>'' AND a.stable_id<>src.stable_id
    ''')
    # Same-bundle relation is deliberately constrained to hero/vehicle/equipment-looking rows.
    con.execute('''
    INSERT OR IGNORE INTO hero_asset_links_v33(hero_id,stable_id,relation,evidence,confidence)
    SELECT d.hero_id,a.stable_id,'related-bundle','same exact bundle as direct hero asset',0.70
    FROM hero_asset_links_v33 d
    JOIN assets src ON src.stable_id=d.stable_id
    JOIN assets a ON a.bundle_id=src.bundle_id
    WHERE d.relation='direct' AND a.stable_id<>src.stable_id
      AND (a.context IN ('hero','formation') OR a.family IN ('characters','vehicles','weapons-equipment')
           OR lower(coalesce(a.asset_path,'')) LIKE '%hero%')
    ''')
    con.execute("INSERT OR REPLACE INTO hero_index_meta_v33(key,value) VALUES('signature',?)",(sig,))
    con.commit();total=con.execute('SELECT count(*) FROM hero_asset_links_v33').fetchone()[0];con.close()
    print('V33_HERO_INDEX_READY heroes='+str(len(HEROES))+' direct='+str(direct)+' links='+str(total)+' seconds='+f'{time.time()-started:.2f}',flush=True)


ensure_hero_index()


def hero_links_for(con,sid):
    return [dict(r) for r in con.execute('''
      SELECT l.hero_id,r.western_name,l.relation,l.evidence,l.confidence
      FROM hero_asset_links_v33 l JOIN hero_registry_v33 r ON r.hero_id=l.hero_id
      WHERE l.stable_id=? ORDER BY l.confidence DESC,r.western_name,l.relation
    ''',(sid,))]


def hero_list_payload():
    con=core.dbcon();out=[]
    for h in HEROES:
        hid=str(h['hero_id'])
        direct=con.execute("SELECT count(distinct stable_id) FROM hero_asset_links_v33 WHERE hero_id=? AND relation='direct'",(hid,)).fetchone()[0]
        total=con.execute('SELECT count(distinct stable_id) FROM hero_asset_links_v33 WHERE hero_id=?',(hid,)).fetchone()[0]
        x=dict(h);x['hero_id']=hid;x['direct_count']=direct;x['linked_count']=total;out.append(x)
    con.close();return out


def _zip_entry_epoch(apk,info):
    try:
        dt=datetime(*info.date_time,tzinfo=timezone.utc)
        if 2000<=dt.year<=datetime.now(timezone.utc).year+1:
            return dt.timestamp(),dt.isoformat().replace('+00:00','Z'),'apk-entry-timestamp'
    except Exception:pass
    try:
        ep=Path(apk).stat().st_mtime
        return ep,datetime.fromtimestamp(ep,timezone.utc).isoformat().replace('+00:00','Z'),'apk-file-mtime'
    except Exception:return None,None,'unknown'


def ensure_source_dates():
    apks=list(v31.apk_paths())
    signature='|'.join(str(p)+':'+str(int(Path(p).stat().st_mtime if Path(p).exists() else 0))+':'+str(Path(p).stat().st_size if Path(p).exists() else 0) for p in apks)
    cat=core.dbcon();asset_count=cat.execute('SELECT count(*) FROM assets').fetchone()[0]
    st=state_con();old=st.execute("SELECT value FROM meta WHERE key='source-date-signature'").fetchone();n=st.execute('SELECT count(*) FROM source_dates').fetchone()[0]
    if old and old[0]==signature and n==asset_count:
        st.close();cat.close();print('V33_SOURCE_DATES cached='+str(n),flush=True);return
    started=time.time();exact={};by_base={}
    for apk in apks:
        try:
            with zipfile.ZipFile(apk,'r') as z:
                for info in z.infolist():
                    key=sf._norm_entry(info.filename);rec=(*_zip_entry_epoch(apk,info),Path(apk).name+':'+info.filename)
                    exact[key]=rec;by_base.setdefault(sf._base(info.filename),rec)
        except Exception as exc:print('V33_SOURCE_DATE_APK_ERROR',Path(apk).name,str(exc)[:120],flush=True)
    st.execute('DELETE FROM source_dates');batch=[];rows=dated=0
    for r in cat.execute('SELECT stable_id,fragment_entry,table_fragment FROM assets'):
        rows+=1;entry=sf._norm_entry(r['fragment_entry']);rec=exact.get(entry)
        if rec is None:
            rec=by_base.get(sf._base(r['fragment_entry'])) or by_base.get(sf._base(r['table_fragment']))
        if rec:
            epoch,iso,kind,source=rec;batch.append((r['stable_id'],epoch,iso,kind,source));dated+=1
        else:batch.append((r['stable_id'],None,None,'unknown',''))
        if len(batch)>=5000:
            st.executemany('INSERT OR REPLACE INTO source_dates VALUES(?,?,?,?,?)',batch);batch=[]
    if batch:st.executemany('INSERT OR REPLACE INTO source_dates VALUES(?,?,?,?,?)',batch)
    st.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('source-date-signature',?)",(signature,));st.commit();st.close();cat.close()
    print('V33_SOURCE_DATES_READY rows='+str(rows)+' dated='+str(dated)+' apks='+str(len(apks))+' seconds='+f'{time.time()-started:.2f}',flush=True)


ensure_source_dates()


def mark_seen(sid):
    now=time.time();con=state_con()
    con.execute('''INSERT INTO seen(stable_id,first_seen,last_seen,view_count) VALUES(?,?,?,1)
      ON CONFLICT(stable_id) DO UPDATE SET last_seen=excluded.last_seen,view_count=seen.view_count+1''',(sid,now,now))
    con.commit();r=con.execute('SELECT * FROM seen WHERE stable_id=?',(sid,)).fetchone();con.close();return dict(r) if r else None


def state_for_ids(ids):
    if not ids:return {},{}
    con=state_con();seen={};dates={}
    for pos in range(0,len(ids),500):
        chunk=ids[pos:pos+500];ph=','.join('?' for _ in chunk)
        for r in con.execute('SELECT * FROM seen WHERE stable_id IN ('+ph+')',chunk):seen[r['stable_id']]=dict(r)
        for r in con.execute('SELECT * FROM source_dates WHERE stable_id IN ('+ph+')',chunk):dates[r['stable_id']]=dict(r)
    con.close();return seen,dates


def _resample():
    try:
        from PIL import Image
        return Image.Resampling.LANCZOS
    except Exception:
        from PIL import Image
        return Image.LANCZOS


def fingerprint_file(sid,path):
    try:
        from PIL import Image
        im=Image.open(path).convert('RGBA');w,h=im.size
        if w<=0 or h<=0:return None
        res=_resample();alpha=im.getchannel('A')
        # Alpha/silhouette hash.
        a8=alpha.resize((8,8),res);av=list(a8.getdata());mean=sum(av)/64.0
        ah=0
        for v in av:ah=(ah<<1)|(1 if v>=mean else 0)
        # dHash on the actually visible RGBA image composited on black.
        bg=Image.new('RGB',im.size,(0,0,0));bg.paste(im.convert('RGB'),mask=alpha)
        g=bg.convert('L').resize((9,8),res);pv=list(g.getdata());dh=0
        for y in range(8):
            for x in range(8):dh=(dh<<1)|(1 if pv[y*9+x]>pv[y*9+x+1] else 0)
        small=bg.resize((16,16),res);pix=list(small.getdata());hist=[0.0]*12
        for rr,gg,bb in pix:
            hist[min(3,rr//64)]+=1;hist[4+min(3,gg//64)]+=1;hist[8+min(3,bb//64)]+=1
        hist=[round(x/(len(pix)*3.0),6) for x in hist]
        gray=list(bg.convert('L').resize((16,16),res).getdata());edges=[]
        for y in range(16):
            for x in range(15):edges.append(abs(gray[y*16+x]-gray[y*16+x+1]))
        for y in range(15):
            for x in range(16):edges.append(abs(gray[y*16+x]-gray[(y+1)*16+x]))
        edge=sum(edges)/max(1,len(edges))/255.0
        rec=(sid,w,h,w/max(1,h),f'{dh:016x}',f'{ah:016x}',json.dumps(hist,separators=(',',':')),edge,str(path),time.time())
        con=state_con();con.execute('INSERT OR REPLACE INTO visual_fingerprints VALUES(?,?,?,?,?,?,?,?,?,?)',rec);con.commit();con.close()
        return {'stable_id':sid,'width':w,'height':h,'aspect':rec[3],'dhash':rec[4],'alpha_hash':rec[5],'hist':hist,'edge':edge}
    except Exception as exc:
        print('V33_FINGERPRINT_ERROR',sid,str(exc)[:160],flush=True);return None


def fingerprint_row(sid):
    con=state_con();r=con.execute('SELECT * FROM visual_fingerprints WHERE stable_id=?',(sid,)).fetchone();con.close()
    if not r:return None
    d=dict(r)
    try:d['hist']=json.loads(d.pop('hist_json') or '[]')
    except Exception:d['hist']=[]
    return d


def warm_cached_fingerprints():
    known=state_con();existing={r[0] for r in known.execute('SELECT stable_id FROM visual_fingerprints')};known.close();added=0
    for p in v31.RENDER_CACHE.glob('LWGA-*-target.png'):
        m=re.match(r'(LWGA-[A-Z0-9]+)-target\.png$',p.name)
        if not m or m.group(1) in existing:continue
        proof=p.with_name(m.group(1)+'-target-proof.json')
        if not proof.is_file():continue
        try:
            meta=json.loads(proof.read_text('utf-8'))
            if not meta.get('accepted') or meta.get('stableId')!=m.group(1):continue
        except Exception:continue
        if fingerprint_file(m.group(1),p):added+=1
    con=state_con();n=con.execute('SELECT count(*) FROM visual_fingerprints').fetchone()[0];con.close()
    print('V33_VISUAL_INDEX cached='+str(n)+' added='+str(added),flush=True)


warm_cached_fingerprints()


def hamming_hex(a,b):
    try:return (int(a,16)^int(b,16)).bit_count()/64.0
    except Exception:return 1.0


def cosine(a,b):
    if not a or not b:return 0.0
    dot=sum(x*y for x,y in zip(a,b));na=math.sqrt(sum(x*x for x in a));nb=math.sqrt(sum(x*x for x in b))
    return dot/(na*nb) if na and nb else 0.0


def visual_similarity(a,b):
    dh=1.0-hamming_hex(a.get('dhash'),b.get('dhash'))
    ah=1.0-hamming_hex(a.get('alpha_hash'),b.get('alpha_hash'))
    hist=cosine(a.get('hist') or [],b.get('hist') or [])
    ar=math.exp(-abs(math.log(max(.01,float(a.get('aspect') or 1))/max(.01,float(b.get('aspect') or 1)))))
    edge=1.0-min(1.0,abs(float(a.get('edge') or 0)-float(b.get('edge') or 0))*3.0)
    return max(0.0,min(1.0,.30*dh+.25*ah+.25*hist+.10*ar+.10*edge))


# ---------- Raster recovery improvements ----------
BASE_MANUAL_PTR=c._manual_ptr_read
BASE_TARGET_PASS=c._render_target_pass
BASE_CLOSURE=mobile.materialize_raster_closure


def identity_hash_from_external(ext):
    m=re.search(r'cab([0-9a-f]{16,64})',str(ext or '').lower())
    return m.group(1) if m else ''


def external_identity_rows(ext,a=None,limit=60):
    cabhash=identity_hash_from_external(ext);con=core.dbcon();rows=[]
    cols={r[1] for r in con.execute('PRAGMA table_info(assets)')}
    if cabhash and 'source_identity' in cols:
        rows=con.execute("SELECT * FROM assets WHERE lower(coalesce(source_identity,'')) LIKE ? LIMIT ?",('%'+cabhash+'%',limit)).fetchall()
    if not rows and a:
        path=str(a.get('asset_path') or '')
        logical=str(a.get('logical_name') or '');alias=str(a.get('alias_name') or '')
        clauses=[];params=[]
        if path:clauses.append('asset_path=?');params.append(path)
        if logical:clauses.append('logical_name=?');params.append(logical)
        if alias:clauses.append('alias_name=?');params.append(alias)
        if clauses:rows=con.execute('SELECT * FROM assets WHERE '+(' OR '.join(clauses))+' LIMIT ?',params+[limit]).fetchall()
    out=[dict(r) for r in rows];con.close();return out


def explorer_manual_ptr_read(ptr,sprite_reader,texture_readers):
    tex,mode=BASE_MANUAL_PTR(ptr,sprite_reader,texture_readers)
    if tex is not None:return tex,mode
    pid=c._int_attr(ptr,'path_id','m_PathID');fid=c._int_attr(ptr,'file_id','m_FileID') or 0
    if pid is None or fid<=0:return None,mode
    ext=c._external_key(sprite_reader,fid);a=getattr(_tls,'asset',None)
    candidates=external_identity_rows(ext,a)
    if not candidates:return None,mode+';source-identity-no-row:'+str(ext)
    try:import UnityPy
    except Exception:return None,mode+';unitypy-missing'
    seen=set();attempted=0
    for row in candidates:
        try:bid=int(row.get('bundle_id'))
        except Exception:continue
        if bid in seen:continue
        seen.add(bid);attempted+=1
        try:p,src=core.v31.materialize_bundle(row);env=UnityPy.load(str(p))
        except Exception:continue
        # The row itself was selected from the exact external CAB/source identity.
        # Inside that serialized file, PathID is the authoritative object key; UnityPy's
        # display/file key is not guaranteed to expose the CAB hash on Android.
        matches=[]
        for obj in env.objects:
            if getattr(obj.type,'name',str(obj.type))!='Texture2D':continue
            if c._path_id(obj)==pid:matches.append(obj)
        if len(matches)==1:
            try:
                tex=matches[0].read();_external_env_hold.append(env)
                while len(_external_env_hold)>4:_external_env_hold.pop(0)
                print('V33_PPTR_SOURCE_IDENTITY_RECOVERED',a.get('stable_id') if a else '?','pid='+str(pid),'external='+str(ext),'bundle='+str(bid),flush=True)
                return tex,'source-identity-external:'+str(ext)
            except Exception:pass
    return None,mode+';source-identity-unresolved:'+str(ext)+':bundles='+str(attempted)


def _identity_sibling_rows(a,limit=24):
    path=str(a.get('asset_path') or '');logical=str(a.get('logical_name') or '');alias=str(a.get('alias_name') or '');folder=str(a.get('asset_folder') or '')
    con=core.dbcon();clauses=[];params=[]
    if path:clauses.append('asset_path=?');params.append(path)
    if logical:clauses.append('logical_name=?');params.append(logical)
    if alias:clauses.append('alias_name=?');params.append(alias)
    rows=[]
    if clauses:rows=list(con.execute('SELECT * FROM assets WHERE ('+' OR '.join(clauses)+') ORDER BY confidence DESC LIMIT ?',params+[limit]))
    if folder and len(rows)<limit:
        extra=con.execute("SELECT * FROM assets WHERE asset_folder=? AND tech_kind IN ('texture2d','sprite','atlas') ORDER BY confidence DESC LIMIT ?",(folder,limit-len(rows))).fetchall();rows+=list(extra)
    con.close();return [dict(r) for r in rows]


def explorer_raster_closure(a,max_deps=None):
    paths,sources=BASE_CLOSURE(a,max_deps);rawpath=str(a.get('asset_path') or '').lower()
    if not (rawpath.endswith(('.png','.jpg','.jpeg','.tga','.dds','.psd')) or str(a.get('tech_kind') or '') in {'sprite','texture2d','atlas'}):return paths,sources
    existing=set()
    for s in sources:
        try:existing.add(int(s.get('bundleId')))
        except Exception:pass
    base_dir=mobile.MOBILE_CLOSURE/a['stable_id'];added=0
    for row in _identity_sibling_rows(a):
        try:bid=int(row.get('bundle_id'))
        except Exception:continue
        if bid in existing:continue
        existing.add(bid)
        try:src,source=core.v31.materialize_bundle(row);dst=base_dir/f'identity-{bid}.bundle';shutil.copy2(src,dst)
        except Exception:continue
        paths.append(dst);sources.append({'bundleId':bid,'ok':True,'source':source,'closureMode':'identity-sibling'});added+=1
        if added>=24:break
    if added:print('V33_RASTER_IDENTITY_AUGMENT',a['stable_id'],'added='+str(added),'total='+str(len(paths)),flush=True)
    return paths,sources


def explorer_target_pass(a,deep=False):
    _tls.asset=a
    try:return BASE_TARGET_PASS(a,deep)
    finally:_tls.asset=None


c._manual_ptr_read=explorer_manual_ptr_read
c.mobile.materialize_raster_closure=explorer_raster_closure
c._render_target_pass=explorer_target_pass

# Fingerprint every accepted exact render.
BASE_RENDER=core.v31.render_asset

def render_with_fingerprint(a):
    p,meta=BASE_RENDER(a)
    if p and Path(p).is_file() and (meta or {}).get('accepted',True):fingerprint_file(a['stable_id'],Path(p))
    return p,meta

core.v31.render_asset=render_with_fingerprint


def q1(qs,name,default=''):
    return (qs.get(name) or [default])[0]


def keyword_tokens(s):
    return [x.strip().strip('"') for x in re.findall(r'"[^"]+"|\S+',str(s or '')) if x.strip().strip('"')][:12]


def attach_state(con):
    con.execute('ATTACH DATABASE ? AS state',(str(STATE_DB),))


def explorer_query_parts(qs):
    q,conditions,params=c._query_parts(qs)
    kws=q1(qs,'keywords').strip()
    for kw in keyword_tokens(kws):conditions.append('lower(a.search_text) LIKE ?');params.append('%'+kw.lower()+'%')
    path=q1(qs,'path_prefix').strip().replace('\\','/').strip('/')
    if path:conditions.append("lower(replace(coalesce(a.asset_path,''),'\\','/')) LIKE ?");params.append(path.lower()+'/%')
    hero=q1(qs,'hero_id').strip();hrel=q1(qs,'hero_relation').strip()
    if hero and hero!='all':
        sub=['hl.stable_id=a.stable_id','hl.hero_id=?'];sp=[hero]
        if hrel=='direct':sub.append("hl.relation='direct'")
        elif hrel=='related':sub.append("hl.relation<>'direct'")
        conditions.append('EXISTS (SELECT 1 FROM hero_asset_links_v33 hl WHERE '+' AND '.join(sub)+')');params+=sp
    view=q1(qs,'view_state').strip()
    if view=='seen':conditions.append('EXISTS (SELECT 1 FROM state.seen sv WHERE sv.stable_id=a.stable_id)')
    elif view=='unseen':conditions.append('NOT EXISTS (SELECT 1 FROM state.seen sv WHERE sv.stable_id=a.stable_id)')
    df=q1(qs,'date_from').strip();dt=q1(qs,'date_to').strip()
    if df:
        try:ep=datetime.fromisoformat(df).replace(tzinfo=timezone.utc).timestamp();conditions.append('EXISTS (SELECT 1 FROM state.source_dates sd WHERE sd.stable_id=a.stable_id AND sd.epoch>=?)');params.append(ep)
        except Exception:pass
    if dt:
        try:ep=datetime.fromisoformat(dt).replace(tzinfo=timezone.utc).timestamp()+86399;conditions.append('EXISTS (SELECT 1 FROM state.source_dates sd WHERE sd.stable_id=a.stable_id AND sd.epoch<=?)');params.append(ep)
        except Exception:pass
    return q,conditions,params


def order_sql(qs,has_fts=False,similar=False):
    sort=q1(qs,'sort','default')
    if similar:return 'sim.score DESC,a.confidence DESC,a.row_no'
    if sort=='date_desc':return "coalesce((SELECT epoch FROM state.source_dates sd WHERE sd.stable_id=a.stable_id),0) DESC,a.row_no"
    if sort=='date_asc':return "CASE WHEN (SELECT epoch FROM state.source_dates sd WHERE sd.stable_id=a.stable_id) IS NULL THEN 1 ELSE 0 END,(SELECT epoch FROM state.source_dates sd WHERE sd.stable_id=a.stable_id) ASC,a.row_no"
    if sort=='unseen_first':return "CASE WHEN EXISTS(SELECT 1 FROM state.seen sv WHERE sv.stable_id=a.stable_id) THEN 1 ELSE 0 END,a.row_no"
    if sort=='seen_recent':return "coalesce((SELECT last_seen FROM state.seen sv WHERE sv.stable_id=a.stable_id),0) DESC,a.row_no"
    if sort=='confidence':return 'a.confidence DESC,a.row_no'
    if sort=='path':return 'lower(a.asset_path),a.row_no'
    return 'a.confidence DESC,a.row_no' if has_fts else 'a.row_no'


def metadata_similarity_candidates(a,limit=900):
    con=core.dbcon();rows=con.execute('''SELECT stable_id,family,visual_role,context,tech_kind,dimension_class,graphic_class,confidence
      FROM assets WHERE stable_id<>? AND (family=? OR visual_role=? OR context=? OR tech_kind=?) ORDER BY confidence DESC LIMIT ?''',
      (a['stable_id'],a.get('family'),a.get('visual_role'),a.get('context'),a.get('tech_kind'),limit)).fetchall();con.close()
    out={}
    for r in rows:
        score=0.0;reasons=[]
        for key,w in [('family',.12),('visual_role',.11),('context',.08),('tech_kind',.08),('dimension_class',.06),('graphic_class',.05)]:
            if a.get(key) and r[key]==a.get(key):score+=w;reasons.append(key)
        if score>0:out[r['stable_id']]={'score':min(.49,score),'basis':'metadata','reasons':reasons}
    return out


def ensure_selected_fingerprint(a):
    fp=fingerprint_row(a['stable_id'])
    if fp:return fp
    try:
        p,meta=core.v31.render_asset(a)
        if p:return fingerprint_row(a['stable_id']) or fingerprint_file(a['stable_id'],p)
    except Exception as exc:print('V33_SIMILAR_SOURCE_RENDER_FAILED',a['stable_id'],str(exc)[:200],flush=True)
    return None


def similarity_candidates(sid,limit=900):
    a=core.get_asset(sid) if hasattr(core,'get_asset') else None
    if not a:
        con=core.dbcon();r=con.execute('SELECT * FROM assets WHERE stable_id=?',(sid,)).fetchone();a=core.rowdict(r);con.close()
    if not a:return {}
    merged=metadata_similarity_candidates(a,limit)
    src=ensure_selected_fingerprint(a)
    if src:
        st=state_con();rows=st.execute('SELECT * FROM visual_fingerprints WHERE stable_id<>?',(sid,)).fetchall();st.close()
        for r in rows:
            d=dict(r)
            try:d['hist']=json.loads(d.get('hist_json') or '[]')
            except Exception:d['hist']=[]
            score=visual_similarity(src,d)
            old=merged.get(d['stable_id'])
            if old:
                score=min(1.0,.86*score+.14*min(1.0,old['score']*2));reasons=['visual']+old['reasons']
            else:reasons=['visual']
            merged[d['stable_id']]={'score':score,'basis':'visual','reasons':reasons}
    return dict(sorted(merged.items(),key=lambda kv:kv[1]['score'],reverse=True)[:limit])


def enrich_rows(con,rows,similar_meta=None):
    out=[];ids=[r['stable_id'] for r in rows];seen,dates=state_for_ids(ids)
    for r in rows:
        d=core.rowdict(r);sid=d['stable_id'];d['event_links']=core.event_links(con,sid);d['hero_links']=hero_links_for(con,sid)
        sv=seen.get(sid);sd=dates.get(sid);d['is_viewed']=bool(sv);d['view_count']=sv.get('view_count',0) if sv else 0;d['last_seen']=sv.get('last_seen') if sv else None
        d['source_date']=sd.get('iso') if sd else None;d['source_date_epoch']=sd.get('epoch') if sd else None;d['source_date_kind']=sd.get('kind') if sd else None;d['source_date_source']=sd.get('source') if sd else None
        if similar_meta and sid in similar_meta:d['similarity_score']=similar_meta[sid]['score'];d['similarity_basis']=similar_meta[sid]['basis'];d['similarity_reasons']=similar_meta[sid]['reasons']
        out.append(d)
    return out


def search_page(qs):
    q,conditions,params=explorer_query_parts(qs);limit=max(1,min(120,int(q1(qs,'limit','60') or 60)));offset=max(0,int(q1(qs,'offset','0') or 0))
    con=core.dbcon();attach_state(con);similar_to=q1(qs,'similar_to').strip();similar_meta=None
    if similar_to:
        similar_meta=similarity_candidates(similar_to);con.execute('CREATE TEMP TABLE similar_order(stable_id TEXT PRIMARY KEY,score REAL)')
        con.executemany('INSERT INTO similar_order VALUES(?,?)',[(sid,m['score']) for sid,m in similar_meta.items()])
        baseq=' FROM similar_order sim JOIN assets a ON a.stable_id=sim.stable_id';p=[]
        if conditions:baseq+=' WHERE '+' AND '.join(conditions);p+=params
        total=con.execute('SELECT count(*)'+baseq,p).fetchone()[0]
        rows=con.execute('SELECT a.*'+baseq+' ORDER BY '+order_sql(qs,False,True)+' LIMIT ? OFFSET ?',p+[limit,offset]).fetchall()
    else:
        fts=v31.fts_expr(q);rows=[];total=0
        if fts:
            baseq=' FROM asset_fts f JOIN assets a ON a.stable_id=f.stable_id WHERE asset_fts MATCH ?';p=[fts]
            if conditions:baseq+=' AND '+' AND '.join(conditions);p+=params
            try:
                total=con.execute('SELECT count(*)'+baseq,p).fetchone()[0]
                rows=con.execute('SELECT a.*'+baseq+' ORDER BY '+order_sql(qs,True)+' LIMIT ? OFFSET ?',p+[limit,offset]).fetchall()
            except sqlite3.OperationalError:
                c2=list(conditions)+['lower(a.search_text) LIKE ?'];p2=params+['%'+q.lower()+'%'];where=' WHERE '+' AND '.join(c2)
                total=con.execute('SELECT count(*) FROM assets a'+where,p2).fetchone()[0]
                rows=con.execute('SELECT a.* FROM assets a'+where+' ORDER BY '+order_sql(qs,False)+' LIMIT ? OFFSET ?',p2+[limit,offset]).fetchall()
        else:
            where=(' WHERE '+' AND '.join(conditions)) if conditions else ''
            total=con.execute('SELECT count(*) FROM assets a'+where,params).fetchone()[0]
            rows=con.execute('SELECT a.* FROM assets a'+where+' ORDER BY '+order_sql(qs,False)+' LIMIT ? OFFSET ?',params+[limit,offset]).fetchall()
    out=enrich_rows(con,rows,similar_meta);con.close();token=c.query_token(qs)
    return {'items':out,'total':total,'offset':offset,'limit':limit,'hasMore':offset+len(out)<total,'queryToken':token,'similarTo':similar_to or None}


def path_children(qs):
    parent=q1(qs,'parent').strip().replace('\\','/').strip('/');query=q1(qs,'q').strip().lower();con=core.dbcon()
    if query:
        rows=con.execute("SELECT * FROM path_nodes WHERE node_type='folder' AND lower(full_path) LIKE ? ORDER BY depth,total_assets DESC LIMIT 120",('%'+query+'%',)).fetchall()
        current=None
    else:
        if parent:
            p=con.execute("SELECT * FROM path_nodes WHERE full_path=? AND node_type IN ('folder','root')",(parent,)).fetchone()
        else:p=con.execute("SELECT * FROM path_nodes WHERE node_type='root' ORDER BY depth LIMIT 1").fetchone()
        if not p:con.close();return {'current':None,'folders':[]}
        current=dict(p);rows=con.execute("SELECT * FROM path_nodes WHERE parent_id=? AND node_type='folder' ORDER BY name",(p['node_id'],)).fetchall()
    out=[{'node_id':r['node_id'],'name':r['name'],'full_path':r['full_path'],'depth':r['depth'],'total_assets':r['total_assets']} for r in rows]
    con.close();return {'current':current,'folders':out,'query':query or None}


def hero_status():
    con=core.dbcon();links=con.execute('SELECT count(*) FROM hero_asset_links_v33').fetchone()[0];direct=con.execute("SELECT count(*) FROM hero_asset_links_v33 WHERE relation='direct'").fetchone()[0];con.close()
    st=state_con();seen=st.execute('SELECT count(*) FROM seen').fetchone()[0];finger=st.execute('SELECT count(*) FROM visual_fingerprints').fetchone()[0];dated=st.execute('SELECT count(*) FROM source_dates WHERE epoch IS NOT NULL').fetchone()[0];st.close()
    return {'heroes':len(HEROES),'heroLinks':links,'heroDirectLinks':direct,'viewed':seen,'visualFingerprints':finger,'datedAssets':dated}


class ExplorerHandler(base.DebugHandler):
    def do_GET(self):
        u=urlparse(self.path);qs=parse_qs(u.query)
        try:
            if u.path=='/api/v33/search':return self.send_json(search_page(qs))
            if u.path=='/api/v33/heroes':return self.send_json({'heroes':hero_list_payload()})
            if u.path=='/api/v33/path/children':return self.send_json(path_children(qs))
            if u.path=='/api/v33/explorer-status':return self.send_json(hero_status())
            if u.path=='/lab/lastwar-global-graphics-viewer-v33.html':
                raw=VIEWER.read_text('utf-8')
                corr='<script src="./global-graphics-v33/search-correlation-v33.js"></script>'
                exp='<script src="./global-graphics-v33/explorer-v33.js"></script>'
                if 'search-correlation-v33.js' not in raw:raw=raw.replace('</body>',corr+'</body>')
                if 'explorer-v33.js' not in raw:raw=raw.replace('</body>',exp+'</body>')
                data=raw.encode('utf-8');self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(data)));self.send_header('Cache-Control','no-store, no-cache, must-revalidate, max-age=0');self.end_headers();self.wfile.write(data);return
        except Exception as exc:
            return self.send_json({'error':'explorer-failed','message':str(exc)},500)
        return super().do_GET()

    def do_POST(self):
        u=urlparse(self.path)
        if u.path!='/api/v33/view':return self.send_json({'error':'not-found'},404)
        try:
            n=int(self.headers.get('Content-Length','0') or 0);body=self.rfile.read(min(n,65536)) if n else b'{}';payload=json.loads(body.decode('utf-8') or '{}');sid=str(payload.get('id') or '')
            if not re.fullmatch(r'LWGA-[A-Z0-9]+',sid):return self.send_json({'error':'invalid-id'},400)
            return self.send_json({'ok':True,'seen':mark_seen(sid)})
        except Exception as exc:return self.send_json({'error':'view-write-failed','message':str(exc)},500)


if __name__=='__main__':
    status=hero_status()
    print('=== WFGG LAST WAR GLOBAL GRAPHICS V33 — EXPLORER + EXACT PNG RECOVERY ===',flush=True)
    print('V33_HERO_FILTER heroes='+str(status['heroes'])+' direct+related-links='+str(status['heroLinks']),flush=True)
    print('V33_VIEW_STATE persistent='+str(STATE_DB)+' viewed='+str(status['viewed']),flush=True)
    print('V33_SOURCE_DATE zip-entry/apk-mtime sort=ON dated='+str(status['datedAssets']),flush=True)
    print('V33_PATH_TREE path_nodes=ON keywords=AND',flush=True)
    print('V33_SIMILAR shape+texture+color+aspect fingerprints='+str(status['visualFingerprints']),flush=True)
    print('V33_PNG_RECOVERY source-identity/CAB-PathID=ON identity-sibling-closure=ON arbitrary-substitution=OFF',flush=True)
    print('V33_AUTO_SKIP runtime-failures=OFF (diagnostic remains visible while fixes are validated)',flush=True)
    print(f'http://127.0.0.1:{core.PORT}/lab/lastwar-global-graphics-viewer-v33.html',flush=True)
    ThreadingHTTPServer(('127.0.0.1',core.PORT),ExplorerHandler).serve_forever()
