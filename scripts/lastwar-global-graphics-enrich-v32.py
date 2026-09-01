#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
from collections import Counter
import json, re, sqlite3, sys, unicodedata

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
CACHE = Path.home() / '.cache/wfgg-lastwar-v31'
DB = CACHE / 'graphics-catalog-v31.sqlite3'
REGISTRY = ROOT / 'data/lastwar/event-registry-v1.json'

if not DB.is_file():
    raise SystemExit(f'Catalogue V31 absent: {DB}')
if not REGISTRY.is_file():
    raise SystemExit(f'Registre événements absent: {REGISTRY}')

IMAGE_EXTS = {'.png','.jpg','.jpeg','.webp','.tga','.bmp','.gif','.dds','.ktx','.ktx2','.exr','.hdr','.psd'}
DIRECT_TECH = {'sprite','texture2d','atlas','render-target'}
COMPONENT_TECH = {'material','mesh','shader','prefab'}
NON_GRAPHIC_TECH = {'animation','animator'}
DIRECT_PATH = (
    '/sprites/','/sprite/','/texture/','/textures/','/textureex/','/atlas/','/atlases/',
    'heroicon','activityicons',' icon ','_icon','icon_','portrait','background','_bg','banner','frame','badge','button','btn'
)
COMPONENT_PATH = ('/material/','/materials/','/mesh/','/meshes/','/prefab/','/prefabs/','/shader/','/shaders/','/vx/','/fx/','/vfx/')
NON_GRAPHIC_PATH = ('/audio/','/sounds/','/sound/','/music/','/lua/','/script/','/scripts/','/timeline/','/animation/','/animations/')


def norm(s: object) -> str:
    s = unicodedata.normalize('NFKD', str(s or '')).encode('ascii','ignore').decode('ascii').lower()
    return re.sub(r'[^a-z0-9]+',' ',s).strip()


def dense(s: object) -> str:
    return re.sub(r'[^a-z0-9]+','',norm(s))


def classify_graphic(row: sqlite3.Row):
    tech = (row['tech_kind'] or '').lower()
    raw = ' '.join(str(row[k] or '') for k in ('asset_path','logical_name','alias_name','visual_role','family','tech_kind'))
    low = raw.lower().replace('\\','/')
    suffix = Path(str(row['asset_path'] or '')).suffix.lower()
    if suffix in IMAGE_EXTS:
        return 'Graphique', 0.99, ['image-extension:'+suffix], 1
    if tech in DIRECT_TECH:
        return 'Graphique', 0.98, ['technical-kind:'+tech], 1
    hits=[t for t in DIRECT_PATH if t in low]
    if hits:
        return 'Graphique', min(0.96,0.82+0.03*len(hits)), ['visual-path:'+x for x in hits[:5]], 1
    if tech in COMPONENT_TECH:
        return 'Composant graphique', 0.94, ['technical-kind:'+tech], None
    hits=[t for t in COMPONENT_PATH if t in low]
    if hits:
        return 'Composant graphique', min(0.90,0.75+0.03*len(hits)), ['visual-component-path:'+x for x in hits[:5]], None
    if tech in NON_GRAPHIC_TECH:
        return 'Non graphique', 0.90, ['technical-kind:'+tech], 0
    hits=[t for t in NON_GRAPHIC_PATH if t in low]
    if hits:
        return 'Non graphique', min(0.90,0.76+0.03*len(hits)), ['non-graphic-path:'+x for x in hits[:5]], 0
    return 'Indéterminé', 0.0, ['insufficient-evidence'], None


def load_events():
    idx=json.loads(REGISTRY.read_text('utf-8')); by_id={}
    for spec in idx.get('files',[]):
        p=REGISTRY.parent/spec['path']
        if not p.is_file():
            print('V32_EVENT_REGISTRY_MISSING',p,flush=True); continue
        data=json.loads(p.read_text('utf-8'))
        for e in data.get('events',[]):
            toks={dense(t) for t in e.get('assetTokens',[]) if len(dense(t))>=5}
            if not toks: continue
            cur=by_id.setdefault(e['id'],{
                'id':e['id'],'name':e.get('name',e['id']),'kind':e.get('kind','event'),
                'phase':e.get('phase',''),'category':e.get('category',''),'cadence':e.get('cadence',''),
                'tokens':set(),'confidence':e.get('confidence','high')
            })
            cur['tokens'].update(toks)
            if e.get('confidence')=='medium':cur['confidence']='medium'
    out=[]
    for e in by_id.values():
        e['tokens']=sorted(e['tokens'],key=len,reverse=True);out.append(e)
    return sorted(out,key=lambda x:x['id'])


