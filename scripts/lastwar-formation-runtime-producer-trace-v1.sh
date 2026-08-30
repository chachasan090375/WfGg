#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
DLL="$HOME/storage/downloads/WFGG_LASTWAR_Assembly-CSharp_recovered.dll"
V4="$ROOT/frontend/lab/master-assets-v2/meta/formation-ptr-exact-v4.json"
BG="$ROOT/frontend/lab/master-assets-v2/meta/formation-background-pipeline-v1.json"
ATLAS="$ROOT/frontend/lab/master-assets-v2/index/lastwar-code-discovery-atlas-v1.json"
OUT="$ROOT/frontend/lab/master-assets-v2/meta/formation-runtime-producer-trace-v1.json"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_FORMATION_RUNTIME_PRODUCER_TRACE_V1.txt"
EXPECTED_DLL_SHA="ed02eadb7764f7ff82a0d9b8746987ece867b2ccf7b06e9022e06c79259c380f"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
for f in "$DLL" "$V4" "$BG" "$ATLAS"; do [[ -s "$f" ]] || fail "fichier absent: $f"; done
command -v python >/dev/null 2>&1 || fail "python absent"
mkdir -p "$(dirname "$OUT")" "$(dirname "$REPORT")"

python - "$DLL" "$V4" "$BG" "$ATLAS" "$OUT" "$REPORT" "$EXPECTED_DLL_SHA" <<'PY'
from pathlib import Path
from collections import defaultdict,deque
import hashlib,json,re,struct,sys

dll,v4p,bgp,atlasp,outp,reportp=map(Path,sys.argv[1:7]); expected=sys.argv[7]
data=dll.read_bytes(); sha=hashlib.sha256(data).hexdigest()
if sha!=expected: raise SystemExit(f'DLL_SHA_MISMATCH expected={expected} actual={sha}')
g=json.loads(v4p.read_text('utf-8')); bg=json.loads(bgp.read_text('utf-8')); a=json.loads(atlasp.read_text('utf-8'))
nodes=g.get('nodes') or []; edges=g.get('edges') or []
if len(nodes)!=3209: raise SystemExit(f'PTR_NODE_COUNT_MISMATCH expected=3209 actual={len(nodes)}')

# ---------- exact V4 graph ancestry ----------
by_id={str(n.get('id')):n for n in nodes if n.get('id') is not None}
by_pid=defaultdict(list)
for n in nodes:
    if n.get('pathID') is not None: by_pid[int(n['pathID'])].append(n)
out_edges=defaultdict(list)
for e in edges: out_edges[str(e.get('from'))].append(e)

def rel(e): return str(e.get('relation') or '').lower()
def node_for_endpoint(v):
    if str(v) in by_id:return by_id[str(v)]
    m=re.search(r'#(-?\d+)$',str(v))
    if m:
        xs=by_pid.get(int(m.group(1)),[])
        return xs[0] if len(xs)==1 else None
    return None

def node_by_pid(pid):
    xs=by_pid.get(int(pid),[]); return xs[0] if len(xs)==1 else None

def first(x): return (x or [{}])[0] if isinstance(x,list) else (x or {})
def ptr(row,path):
    for p in row.get('pointers') or []:
        if p.get('path')==path:return int(p.get('pathId') or p.get('pathID') or 0)
    return 0
bgr=first(bg.get('FormationBgRawImage')); rtr=first(bg.get('FormationRTRawImage'))
anchors={
 'FormationBg':{'rawImagePathID':int(bgr.get('pathId') or 0),'gameObjectPathID':ptr(bgr,'m_GameObject')},
 'FormationRT':{'rawImagePathID':int(rtr.get('pathId') or 0),'gameObjectPathID':ptr(rtr,'m_GameObject')},
}

def components(go):
    out=[]
    if not go:return out
    for e in out_edges.get(str(go.get('id')),[]):
        if rel(e)=='component_ref':
            n=node_for_endpoint(e.get('to'))
            if n:out.append(n)
    return out

def script_names_on_go(go):
    rows=[]
    for c in components(go):
        for e in out_edges.get(str(c.get('id')),[]):
            if rel(e)=='script_ref':
                s=node_for_endpoint(e.get('to'))
                if s: rows.append({'componentPathID':c.get('pathID'),'componentType':c.get('type'),'scriptPathID':s.get('pathID'),'scriptName':s.get('name') or ''})
    ded=[];seen=set()
    for r in rows:
        k=(r['componentPathID'],r['scriptPathID'],r['scriptName'])
        if k not in seen:seen.add(k);ded.append(r)
    return ded

