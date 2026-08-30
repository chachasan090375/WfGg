#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — exact IL string XREF for FormationBg / FormationRT.
# Reads ONLY the already recovered Assembly-CSharp DLL. No APK, no bundles, no game writes.
# Scope: exact #US literals FormationBg and FormationRT -> ldstr MethodDef XREF -> exact calls.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
DLL="$HOME/storage/downloads/WFGG_LASTWAR_Assembly-CSharp_recovered.dll"
ATLAS="$ROOT/frontend/lab/master-assets-v2/index/lastwar-code-discovery-atlas-v1.json"
OUT="$ROOT/frontend/lab/master-assets-v2/meta/formation-runtime-name-il-xref-v1.json"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_FORMATION_RUNTIME_NAME_IL_XREF_V1.txt"
EXPECTED_SHA="ed02eadb7764f7ff82a0d9b8746987ece867b2ccf7b06e9022e06c79259c380f"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
[[ -s "$DLL" ]] || fail "DLL recuperee absente: $DLL"
[[ -s "$ATLAS" ]] || fail "atlas CLR absent: $ATLAS"
command -v python >/dev/null 2>&1 || fail "python absent"
mkdir -p "$(dirname "$OUT")" "$(dirname "$REPORT")"
actual_sha="$(sha256sum "$DLL" | awk '{print $1}')"
[[ "$actual_sha" == "$EXPECTED_SHA" ]] || fail "SHA DLL inattendu: $actual_sha"

python - "$DLL" "$ATLAS" "$OUT" "$REPORT" <<'PY'
from pathlib import Path
from collections import defaultdict, deque
import hashlib,json,re,struct,sys

dll=Path(sys.argv[1]); atlasp=Path(sys.argv[2]); outp=Path(sys.argv[3]); reportp=Path(sys.argv[4])
data=dll.read_bytes(); atlas=json.loads(atlasp.read_text('utf-8'))
needles=['FormationBg','FormationRT']
u16=lambda o:struct.unpack_from('<H',data,o)[0]
u32=lambda o:struct.unpack_from('<I',data,o)[0]
u64=lambda o:struct.unpack_from('<Q',data,o)[0]
if data[:2]!=b'MZ':raise SystemExit('DLL_MZ_INVALID')
e_lfanew=u32(0x3c)
if data[e_lfanew:e_lfanew+4]!=b'PE\0\0':raise SystemExit('DLL_PE_INVALID')
coff=e_lfanew+4;nsec=u16(coff+2);opt_size=u16(coff+16);opt=coff+20;magic=u16(opt);dd=opt+(96 if magic==0x10b else 112)
secs=[];sec_off=opt+opt_size
for i in range(nsec):
    o=sec_off+i*40;secs.append((u32(o+12),u32(o+8),u32(o+16),u32(o+20)))
def rvaoff(rva):
    for va,vs,rs,ro in secs:
        if va<=rva<va+max(vs,rs):return ro+(rva-va)
    if rva<len(data):return rva
    raise ValueError(rva)
clr=rvaoff(u32(dd+14*8));meta=rvaoff(u32(clr+8))
if data[meta:meta+4]!=b'BSJB':raise SystemExit('CLR_METADATA_INVALID')
ver=u32(meta+12);q=(meta+16+ver+3)&~3;nstreams=u16(q+2);q+=4
sm={}
for _ in range(nstreams):
    off=u32(q);size=u32(q+4);q+=8;e=data.find(b'\0',q,q+64)
    if e<0:raise SystemExit('CLR_STREAM_NAME_INVALID')
    name=data[q:e].decode('ascii','replace');q=(e+4)&~3;sm[name]=(meta+off,size)
so,ss=sm['#Strings'];uso,uss=sm.get('#US',(0,0));to,ts=sm.get('#~',sm.get('#-'))
if not uso:raise SystemExit('CLR_US_HEAP_ABSENT')
def s_at(i):
    if not i:return ''
    o=so+i;e=data.find(b'\0',o,so+ss);return data[o:(e if e>=0 else min(o+512,so+ss))].decode('utf-8','replace')
