#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — recover the protected Assembly-CSharp.mdl PE header
# and enumerate CLR TypeDef/MethodDef names with a tiny stdlib-only parser.
# Read-only on the installed APK. Recovered DLL stays local and is NOT committed.

PKG="com.fun.lastwar.gp"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
OUT="$ROOT/frontend/lab/master-assets-v2/meta/assembly-csharp-clr-types-v1.json"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_ASSEMBLY_CSHARP_CLR_TYPES.txt"
RECOVERED="$HOME/storage/downloads/WFGG_LASTWAR_Assembly-CSharp_recovered.dll"
TMP="${TMPDIR:-$HOME/.cache}/wfgg-assembly-csharp-clr"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
command -v python >/dev/null 2>&1 || fail "python absent"
mkdir -p "$TMP" "$(dirname "$OUT")" "$(dirname "$REPORT")"
rm -rf "$TMP"/*

mapfile -t APKS < <(cmd package path "$PKG" 2>/dev/null | sed -n 's/^package://p')
[[ ${#APKS[@]} -gt 0 ]] || fail "APK Last War introuvable"

python - "$OUT" "$REPORT" "$RECOVERED" "${APKS[@]}" <<'PY'
from __future__ import annotations
from pathlib import Path
import sys,zipfile,struct,json,re,hashlib

out=Path(sys.argv[1]); report=Path(sys.argv[2]); recovered=Path(sys.argv[3]); apks=[Path(x) for x in sys.argv[4:]]
source=None; data=None
for apk in apks:
    try:
        with zipfile.ZipFile(apk) as z:
            n='assets/Assemblies/Assembly-CSharp.mdl'
            if n in z.namelist():
                data=bytearray(z.read(n)); source={'apk':str(apk),'entry':n,'bytes':len(data)}; break
    except Exception: pass
if data is None: raise SystemExit('ERREUR: Assembly-CSharp.mdl introuvable')
orig_sha=hashlib.sha256(data).hexdigest()

# Protection observed on this build: first DOS-header bytes are XOR 0x13.
# Restore only the bytes that match the canonical DOS header under that transform.
canonical=bytes.fromhex('4d5a90000300000004000000ffff0000b80000')
patched=[]
for i,b in enumerate(canonical):
    if i < len(data) and data[i] == (b ^ 0x13):
        data[i]=b; patched.append(i)
# Ensure MZ for parsers, but do not touch any other payload byte.
data[0:2]=b'MZ'
recovered.write_bytes(data)

u16=lambda o: struct.unpack_from('<H',data,o)[0]
u32=lambda o: struct.unpack_from('<I',data,o)[0]
u64=lambda o: struct.unpack_from('<Q',data,o)[0]
if data[:2] != b'MZ': raise SystemExit('ERREUR: MZ non restaure')
e_lfanew=u32(0x3c)
if data[e_lfanew:e_lfanew+4] != b'PE\0\0': raise SystemExit(f'ERREUR: PE absent a {e_lfanew}')
coff=e_lfanew+4; sections=u16(coff+2); opt_size=u16(coff+16); opt=coff+20; magic=u16(opt)
if magic==0x10b: dd=opt+96
elif magic==0x20b: dd=opt+112
else: raise SystemExit(f'ERREUR: optional header magic {magic:#x}')
clr_rva=u32(dd+14*8); clr_size=u32(dd+14*8+4)
sec_off=opt+opt_size
secs=[]
for i in range(sections):
    o=sec_off+i*40
    name=bytes(data[o:o+8]).split(b'\0',1)[0].decode('ascii','replace')
    vsize=u32(o+8); va=u32(o+12); rawsize=u32(o+16); raw=u32(o+20)
    secs.append({'name':name,'va':va,'vsize':vsize,'raw':raw,'rawsize':rawsize})
def rva_to_off(rva:int)->int:
    for s in secs:
        span=max(s['vsize'],s['rawsize'])
        if s['va'] <= rva < s['va']+span:
            return s['raw']+(rva-s['va'])
    if rva < len(data): return rva
    raise ValueError(f'RVA hors sections: {rva:#x}')
clr_off=rva_to_off(clr_rva)
metadata_rva=u32(clr_off+8); metadata_size=u32(clr_off+12); meta=rva_to_off(metadata_rva)
if bytes(data[meta:meta+4]) != b'BSJB': raise SystemExit(f'ERREUR: BSJB absent a {meta}')
ver_len=u32(meta+12); p=meta+16+ver_len; p=(p+3)&~3; flags=u16(p); streams=u16(p+2); p+=4
stream_map={}
for _ in range(streams):
    off=u32(p); size=u32(p+4); p+=8
    end=data.find(0,p,p+64)
    if end<0: raise SystemExit('ERREUR: nom de stream invalide')
    name=bytes(data[p:end]).decode('ascii','replace'); p=(end+1+3)&~3
    stream_map[name]={'offset':meta+off,'size':size}
if '#Strings' not in stream_map or not ('#~' in stream_map or '#-' in stream_map):
    raise SystemExit('ERREUR: streams CLR incomplets')
strings=stream_map['#Strings']; tables=stream_map.get('#~',stream_map.get('#-'))

def str_at(idx:int)->str:
    if idx==0:return ''
    o=strings['offset']+idx; e=data.find(0,o,strings['offset']+strings['size'])
    if e<0:e=min(len(data),o+256)
    return bytes(data[o:e]).decode('utf-8','replace')

t=tables['offset']; heap_sizes=data[t+6]; valid=u64(t+8); q=t+24
rows={}
for tid in range(64):
    if (valid>>tid)&1:
        rows[tid]=u32(q); q+=4
rowdata=q
strsz=4 if heap_sizes&1 else 2; guidsz=4 if heap_sizes&2 else 2; blobsz=4 if heap_sizes&4 else 2
def idxsz(tid): return 4 if rows.get(tid,0)>=65536 else 2
def cidx(tagbits,*tids): return 4 if max((rows.get(x,0) for x in tids),default=0) >= (1<<(16-tagbits)) else 2
# Only row sizes required up through MethodDef table (0..6).
row_size={
 0:2+strsz+guidsz*3,
 1:cidx(2,0,1,26,35)+strsz*2,
 2:4+strsz*2+cidx(2,1,2,27)+idxsz(4)+idxsz(6),
 3:idxsz(4),
 4:2+strsz+blobsz,
 5:idxsz(6),
 6:4+2+2+strsz+blobsz+idxsz(8),
}
offs={}; cur=rowdata
for tid in range(7):
    if (valid>>tid)&1:
        offs[tid]=cur; cur += row_size[tid]*rows.get(tid,0)

def read_idx(o,sz): return u16(o) if sz==2 else u32(o)
# Parse MethodDef names first.
methods=[None]
mo=offs.get(6,0)
for rid in range(1,rows.get(6,0)+1):
    o=mo+(rid-1)*row_size[6]
    rva=u32(o); name_i=read_idx(o+8,strsz); name=str_at(name_i)
    methods.append({'rid':rid,'rva':rva,'name':name})
# Parse TypeDef and method ranges.
types=[]; to=offs.get(2,0)
raw_types=[]
for rid in range(1,rows.get(2,0)+1):
    o=to+(rid-1)*row_size[2]
    pos=o+4; name_i=read_idx(pos,strsz);pos+=strsz; ns_i=read_idx(pos,strsz);pos+=strsz
    pos+=cidx(2,1,2,27); pos+=idxsz(4); method_start=read_idx(pos,idxsz(6))
    raw_types.append({'rid':rid,'name':str_at(name_i),'namespace':str_at(ns_i),'methodStart':method_start})
for i,ty in enumerate(raw_types):
    start=ty['methodStart']; end=(raw_types[i+1]['methodStart']-1 if i+1<len(raw_types) else rows.get(6,0))
    ty['methods']=[methods[r] for r in range(max(1,start),min(end,len(methods)-1)+1)] if start else []
    types.append(ty)

rx=re.compile(r'(formation|hero.?show|show.?hero|camera|rendertexture|worldcity|arabicmirror|pvp)',re.I)
interesting=[]
for ty in types:
    hits=[m for m in ty['methods'] if rx.search(m['name'] or '')]
    typehit=bool(rx.search((ty['namespace']+'.'+ty['name']).strip('.')))
    if typehit or hits:
        score=(80 if typehit else 0)+len(hits)*8
        if re.search(r'hero.?show|formation|pvp',ty['name'],re.I):score+=80
        interesting.append({'rid':ty['rid'],'namespace':ty['namespace'],'name':ty['name'],'score':score,'methodCount':len(ty['methods']),'matchedMethods':hits[:120],'allMethods':[m['name'] for m in ty['methods'][:250]]})
interesting.sort(key=lambda x:(-x['score'],x['namespace'],x['name']))

summary={'format':'WFGG_LASTWAR_ASSEMBLY_CSHARP_CLR_TYPES_V1','source':source,'originalSha256':orig_sha,'recoveredLocalPath':str(recovered),'patchedHeaderOffsets':patched,'pe':{'e_lfanew':e_lfanew,'sections':sections,'optionalMagic':magic,'clrRva':clr_rva,'clrSize':clr_size,'metadataRva':metadata_rva,'metadataSize':metadata_size,'metadataOffset':meta,'streams':stream_map},'tables':{'TypeDef':rows.get(2,0),'MethodDef':rows.get(6,0)},'interestingTypeCount':len(interesting),'interestingTypes':interesting[:500],'guardrails':{'apkReadOnly':True,'recoveredDllCommitted':False,'previewUntouched':True,'mainUntouched':True}}
out.write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n','utf-8')
lines=['WfGg Last War — ASSEMBLY-CSHARP CLR TYPE MAP','',f"source={source['entry']} bytes={source['bytes']}",f"patchedHeaderOffsets={patched}",f"PE={e_lfanew} CLR_RVA={clr_rva:#x} metadataOffset={meta} metadataSize={metadata_size}",f"TypeDef={rows.get(2,0)} MethodDef={rows.get(6,0)} interestingTypes={len(interesting)}",'', 'TOP INTERESTING TYPES']
for ty in interesting[:120]:
    lines.append(f"TYPE score={ty['score']} rid={ty['rid']} {ty['namespace']+'.' if ty['namespace'] else ''}{ty['name']} methods={ty['methodCount']}")
    for m in ty['matchedMethods'][:40]: lines.append(f"  METHOD rid={m['rid']} rva=0x{m['rva']:x} {m['name']}")
report.write_text('\n'.join(lines)+'\n','utf-8')
print('ASSEMBLY_CSHARP_CLR_TYPES_OK',f"typedefs={rows.get(2,0)}",f"methods={rows.get(6,0)}",f"interesting={len(interesting)}",f"metadata={meta}")
for ty in interesting[:20]:
    print('CLR_TYPE',f"score={ty['score']}",f"rid={ty['rid']}",(ty['namespace']+'.' if ty['namespace'] else '')+ty['name'])
    for m in ty['matchedMethods'][:6]: print('  CLR_METHOD',m['name'])
print('ASSEMBLY_CSHARP_CLR_TYPES_JSON',out)
print('ASSEMBLY_CSHARP_CLR_TYPES_REPORT',report)
print('RECOVERED_DLL_LOCAL',recovered)
PY

git add scripts/lastwar-assembly-csharp-clr-types.sh "$OUT"
if ! git diff --cached --quiet; then
  git commit -m "lab: recover Assembly-CSharp CLR type map"
  git push origin "$BRANCH"
fi

echo "=== ASSEMBLY-CSHARP CLR TYPE MAP TERMINE ==="
echo "JSON: $OUT"
echo "Rapport: $REPORT"
echo "DLL restauree localement seulement: $RECOVERED"
echo "Preview inchangée. main non modifiée."
