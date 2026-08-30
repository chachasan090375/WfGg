#!/data/data/com.termux/files/usr/bin/env python
from __future__ import annotations
from pathlib import Path
import gzip,hashlib,json,sys

ROOT=Path(__file__).resolve().parents[1]
IDX=ROOT/'frontend/lab/master-assets-v2/index'
RAW=Path(sys.argv[1]) if len(sys.argv)>1 else IDX/'lastwar-visual-reconstruction-map-v1.json'
MANIFEST=IDX/'lastwar-visual-reconstruction-map-v1.manifest.json'
PARTDIR=IDX/'lastwar-visual-reconstruction-map-v1.parts'
TMP=IDX/'.lastwar-visual-reconstruction-map-v1.json.gz.tmp'
MAX_PART=48*1024*1024

if not RAW.is_file():
    raise SystemExit(f'RAW_MAP_ABSENT {RAW}')

PARTDIR.mkdir(parents=True,exist_ok=True)
for p in PARTDIR.iterdir():
    if p.is_file(): p.unlink()

raw_hash=hashlib.sha256()
raw_bytes=0
with RAW.open('rb') as src, TMP.open('wb') as dst:
    with gzip.GzipFile(fileobj=dst,mode='wb',compresslevel=9,mtime=0) as gz:
        while True:
            chunk=src.read(1024*1024)
            if not chunk: break
            raw_hash.update(chunk); raw_bytes+=len(chunk); gz.write(chunk)

gz_hash=hashlib.sha256()
gz_bytes=0
with TMP.open('rb') as f:
    while True:
        chunk=f.read(1024*1024)
        if not chunk: break
        gz_hash.update(chunk); gz_bytes+=len(chunk)

parts=[]
with TMP.open('rb') as src:
    i=0
    while True:
        chunk=src.read(MAX_PART)
        if not chunk: break
        name=f'part-{i:03d}.bin'
        path=PARTDIR/name
        path.write_bytes(chunk)
        parts.append({'name':name,'bytes':len(chunk),'sha256':hashlib.sha256(chunk).hexdigest()})
        i+=1

manifest={
    'format':'WFGG_LASTWAR_VISUAL_RECONSTRUCTION_MAP_PACK_V1',
    'codec':'gzip',
    'maxPartBytes':MAX_PART,
    'rawFileName':RAW.name,
    'uncompressedBytes':raw_bytes,
    'uncompressedSha256':raw_hash.hexdigest(),
    'compressedBytes':gz_bytes,
    'compressedSha256':gz_hash.hexdigest(),
    'parts':parts,
    'loadRule':'Concatenate parts in listed order, verify compressed SHA256, gzip-decompress, verify uncompressed SHA256, then parse JSON.',
    'githubSafe':all(x['bytes'] < 100*1024*1024 for x in parts),
}
MANIFEST.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n','utf-8')
TMP.unlink(missing_ok=True)
RAW.unlink(missing_ok=True)

print('LASTWAR_RECONSTRUCTION_MAP_PACK_OK',f'raw={raw_bytes}',f'gzip={gz_bytes}',f'parts={len(parts)}',f'maxPart={max((x["bytes"] for x in parts),default=0)}')
print('MANIFEST',MANIFEST)
print('PARTDIR',PARTDIR)