def comp(o):
    b=data[o]
    if b<0x80:return b,1
    if b<0xC0:return ((b&63)<<8)|data[o+1],2
    return ((b&31)<<24)|(data[o+1]<<16)|(data[o+2]<<8)|data[o+3],4
def us_at(i):
    if i<=0 or i>=uss:return ''
    try:
        n,k=comp(uso+i);raw=data[uso+i+k:uso+i+k+n]
        if raw:raw=raw[:-1]
        return raw.decode('utf-16le','replace')
    except:return ''

# Enumerate #US exactly once, retaining only the two requested literals.
us_hits=defaultdict(list);i=1
while i<uss:
    try:n,k=comp(uso+i)
    except:break
    if n<=0:
        i+=max(k,1);continue
    raw=data[uso+i+k:uso+i+k+n]
    body=raw[:-1] if raw else raw
    try:s=body.decode('utf-16le','replace')
    except:s=''
    if s in needles:
        us_hits[s].append({'heapIndex':i,'token':0x70000000|i,'heapFileOffset':uso+i})
    i+=k+n

heap=data[to+6];valid=u64(to+8);q=to+24;rows={}
for tid in range(64):
    if (valid>>tid)&1:rows[tid]=u32(q);q+=4
row0=q;strsz=4 if heap&1 else 2;guidsz=4 if heap&2 else 2;blobsz=4 if heap&4 else 2
def ix(t):return 4 if rows.get(t,0)>=65536 else 2
def cx(bits,*tids):return 4 if max([rows.get(x,0) for x in tids] or [0])>=(1<<(16-bits)) else 2
rs={0:2+strsz+guidsz*3,1:cx(2,0,26,35,1)+2*strsz,2:4+2*strsz+cx(2,1,2,27)+ix(4)+ix(6),3:ix(4),4:2+strsz+blobsz,5:ix(6),6:4+2+2+strsz+blobsz+ix(8),7:ix(8),8:2+2+strsz,9:ix(2)+cx(2,1,2,27),10:cx(3,2,1,26,6,27)+strsz+blobsz}
offs={};cur=row0
for tid in range(11):
    if (valid>>tid)&1:
        if tid not in rs:raise SystemExit(f'ROW_SIZE_UNSUPPORTED_{tid}')
        offs[tid]=cur;cur+=rs[tid]*rows.get(tid,0)
def ri(o,z):return u16(o) if z==2 else u32(o)
tr=[None]
for rid in range(1,rows.get(1,0)+1):
    o=offs[1]+(rid-1)*rs[1];p=o+cx(2,0,26,35,1);ni=ri(p,strsz);p+=strsz;nsi=ri(p,strsz);tr.append((s_at(nsi),s_at(ni)))
methods=[None]
for rid in range(1,rows.get(6,0)+1):
    o=offs[6]+(rid-1)*rs[6];methods.append({'rid':rid,'rva':u32(o),'name':s_at(ri(o+8,strsz))})
raw=[]
for rid in range(1,rows.get(2,0)+1):
    o=offs[2]+(rid-1)*rs[2];p=o+4;ni=ri(p,strsz);p+=strsz;nsi=ri(p,strsz);p+=strsz;p+=cx(2,1,2,27)+ix(4);ms=ri(p,ix(6));raw.append({'rid':rid,'namespace':s_at(nsi),'name':s_at(ni),'methodStart':ms})
types=[];owner={}
for j,t in enumerate(raw):
    mend=(raw[j+1]['methodStart']-1 if j+1<len(raw) else rows.get(6,0));t['methodEnd']=mend;types.append(t)
    if t['methodStart']:
        for r in range(max(1,t['methodStart']),min(mend,len(methods)-1)+1):owner[r]=t
by_type_rid={x['rid']:x for x in types}
def fullname(t):return ((t.get('namespace')+'.') if t.get('namespace') else '')+t.get('name','')
def symbol(rid):
    m=methods[rid];return (fullname(owner.get(rid,{}))+'.' if owner.get(rid) else '')+m['name']
