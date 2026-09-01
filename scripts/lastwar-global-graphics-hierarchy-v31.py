#!/usr/bin/env python3
from pathlib import Path
from collections import Counter,defaultdict
import hashlib,json,re,sqlite3,sys

ROOT=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else Path(__file__).resolve().parents[1]
DB=Path.home()/'.cache/wfgg-lastwar-v31/graphics-catalog-v31.sqlite3'
if not DB.is_file(): raise SystemExit(f'Catalogue absent: {DB}')

def node_id(path): return 'LWPATH-'+hashlib.sha1(path.encode('utf-8','replace')).hexdigest()[:14].upper()
def clean_path(s):
    s=str(s or '').strip().replace('\\','/')
    s=re.sub(r'/+','/',s).strip('/')
    return s

con=sqlite3.connect(DB);con.row_factory=sqlite3.Row
cols={r[1] for r in con.execute('pragma table_info(assets)')}
if 'path_node_id' not in cols: con.execute('ALTER TABLE assets ADD COLUMN path_node_id TEXT')
con.executescript('''
DROP TABLE IF EXISTS path_nodes;
CREATE TABLE path_nodes(
 node_id TEXT PRIMARY KEY,parent_id TEXT,name TEXT,full_path TEXT UNIQUE,depth INTEGER,node_type TEXT,
 direct_assets INTEGER,total_assets INTEGER,family_counts_json TEXT,scope_counts_json TEXT
);
CREATE INDEX idx_path_nodes_parent ON path_nodes(parent_id);
CREATE INDEX idx_assets_path_node ON assets(path_node_id);
''')

nodes={}
direct=Counter(); families=defaultdict(Counter); scopes=defaultdict(Counter); asset_leaf={}
root_id=node_id('');nodes['']=(root_id,None,'','',0,'root')
rows=con.execute('SELECT stable_id,asset_path,logical_name,alias_name,family,scope_kind FROM assets')
for r in rows:
    raw=clean_path(r['asset_path']) or clean_path(r['logical_name']) or clean_path(r['alias_name'])
    if not raw: raw='__unpathed__/'+r['stable_id']
    parts=[p for p in raw.split('/') if p]
    parent_path='';parent=root_id
    for i,part in enumerate(parts):
        full='/'.join(parts[:i+1]);nid=node_id(full);typ='file' if i==len(parts)-1 else 'folder'
        if full not in nodes: nodes[full]=(nid,parent,part,full,i+1,typ)
        parent_path=full;parent=nid
        families[full][r['family'] or 'unknown']+=1;scopes[full][r['scope_kind'] or 'unknown']+=1
    leaf=parent if parts else root_id
    direct[raw]+=1;asset_leaf[r['stable_id']]=leaf
    families[''][r['family'] or 'unknown']+=1;scopes[''][r['scope_kind'] or 'unknown']+=1

children=defaultdict(list)
for full,(nid,pid,name,path,depth,typ) in nodes.items():
    if pid: children[pid].append(nid)
id_to_path={v[0]:k for k,v in nodes.items()}
totals={}
def total(nid):
    if nid in totals:return totals[nid]
    full=id_to_path[nid];n=direct.get(full,0)+sum(total(c) for c in children.get(nid,[]));totals[nid]=n;return n
total(root_id)

payload=[]
for full,(nid,pid,name,path,depth,typ) in nodes.items():
    payload.append((nid,pid,name,path,depth,typ,direct.get(full,0),totals.get(nid,0),json.dumps(families.get(full,{}),ensure_ascii=False,separators=(',',':')),json.dumps(scopes.get(full,{}),ensure_ascii=False,separators=(',',':'))))
con.executemany('INSERT INTO path_nodes VALUES(?,?,?,?,?,?,?,?,?,?)',payload)
con.executemany('UPDATE assets SET path_node_id=? WHERE stable_id=?',[(nid,sid) for sid,nid in asset_leaf.items()])
con.commit();con.close()
print('V31_HIERARCHY_READY',f'nodes={len(payload)}',f'assets={len(asset_leaf)}',flush=True)
