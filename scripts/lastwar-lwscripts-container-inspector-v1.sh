#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
RAW="$ROOT/frontend/lab/master-assets-v2/runtime-lua/raw"
IL="$ROOT/frontend/lab/master-assets-v2/meta/lwlua-container-il-trace-v1.json"
OUT="$ROOT/frontend/lab/formation-lua-trace-viewer-data/lwscripts-container-inspector-v1.json"
META="$ROOT/frontend/lab/master-assets-v2/meta/lwscripts-container-inspector-v1.json"
fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
[[ -s "$RAW/LWScripts.data" ]] || fail "LWScripts.data absent"
command -v python >/dev/null 2>&1 || fail "python absent"
mkdir -p "$(dirname "$OUT")" "$(dirname "$META")"
python - "$RAW" "$IL" "$OUT" "$META" <<'PY'
from __future__ import annotations
from pathlib import Path
import collections,hashlib,json,math,re,struct,sys,zlib
raw,ilp,out,meta=map(Path,sys.argv[1:])
data_path=raw/'LWScripts.data'

def entropy(b:bytes):
    if not b:return 0.0
    c=collections.Counter(b); n=len(b)
    return -sum((v/n)*math.log2(v/n) for v in c.values())

def text_view(p:Path):
    b=p.read_bytes() if p.exists() else b''
    dec=[]
    for enc in ('utf-8','utf-16le','utf-16be','latin-1'):
        try:
            s=b.decode(enc)
            printable=sum(ch.isprintable() or ch in '\r\n\t' for ch in s)/max(1,len(s))
            if printable>.75: dec.append({'encoding':enc,'score':round(printable,4),'text':s})
        except:pass
    return {'name':p.name,'bytes':len(b),'hex':b.hex(),'decodings':dec}

def strings(b:bytes, limit=80):
    arr=[]
    for m in re.finditer(rb'[\x20-\x7e]{6,}',b):
        arr.append({'offset':m.start(),'text':m.group().decode('ascii','replace')[:500]})
        if len(arr)>=limit:break
    return arr

