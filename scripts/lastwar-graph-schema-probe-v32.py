#!/usr/bin/env python3
from pathlib import Path
import gzip, hashlib, json, sys, time

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


def main():
    m=pack();print('PROBE_MANIFEST',json.dumps(m,ensure_ascii=False)[:4000],flush=True)
    t=time.time()
    with gzip.open(PACK,'rt',encoding='utf-8',errors='strict') as fh:data=json.load(fh)
    print('PROBE_FULL_LOAD_SECONDS',round(time.time()-t,3),flush=True)
    print('PROBE_TOP_TYPE',type(data).__name__,flush=True)
    if not isinstance(data,dict):
        print('PROBE_TOP_SAMPLE',repr(data)[:12000]);return
    print('PROBE_TOP_KEYS',list(data.keys()),flush=True)
    for k,v in data.items():
        desc={'type':type(v).__name__}
        try:desc['len']=len(v)
        except Exception:pass
        print('PROBE_TOP_FIELD',k,json.dumps(desc),flush=True)
        if isinstance(v,list) and v:
            for i,item in enumerate(v[:3]):
                print('PROBE_LIST_SAMPLE',k,i,json.dumps(item,ensure_ascii=False,separators=(',',':'))[:16000],flush=True)
            if isinstance(v[0],dict):
                print('PROBE_LIST_KEYS',k,sorted({kk for item in v[:50] if isinstance(item,dict) for kk in item.keys()}),flush=True)
        elif isinstance(v,dict):
            print('PROBE_DICT_KEYS',k,list(v.keys())[:100],flush=True)
            for kk,vv in list(v.items())[:3]:print('PROBE_DICT_SAMPLE',k,kk,json.dumps(vv,ensure_ascii=False,separators=(',',':'))[:8000],flush=True)

if __name__=='__main__':main()