def parent_go(go):
    trs=[c for c in components(go) if str(c.get('type')) in ('Transform','RectTransform')]
    for t in trs:
        pe=[e for e in out_edges.get(str(t.get('id')),[]) if rel(e)=='hierarchy_ref' and 'm_Father' in str(e.get('fieldPath'))]
        for e in pe:
            pt=node_for_endpoint(e.get('to'))
            if not pt:continue
            for ge in out_edges.get(str(pt.get('id')),[]):
                if rel(ge)=='gameobject_ref' and 'm_GameObject' in str(ge.get('fieldPath')):
                    pg=node_for_endpoint(ge.get('to'))
                    if pg:return pg
    return None

ancestor_chains={}
ancestor_script_rows=[]
for an,x in anchors.items():
    go=node_by_pid(x['gameObjectPathID']); chain=[];seen=set();level=0
    while go and str(go.get('id')) not in seen and level<32:
        seen.add(str(go.get('id')))
        scripts=script_names_on_go(go)
        row={'level':level,'gameObjectId':go.get('id'),'gameObjectPathID':go.get('pathID'),'gameObjectName':go.get('name'),'scripts':scripts}
        chain.append(row)
        for s in scripts:ancestor_script_rows.append({'anchor':an,'level':level,'gameObjectName':go.get('name'),**s})
        go=parent_go(go);level+=1
    ancestor_chains[an]=chain

# ---------- atlas joins ----------
types=a.get('types') or []; methods=a.get('methods') or []; internal=a.get('internalEdges') or []; external=a.get('externalCalls') or []
type_by_rid={int(t['rid']):t for t in types}; method_by_rid={int(m['rid']):m for m in methods}; methods_by_type=defaultdict(list)
for m in methods:
    if m.get('typeRid') is not None:methods_by_type[int(m['typeRid'])].append(m)
def full_type(t):return ((str(t.get('namespace'))+'.') if t.get('namespace') else '')+str(t.get('name') or '')
def sym(rid):
    m=method_by_rid.get(int(rid));
    if not m:return f'M:{rid}'
    t=type_by_rid.get(int(m.get('typeRid') or 0));return (full_type(t)+'.' if t else '')+str(m.get('name') or '')
by_typename=defaultdict(list)
for t in types:by_typename[str(t.get('name') or '')].append(t)

# exact external API map already indexed
ext_by_method=defaultdict(list)
for ex in external:
    target=str(ex.get('target') or '')
    for rid in ex.get('callerRids') or []:ext_by_method[int(rid)].append(target)

def write_api(s):
    x=s.lower()
    if 'rawimage' in x and 'set_texture' in x:return 'RawImage.set_texture'
    if 'camera' in x and ('set_targettexture' in x or 'set_target_texture' in x):return 'Camera.set_targetTexture'
    if 'graphics' in x and 'blit' in x:return 'Graphics.Blit'
    if 'commandbuffer' in x and 'blit' in x:return 'CommandBuffer.Blit'
    if 'material' in x and ('settexture' in x or 'set_texture' in x):return 'Material.SetTexture'
    if 'shader' in x and ('setglobaltexture' in x or 'set_global_texture' in x):return 'Shader.SetGlobalTexture'
    if 'videoplayer' in x and 'targettexture' in x:return 'VideoPlayer.targetTexture'
    return None

def lookup_api(s):
    x=s.lower()
    if 'gameobject.find' in x:return 'GameObject.Find'
    if 'transform.find' in x:return 'Transform.Find'
    if 'getcomponent' in x:return 'GetComponent'
    return None
write_callers={rid for rid,ts in ext_by_method.items() if any(write_api(t) for t in ts)}
adj=defaultdict(list)
for p in internal:
    if isinstance(p,(list,tuple)) and len(p)>=2:
        try:adj[int(p[0])].append(int(p[1]))
        except:pass

