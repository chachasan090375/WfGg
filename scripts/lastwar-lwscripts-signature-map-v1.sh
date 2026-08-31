#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
RAW="$ROOT/frontend/lab/master-assets-v2/runtime-lua/raw/LWScripts.data"
META="$ROOT/frontend/lab/master-assets-v2/meta/lwscripts-signature-map-v1.json"
VIEW="$ROOT/frontend/lab/formation-lua-trace-viewer-data/lwscripts-signature-map.json"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_LWSCRIPTS_SIGNATURE_MAP_V1.txt"
fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
[[ -s "$RAW" ]] || fail "LWScripts.data absent"
mkdir -p "$(dirname "$META")" "$(dirname "$VIEW")" "$(dirname "$REPORT")"
python - "$RAW" "$META" "$VIEW" "$REPORT" <<'PY'
from pathlib import Path
import json,sys,collections,struct,zlib,gzip,bz2,lzma,io,zipfile
raw,meta,view,report=map(Path,sys.argv[1:])
b=raw.read_bytes(); n=len(b)
patterns=[
 (b'\x1bLua','LUAC'),(b'PK\x03\x04','PKZIP'),(b'\x1f\x8b','GZIP'),(b'\x04\x22\x4d\x18','LZ4-FRAME'),
 (b'7z\xbc\xaf\x27\x1c','7ZIP'),(b'\xfd7zXZ\x00','XZ'),(b'BZh','BZIP2'),(b'UnityFS','UnityFS'),(b'UnityWeb','UnityWeb')]
occ=[]
for pat,name in patterns:
    pos=0
    while True:
        j=b.find(pat,pos)
        if j<0: break
        occ.append({'signature':name,'offset':j})
        pos=j+1
# zlib headers are too common to count globally as proof; only sample aligned candidates near other markers.
occ.sort(key=lambda x:x['offset'])
counts=collections.Counter(x['signature'] for x in occ)
# Local context around first 400 markers.
for x in occ[:400]:
    o=x['offset']; x['beforeHex']=b[max(0,o-16):o].hex(); x['headHex']=b[o:o+32].hex()
    x['nextOffset']=None
