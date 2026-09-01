#!/usr/bin/env python3
from pathlib import Path
from collections import Counter
import json,re,sqlite3,sys,unicodedata

ROOT=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else Path(__file__).resolve().parents[1]
DB=Path.home()/'.cache/wfgg-lastwar-v31/graphics-catalog-v31.sqlite3'
if not DB.is_file(): raise SystemExit(f'Catalogue absent: {DB}')

def norm(s):
    s=unicodedata.normalize('NFKD',str(s or '')).encode('ascii','ignore').decode().lower()
    return re.sub(r'[^a-z0-9]+',' ',s).strip()

def word_hit(text,words):
    toks=set(norm(text).split())
    return next((w for w in words if w in toks),None)

# Region/language is accepted only on an explicit delimited language marker.
# This intentionally rejects substring matches such as "en" inside ordinary names.
region_rx=re.compile(r'(?i)(?:^|[_\-./])(jp|kr|cn|tw|en|fr|it|es)(?=$|[_\-./0-9])')
generic_words={'common','shared','global','generic','default'}
feature_map=[
 ('formation',{'formation','squad','herosquad','squadequip'}),
 ('hero',{'hero','heroshow','herodetail','heroexhibit'}),
 ('alliance',{'alliance','guild'}),
 ('inventory',{'inventory','bag','warehouse'}),
 ('shop',{'shop','store','mall'}),
 ('world-map',{'worldmap','bigmap'}),
 ('base',{'basebuilding','headquarter','headquarters','hq'})
]

con=sqlite3.connect(DB);con.row_factory=sqlite3.Row
rows=con.execute("SELECT stable_id,asset_path,logical_name,alias_name,evidence_json FROM assets WHERE scope_kind='regional'").fetchall()
kept=corrected=0
for r in rows:
    raw=' '.join(str(r[k] or '') for k in ('asset_path','logical_name','alias_name'))
    m=region_rx.search(raw)
    try:ev=json.loads(r['evidence_json'] or '{}')
    except Exception:ev={}
    if m:
        lang=m.group(1).lower();ev['scope']=['explicit-region-marker:'+m.group(0)]
        con.execute("UPDATE assets SET scope_kind='regional',scope_id=?,scope_name=?,scope_conf=?,evidence_json=? WHERE stable_id=?",(lang,lang.upper(),0.96,json.dumps(ev,ensure_ascii=False,separators=(',',':')),r['stable_id']))
        kept+=1;continue
    text=norm(raw);kind='unknown';sid='';name='';conf=0.0;evidence=[]
    g=word_hit(text,generic_words)
    if g:
        kind='generic';sid='generic';name='Jeu générique';conf=.80;evidence=['explicit-generic-token:'+g]
    else:
        toks=set(text.split())
        for fid,terms in feature_map:
            hit=next((t for t in terms if t in toks),None)
            if hit:
                kind='feature';sid=fid;name=fid;conf=.75;evidence=['permanent-feature-token:'+hit];break
    ev['scope']=evidence
    ev['scopeCorrection']='regional-substring-false-positive-removed'
    con.execute('UPDATE assets SET scope_kind=?,scope_id=?,scope_name=?,scope_period=?,scope_conf=?,evidence_json=? WHERE stable_id=?',(kind,sid,name,'',conf,json.dumps(ev,ensure_ascii=False,separators=(',',':')),r['stable_id']))
    corrected+=1

con.execute("DELETE FROM facets WHERE axis IN ('scope_kind','scope_id')")
for axis in ('scope_kind','scope_id'):
    counts=Counter()
    for value,count in con.execute(f'SELECT {axis},count(*) FROM assets GROUP BY {axis}'):
        counts[value or 'unknown']=count
    con.executemany('INSERT INTO facets(axis,value,count) VALUES(?,?,?)',[(axis,k,v) for k,v in counts.items()])
con.commit()
counts=con.execute('SELECT scope_kind,count(*) FROM assets GROUP BY scope_kind ORDER BY count(*) DESC').fetchall()
con.close()
print('V31_SCOPE_CORRECT_READY',f'regionalKept={kept}',f'falseRegionalCorrected={corrected}',f'scopes={counts}',flush=True)