def shortest_write_path(start,maxd=5):
    start=int(start)
    if start in write_callers:return [start]
    q=deque([start]);par={start:None};dep={start:0}
    while q:
        x=q.popleft();d=dep[x]
        if d>=maxd:continue
        for y in adj.get(x,[]):
            if y in par:continue
            par[y]=x;dep[y]=d+1
            if y in write_callers:
                z=[];c=y
                while c is not None:z.append(c);c=par[c]
                return list(reversed(z))
            q.append(y)
    return None

resolved_ancestor=[];ambiguous_ancestor=[]
seen_script=set()
for r in ancestor_script_rows:
    name=str(r.get('scriptName') or '')
    if not name or name in seen_script:continue
    seen_script.add(name);cand=by_typename.get(name,[])
    if len(cand)==1:
        t=cand[0]; mr=methods_by_type[int(t['rid'])]; evid=[]
        for m in mr:
            rid=int(m['rid']); wr=[{'api':write_api(x),'target':x} for x in ext_by_method.get(rid,[]) if write_api(x)]
            lk=[{'api':lookup_api(x),'target':x} for x in ext_by_method.get(rid,[]) if lookup_api(x)]
            p=shortest_write_path(rid)
            if wr or lk or (p and len(p)>1):evid.append({'rid':rid,'symbol':sym(rid),'writes':wr,'lookups':lk,'writePath':p,'writePathSymbols':[sym(x) for x in p] if p else []})
        resolved_ancestor.append({'scriptName':name,'typeRid':int(t['rid']),'fullName':full_type(t),'methodCount':len(mr),'evidence':evid})
    elif len(cand)>1:ambiguous_ancestor.append({'scriptName':name,'candidates':[{'rid':int(t['rid']),'fullName':full_type(t)} for t in cand]})

# ---------- targeted exact IL string XREF ----------
u16=lambda o:struct.unpack_from('<H',data,o)[0];u32=lambda o:struct.unpack_from('<I',data,o)[0];u64=lambda o:struct.unpack_from('<Q',data,o)[0]
if data[:2]!=b'MZ':raise SystemExit('DLL_MZ_MISSING')
e_lfanew=u32(0x3c)
if data[e_lfanew:e_lfanew+4]!=b'PE\0\0':raise SystemExit('DLL_PE_MISSING')
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
ver=u32(meta+12);q=(meta+16+ver+3)&~3;nstreams=u16(q+2);q+=4;sm={}
for _ in range(nstreams):
    off=u32(q);size=u32(q+4);q+=8;e=data.find(b'\0',q,q+64);name=data[q:e].decode('ascii','replace');q=(e+4)&~3;sm[name]=(meta+off,size)
so,ss=sm['#Strings'];uso,uss=sm.get('#US',(0,0));to,ts=sm.get('#~',sm.get('#-'))
def s_at(i):
    if not i:return ''
    o=so+i;e=data.find(b'\0',o,so+ss);return data[o:(e if e>=0 else min(o+512,so+ss))].decode('utf-8','replace')
def comp(o):
    b=data[o]
    if b<0x80:return b,1
    if b<0xC0:return ((b&63)<<8)|data[o+1],2
    return ((b&31)<<24)|(data[o+1]<<16)|(data[o+2]<<8)|data[o+3],4
def us_at(i):
    if not uso or i<=0 or i>=uss:return ''
    try:n,k=comp(uso+i);raw=data[uso+i+k:uso+i+k+n];raw=raw[:-1] if raw else raw;return raw.decode('utf-16le','replace')
    except:return ''
heap=data[to+6];valid=u64(to+8);q=to+24;rows={}
for tid in range(64):
    if (valid>>tid)&1:rows[tid]=u32(q);q+=4
row0=q;strsz=4 if heap&1 else 2;guidsz=4 if heap&2 else 2;blobsz=4 if heap&4 else 2
def ix(t):return 4 if rows.get(t,0)>=65536 else 2
def cx(bits,*tids):return 4 if max([rows.get(x,0) for x in tids] or [0])>=(1<<(16-bits)) else 2
rs={0:2+strsz+guidsz*3,1:cx(2,0,26,35,1)+2*strsz,2:4+2*strsz+cx(2,1,2,27)+ix(4)+ix(6),3:ix(4),4:2+strsz+blobsz,5:ix(6),6:4+2+2+strsz+blobsz+ix(8)}
offs={};cur=row0
for tid in range(7):
    if (valid>>tid)&1:offs[tid]=cur;cur+=rs[tid]*rows.get(tid,0)