mr=[None];mps=cx(3,2,1,26,6,27)
for rid in range(1,rows.get(10,0)+1):
    o=offs[10]+(rid-1)*rs[10];par=ri(o,mps);ni=ri(o+mps,strsz);mr.append((par,s_at(ni)))
def parent_name(c):
    tag=c&7;rid=c>>3
    if tag==0 and rid in by_type_rid:return fullname(by_type_rid[rid])
    if tag==1 and rid<len(tr):ns,n=tr[rid];return (ns+'.' if ns else '')+n
    if tag==3 and rid in owner:return fullname(owner[rid])
    return f'tag{tag}:rid{rid}'
def tok(v):
    tab=(v>>24)&255;rid=v&0xffffff
    if tab==6 and 0<rid<len(methods):return ('internal',rid,symbol(rid))
    if tab==10 and 0<rid<len(mr):return ('external',rid,parent_name(mr[rid][0])+'.'+mr[rid][1])
    return ('other',rid,f'0x{v:08x}')
def body(m):
    if not m['rva']:return None
    try:o=rvaoff(m['rva'])
    except:return None
    b=data[o]
    if b&3==2:cs=b>>2;s=o+1
    elif b&3==3:
        h=u16(o);hs=((h>>12)&15)*4;cs=u32(o+4);s=o+hs
    else:return None
    return data[s:s+cs] if s+cs<=len(data) else None

token_ops={0x27:'jmp',0x28:'call',0x29:'calli',0x6f:'callvirt',0x72:'ldstr',0x73:'newobj'}
other_token={0x70,0x71,0x74,0x75,0x79,0x7b,0x7c,0x7d,0x7e,0x7f,0x80,0x81,0x8c,0x8d,0x8f,0xa3,0xa4,0xa5,0xc2,0xc6,0xd0}
short1=set(range(0x2b,0x38))|{0x0e,0x0f,0x10,0x11,0x12,0x13,0x1f,0xde};long4=set(range(0x38,0x45))|{0x20,0xdd,0x22};long8={0x21,0x23}
fe_token={0x06,0x07,0x15,0x16,0x1c};fe_u16={0x09,0x0a,0x0b,0x0c,0x0d,0x0e};fe_u8={0x12,0x19}
def scan_il(m):
    il=body(m)
    if il is None:return [],[],[]
    internal=[];external=[];strings=[];i=0
    while i<len(il):
        op=il[i];i+=1
        if op==0xfe:
            if i>=len(il):break
            o2=il[i];i+=1
            if o2 in fe_token:
                if i+4>len(il):break
                v=struct.unpack_from('<I',il,i)[0];i+=4
                if o2 in (0x06,0x07):
                    k,r,n=tok(v)
                    if k=='internal':internal.append((r,n))
                    elif k=='external':external.append((r,n))
            elif o2 in fe_u16:i+=2
            elif o2 in fe_u8:i+=1
            continue
        if op in token_ops or op in other_token:
            if i+4>len(il):break
            v=struct.unpack_from('<I',il,i)[0];i+=4
            if op==0x72:
                s=us_at(v&0xffffff)
                if s:strings.append((s,v))
            elif op in (0x27,0x28,0x6f,0x73):
                k,r,n=tok(v)
                if k=='internal':internal.append((r,n))
                elif k=='external':external.append((r,n))
        elif op==0x45:
            if i+4>len(il):break
            n=struct.unpack_from('<I',il,i)[0];i+=4+4*n
        elif op in short1:i+=1
        elif op in long4:i+=4
        elif op in long8:i+=8
    return internal,external,strings

xref=[];method_cache={}
for m in methods[1:]:
    ins,exts,strings=scan_il(m);method_cache[m['rid']]={'internal':ins,'external':exts,'strings':strings}
    exact=[{'literal':s,'token':v} for s,v in strings if s in needles]
    if exact:
        xref.append({'rid':m['rid'],'symbol':symbol(m['rid']),'rva':m['rva'],'exactStrings':exact,'internalCalls':[{'rid':r,'symbol':n} for r,n in ins],'externalCalls':[n for _,n in exts]})

