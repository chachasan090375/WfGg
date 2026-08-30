#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — Formation dynamic binding bridge V1.
# Narrow evidence pass only:
# - exact CLR atlas methods already known around XLua/resource loading
# - targeted IL ldstr/XREF for exact Formation panel/path names in recovered DLL
# NO APK read, NO bundle scan/extraction, NO atlas rebuild, NO candidate promotion.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
ATLAS="$ROOT/frontend/lab/master-assets-v2/index/lastwar-code-discovery-atlas-v1.json"
DLL="$HOME/storage/downloads/WFGG_LASTWAR_Assembly-CSharp_recovered.dll"
OUT="$ROOT/frontend/lab/master-assets-v2/meta/formation-dynamic-binding-bridge-v1.json"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_FORMATION_DYNAMIC_BINDING_BRIDGE_V1.txt"
EXPECTED_DLL_SHA="ed02eadb7764f7ff82a0d9b8746987ece867b2ccf7b06e9022e06c79259c380f"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
[[ -s "$ATLAS" ]] || fail "atlas absent: $ATLAS"
[[ -s "$DLL" ]] || fail "DLL récupérée absente: $DLL"
command -v python >/dev/null 2>&1 || fail "python absent"
sha="$(sha256sum "$DLL" | awk '{print $1}')"
[[ "$sha" == "$EXPECTED_DLL_SHA" ]] || fail "DLL SHA inattendu: $sha"
mkdir -p "$(dirname "$OUT")" "$(dirname "$REPORT")"

python - "$ATLAS" "$DLL" "$OUT" "$REPORT" <<'PY'
from __future__ import annotations
from pathlib import Path
from collections import defaultdict, deque
import hashlib,json,re,struct,sys

atlasp,dllp,outp,reportp=map(Path,sys.argv[1:])
a=json.loads(atlasp.read_text('utf-8'))
data=dllp.read_bytes()

# ---------- atlas helpers ----------
types=a.get('types') or []
methods=a.get('methods') or []
internal=a.get('internalEdges') or []
external=a.get('externalCalls') or []
type_by_rid={int(t['rid']):t for t in types}
method_by_rid={int(m['rid']):m for m in methods}
methods_by_type=defaultdict(list)
for m in methods:
    if m.get('typeRid') is not None: methods_by_type[int(m['typeRid'])].append(m)

def full_type(t):
    return ((str(t.get('namespace'))+'.') if t.get('namespace') else '')+str(t.get('name') or '')
def symbol(m):
    t=type_by_rid.get(int(m.get('typeRid') or 0))
    return (full_type(t)+'.' if t else '')+str(m.get('name') or '')

# Known exact boundary symbols accumulated in previous evidence.
needle_symbols=[
 'XLuaManager.Initialize',
 'XLuaManager.CustomLoaderImpl',
 'LuaUIFormLogic.LuaInit',
 'PBController.OnLoadAssets',
]
selected=[]
for m in methods:
    s=symbol(m)
    if any(s.endswith(n) or s==n for n in needle_symbols):
        selected.append(m)
selected.sort(key=lambda m:(symbol(m),int(m['rid'])))

ext_by_rid=defaultdict(list)
for ex in external:
    for rid in ex.get('callerRids') or []:
        ext_by_rid[int(rid)].append(str(ex.get('target') or ''))

in_adj=defaultdict(set);out_adj=defaultdict(set)
for e in internal:
    if isinstance(e,(list,tuple)) and len(e)>=2:
        try:
            x,y=int(e[0]),int(e[1]);out_adj[x].add(y);in_adj[y].add(x)
        except:pass

atlas_rows=[]
for m in selected:
    rid=int(m['rid'])
    atlas_rows.append({
      'rid':rid,'symbol':symbol(m),'strings':m.get('strings') or [],
      'externalCalls':sorted(set(ext_by_rid.get(rid,[]))),
      'callers':sorted(in_adj.get(rid,set())),
      'callees':sorted(out_adj.get(rid,set())),
      'tags':m.get('tags') or [],
    })

