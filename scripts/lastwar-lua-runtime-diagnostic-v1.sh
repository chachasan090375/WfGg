#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
RUNTIME="$ROOT/frontend/lab/master-assets-v2/runtime-lua"
META="$ROOT/frontend/lab/master-assets-v2/meta/lua-runtime-diagnostic-v1.json"
IL="$ROOT/frontend/lab/master-assets-v2/meta/lwlua-container-il-trace-v1.json"
OUT="$ROOT/frontend/lab/formation-lua-trace-viewer-data/runtime-diagnostic.json"
fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
command -v python >/dev/null 2>&1 || fail "python absent"
[[ -d "$RUNTIME/raw" ]] || fail "runtime Lua non matérialisé"
mkdir -p "$(dirname "$META")" "$(dirname "$OUT")"
python - "$RUNTIME" "$IL" "$META" "$OUT" <<'PY'
from __future__ import annotations
from pathlib import Path
import json,re,sys,hashlib,zlib,gzip,bz2,lzma
runtime,ilp,meta,out=map(Path,sys.argv[1:])
raw=runtime/'raw'
anchors=['UIHeroPVPFormationPanel','FormationRT','FormationBg','FormationContent','A_Hero_Audie_01','RenderTexture','targetTexture','RawImage','Camera']

def signature(b:bytes):
    if b.startswith(b'UnityFS'): return 'UnityFS'
    if b.startswith(b'UnityWeb'): return 'UnityWeb'
    if b.startswith(b'PK\x03\x04'): return 'PKZIP'
    if b.startswith(b'\x1f\x8b'): return 'GZIP'
    if b.startswith(b'\x04\x22\x4d\x18'): return 'LZ4-FRAME'
    if b.startswith(b'7z\xbc\xaf\x27\x1c'): return '7ZIP'
    if b.startswith(b'\xfd7zXZ\x00'): return 'XZ'
    if b.startswith(b'BZh'): return 'BZIP2'
    if b.startswith(b'\x1bLua'): return 'LUAC'
    if b[:16].lower().startswith(b'chacha'): return 'CHACHA'
    if len(b)>=2 and b[0]==0x78 and b[1] in (0x01,0x5e,0x9c,0xda): return 'ZLIB?'
    return 'UNKNOWN'

def printable_score(s:str):
    if not s:return 0.0
    good=sum(ch.isprintable() or ch in '\r\n\t' for ch in s)
    return good/len(s)

def decode_candidates(b:bytes):
    rows=[]
    for enc in ('utf-8','utf-16le','utf-16be','latin-1'):
        try:s=b[:min(len(b),262144)].decode(enc,'strict')
        except:continue
        score=printable_score(s)
        if score>.70:
            rows.append({'encoding':enc,'score':round(score,4),'preview':s[:1200]})
    rows.sort(key=lambda x:x['score'],reverse=True)
    return rows[:4]

def strings_ascii(b:bytes,limit=80):
    out=[]
    for m in re.finditer(rb'[\x20-\x7e]{5,}',b[:min(len(b),8*1024*1024)]):
        s=m.group().decode('ascii','replace')
        if s not in [x['text'] for x in out]:out.append({'offset':m.start(),'text':s[:300]})
        if len(out)>=limit:break
    return out

def strings_utf16le(b:bytes,limit=40):
    out=[]
    pat=re.compile(rb'(?:[\x20-\x7e]\x00){5,}')
    for m in pat.finditer(b[:min(len(b),8*1024*1024)]):
        try:s=m.group().decode('utf-16le')
        except:continue
        if s not in [x['text'] for x in out]:out.append({'offset':m.start(),'text':s[:300]})
        if len(out)>=limit:break
    return out

def anchor_hits(b:bytes):
    hits=[]
    low=b.lower()
    for a in anchors:
        for enc,label in ((a.encode(),'utf8'),(a.encode('utf-16le'),'utf16le')):
            p=low.find(enc.lower())
            if p>=0:hits.append({'anchor':a,'encoding':label,'offset':p})
    return hits

def try_decompress(b:bytes):
    tests=[]
    funcs=[('gzip',gzip.decompress),('zlib',zlib.decompress),('bz2',bz2.decompress),('xz',lzma.decompress)]
    for name,fn in funcs:
        try:
            d=fn(b)
            tests.append({'method':name,'ok':True,'bytes':len(d),'signature':signature(d[:32]),'headHex':d[:32].hex(),'ascii':strings_ascii(d,20),'anchors':anchor_hits(d)})
        except Exception as e:
            tests.append({'method':name,'ok':False,'error':type(e).__name__})
    return tests

files=[]
for p in sorted(raw.glob('*')):
    if not p.is_file():continue
    b=p.read_bytes()
    files.append({
      'name':p.name,'path':str(p),'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest(),
      'signature':signature(b[:64]),'headHex':b[:64].hex(),'tailHex':b[-32:].hex() if b else '',
      'decodings':decode_candidates(b),'asciiStrings':strings_ascii(b),'utf16Strings':strings_utf16le(b),
      'anchorHits':anchor_hits(b),'decompression':try_decompress(b) if len(b)<128*1024*1024 else []
    })

matp=runtime.parent/'meta'/'lua-runtime-materialize-v1.json'
materialize={}
if matp.exists():
    try:materialize=json.loads(matp.read_text('utf-8'))
    except Exception as e:materialize={'readError':str(e)}
loader=[]
if ilp.exists():
    try:
        d=json.loads(ilp.read_text('utf-8'))
        for r in d.get('exactBoundaryMethodIL') or []:
            sym=str(r.get('symbol') or '')
            if any(x in sym for x in ('LWLuaFile.','LWLuaFileUpdate','XLuaManager.CustomLoaderImpl')):
                loader.append({'symbol':sym,'rid':r.get('rid'),'strings':r.get('strings') or [],'internalCalls':r.get('internalCalls') or [],'externalCalls':r.get('externalCalls') or []})
    except Exception as e:loader=[{'error':str(e)}]

result={'format':'WFGG_LASTWAR_LUA_RUNTIME_DIAGNOSTIC_V1','files':files,'materialize':materialize,'loaderMethods':loader,
        'summary':{'rawFiles':len(files),'materializedExtracted':len(materialize.get('extracted') or []) if isinstance(materialize,dict) else 0,'materializeErrors':len(materialize.get('errors') or []) if isinstance(materialize,dict) else 0,'loaderMethods':len(loader)},
        'nextHint':'Use raw signatures + loader external calls to choose exact decoder; do not rescan bundles.'}
text=json.dumps(result,ensure_ascii=False,indent=2)+'\n';meta.write_text(text,'utf-8');out.write_text(text,'utf-8')
print(f"LUA_RUNTIME_DIAGNOSTIC_V1_READY raw={len(files)} extracted={result['summary']['materializedExtracted']} errors={result['summary']['materializeErrors']} loaderMethods={len(loader)}")
for r in files: print(f"RAW {r['name']} bytes={r['bytes']} sig={r['signature']} decodings={','.join(x['encoding'] for x in r['decodings']) or '-'} anchors={len(r['anchorHits'])}")
for r in loader:
    if r.get('symbol'):print(f"LOADER {r['symbol']} ext={len(r.get('externalCalls') or [])} strings={len(r.get('strings') or [])}")
print('JSON='+str(meta))
PY