# Classify exact XREF methods and directed paths to write APIs using existing IL graph only.
def classify_api(n):
    s=n.lower()
    if 'rawimage' in s and ('set_texture' in s or '.set_texture' in s):return 'RawImage.set_texture'
    if 'camera' in s and ('set_targettexture' in s or 'set_target_texture' in s):return 'Camera.set_targetTexture'
    if 'rendertexture' in s:return 'RenderTexture'
    if 'graphics' in s and 'blit' in s:return 'Graphics.Blit'
    if 'commandbuffer' in s and 'blit' in s:return 'CommandBuffer.Blit'
    if 'material' in s and ('settexture' in s or 'set_texture' in s):return 'Material.SetTexture'
    if 'shader' in s and ('setglobaltexture' in s or 'set_global_texture' in s):return 'Shader.SetGlobalTexture'
    return None
def classify_lookup(n):
    s=n.lower()
    if 'gameobject.find' in s:return 'GameObject.Find'
    if 'transform.find' in s:return 'Transform.Find'
    if 'getcomponent' in s:return 'GetComponent'
    if 'findobject' in s:return 'FindObject'
    return None

direct=[]
for row in xref:
    ap=[];lp=[]
    for n in row['externalCalls']:
        a=classify_api(n);l=classify_lookup(n)
        if a:ap.append({'class':a,'target':n})
        if l:lp.append({'class':l,'target':n})
    if ap or lp:direct.append({'rid':row['rid'],'symbol':row['symbol'],'renderApis':ap,'lookupApis':lp})

adj=defaultdict(list)
for rid,c in method_cache.items():
    for callee,_ in c['internal']:adj[rid].append(callee)
write_rids=set()
write_by_rid=defaultdict(list)
for rid,c in method_cache.items():
    for _,n in c['external']:
        a=classify_api(n)
        if a:
            write_rids.add(rid);write_by_rid[rid].append({'class':a,'target':n})
paths=[]
for row in xref:
    start=row['rid'];q=deque([start]);par={start:None};depth={start:0};found=[]
    if start in write_rids:found=[start]
    while q and not found:
        x=q.popleft();d=depth[x]
        if d>=5:continue
        for y in adj.get(x,[]):
            if y in par:continue
            par[y]=x;depth[y]=d+1
            if y in write_rids:found.append(y);break
            q.append(y)
    for end in found[:3]:
        chain=[];z=end
        while z is not None:chain.append(z);z=par.get(z)
        chain.reverse();paths.append({'startRid':start,'depth':len(chain)-1,'methodRids':chain,'symbols':[symbol(r) for r in chain],'writeApis':write_by_rid[end]})

# Raw byte diagnostics distinguish "not in #US" from "present elsewhere in DLL".
raw_hits={}
for needle in needles:
    a=needle.encode('ascii');u=needle.encode('utf-16le')
    def positions(pat,limit=30):
        out=[];pos=0
        while len(out)<limit:
            j=data.find(pat,pos)
            if j<0:break
            out.append(j);pos=j+1
        return out
    raw_hits[needle]={'asciiOffsets':positions(a),'utf16leOffsets':positions(u)}