def ri(o,z):return u16(o) if z==2 else u32(o)
dll_methods=[None]
for rid in range(1,rows.get(6,0)+1):
    o=offs[6]+(rid-1)*rs[6];dll_methods.append({'rid':rid,'rva':u32(o),'name':s_at(ri(o+8,strsz))})
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
short1=set(range(0x2b,0x38))|{0x0e,0x0f,0x10,0x11,0x12,0x13,0x1f,0xde};long4=set(range(0x38,0x45))|{0x20,0xdd,0x22};long8={0x21,0x23};token_ops={0x27,0x28,0x29,0x6f,0x70,0x71,0x72,0x73,0x74,0x75,0x79,0x7b,0x7c,0x7d,0x7e,0x7f,0x80,0x81,0x8c,0x8d,0x8f,0xa3,0xa4,0xa5,0xc2,0xc6,0xd0};fe_token={0x06,0x07,0x15,0x16,0x1c};fe_u16={0x09,0x0a,0x0b,0x0c,0x0d,0x0e};fe_u8={0x12,0x19}
def strings_in_method(m):
    il=body(m);out=[]
    if il is None:return out
    i=0
    while i<len(il):
        op=il[i];i+=1
        if op==0xfe:
            if i>=len(il):break
            o2=il[i];i+=1
            if o2 in fe_token:i+=4
            elif o2 in fe_u16:i+=2
            elif o2 in fe_u8:i+=1
            continue
        if op in token_ops:
            if i+4>len(il):break
            v=struct.unpack_from('<I',il,i)[0];i+=4
            if op==0x72:
                s=us_at(v&0xffffff)
                if s:out.append(s)
        elif op==0x45:
            if i+4>len(il):break
            n=struct.unpack_from('<I',il,i)[0];i+=4+4*n
        elif op in short1:i+=1
        elif op in long4:i+=4
        elif op in long8:i+=8
    return out

wanted={'FormationBg','FormationRT'};exact_xrefs=[];containing=[]
for m in dll_methods[1:]:
    ss2=strings_in_method(m)
    for s in ss2:
        if s in wanted: exact_xrefs.append({'rid':m['rid'],'symbol':sym(m['rid']),'literal':s,'externalCalls':ext_by_method.get(m['rid'],[]),'writePath':shortest_write_path(m['rid'])})
        elif any(w in s for w in wanted):containing.append({'rid':m['rid'],'symbol':sym(m['rid']),'literal':s})
raw_counts={w:{'ascii':data.count(w.encode()),'utf16le':data.count(w.encode('utf-16le'))} for w in wanted}
for x in exact_xrefs:
    p=x.get('writePath');x['writePathSymbols']=[sym(r) for r in p] if p else [];x['directWrites']=[{'api':write_api(t),'target':t} for t in x['externalCalls'] if write_api(t)];x['lookups']=[{'api':lookup_api(t),'target':t} for t in x['externalCalls'] if lookup_api(t)]

ancestor_write_evidence=[]
for t in resolved_ancestor:
    for e in t['evidence']:
        if e.get('writes') or e.get('writePath'):ancestor_write_evidence.append({'scriptName':t['scriptName'],'fullName':t['fullName'],**e})

if exact_xrefs:
    strategy='inspect_exact_il_name_xrefs_and_write_paths'
elif ancestor_write_evidence:
    strategy='inspect_exact_ancestor_controller_write_paths'
else:
    strategy='trace_xlua_or_runtime_ui_binding_from_exact_ancestor_script_set'

result={
 'format':'WFGG_LASTWAR_FORMATION_RUNTIME_PRODUCER_TRACE_V1',
 'dll':{'path':str(dll),'sha256':sha,'methods':len(dll_methods)-1},
 'ptr':{'nodes':len(nodes),'edges':len(edges),'anchors':anchors},
 'exactNameXrefs':exact_xrefs,
 'containingNameXrefs':containing[:100],
 'rawNameByteCounts':raw_counts,
 'ancestorChains':ancestor_chains,
 'ancestorScriptRows':ancestor_script_rows,
 'resolvedAncestorScripts':resolved_ancestor,
 'ambiguousAncestorScripts':ambiguous_ancestor,
 'ancestorWriteEvidence':ancestor_write_evidence,
 'counts':{'exactNameXrefs':len(exact_xrefs),'containingNameXrefs':len(containing),'ancestorScriptRows':len(ancestor_script_rows),'resolvedAncestorScripts':len(resolved_ancestor),'ancestorWriteEvidence':len(ancestor_write_evidence)},
 'conclusion':{'nextStrategy':strategy},
 'guardrails':{'apkAccess':False,'bundleScan':False,'newExtraction':False,'dllExactStringXrefOnly':True,'candidatePromotion':False,'mainUntouched':True,'previewUntouched':True}
}
outp.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf-8')

