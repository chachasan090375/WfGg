#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
from collections import Counter, defaultdict
import gzip, hashlib, json, os, re, sqlite3, sys, time, unicodedata

ROOT=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else Path(__file__).resolve().parents[1]
INDEX=ROOT/'frontend/lab/master-assets-v2/index'
MANIFEST=INDEX/'lastwar-visual-reconstruction-map-v1.manifest.json'
PARTS=INDEX/'lastwar-visual-reconstruction-map-v1.parts'
REGISTRY=ROOT/'data/lastwar/event-registry-v1.json'
CACHE=Path.home()/'.cache/wfgg-lastwar-v31'
DB=CACHE/'graphics-catalog-v31.sqlite3'
PACK=CACHE/'lastwar-visual-reconstruction-map-v1.json.gz'
SUMMARY=CACHE/'event-graph-crosswalk-v32-summary.json'

if not MANIFEST.is_file(): raise SystemExit(f'Manifest graph absent: {MANIFEST}')
if not REGISTRY.is_file(): raise SystemExit(f'Registre absent: {REGISTRY}')
if not DB.is_file(): raise SystemExit(f'Catalogue absent: {DB}')


def dense(s):
    s=unicodedata.normalize('NFKD',str(s or '')).encode('ascii','ignore').decode().lower()
    return re.sub(r'[^a-z0-9]+','',s)


def clean_raw(s): return str(s or '').strip().replace('\\','/').lower()


def load_registry():
    idx=json.loads(REGISTRY.read_text('utf-8')); events={}; token_to_events=defaultdict(set)
    for spec in idx.get('files',[]):
        p=REGISTRY.parent/spec['path']
        if not p.is_file(): continue
        for e in json.loads(p.read_text('utf-8')).get('events',[]):
            events[e['id']]={'name':e.get('name',e['id']),'kind':e.get('kind','event'),'phase':e.get('phase','')}
            for tok in e.get('assetTokens',[]):
                t=dense(tok)
                if len(t)>=5: token_to_events[t].add(e['id'])
    return events,token_to_events


def rebuild_pack():
    m=json.loads(MANIFEST.read_text('utf-8'))
    expected=m.get('compressedSha256','')
    if PACK.is_file():
        h=hashlib.sha256(PACK.read_bytes()).hexdigest()
        if h==expected:return m
    tmp=PACK.with_suffix('.tmp.gz'); h=hashlib.sha256()
    with tmp.open('wb') as out:
        for part in m['parts']:
            p=PARTS/part['name']; hp=hashlib.sha256()
            with p.open('rb') as f:
                while True:
                    b=f.read(1024*1024)
                    if not b:break
                    hp.update(b);h.update(b);out.write(b)
            if hp.hexdigest()!=part['sha256']:raise RuntimeError(f'Hash part invalide: {p}')
    if h.hexdigest()!=expected:raise RuntimeError('Hash gzip assemblé invalide')
    tmp.replace(PACK);return m


class CharReader:
    def __init__(self,fh,chunk=1<<16):self.fh=fh;self.chunk=chunk;self.buf='';self.i=0;self.eof=False
    def get(self):
        if self.i>=len(self.buf):
            self.buf=self.fh.read(self.chunk);self.i=0
            if not self.buf:self.eof=True;return ''
        c=self.buf[self.i];self.i+=1;return c


def seek_marker(r,marker):
    q=''
    while not r.eof:
        c=r.get()
        if not c:return False
        q=(q+c)[-len(marker):]
        if q==marker:return True
    return False


def iter_array_objects(key):
    with gzip.open(PACK,'rt',encoding='utf-8',errors='replace') as fh:
        r=CharReader(fh);marker='"'+key+'"'
        if not seek_marker(r,marker):return
        while True:
            c=r.get()
            if not c:return
            if c=='[':break
        while True:
            c=r.get()
            while c and (c.isspace() or c==','):c=r.get()
            if not c or c==']':return
            if c not in '{[':
                # Skip scalar values defensively.
                while c and c not in ',]':c=r.get()
                if c==']':return
                continue
            buf=[c];depth=1;instr=False;esc=False
            while depth:
                c=r.get()
                if not c:return
                buf.append(c)
                if instr:
                    if esc:esc=False
                    elif c=='\\':esc=True
                    elif c=='"':instr=False
                else:
                    if c=='"':instr=True
                    elif c in '{[':depth+=1
                    elif c in '}]':depth-=1
            try: yield json.loads(''.join(buf))
            except Exception: continue