next_strategy='inspect_exact_il_name_xrefs_and_write_paths' if xref else ('trace_non_csharp_runtime_name_source_lua_or_serialized_logic' if any(raw_hits[n]['asciiOffsets'] or raw_hits[n]['utf16leOffsets'] for n in needles) else 'runtime_names_absent_from_csharp_dll_trace_lua_or_dynamic_lookup')
result={'format':'WFGG_LASTWAR_FORMATION_RUNTIME_NAME_IL_XREF_V1','dll':{'path':str(dll),'sha256':hashlib.sha256(data).hexdigest()},'needles':needles,'counts':{'typedefs':len(types),'methods':len(methods)-1,'userStringExactEntries':sum(len(v) for v in us_hits.values()),'xrefMethods':len(xref),'directEvidenceMethods':len(direct),'directedWritePaths':len(paths)},'userStringExactHits':dict(us_hits),'methodXrefs':xref,'directEvidence':direct,'directedWritePaths':paths,'rawByteDiagnostics':raw_hits,'conclusion':{'nextStrategy':next_strategy,'important':'Only exact #US equality and decoded ldstr XREF are promoted. Raw byte offsets are diagnostics only.'},'guardrails':{'recoveredDllOnly':True,'dllShaGuard':True,'apkAccess':False,'bundleScan':False,'atlasRebuild':False,'candidatePromotion':False,'mainUntouched':True,'previewUntouched':True}}
outp.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf-8')
lines=['WfGg Last War — FORMATION RUNTIME NAME IL XREF V1','',f"dllSha256={result['dll']['sha256']}",f"typedefs={len(types)} methods={len(methods)-1} #US_exact={result['counts']['userStringExactEntries']} xrefMethods={len(xref)} direct={len(direct)} writePaths={len(paths)}",f"nextStrategy={next_strategy}",'','EXACT #US LITERALS']
for n in needles:
    hs=us_hits.get(n,[])
    if hs:
        for h in hs:lines.append(f"  {n} heapIndex={h['heapIndex']} token=0x{h['token']:08x} fileOffset={h['heapFileOffset']}")
    else:lines.append(f'  {n}: NONE')
lines+=['','EXACT ldstr METHOD XREFS']
if xref:
    for r in xref:
        lines.append(f"  M:{r['rid']} {r['symbol']} strings={','.join(x['literal'] for x in r['exactStrings'])}")
        for n in r['externalCalls'][:40]:lines.append('    EXTERNAL '+n)
else:lines.append('  NONE')
lines+=['','DIRECT LOOKUP / WRITE EVIDENCE']
if direct:
    for r in direct:
        lines.append(f"  M:{r['rid']} {r['symbol']}")
        for x in r['lookupApis']:lines.append(f"    LOOKUP {x['class']} :: {x['target']}")
        for x in r['renderApis']:lines.append(f"    WRITE {x['class']} :: {x['target']}")
else:lines.append('  NONE')
lines+=['','DIRECTED EXACT NAME -> TEXTURE WRITE PATHS']
if paths:
    for p in paths:
        lines.append(f"  depth={p['depth']} "+' -> '.join('M:'+str(x) for x in p['methodRids']))
        lines.append('    SYMBOLS '+' -> '.join(p['symbols']))
        for a in p['writeApis']:lines.append(f"    WRITE {a['class']} :: {a['target']}")
else:lines.append('  NONE')
lines+=['','RAW BYTE DIAGNOSTICS (NOT XREF EVIDENCE)']
for n in needles:lines.append(f"  {n} ascii={raw_hits[n]['asciiOffsets']} utf16le={raw_hits[n]['utf16leOffsets']}")
lines+=['','NEXT '+next_strategy,'RULE: exact #US + decoded ldstr only are XREF evidence; raw byte presence is diagnostic only.','RULE: recovered DLL only; no APK/bundle read, no atlas rebuild, no candidate promotion, main/preview untouched.']
reportp.write_text('\n'.join(lines)+'\n','utf-8')
print('FORMATION_IL_XREF_OK',f"us={result['counts']['userStringExactEntries']}",f"xrefs={len(xref)}",f"direct={len(direct)}",f"paths={len(paths)}")
for r in xref[:20]:print('FORMATION_IL_XREF_METHOD',f"M:{r['rid']}",r['symbol'],','.join(x['literal'] for x in r['exactStrings']))
for p in paths[:20]:print('FORMATION_IL_XREF_WRITE_PATH',p['depth'],'->'.join('M:'+str(x) for x in p['methodRids']))
print('FORMATION_IL_XREF_NEXT',next_strategy)
print('FORMATION_IL_XREF_JSON',outp)
print('FORMATION_IL_XREF_REPORT',reportp)
PY

git add "$OUT"
if ! git diff --cached --quiet; then
  git commit -m "lab: xref exact Formation runtime names in recovered IL"
  git push origin "$BRANCH"
fi

echo "FORMATION_IL_XREF_DONE"