for i,x in enumerate(occ[:-1]): x['nextOffset']=occ[i+1]['offset']
# spacing stats per type
spacing={}
for typ in counts:
    xs=[x['offset'] for x in occ if x['signature']==typ]
    ds=[bb-aa for aa,bb in zip(xs,xs[1:])]
    spacing[typ]={'count':len(xs),'firstOffsets':xs[:60],'minGap':min(ds) if ds else None,'medianGap':sorted(ds)[len(ds)//2] if ds else None,'maxGap':max(ds) if ds else None}
# Candidate decodes at exact signatures, capped.
decodes=[]
def add_decode(sig,off,ok,kind,consumed=None,out_bytes=None,detail=None):
    decodes.append({'signature':sig,'offset':off,'ok':ok,'kind':kind,'consumed':consumed,'outputBytes':out_bytes,'detail':detail})
for x in occ[:300]:
    sig=x['signature']; off=x['offset']; chunk=b[off:]
    try:
        if sig=='GZIP':
            bio=io.BytesIO(chunk)
            with gzip.GzipFile(fileobj=bio) as g: d=g.read(16*1024*1024)
            add_decode(sig,off,True,'gzip',bio.tell(),len(d),d[:24].hex())
        elif sig=='XZ':
            d=lzma.decompress(chunk); add_decode(sig,off,True,'xz',None,len(d),d[:24].hex())
        elif sig=='BZIP2':
            d=bz2.decompress(chunk); add_decode(sig,off,True,'bzip2',None,len(d),d[:24].hex())
        elif sig=='PKZIP':
            z=zipfile.ZipFile(io.BytesIO(chunk)); names=z.namelist()[:12]; add_decode(sig,off,True,'zip',None,None,' | '.join(names))
        elif sig=='LUAC':
            ver=chunk[4] if len(chunk)>4 else None
            fmt=chunk[5] if len(chunk)>5 else None
            add_decode(sig,off,True,'luac-header',None,None,f'versionByte={ver} formatByte={fmt}')
    except Exception as e:
        add_decode(sig,off,False,sig.lower(),None,None,type(e).__name__+':'+str(e)[:160])
# Detect whether LUAC markers have sane headers.
luac=[d for d in decodes if d['signature']=='LUAC']
sane_luac=[d for d in luac if d['ok'] and d.get('detail') and 'versionByte=' in d['detail']]
# Framing clues from bytes immediately before signatures: interpret 4-byte LE/BE possible length fields.
frames=[]
for x in occ[:400]:
    o=x['offset']
    if o<4: continue
    le=struct.unpack_from('<I',b,o-4)[0]; be=struct.unpack_from('>I',b,o-4)[0]
    nextoff=x.get('nextOffset')
    gap=(nextoff-o) if nextoff is not None else None
    plausible=[]
    for endian,val in [('le32',le),('be32',be)]:
        if 0<val<=n-o:
            if gap is None or abs(val-gap)<=32 or abs(val+4-gap)<=32: plausible.append({'endian':endian,'value':val,'gapToNext':gap})
    if plausible: frames.append({'signature':x['signature'],'offset':o,'prefixLengthCandidates':plausible,'prefixHex':b[max(0,o-16):o].hex()})
# verdict
if counts.get('LUAC',0)>=10:
    verdict='MANY_LUAC_MARKERS'
    hint='LWScripts.data likely contains many compiled Lua chunks or embedded Lua bytecode. Next step: derive boundaries and module names, then feed carved chunks to the visual graph.'
elif counts.get('PKZIP',0)>=2 or counts.get('GZIP',0)>=2 or counts.get('LZ4-FRAME',0)>=2:
    verdict='MULTI_COMPRESSED_FRAMES'
    hint='Multiple standard compressed frames detected. Next step: carve/decompress successful frames and index their contents.'
elif occ:
    verdict='MIXED_EMBEDDED_SIGNATURES'
    hint='Mixed embedded signatures found. Use spacing/prefix lengths to derive framing before carving.'
else:
    verdict='NO_KNOWN_MARKERS'
    hint='No reliable standard markers; follow loader framing/decryption.'
result={'format':'WFGG_LASTWAR_LWSCRIPTS_SIGNATURE_MAP_V1','bytes':n,'counts':dict(counts),'occurrences':occ[:600],'spacing':spacing,'decodeAttempts':decodes[:300],'frameClues':frames[:200],'verdict':verdict,'nextHint':hint}
js=json.dumps(result,ensure_ascii=False,indent=2)+'\n'; meta.write_text(js,'utf-8'); view.write_text(js,'utf-8')
lines=['LWSCRIPTS_SIGNATURE_MAP_V1_READY',f'bytes={n} markers={len(occ)} types={len(counts)} verdict={verdict}','--- COUNTS ---']
for k,v in counts.most_common(): lines.append(f'{k}={v}')
lines.append('--- FIRST OFFSETS ---')
for x in occ[:80]: lines.append(f"{x['signature']} @{x['offset']}")
lines.append('--- SUCCESSFUL DECODES ---')
oks=[d for d in decodes if d['ok']]
for d in oks[:80]: lines.append(f"{d['signature']} @{d['offset']} kind={d['kind']} out={d.get('outputBytes')} detail={d.get('detail')}")
if not oks: lines.append('NONE')
lines.append('--- FRAME CLUES ---')
for f in frames[:60]: lines.append(f"{f['signature']} @{f['offset']} prefix={f['prefixLengthCandidates']}")
if not frames: lines.append('NONE')
lines.append('--- VERDICT ---'); lines.append(verdict); lines.append(hint); lines.append(f'JSON={meta}')
text='\n'.join(lines)+'\n'; report.write_text(text,'utf-8'); print(text,end='')
PY