lines=['WfGg Last War — FORMATION RUNTIME PRODUCER TRACE V1','',f'dllSha={sha}',f'ptrNodes={len(nodes)} ptrEdges={len(edges)} atlasMethods={len(methods)}',f'exactNameXrefs={len(exact_xrefs)} containingNameXrefs={len(containing)} ancestorScriptRows={len(ancestor_script_rows)} resolvedAncestorScripts={len(resolved_ancestor)} ancestorWriteEvidence={len(ancestor_write_evidence)}',f'nextStrategy={strategy}','','RAW EXACT NAME BYTE COUNTS']
for w,c in sorted(raw_counts.items()):lines.append(f'  {w} ascii={c["ascii"]} utf16le={c["utf16le"]}')
lines+=['','EXACT IL NAME XREFS']
if exact_xrefs:
    for x in exact_xrefs:
        lines.append(f"  M:{x['rid']} {x['symbol']} literal={x['literal']}")
        for q in x['lookups']:lines.append(f"    LOOKUP {q['api']} :: {q['target']}")
        for q in x['directWrites']:lines.append(f"    WRITE {q['api']} :: {q['target']}")
        if x['writePathSymbols']:lines.append('    WRITE_PATH '+' -> '.join(x['writePathSymbols']))
else:lines.append('  NONE')
lines+=['','EXACT ANCESTOR CHAINS + SCRIPTS']
for an,chain in ancestor_chains.items():
    lines.append('  '+an)
    for r in chain:
        ss3=','.join(sorted({s['scriptName'] for s in r['scripts'] if s.get('scriptName')})) or '-'
        lines.append(f"    L{r['level']} GO={r['gameObjectName'] or '-'} pathID={r['gameObjectPathID']} scripts={ss3}")
lines+=['','ANCESTOR SCRIPT CLR WRITE / LOOKUP EVIDENCE']
if ancestor_write_evidence:
    for e in ancestor_write_evidence[:120]:
        lines.append(f"  {e['scriptName']} M:{e['rid']} {e['symbol']}")
        for q in e.get('lookups',[]):lines.append(f"    LOOKUP {q['api']} :: {q['target']}")
        for q in e.get('writes',[]):lines.append(f"    WRITE {q['api']} :: {q['target']}")
        if e.get('writePathSymbols'):lines.append('    WRITE_PATH '+' -> '.join(e['writePathSymbols']))
else:lines.append('  NONE')
lines+=['','NEXT '+strategy,'RULE: exact IL string equality or exact V4 ancestor/script identity only.','RULE: no APK read, no bundle scan/extraction, no candidate promotion, main/preview untouched.']
reportp.write_text('\n'.join(lines)+'\n','utf-8')
print('FORMATION_RUNTIME_PRODUCER_OK',f'exactNameXrefs={len(exact_xrefs)}',f'ancestorScripts={len(resolved_ancestor)}',f'ancestorWriteEvidence={len(ancestor_write_evidence)}')
for x in exact_xrefs[:20]:print('FORMATION_RUNTIME_NAME_XREF',x['literal'],f"M:{x['rid']}",x['symbol'])
for e in ancestor_write_evidence[:20]:print('FORMATION_RUNTIME_ANCESTOR_WRITE',e['scriptName'],f"M:{e['rid']}",e['symbol'])
print('FORMATION_RUNTIME_PRODUCER_NEXT',strategy)
print('FORMATION_RUNTIME_PRODUCER_JSON',outp)
print('FORMATION_RUNTIME_PRODUCER_REPORT',reportp)
PY

git add "$OUT"
if ! git diff --cached --quiet; then
  git commit -m "lab: trace Formation runtime producer from exact names and ancestors"
  git push origin "$BRANCH"
fi

echo "FORMATION_RUNTIME_PRODUCER_DONE"