# ---------- minimal CLR metadata + IL parser ----------
u16=lambda o:struct.unpack_from('<H',data,o)[0]
u32=lambda o:struct.unpack_from('<I',data,o)[0]
u64=lambda o:struct.unpack_from('<Q',data,o)[0]
if data[:2]!=b'MZ':raise SystemExit('DLL_MZ_INVALID')
el=u32(0x3c)
if data[el:el+4]!=b'PE\0\0':raise SystemExit('DLL_PE_INVALID')
coff=el+4;nsec=u16(coff+2);optsz=u16(coff+16);opt=coff+20;magic=u16(opt);dd=opt+(96 if magic==0x10b else 112)
secs=[];soff=opt+optsz
for i in range(nsec):
    o=soff+i*40;secs.append((u32(o+12),u32(o+8),u32(o+16),u32(o+20)))
def rvaoff(rva):
    for va,vs,rs,ro in secs:
        if va<=rva<va+max(vs,rs):return ro+(rva-va)
    if rva<len(data):return rva
    raise ValueError(rva)
clr=rvaoff(u32(dd+14*8));meta=rvaoff(u32(clr+8))
if data[meta:meta+4]!=b'BSJB':raise SystemExit('BSJB_INVALID')
ver=u32(meta+12);q=(meta+16+ver+3)&~3;nstreams=u16(q+2);q+=4
sm={}
for _ in range(nstreams):
    off=u32(q);size=u32(q+4);q+=8;e=data.find(b'\0',q,q+64)
    nm=data[q:e].decode('ascii','replace');q=(e+4)&~3;sm[nm]=(meta+off,size)
str_o,str_s=sm['#Strings']; us_o,us_s=sm.get('#US',(0,0)); tbl_o,tbl_s=sm.get('#~',sm.get('#-'))
def s_at(i):
    if not i:return ''
    o=str_o+i;e=data.find(b'\0',o,str_o+str_s)
    return data[o:(e if e>=0 else min(o+512,str_o+str_s))].decode('utf-8','replace')
def comp(o):
    b=data[o]
    if b<0x80:return b,1
    if b<0xC0:return ((b&63)<<8)|data[o+1],2
    return ((b&31)<<24)|(data[o+1]<<16)|(data[o+2]<<8)|data[o+3],4
def us_at(i):
    if not us_o or i<=0 or i>=us_s:return ''
    try:
        n,k=comp(us_o+i);raw=data[us_o+i+k:us_o+i+k+n]
        if raw:raw=raw[:-1]
        return raw.decode('utf-16le','replace')
    except:return ''

heap=data[tbl_o+6];valid=u64(tbl_o+8);q=tbl_o+24;rows={}
for tid in range(64):
    if (valid>>tid)&1:rows[tid]=u32(q);q+=4
row0=q;strsz=4 if heap&1 else 2;guidsz=4 if heap&2 else 2;blobsz=4 if heap&4 else 2
def ix(t):return 4 if rows.get(t,0)>=65536 else 2
def cx(bits,*tids):return 4 if max([rows.get(x,0) for x in tids] or [0])>=(1<<(16-bits)) else 2
rs={0:2+strsz+guidsz*3,1:cx(2,0,26,35,1)+2*strsz,2:4+2*strsz+cx(2,1,2,27)+ix(4)+ix(6),3:ix(4),4:2+strsz+blobsz,5:ix(6),6:4+2+2+strsz+blobsz+ix(8),7:ix(8),8:2+2+strsz,9:ix(2)+cx(2,1,2,27),10:cx(3,2,1,26,6,27)+strsz+blobsz}
offs={};cur=row0
for tid in range(11):
    if (valid>>tid)&1:
        if tid not in rs:raise SystemExit(f'ROW_SIZE_MISSING_{tid}')
        offs[tid]=cur;cur+=rs[tid]*rows.get(tid,0)
def ri(o,z):return u16(o) if z==2 else u32(o)

