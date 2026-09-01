#!/usr/bin/env python3
from pathlib import Path
from collections import Counter
import json,re,sqlite3,sys,unicodedata

ROOT=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else Path(__file__).resolve().parents[1]
DB=Path.home()/'.cache/wfgg-lastwar-v31/graphics-catalog-v31.sqlite3'
TAX=ROOT/'frontend/lab/global-graphics-v31/taxonomy-v31.json'
if not DB.is_file(): raise SystemExit(f'Catalogue absent: {DB}')
tax=json.loads(TAX.read_text('utf-8'))

def norm(s):
    s=unicodedata.normalize('NFKD',str(s or '')).encode('ascii','ignore').decode().lower()
    return re.sub(r'[^a-z0-9]+',' ',s).strip()

def match_expr(alias):
    toks=[t for t in norm(alias).split() if len(t)>1 and t not in {'de','du','des','le','la','les','the','of','and'}]
    if not toks:return None,[]
    return ' AND '.join('"'+t+'"' for t in toks),toks

con=sqlite3.connect(DB)
con.row_factory=sqlite3.Row
known=tax.get('knownScopes',[])
changed=0
for scope in known:
    ids=set()
    aliases=list(scope.get('aliases') or [])+[scope.get('id',''),scope.get('name','')]
    for alias in aliases:
        expr,toks=match_expr(alias)
        if not expr:continue
        try:
            for r in con.execute('SELECT stable_id FROM asset_fts WHERE asset_fts MATCH ?',(expr,)): ids.add(r['stable_id'])
        except sqlite3.OperationalError:
            like='%'+norm(alias)+'%'
            for r in con.execute('SELECT stable_id FROM assets WHERE lower(search_text) LIKE ?',(like,)): ids.add(r['stable_id'])
    if not ids:continue
    evidence='manual-known-scope:'+scope.get('id','')
    for sid in ids:
        row=con.execute('SELECT evidence_json FROM assets WHERE stable_id=?',(sid,)).fetchone()
        try: ev=json.loads(row['evidence_json'] or '{}') if row else {}
        except Exception: ev={}
        sev=list(ev.get('scope') or [])
        if evidence not in sev:sev.append(evidence)
        ev['scope']=sev
        ev['scopeRecurrence']=scope.get('recurrence','')
        con.execute('UPDATE assets SET scope_kind=?,scope_id=?,scope_name=?,scope_period=?,scope_conf=?,evidence_json=? WHERE stable_id=?',(
            scope.get('kind','event'),scope.get('id',''),scope.get('name',''),scope.get('recurrence',''),0.99,json.dumps(ev,ensure_ascii=False,separators=(',',':')),sid))
        changed+=1

# If the asset itself explicitly says recurring/weekly/monthly and it was already
# proven to be an event, promote only the lifecycle facet; never invent an event id.
recurring=[norm(x) for x in tax.get('scopeDiscovery',{}).get('recurringTokens',[]) if norm(x)]
for tok in recurring:
    rows=con.execute("SELECT stable_id,evidence_json FROM assets WHERE scope_kind='event' AND lower(search_text) LIKE ?",('%'+tok+'%',)).fetchall()
    for row in rows:
        try:ev=json.loads(row['evidence_json'] or '{}')
        except Exception:ev={}
        sev=list(ev.get('scope') or []); marker='recurrence-token:'+tok
        if marker not in sev:sev.append(marker)
        ev['scope']=sev
        con.execute("UPDATE assets SET scope_kind='recurring-event',scope_conf=max(scope_conf,0.90),evidence_json=? WHERE stable_id=?",(json.dumps(ev,ensure_ascii=False,separators=(',',':')),row['stable_id']))
        changed+=1

# Rebuild only scope facets after enrichment.
con.execute("DELETE FROM facets WHERE axis IN ('scope_kind','scope_id')")
for axis in ('scope_kind','scope_id'):
    counts=Counter()
    for value,count in con.execute(f'SELECT {axis},count(*) FROM assets GROUP BY {axis}'):
        counts[value or 'unknown']=count
    con.executemany('INSERT INTO facets(axis,value,count) VALUES(?,?,?)',[(axis,k,v) for k,v in counts.items()])
con.commit();con.close()
print('V31_SCOPE_ENRICH_READY',f'updates={changed}',flush=True)