def nid(obj):
    for k in ('id','nodeId','node_id','key'):
        if k in obj and obj[k] is not None:return str(obj[k])
    return ''


def edge_parts(e):
    s=t=rel=''
    for k in ('source','from','src','sourceId','source_id'):
        if k in e:s=str(e[k]);break
    for k in ('target','to','dst','targetId','target_id'):
        if k in e:t=str(e[k]);break
    for k in ('relation','type','kind','label'):
        if k in e:rel=str(e[k]);break
    conf=str(e.get('confidence','')).lower()
    candidate=bool(e.get('candidate',False)) or rel in {'candidate','candidate_contains'} or conf=='candidate'
    return s,t,rel,candidate


def merge_relation(old,new):
    rank={'candidate':0,'used-by':1,'belongs-to':2}
    return new if rank.get(new,0)>rank.get(old,-1) else old


def strings_in(obj):
    stack=[obj]
    while stack:
        x=stack.pop()
        if isinstance(x,str):yield x
        elif isinstance(x,dict):stack.extend(x.values())
        elif isinstance(x,list):stack.extend(x)


def main():
    start=time.time();m=rebuild_pack();events,tokmap=load_registry()
    tokens=sorted(tokmap,key=len,reverse=True)
    rx=re.compile('|'.join(re.escape(t) for t in tokens)) if tokens else None
    links={} # (event,node)-> relation
    seed_evidence={}
    node_count=seed_nodes=0
    for node in iter_array_objects('nodes'):
        node_count+=1; nodeid=nid(node)
        if not nodeid or not rx:continue
        text=dense(json.dumps(node,ensure_ascii=False,separators=(',',':')))
        found={m.group(0) for m in rx.finditer(text)}
        if not found:continue
        evs=set();
        for tok in found:evs.update(tokmap[tok])
        for ev in evs:
            links[(ev,nodeid)]='belongs-to';seed_evidence[(ev,nodeid)]=sorted(t for t in found if ev in tokmap[t])[:8]
        seed_nodes+=1
    print('V32_GRAPH_SEEDS',f'nodes={node_count}',f'seedNodes={seed_nodes}',f'eventNodeLinks={len(links)}',flush=True)

    # Three bounded passes: ownership/container closure, one exact dependency hop,
    # then contents of those dependency bundles. Candidate edges never propagate.
    allowed_same={'contains','stored_in','groups'}
    for passno in range(1,4):
        changed=0
        snapshot=dict(links)
        for e in iter_array_objects('edges'):
            s,t,rel,candidate=edge_parts(e)
            if candidate or not s or not t:continue
            if rel in allowed_same:
                for (ev,node),r0 in list(snapshot.items()):
                    if node==s:
                        key=(ev,t);new=r0;old=links.get(key)
                        merged=merge_relation(old,new)
                        if merged!=old:links[key]=merged;changed+=1
                    elif node==t:
                        key=(ev,s);new=r0;old=links.get(key)
                        merged=merge_relation(old,new)
                        if merged!=old:links[key]=merged;changed+=1
            elif rel=='depends_on':
                for (ev,node),r0 in list(snapshot.items()):
                    if node==s:
                        key=(ev,t);new='used-by';old=links.get(key)
                        merged=merge_relation(old,new)
                        if merged!=old:links[key]=merged;changed+=1
        print('V32_GRAPH_PROPAGATE',f'pass={passno}',f'changed={changed}',f'links={len(links)}',flush=True)
        if not changed:break

    relevant_nodes={node for _,node in links}
    node_meta={}
    for node in iter_array_objects('nodes'):
        nodeid=nid(node)
        if nodeid in relevant_nodes:node_meta[nodeid]=node
    print('V32_GRAPH_NODE_META',f'relevant={len(relevant_nodes)}',f'resolved={len(node_meta)}',flush=True)

    con=sqlite3.connect(DB);con.row_factory=sqlite3.Row
    # Exact textual reverse index from the canonical 107k catalog.
    exact=defaultdict(set);base=defaultdict(set)
    for r in con.execute('SELECT stable_id,asset_path,logical_name,alias_name FROM assets'):
        sid=r['stable_id']
        for k in ('asset_path','logical_name','alias_name'):
            raw=clean_raw(r[k])
            if not raw:continue
            exact[raw].add(sid)
            bn=raw.rsplit('/',1)[-1]
            if len(bn)>=8:base[bn].add(sid)
    inserted=updated=0;relation_counts=Counter();event_counts=Counter()
    for (ev,nodeid),relation in links.items():
        node=node_meta.get(nodeid)
        if not node:continue
        sids=set();evidence_strings=[]
        for s in strings_in(node):
            raw=clean_raw(s)
            if not raw:continue
            if raw in exact:sids.update(exact[raw]);evidence_strings.append(raw)
            bn=raw.rsplit('/',1)[-1]
            if len(bn)>=8 and len(base.get(bn,()))==1:sids.update(base[bn]);evidence_strings.append('basename:'+bn)
        for sid in sids:
            existing=con.execute('SELECT relation,confidence FROM event_asset_links_v32 WHERE event_id=? AND stable_id=? ORDER BY confidence DESC LIMIT 1',(ev,sid)).fetchone()
            target=relation
            if existing and existing['relation']=='belongs-to':target='belongs-to'
            conf=0.995 if target=='belongs-to' else 0.88
            evd={'source':'exact-reconstruction-graph','graphNode':nodeid,'relation':target,'strings':evidence_strings[:8],'seedTokens':seed_evidence.get((ev,nodeid),[])}
            before=con.total_changes
            con.execute('INSERT OR REPLACE INTO event_asset_links_v32(event_id,stable_id,relation,confidence,evidence_json) VALUES(?,?,?,?,?)',(ev,sid,target,conf,json.dumps(evd,ensure_ascii=False,separators=(',',':'))))
            if con.total_changes>before:inserted+=1
            relation_counts[target]+=1;event_counts[ev]+=1

    con.execute("DELETE FROM facets WHERE axis IN ('event_id','event_relation')")
    for value,count in con.execute('SELECT event_id,count(distinct stable_id) FROM event_asset_links_v32 GROUP BY event_id'):
        con.execute('INSERT INTO facets(axis,value,count) VALUES(?,?,?)',('event_id',value,count))
    for value,count in con.execute('SELECT relation,count(*) FROM event_asset_links_v32 GROUP BY relation'):
        con.execute('INSERT INTO facets(axis,value,count) VALUES(?,?,?)',('event_relation',value,count))
    con.commit()
    final_links=con.execute('SELECT count(*) FROM event_asset_links_v32').fetchone()[0]
    final_assets=con.execute('SELECT count(distinct stable_id) FROM event_asset_links_v32').fetchone()[0]
    con.close()
    summary={
      'schemaVersion':32,'generatedAt':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
      'graphUncompressedBytes':m.get('uncompressedBytes'),'registryEvents':len(events),'seedNodes':seed_nodes,
      'graphRelatedNodes':len(relevant_nodes),'resolvedNodeMetadata':len(node_meta),'mappedWrites':inserted,
      'eventAssetLinks':final_links,'eventLinkedAssets':final_assets,'relationCounts':dict(relation_counts),
      'topEvents':event_counts.most_common(40),'seconds':round(time.time()-start,2),
      'policy':'candidate edges never propagate; belongs-to outranks used-by; dependency propagation bounded to 3 passes'
    }
    SUMMARY.write_text(json.dumps(summary,ensure_ascii=False,indent=2),'utf-8')
    print('V32_EVENT_GRAPH_READY',json.dumps(summary,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