# TypeRef
tr=[None]
for rid in range(1,rows.get(1,0)+1):
    o=offs[1]+(rid-1)*rs[1];p=o+cx(2,0,26,35,1);ni=ri(p,strsz);p+=strsz;nsi=ri(p,strsz)
    tr.append((s_at(nsi),s_at(ni)))
# MethodDef
md=[None]
for rid in range(1,rows.get(6,0)+1):
    o=offs[6]+(rid-1)*rs[6];md.append({'rid':rid,'rva':u32(o),'name':s_at(ri(o+8,strsz))})
# TypeDef + owner map
raw=[]
for rid in range(1,rows.get(2,0)+1):
    o=offs[2]+(rid-1)*rs[2];p=o+4;ni=ri(p,strsz);p+=strsz;nsi=ri(p,strsz);p+=strsz;p+=cx(2,1,2,27)+ix(4);ms=ri(p,ix(6))
    raw.append({'rid':rid,'namespace':s_at(nsi),'name':s_at(ni),'methodStart':ms})
owner={};td={x['rid']:x for x in raw}
for i,t in enumerate(raw):
    end=(raw[i+1]['methodStart']-1 if i+1<len(raw) else rows.get(6,0))
    if t['methodStart']:
        for r in range(max(1,t['methodStart']),min(end,len(md)-1)+1):owner[r]=t

def tname(t):return ((t.get('namespace')+'.') if t.get('namespace') else '')+t.get('name','')
# MemberRef
mr=[None];mps=cx(3,2,1,26,6,27)
for rid in range(1,rows.get(10,0)+1):
    o=offs[10]+(rid-1)*rs[10];par=ri(o,mps);ni=ri(o+mps,strsz);mr.append((par,s_at(ni)))
def parent_name(c):
    tag=c&7;rid=c>>3
    if tag==0 and rid in td:return tname(td[rid])
    if tag==1 and rid<len(tr):ns,n=tr[rid];return (ns+'.' if ns else '')+n
    if tag==3 and rid in owner:return tname(owner[rid])
    return f'tag{tag}:rid{rid}'
def token_name(tok):
    tab=(tok>>24)&255;rid=tok&0xffffff
    if tab==6 and rid<len(md):return ('internal',rid,tname(owner.get(rid,{}))+'.'+md[rid]['name'])
    if tab==10 and rid<len(mr):return ('external',rid,parent_name(mr[rid][0])+'.'+mr[rid][1])
    return ('other',rid,f'0x{tok:08x}')
def body(m):
    if not m or not m['rva']:return None
    try:o=rvaoff(m['rva'])
    except:return None
    b=data[o]
    if b&3==2:cs=b>>2;s=o+1
    elif b&3==3:
        h=u16(o);hs=((h>>12)&15)*4;cs=u32(o+4);s=o+hs
    else:return None
    return data[s:s+cs] if s+cs<=len(data) else None

token_ops={0x27,0x28,0x29,0x6f,0x72,0x73};other_token={0x70,0x71,0x74,0x75,0x79,0x7b,0x7c,0x7d,0x7e,0x7f,0x80,0x81,0x8c,0x8d,0x8f,0xa3,0xa4,0xa5,0xc2,0xc6,0xd0}
short1=set(range(0x2b,0x38))|{0x0e,0x0f,0x10,0x11,0x12,0x13,0x1f,0xde};long4=set(range(0x38,0x45))|{0x20,0xdd,0x22};long8={0x21,0x23}
fe_token={0x06,0x07,0x15,0x16,0x1c};fe_u16={0x09,0x0a,0x0b,0x0c,0x0d,0x0e};fe_u8={0x12,0x19}
def scan_il(m):
    il=body(m)
    if il is None:return {'strings':[],'internal':[],'external':[]}
    strings=[];ins=[];ext=[];i=0
    while i<len(il):
        op=il[i];i+=1
        if op==0xfe:
            if i>=len(il):break
            o2=il[i];i+=1
            if o2 in fe_token:
                if i+4>len(il):break
                tokv=struct.unpack_from('<I',il,i)[0];i+=4
                if o2 in (0x06,0x07):
                    k,r,n=token_name(tokv); (ins if k=='internal' else ext if k=='external' else []).append((r,n))
            elif o2 in fe_u16:i+=2
            elif o2 in fe_u8:i+=1
            continue
        if op in token_ops or op in other_token:
            if i+4>len(il):break
            tokv=struct.unpack_from('<I',il,i)[0];i+=4
            if op==0x72:
                s=us_at(tokv&0xffffff)
                if s:strings.append(s)
            elif op in (0x27,0x28,0x6f,0x73):
                k,r,n=token_name(tokv)
                if k=='internal':ins.append((r,n))
                elif k=='external':ext.append((r,n))
        elif op==0x45:
            if i+4>len(il):break
            n=struct.unpack_from('<I',il,i)[0];i+=4+4*n
        elif op in short1:i+=1
        elif op in long4:i+=4
        elif op in long8:i+=8
    return {'strings':strings,'internal':ins,'external':ext}

