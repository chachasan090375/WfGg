#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
RUNTIME="$ROOT/frontend/lab/master-assets-v2/runtime-lua/raw"
IL="$ROOT/frontend/lab/master-assets-v2/meta/lwlua-container-il-trace-v1.json"
META="$ROOT/frontend/lab/master-assets-v2/meta/lwscripts-structure-v1.json"
VIEW="$ROOT/frontend/lab/formation-lua-trace-viewer-data/lwscripts-structure.json"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_LWSCRIPTS_STRUCTURE_V1.txt"
fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
[[ -s "$RUNTIME/LWScripts.data" ]] || fail "LWScripts.data absent"
command -v python >/dev/null 2>&1 || fail "python absent"
mkdir -p "$(dirname "$META")" "$(dirname "$VIEW")" "$(dirname "$REPORT")"
python - "$RUNTIME" "$IL" "$META" "$VIEW" "$REPORT" <<'PY'
from __future__ import annotations
from pathlib import Path
import collections,hashlib,json,math,re,struct,sys,zlib
runtime,ilp,meta,view,report=map(Path,sys.argv[1:])

def text_file(name):
    p=runtime/name
    if not p.exists(): return {'name':name,'exists':False}
    b=p.read_bytes()
    decs=[]
    for enc in ('utf-8','utf-16le','utf-16be','latin-1'):
        try:
            s=b.decode(enc,'strict')
            score=sum(ch.isprintable() or ch in '\r\n\t' for ch in s)/max(1,len(s))
            if score>.7: decs.append({'encoding':enc,'score':round(score,4),'text':s})
        except: pass
    decs.sort(key=lambda x:x['score'],reverse=True)
    best=decs[0]['text'] if decs else ''
    nums=[]
    for tok in re.findall(r'(?<![A-Za-z0-9])(?:0x[0-9A-Fa-f]+|\d+)(?![A-Za-z0-9])',best):
        try: nums.append({'token':tok,'value':int(tok,0)})
        except: pass
    return {'name':name,'exists':True,'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest(),'headHex':b[:128].hex(),'decodings':decs,'bestText':best,'numericTokens':nums}

def entropy(b):
    if not b:return 0.0
    c=collections.Counter(b); n=len(b)
    return -sum((v/n)*math.log2(v/n) for v in c.values())

def sigat(b,off):
    x=b[off:off+16]
    sigs=[(b'UnityFS','UnityFS'),(b'UnityWeb','UnityWeb'),(b'PK\x03\x04','PKZIP'),(b'\x1f\x8b','GZIP'),(b'7z\xbc\xaf\x27\x1c','7ZIP'),(b'\xfd7zXZ\x00','XZ'),(b'BZh','BZIP2'),(b'\x1bLua','LUAC'),(b'\x04\x22\x4d\x18','LZ4-FRAME')]
    for s,n in sigs:
        if x.startswith(s):return n
    if len(x)>=2 and x[0]==0x78 and x[1] in (0x01,0x5e,0x9c,0xda):return 'ZLIB?'
    return None

data=(runtime/'LWScripts.data').read_bytes(); n=len(data)
windows=[]
win=min(1024*1024,n)
for i in range(12):
    off=0 if n<=win else round((n-win)*i/11)
    chunk=data[off:off+win]
    windows.append({'offset':off,'bytes':len(chunk),'entropy':round(entropy(chunk),5),'zeroPct':round(chunk.count(0)*100/max(1,len(chunk)),4),'asciiPct':round(sum(32<=x<127 for x in chunk)*100/max(1,len(chunk)),4)})

known=[]
patterns=[(b'UnityFS','UnityFS'),(b'PK\x03\x04','PKZIP'),(b'\x1f\x8b','GZIP'),(b'\x1bLua','LUAC'),(b'\x04\x22\x4d\x18','LZ4-FRAME'),(b'7z\xbc\xaf\x27\x1c','7ZIP')]
# Targeted signature search: first/last 16 MiB + sparse 2 MiB windows, not a full brute-force content scan.
regions=[]
span=min(16*1024*1024,n)
regions.append((0,data[:span]))
if n>span: regions.append((n-span,data[-span:]))
for i in range(1,8):
    off=round((n-min(n,2*1024*1024))*i/8); regions.append((off,data[off:off+min(2*1024*1024,n-off)]))
seen=set()
for base,b in regions:
    for pat,name in patterns:
        start=0
        while True:
            j=b.find(pat,start)
            if j<0:break
            off=base+j
            if (name,off) not in seen:
                seen.add((name,off));known.append({'signature':name,'offset':off})
            start=j+1
            if len(known)>200:break
        if len(known)>200:break
    if len(known)>200:break

head=data[:256];tail=data[-256:]
ints=[]
for off in range(0,min(64,len(head))-3,4):
    u32=struct.unpack_from('<I',head,off)[0]
    be32=struct.unpack_from('>I',head,off)[0]
    ints.append({'offset':off,'le32':u32,'be32':be32,'leMatchesFileSize':u32==n,'beMatchesFileSize':be32==n})

crc=zlib.crc32(data)&0xffffffff
sha=hashlib.sha256(data).hexdigest()
small={x:text_file(x) for x in ('lua','lua.version','LWScripts.txt')}

comparisons=[]
for name,r in small.items():
    for tok in r.get('numericTokens',[]):
        v=tok['value']; labels=[]
        if v==n: labels.append('FILE_SIZE')
        if v==crc: labels.append('CRC32_DEC')
        if v==(crc & 0xffffffff): labels.append('CRC32')
        if labels: comparisons.append({'file':name,'token':tok['token'],'value':v,'matches':labels})

loader=[]
if ilp.exists():
    try:
        d=json.loads(ilp.read_text('utf-8'))
        for r in d.get('exactBoundaryMethodIL') or []:
            sym=str(r.get('symbol') or '')
            if any(k in sym for k in ('LWLuaFile.LoadFile','LWLuaFile._Load','LWLuaFile.Load','LWLuaFileUpdate.ApplyUpdate','LWLuaFileUpdate.InitFileOnAppStart')):
                loader.append({'symbol':sym,'rid':r.get('rid'),'strings':r.get('strings') or [],'internalCalls':r.get('internalCalls') or [],'externalCalls':r.get('externalCalls') or []})
    except Exception as e: loader=[{'error':str(e)}]

# Derive a conservative structural verdict.
avg=sum(x['entropy'] for x in windows)/max(1,len(windows))
if avg>7.75 and not known:
    verdict='HIGH_ENTROPY_NO_STANDARD_SIGNATURE'
    hint='Likely encrypted or strongly compressed/custom-framed. Follow LWLuaFile.LoadFile/_Load before trying generic archive extraction.'
elif known:
    verdict='EMBEDDED_STANDARD_SIGNATURES_FOUND'
    hint='Inspect signature offsets and loader calls; the data may be concatenated/framed.'
else:
    verdict='NONSTANDARD_BINARY'
    hint='Use tiny metadata files plus loader calls to determine framing/decryption.'

result={'format':'WFGG_LASTWAR_LWSCRIPTS_STRUCTURE_V1','data':{'bytes':n,'sha256':sha,'crc32':crc,'crc32Hex':f'{crc:08x}','headHex':head.hex(),'tailHex':tail.hex(),'windows':windows,'avgEntropy':round(avg,5),'knownSignatures':known,'headerIntegers':ints},'smallFiles':small,'metadataMatches':comparisons,'loaderMethods':loader,'verdict':verdict,'nextHint':hint,'guardrails':{'targetedStructureOnly':True,'noFullSignatureBruteforce':True,'mainUntouched':True}}
js=json.dumps(result,ensure_ascii=False,indent=2)+'\n';meta.write_text(js,'utf-8');view.write_text(js,'utf-8')
lines=['LWSCRIPTS_STRUCTURE_V1_READY',f"dataBytes={n} crc32={crc:08x} avgEntropy={avg:.5f} signatures={len(known)} verdict={verdict}",'--- SMALL FILES ---']
for name,r in small.items():
    lines.append(f'[{name}] bytes={r.get("bytes",0)}')
    lines.append((r.get('bestText') or '<no readable text>').replace('\r','\\r'))
lines.append('--- METADATA MATCHES ---')
if comparisons:
    for x in comparisons: lines.append(f"{x['file']} token={x['token']} -> {','.join(x['matches'])}")
else: lines.append('NONE')
lines.append('--- ENTROPY WINDOWS ---')
for x in windows: lines.append(f"off={x['offset']} H={x['entropy']} zero={x['zeroPct']}% ascii={x['asciiPct']}%")
lines.append('--- SIGNATURE OFFSETS ---')
if known:
    for x in known[:80]: lines.append(f"{x['signature']} @{x['offset']}")
else: lines.append('NONE')
lines.append('--- LOADER METHODS ---')
for r in loader:
    lines.append(f"METHOD {r.get('symbol')} rid={r.get('rid')}")
    for s in r.get('strings') or []: lines.append('  STR '+repr(s))
    for c in r.get('internalCalls') or []: lines.append('  CALL '+c)
    for c in r.get('externalCalls') or []: lines.append('  EXT '+c)
lines.append('--- VERDICT ---');lines.append(verdict);lines.append(hint);lines.append(f'JSON={meta}')
text='\n'.join(lines)+'\n';report.write_text(text,'utf-8');print(text,end='')
PY
