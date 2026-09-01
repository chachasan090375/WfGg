#!/usr/bin/env python3
from pathlib import Path
import gzip, hashlib, json, sys

ROOT=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else Path(__file__).resolve().parents[1]
INDEX=ROOT/'frontend/lab/master-assets-v2/index'
MANIFEST=INDEX/'lastwar-visual-reconstruction-map-v1.manifest.json'
PARTS=INDEX/'lastwar-visual-reconstruction-map-v1.parts'
CACHE=Path.home()/'.cache/wfgg-lastwar-v31';CACHE.mkdir(parents=True,exist_ok=True)
PACK=CACHE/'lastwar-visual-reconstruction-map-v1.json.gz'


def sha256_file(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()


def pack():
    m=json.loads(MANIFEST.read_text('utf-8'));want=m['compressedSha256']
    if PACK.is_file() and sha256_file(PACK)==want:return m
    h=hashlib.sha256();tmp=PACK.with_suffix('.tmp.gz')
    with tmp.open('wb') as out:
        for part in m['parts']:
            p=PARTS/part['name']
            with p.open('rb') as f:
                for b in iter(lambda:f.read(1024*1024),b''):
                    h.update(b);out.write(b)
    assert h.hexdigest()==want,(h.hexdigest(),want)
    tmp.replace(PACK);return m


def iter_array_objects(key,limit=10,chunk_size=1<<20):
    decoder=json.JSONDecoder();marker='"'+key+'"';buf='';started=False;n=0
    with gzip.open(PACK,'rt',encoding='utf-8',errors='replace') as fh:
        while not started:
            chunk=fh.read(chunk_size)
            if not chunk:return
            buf+=chunk;pos=buf.find(marker)
            if pos<0:
                buf=buf[-max(len(marker)+32,128):];continue
            bracket=buf.find('[',pos+len(marker))
            while bracket<0:
                chunk=fh.read(chunk_size)
                if not chunk:return
                buf+=chunk;bracket=buf.find('[',pos+len(marker))
            buf=buf[bracket+1:];started=True
        while n<limit:
            i=0
            while i<len(buf) and (buf[i].isspace() or buf[i]==','):i+=1
            if i<len(buf) and buf[i]==']':return
            if i:buf=buf[i:]
            try:
                obj,end=decoder.raw_decode(buf);buf=buf[end:]
                if isinstance(obj,dict):
                    n+=1;yield obj
            except json.JSONDecodeError:
                chunk=fh.read(chunk_size)
                if not chunk:return
                buf+=chunk


def main():
    m=pack();print('PROBE_MANIFEST',json.dumps(m,ensure_ascii=False)[:4000])
    nodes=list(iter_array_objects('nodes',5));edges=list(iter_array_objects('edges',12))
    print('PROBE_NODE_COUNT',len(nodes));
    for i,o in enumerate(nodes):print('PROBE_NODE',i,json.dumps(o,ensure_ascii=False,separators=(',',':'))[:12000])
    print('PROBE_EDGE_COUNT',len(edges))
    for i,o in enumerate(edges):print('PROBE_EDGE',i,json.dumps(o,ensure_ascii=False,separators=(',',':'))[:12000])
    print('PROBE_NODE_KEYS',sorted({k for o in nodes for k in o.keys()}))
    print('PROBE_EDGE_KEYS',sorted({k for o in edges for k in o.keys()}))

if __name__=='__main__':main()