# Exact methods targeted above, decoded directly from DLL.
exact_method_il=[]
for row in atlas_rows:
    rid=row['rid']; m=md[rid] if 0<rid<len(md) else None; sc=scan_il(m)
    exact_method_il.append({'rid':rid,'symbol':row['symbol'],'strings':sc['strings'],'internalCalls':[x[1] for x in sc['internal']],'externalCalls':[x[1] for x in sc['external']]})

# Exact string XREF targets. Full prefab path first; names are secondary exact strings.
TARGETS=[
 'Assets/Main/Prefabs/UI/UIHero/LWHero/UIHeroPVPFormationPanel.prefab',
 'UIHeroPVPFormationPanel',
 'FormationContent',
 'MiddleContentContainer',
]
# Decode #US once to exact value->offsets.
us_exact=defaultdict(list)
pos=1
while us_o and pos<us_s:
    try:
        n,k=comp(us_o+pos)
        if n<=0:pos+=max(k,1);continue
        rawv=data[us_o+pos+k:us_o+pos+k+n]
        if rawv:rawv=rawv[:-1]
        val=rawv.decode('utf-16le','replace')
        if val in TARGETS:us_exact[val].append(pos)
        pos+=k+n
    except:
        pos+=1

# Only methods with targeted ldstr are materialized.
xrefs=[]
for rid in range(1,len(md)):
    m=md[rid];sc=scan_il(m)
    hits=sorted(set(s for s in sc['strings'] if s in TARGETS))
    if not hits:continue
    xrefs.append({'rid':rid,'symbol':tname(owner.get(rid,{}))+'.'+m['name'],'strings':hits,'allStrings':sc['strings'],'internalCalls':[n for _,n in sc['internal']],'externalCalls':[n for _,n in sc['external']]})

# Classify exact XREF evidence.
def classes(calls):
    z=[]
    for n in calls:
        s=n.lower()
        if 'resources.load' in s or 'assetbundle' in s or 'loadasset' in s or 'resourcemanager' in s or 'assetmanager' in s:z.append('resource-loader')
        if 'instantiate' in s:z.append('instantiate')
        if 'xlua' in s or 'luaenv' in s or 'luafunction' in s or 'luatable' in s:z.append('lua-boundary')
        if 'gameobject.find' in s or 'transform.find' in s:z.append('runtime-find')
        if 'rawimage' in s and 'set_texture' in s:z.append('rawimage-write')
        if 'camera' in s and 'targettexture' in s:z.append('camera-targettexture')
    return sorted(set(z))
for r in xrefs:r['classes']=classes(r['externalCalls'])

# Compact boundary findings from exact loader methods.
loader_strings=[]
for r in exact_method_il:
    for s in r['strings']:
        if s and s not in loader_strings:loader_strings.append(s)