size=data_path.stat().st_size
with data_path.open('rb') as f:
    head=f.read(min(size,1024*1024))
    f.seek(max(0,size//2-512*1024)); middle=f.read(min(size,1024*1024))
    f.seek(max(0,size-1024*1024)); tail=f.read(min(size,1024*1024))

patterns={
 'ZIP':b'PK\x03\x04','ZIP_EOCD':b'PK\x05\x06','GZIP':b'\x1f\x8b','LZ4_FRAME':b'\x04\x22\x4d\x18',
 'ZSTD':b'\x28\xb5\x2f\xfd','XZ':b'\xfd7zXZ\x00','BZIP2':b'BZh','UNITYFS':b'UnityFS','LUAC':b'\x1bLua','CHACHA_ASCII':b'ChaCha'
}
# Signature search by streaming chunks, exact offsets; cap occurrences per type.
occ={k:[] for k in patterns}
chunk_size=4*1024*1024
maxpat=max(map(len,patterns.values()))
with data_path.open('rb') as f:
    base=0; carry=b''
    while True:
        chunk=f.read(chunk_size)
        if not chunk:break
        blob=carry+chunk; origin=base-len(carry)
        for k,pat in patterns.items():
            if len(occ[k])>=40:continue
            start=0
            while len(occ[k])<40:
                i=blob.find(pat,start)
                if i<0:break
                off=origin+i
                if off>=0 and (not occ[k] or occ[k][-1]!=off):occ[k].append(off)
                start=i+1
        base+=len(chunk);carry=blob[-(maxpat-1):] if maxpat>1 else b''

# Plausible zlib headers: don't full-scan every 0x78 byte; sample first/last 16 MiB and verify CMF/FLG checksum.
zlib_offsets=[]
def scan_zlib_region(blob:bytes, origin:int):
    for i in range(len(blob)-1):
        if blob[i]==0x78 and ((blob[i]<<8)+blob[i+1])%31==0 and (blob[i]&0x0f)==8:
            off=origin+i
            if off not in zlib_offsets:zlib_offsets.append(off)
            if len(zlib_offsets)>=80:return
scan_zlib_region(head,0)
if len(zlib_offsets)<80:scan_zlib_region(tail,max(0,size-len(tail)))

# Probe whether candidate compressed streams actually inflate for a few headers.
probes=[]
for off in zlib_offsets[:12]:
    try:
        with data_path.open('rb') as f:f.seek(off); sample=f.read(min(8*1024*1024,size-off))
        dz=zlib.decompressobj(); outb=dz.decompress(sample,512*1024)
        probes.append({'kind':'zlib','offset':off,'ok':bool(outb),'outBytes':len(outb),'outHeadHex':outb[:32].hex(),'outStrings':strings(outb[:128*1024],12)})
    except Exception as e:probes.append({'kind':'zlib','offset':off,'ok':False,'error':type(e).__name__+':'+str(e)[:180]})

# Integer interpretations of first bytes can reveal length-prefixed custom containers.
ints=[]
for endian,fmt in [('le','<'),('be','>')]:
    vals=[]
    for width,code in [(2,'H'),(4,'I'),(8,'Q')]:
        if len(head)>=width:
            try:vals.append({'width':width,'value':struct.unpack(fmt+code,head[:width])[0]})
            except:pass
    ints.append({'endian':endian,'values':vals})

# Pull exact loader/update method evidence already recovered from DLL.
methods=[]
if ilp.exists():
    try:
        d=json.loads(ilp.read_text('utf-8'))
        rows=d.get('exactBoundaryMethodIL') or []
        wanted=('LWLuaFile.Load','LWLuaFile._Load','LWLuaFile.LoadFile','LWLuaFileUpdate.InitFileOnAppStart','LWLuaFileUpdate.ApplyUpdate','LWLuaFileUpdate.SaveUpdateFile','LWLuaFileUpdateParallel.th_LwScriptLoad','LWLuaFileUpdateParallel.mt_LwScriptSwap')
        for r in rows:
            sym=str(r.get('symbol') or '')
            if sym in wanted:
                methods.append({'symbol':sym,'rid':r.get('rid'),'strings':r.get('strings') or [],'internalCalls':r.get('internalCalls') or [],'externalCalls':r.get('externalCalls') or []})
    except Exception as e:methods=[{'error':type(e).__name__+':'+str(e)}]

# Method call keyword summary for instant classification.
kw=('zip','gzip','deflate','compress','decompress','inflate','lz4','zstd','decrypt','encrypt','chacha','aes','crc','stream','memory','file','binary','reader','writer')
call_hits=[]
for m in methods:
    for c in [*(m.get('internalCalls') or []),*(m.get('externalCalls') or [])]:
        if any(k in str(c).lower() for k in kw): call_hits.append({'method':m.get('symbol'),'call':c})

result={
 'format':'WFGG_LASTWAR_LWSCRIPTS_CONTAINER_INSPECTOR_V1',
 'smallFiles':[text_view(raw/'lua'),text_view(raw/'lua.version'),text_view(raw/'LWScripts.txt')],
 'data':{'path':str(data_path),'bytes':size,'sha256':hashlib.sha256(data_path.read_bytes()).hexdigest(),
         'headHex':head[:256].hex(),'tailHex':tail[-256:].hex(),'headEntropy':round(entropy(head),5),'middleEntropy':round(entropy(middle),5),'tailEntropy':round(entropy(tail),5),
         'headStrings':strings(head[:512*1024],60),'tailStrings':strings(tail[-512*1024:],60),'integerViews':ints,
         'signatureOffsets':occ,'zlibHeaderOffsets':zlib_offsets,'decompressionProbes':probes},
 'methods':methods,'compressionCryptoCallHits':call_hits,
 'verdictHints':{
   'highEntropy': all(entropy(x)>7.5 for x in (head,middle,tail)),
   'hasKnownContainerSignature': any(v for v in occ.values()),
   'hasVerifiedZlibProbe': any(p.get('ok') for p in probes),
   'next':'Prefer exact loader/update calls and small metadata semantics over blind carving.'
 }
}
text=json.dumps(result,ensure_ascii=False,indent=2)+'\n';out.write_text(text,'utf-8');meta.write_text(text,'utf-8')
print('LWSCRIPTS_CONTAINER_INSPECTOR_V1_READY')
print(f"DATA bytes={size} entropy={result['data']['headEntropy']}/{result['data']['middleEntropy']}/{result['data']['tailEntropy']} knownSigs={sum(len(v) for v in occ.values())} zlibCandidates={len(zlib_offsets)} verifiedZlib={sum(1 for p in probes if p.get('ok'))}")
for sf in result['smallFiles']:
    best=(sf['decodings'][0]['text'] if sf['decodings'] else '').replace('\n','\\n').replace('\r','\\r')
    print(f"TEXT {sf['name']} bytes={sf['bytes']} :: {best[:500]}")
print(f"METHODS={len(methods)} callHits={len(call_hits)}")
for h in call_hits[:40]:print(f"CALLHIT {h['method']} :: {h['call']}")
print('JSON='+str(out))
PY