def ensure_columns(con):
    cols={r[1] for r in con.execute('pragma table_info(assets)')}
    for col,typ in {'graphic_class':'TEXT','graphic_conf':'REAL','graphic_evidence_json':'TEXT','is_graphic':'INTEGER'}.items():
        if col not in cols: con.execute(f'ALTER TABLE assets ADD COLUMN {col} {typ}')
    con.executescript('''
      DROP TABLE IF EXISTS event_registry_v32;
      DROP TABLE IF EXISTS event_asset_links_v32;
      CREATE TABLE event_registry_v32(
        event_id TEXT PRIMARY KEY,event_name TEXT,kind TEXT,phase TEXT,category TEXT,cadence TEXT,confidence TEXT,tokens_json TEXT
      );
      CREATE TABLE event_asset_links_v32(
        event_id TEXT,stable_id TEXT,relation TEXT,confidence REAL,evidence_json TEXT,
        PRIMARY KEY(event_id,stable_id,relation)
      );
      CREATE INDEX idx_event_links_asset_v32 ON event_asset_links_v32(stable_id);
      CREATE INDEX idx_event_links_event_v32 ON event_asset_links_v32(event_id,relation);
      CREATE INDEX IF NOT EXISTS idx_assets_graphic_class_v32 ON assets(graphic_class);
    ''')


def rebuild_facets(con):
    con.execute("DELETE FROM facets WHERE axis IN ('graphic_class','event_id','event_relation')")
    for value,count in con.execute("SELECT coalesce(graphic_class,'Indéterminé'),count(*) FROM assets GROUP BY coalesce(graphic_class,'Indéterminé')"):
        con.execute('INSERT INTO facets(axis,value,count) VALUES(?,?,?)',('graphic_class',value,count))
    for value,count in con.execute('SELECT event_id,count(distinct stable_id) FROM event_asset_links_v32 GROUP BY event_id'):
        con.execute('INSERT INTO facets(axis,value,count) VALUES(?,?,?)',('event_id',value,count))
    for value,count in con.execute('SELECT relation,count(*) FROM event_asset_links_v32 GROUP BY relation'):
        con.execute('INSERT INTO facets(axis,value,count) VALUES(?,?,?)',('event_relation',value,count))


def main():
    con=sqlite3.connect(DB); con.row_factory=sqlite3.Row;ensure_columns(con);events=load_events()
    con.executemany('INSERT OR REPLACE INTO event_registry_v32 VALUES(?,?,?,?,?,?,?,?)',[
        (e['id'],e['name'],e['kind'],e['phase'],e['category'],e['cadence'],e['confidence'],json.dumps(e['tokens'],separators=(',',':')))
        for e in events
    ])
    graphic_counts=Counter();event_counts=Counter();multi=0;total=0
    rows=con.execute('SELECT stable_id,asset_path,logical_name,alias_name,visual_role,family,tech_kind FROM assets')
    for row in rows:
        gclass,gconf,gev,isg=classify_graphic(row)
        con.execute('UPDATE assets SET graphic_class=?,graphic_conf=?,graphic_evidence_json=?,is_graphic=? WHERE stable_id=?',
                    (gclass,gconf,json.dumps(gev,ensure_ascii=False,separators=(',',':')),isg,row['stable_id']))
        graphic_counts[gclass]+=1
        hay=dense(' '.join(str(row[k] or '') for k in ('asset_path','logical_name','alias_name')));matched=[]
        for e in events:
            hits=[t for t in e['tokens'] if t in hay]
            if not hits: continue
            conf=0.99 if e['confidence']=='high' else 0.90
            ev={'source':'curated-asset-token','tokens':hits[:5],'phase':e['phase'],'category':e['category']}
            con.execute('INSERT OR IGNORE INTO event_asset_links_v32 VALUES(?,?,?,?,?)',
                        (e['id'],row['stable_id'],'belongs-to',conf,json.dumps(ev,ensure_ascii=False,separators=(',',':'))))
            event_counts[e['id']]+=1;matched.append(e['id'])
        if len(set(matched))>1:multi+=1
        total+=1
        if total%20000==0:print('V32_ENRICH_PROGRESS',total,flush=True)
    rebuild_facets(con);con.commit();linked=con.execute('SELECT count(*) FROM event_asset_links_v32').fetchone()[0];linked_assets=con.execute('SELECT count(distinct stable_id) FROM event_asset_links_v32').fetchone()[0];con.close()
    print('V32_GRAPHIC_COUNTS',json.dumps(graphic_counts,ensure_ascii=False),flush=True)
    print('V32_EVENT_DIRECT_READY',f'registryEvents={len(events)}',f'links={linked}',f'linkedAssets={linked_assets}',f'multiEventAssets={multi}',flush=True)
    print('V32_TOP_EVENTS',json.dumps(event_counts.most_common(30),ensure_ascii=False),flush=True)

if __name__=='__main__':main()