if any('Assets/Main/Prefabs/UI/UIHero/LWHero/UIHeroPVPFormationPanel.prefab' in r['strings'] for r in xrefs):
    next_strategy='inspect_exact_csharp_panel_loader_xref'
elif xrefs:
    next_strategy='inspect_exact_panel_name_xrefs_then_dynamic_boundary'
elif loader_strings:
    next_strategy='use_exact_xlua_loader_strings_to_locate_script_container'
else:
    next_strategy='targeted_current_install_lua_container_locator_from_xlua_loader_methods'

result={
 'format':'WFGG_LASTWAR_FORMATION_DYNAMIC_BINDING_BRIDGE_V1',
 'dllSha256':hashlib.sha256(data).hexdigest(),
 'atlasExactBoundaryMethods':atlas_rows,
 'exactBoundaryMethodIL':exact_method_il,
 'targets':TARGETS,
 'usExactOffsets':{k:v for k,v in us_exact.items()},
 'exactStringXrefs':xrefs,
 'loaderStrings':loader_strings,
 'counts':{'selectedBoundaryMethods':len(atlas_rows),'exactStringXrefMethods':len(xrefs),'loaderStrings':len(loader_strings)},
 'nextStrategy':next_strategy,
 'guardrails':{'recoveredDllOnly':True,'apkAccess':False,'bundleScan':False,'bundleExtraction':False,'atlasRebuild':False,'candidatePromotion':False,'mainUntouched':True,'previewUntouched':True}
}
outp.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf-8')

lines=['WfGg Last War — FORMATION DYNAMIC BINDING BRIDGE V1','',
 f"dllSha256={result['dllSha256']}",
 f"boundaryMethods={len(atlas_rows)} exactStringXrefMethods={len(xrefs)} loaderStrings={len(loader_strings)}",
 f"nextStrategy={next_strategy}",'',
 'EXACT BOUNDARY METHODS']
if exact_method_il:
    for r in exact_method_il:
        lines.append(f"  M:{r['rid']} {r['symbol']}")
        for s in r['strings']:lines.append('    STRING '+repr(s))
        for x in r['externalCalls'][:30]:lines.append('    EXT '+x)
else:lines.append('  NONE')
lines += ['', 'EXACT PANEL / HIERARCHY STRING XREFS']
if xrefs:
    for r in xrefs:
        lines.append(f"  M:{r['rid']} {r['symbol']} strings={r['strings']} classes={r['classes']}")
        for x in r['externalCalls'][:30]:lines.append('    EXT '+x)
else:lines.append('  NONE')
lines += ['', 'XLUA / LOADER STRINGS']
if loader_strings:
    for s in loader_strings:lines.append('  '+repr(s))
else:lines.append('  NONE')
lines += ['', 'NEXT '+next_strategy,
 'RULE: exact MethodDef + decoded IL/string evidence only; names without exact XREF are not promoted.',
 'RULE: recovered DLL only; no APK read, bundle scan/extraction, atlas rebuild, candidate promotion, main/preview modification.']
reportp.write_text('\n'.join(lines)+'\n','utf-8')
print('FORMATION_DYNAMIC_BRIDGE_OK',f'boundaryMethods={len(atlas_rows)}',f'xrefs={len(xrefs)}',f'loaderStrings={len(loader_strings)}')
for r in xrefs[:30]:print('FORMATION_DYNAMIC_XREF',f"M:{r['rid']}",r['symbol'],','.join(r['classes']) or '-')
for s in loader_strings[:30]:print('FORMATION_DYNAMIC_LOADER_STRING',repr(s))
print('FORMATION_DYNAMIC_BRIDGE_NEXT',next_strategy)
print('FORMATION_DYNAMIC_BRIDGE_JSON',outp)
print('FORMATION_DYNAMIC_BRIDGE_REPORT',reportp)
PY

git add "$OUT"
if ! git diff --cached --quiet; then
  git commit -m "lab: trace Formation dynamic binding bridge"
  git push origin "$BRANCH"
fi

echo "FORMATION_DYNAMIC_BRIDGE_DONE"
