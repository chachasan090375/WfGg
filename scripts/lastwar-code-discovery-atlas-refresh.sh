#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — CODE DISCOVERY ATLAS
# Builds a reusable map of what is known AND what is still unknown in Assembly-CSharp.
# Fast: CLR metadata/IL only. No AssetBundle iteration, no UnityPy global scan, game read-only.

PKG="com.fun.lastwar.gp"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
DLL="$HOME/storage/downloads/WFGG_LASTWAR_Assembly-CSharp_recovered.dll"
KNOWN="$ROOT/frontend/lab/master-assets-v2/index/lastwar-code-known-anchors-v1.json"
OUT="$ROOT/frontend/lab/master-assets-v2/index/lastwar-code-discovery-atlas-v1.json"
TSV="$ROOT/frontend/lab/master-assets-v2/index/lastwar-code-discovery-frontier-v1.tsv"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_CODE_DISCOVERY_ATLAS.txt"
PY="${TMPDIR:-$HOME/.cache}/wfgg-lastwar-code-discovery-atlas.py"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
command -v python >/dev/null 2>&1 || fail "python absent"
[[ -s "$KNOWN" ]] || fail "registre known anchors absent"
mkdir -p "$(dirname "$OUT")" "$(dirname "$REPORT")" "$(dirname "$PY")"

if [[ ! -s "$DLL" ]]; then
  mapfile -t APKS < <(cmd package path "$PKG" 2>/dev/null | sed -n 's/^package://p')
  [[ ${#APKS[@]} -gt 0 ]] || fail "APK Last War introuvable"
  python - "$DLL" "${APKS[@]}" <<'PYREC'
from pathlib import Path
import sys,zipfile
out=Path(sys.argv[1]); data=None
for x in sys.argv[2:]:
    try:
        with zipfile.ZipFile(x) as z:
            n='assets/Assemblies/Assembly-CSharp.mdl'
            if n in z.namelist(): data=bytearray(z.read(n)); break
    except Exception: pass
if data is None: raise SystemExit('Assembly-CSharp.mdl introuvable')
canonical=bytes.fromhex('4d5a90000300000004000000ffff0000b80000')
for i,b in enumerate(canonical):
    if i<len(data) and data[i] == (b ^ 0x13): data[i]=b
data[0:2]=b'MZ'; out.write_bytes(data)
PYREC
fi

python - "$DLL" "$KNOWN" "$OUT" "$TSV" "$REPORT" <<'PYEOF'
from pathlib import Path
from collections import defaultdict,deque,Counter
import csv,hashlib,json,re,struct,sys,time

dll=Path(sys.argv[1]); known_path=Path(sys.argv[2]); out=Path(sys.argv[3]); tsv=Path(sys.argv[4]); report=Path(sys.argv[5])
t0=time.time(); data=dll.read_bytes(); known=json.loads(known_path.read_text('utf-8'))
u16=lambda o:struct.unpack_from('<H',data,o)[0]
u32=lambda o:struct.unpack_from('<I',data,o)[0]
u64=lambda o:struct.unpack_from('<Q',data,o)[0]
if data[:2]!=b'MZ':raise SystemExit('DLL restauree invalide')
e_lfanew=u32(0x3c)
if data[e_lfanew:e_lfanew+4]!=b'PE\0\0':raise SystemExit('PE absent')
coff=e_lfanew+4; nsec=u16(coff+2); opt_size=u16(coff+16); opt=coff+20; magic=u16(opt); dd=opt+(96 if magic==0x10b else 112)
secs=[]; sec_off=opt+opt_size
for i in range(nsec):
    o=sec_off+i*40;secs.append((u32(o+12),u32(o+8),u32(o+16),u32(o+20)))
def rvaoff(rva):
    for va,vs,rs,ro in secs:
        if va<=rva<va+max(vs,rs):return ro+(rva-va)
    if rva<len(data):return rva
    raise ValueError(rva)
clr=rvaoff(u32(dd+14*8)); meta=rvaoff(u32(clr+8))
if data[meta:meta+4]!=b'BSJB':raise SystemExit('BSJB absent')
ver=u32(meta+12); q=(meta+16+ver+3)&~3; nstreams=u16(q+2);q+=4
sm={}
for _ in range(nstreams):
    off=u32(q);size=u32(q+4);q+=8;e=data.find(b'\0',q,q+64);name=data[q:e].decode('ascii','replace');q=(e+4)&~3;sm[name]=(meta+off,size)
so,ss=sm['#Strings']; uso,uss=sm.get('#US',(0,0)); to,ts=sm.get('#~',sm.get('#-'))
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
row0=q; strsz=4 if heap&1 else 2; guidsz=4 if heap&2 else 2; blobsz=4 if heap&4 else 2
def ix(t):return 4 if rows.get(t,0)>=65536 else 2
def cx(bits,*tids):return 4 if max([rows.get(x,0) for x in tids] or [0])>=(1<<(16-bits)) else 2
rs={0:2+strsz+guidsz*3,1:cx(2,0,26,35,1)+2*strsz,2:4+2*strsz+cx(2,1,2,27)+ix(4)+ix(6),3:ix(4),4:2+strsz+blobsz,5:ix(6),6:4+2+2+strsz+blobsz+ix(8),7:ix(8),8:2+2+strsz,9:ix(2)+cx(2,1,2,27),10:cx(3,2,1,26,6,27)+strsz+blobsz}
offs={};cur=row0
for tid in range(11):
    if (valid>>tid)&1:
        if tid not in rs:raise SystemExit(f'row size table {tid} absent')
        offs[tid]=cur;cur+=rs[tid]*rows.get(tid,0)
def ri(o,z):return u16(o) if z==2 else u32(o)

# TypeRef / MethodDef / TypeDef / MemberRef
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
for i,t in enumerate(raw):
    mend=(raw[i+1]['methodStart']-1 if i+1<len(raw) else rows.get(6,0));t['methodEnd']=mend;types.append(t)
    if t['methodStart']:
        for r in range(max(1,t['methodStart']),min(mend,len(methods)-1)+1):owner[r]=t
by_type_rid={x['rid']:x for x in types}
def fullname(t):return ((t.get('namespace')+'.') if t.get('namespace') else '')+t.get('name','')
mr=[None];mps=cx(3,2,1,26,6,27)
for rid in range(1,rows.get(10,0)+1):
    o=offs[10]+(rid-1)*rs[10];par=ri(o,mps);ni=ri(o+mps,strsz);mr.append((par,s_at(ni)))
def parent_name(c):
    tag=c&7;rid=c>>3
    if tag==0 and rid in by_type_rid:return fullname(by_type_rid[rid])
    if tag==1 and rid<len(tr):ns,n=tr[rid];return (ns+'.' if ns else '')+n
    if tag==3 and rid in owner:return fullname(owner[rid])
    return f'tag{tag}:rid{rid}'
def tok(tok):
    tab=(tok>>24)&255;rid=tok&0xffffff
    if tab==6 and rid<len(methods):return ('internal',rid,fullname(owner.get(rid,{}))+'.'+methods[rid]['name'])
    if tab==10 and rid<len(mr):return ('external',rid,parent_name(mr[rid][0])+'.'+mr[rid][1])
    return ('other',rid,f'0x{tok:08x}')

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
# Other token-bearing opcodes are skipped correctly so parsing remains aligned.
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
                    k,r,n=tok(v);(internal if k=='internal' else external if k=='external' else []).append((r,n))
            elif o2 in fe_u16:i+=2
            elif o2 in fe_u8:i+=1
            continue
        if op in token_ops or op in other_token:
            if i+4>len(il):break
            v=struct.unpack_from('<I',il,i)[0];i+=4
            if op==0x72:
                s=us_at(v&0xffffff)
                if s:strings.append(s)
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

known_types=set(known.get('knownTypes',[])); known_methods=set(known.get('knownMethods',[])); known_strings=[x.lower() for x in known.get('knownRuntimeStrings',[])]
framework_prefix=('System.','UnityEngine.','Microsoft.','Google.','TMPro.','Newtonsoft.','DG.Tweening.','Cysharp.','BestHTTP.','Firebase.')
re_scene=re.compile(r'(LoadScene|SceneManager|LoadLevel|SceneLoader)',re.I)
re_asset=re.compile(r'(Resources\.Load|LoadAsset|Addressables|AssetBundle)',re.I)
re_inst=re.compile(r'(Instantiate|Object\.Instantiate)',re.I)
re_render=re.compile(r'(Camera|RenderTexture|RenderPipeline|Shader|Material|Texture|Mesh|Graphics|Blit|Culling|PostProcess|Blur)',re.I)
re_anim=re.compile(r'(Animator|Animation|Playable|Timeline)',re.I)
re_ui=re.compile(r'(^UI|Panel|Window|View|Widget|Dialog|Popup|Screen)',re.I)
re_path=re.compile(r'(Assets/|\.unity$|\.prefab$|\.mat$|\.controller$|\.anim$|\.png$|\.jpg$|\.bundle$)',re.I)

edges=[]; reverse=defaultdict(set); outgoing=defaultdict(set); ext_by_method=defaultdict(list); str_by_method=defaultdict(list); method_tags=defaultdict(set); external_catalog=defaultdict(set)
for m in methods[1:]:
    ins,exts,strings=scan_il(m);rid=m['rid'];ot=fullname(owner.get(rid,{}));mn=m['name']
    for callee,n in ins:
        if callee!=rid:
            outgoing[rid].add(callee);reverse[callee].add(rid);edges.append([rid,callee])
    for _,n in exts:
        ext_by_method[rid].append(n);external_catalog[n].add(rid)
        if re_scene.search(n):method_tags[rid].add('scene-loader')
        if re_asset.search(n):method_tags[rid].add('asset-loader')
        if re_inst.search(n):method_tags[rid].add('instantiate')
        if re_render.search(n):method_tags[rid].add('render-camera')
        if re_anim.search(n):method_tags[rid].add('animation')
    if re_ui.search(ot) or re_ui.search(mn):method_tags[rid].add('ui')
    good=[]
    for s in strings:
        sl=s.lower()
        if re_path.search(s) or any(k in sl for k in known_strings) or ('/' in s and len(s)<300) or (len(s)<120 and re.search(r'[A-Za-z_]{5,}',s)):
            good.append(s)
    if good:
        str_by_method[rid]=good[:12];method_tags[rid].add('string-evidence')
        if any(re_path.search(s) for s in good):method_tags[rid].add('resource-path-string')

# Resolve seed methods and distance in undirected internal call graph.
seed=set()
for m in methods[1:]:
    rid=m['rid'];ft=fullname(owner.get(rid,{}));fm=ft+'.'+m['name']
    if ft in known_types or fm in known_methods:seed.add(rid)
dist={r:0 for r in seed};dq=deque(seed)
while dq:
    x=dq.popleft();d=dist[x]
    if d>=3:continue
    for y in outgoing.get(x,set())|reverse.get(x,set()):
        if y not in dist:dist[y]=d+1;dq.append(y)

def score_method(rid):
    s=0;tags=method_tags.get(rid,set());d=dist.get(rid)
    if d is not None:s += {0:1000,1:350,2:180,3:80}.get(d,0)
    for tag,w in [('scene-loader',300),('asset-loader',260),('instantiate',180),('render-camera',160),('animation',80),('resource-path-string',150),('string-evidence',30),('ui',30)]:
        if tag in tags:s+=w
    s+=min(len(reverse.get(rid,set())),20)*3+min(len(outgoing.get(rid,set())),20)*2
    return s

compact_methods=[];frontier=[];status_counts=Counter();tag_counts=Counter()
for m in methods[1:]:
    rid=m['rid'];t=owner.get(rid,{});ft=fullname(t);fm=ft+'.'+m['name'];d=dist.get(rid);status='known' if rid in seed else 'unknown'
    tags=sorted(method_tags.get(rid,set()));sc=score_method(rid);status_counts[status]+=1;tag_counts.update(tags)
    rec={'rid':rid,'typeRid':t.get('rid'),'name':m['name'],'status':status,'d':d,'in':len(reverse.get(rid,set())),'out':len(outgoing.get(rid,set())),'tags':tags,'score':sc}
    compact_methods.append(rec)
    if status=='unknown' and (sc>0 or tags):
        fr={**rec,'owner':ft,'symbol':fm,'strings':str_by_method.get(rid,[]),'externalCalls':sorted(set(ext_by_method.get(rid,[])))[:30],'callers':sorted(reverse.get(rid,set()))[:50],'callees':sorted(outgoing.get(rid,set()))[:50]}
        frontier.append(fr)
frontier.sort(key=lambda x:(-x['score'],x['symbol']))

compact_types=[]
for t in types:
    ft=fullname(t);mr=list(range(max(1,t['methodStart']),min(t['methodEnd'],len(methods)-1)+1)) if t['methodStart'] else []
    ks=sum(1 for r in mr if r in seed);interest=max([score_method(r) for r in mr] or [0]);compact_types.append({'rid':t['rid'],'namespace':t['namespace'],'name':t['name'],'status':'known' if ft in known_types else 'unknown','methodStart':t['methodStart'],'methodEnd':t['methodEnd'],'knownMethods':ks,'interest':interest})

# Unknown external calls are not necessarily game code; preserve them with caller locations and classify framework/vendor.
ext=[]
for target,callers in external_catalog.items():
    owner_name=target.rsplit('.',1)[0] if '.' in target else target
    cls='framework' if owner_name.startswith(framework_prefix) else 'unclassified-external'
    tags=[]
    for rg,tag in [(re_scene,'scene-loader'),(re_asset,'asset-loader'),(re_inst,'instantiate'),(re_render,'render-camera'),(re_anim,'animation')]:
        if rg.search(target):tags.append(tag)
    ext.append({'target':target,'classification':cls,'tags':tags,'callerRids':sorted(callers),'callerCount':len(callers)})
ext.sort(key=lambda x:(0 if x['classification']=='unclassified-external' else 1,-x['callerCount'],x['target']))

atlas={
 'format':'WFGG_LASTWAR_CODE_DISCOVERY_ATLAS_V1',
 'purpose':'Persistent known/unknown CLR map. Query before new reverse-engineering scans.',
 'source':{'dll':str(dll),'sha256':hashlib.sha256(data).hexdigest(),'knownAnchors':str(known_path)},
 'counts':{'types':len(types),'methods':len(methods)-1,'internalEdges':len(edges),'frontier':len(frontier),'externalTargets':len(ext),'knownMethods':len(seed),'unknownMethods':(len(methods)-1-len(seed))},
 'statusCounts':dict(status_counts),'tagCounts':dict(tag_counts),
 'stableIds':{'type':'T:<TypeDef RID>','method':'M:<MethodDef RID>','rule':'CLR RID is stable for this exact Assembly-CSharp SHA256; on game update re-resolve by full symbol and preserve previous SHA lineage.'},
 'types':compact_types,'methods':compact_methods,'internalEdges':edges,'frontier':frontier,'externalCalls':ext,
 'knownAnchors':known,
 'workflow':[
   'Query atlas by symbol/RID/tag/near-known before any new scan.',
   'Unknown entries are preserved, not discarded.',
   'When understood, add symbol/fact to lastwar-code-known-anchors-v1.json and refresh atlas.',
   'When disproved, add to negativeKnowledge so the same expensive hypothesis is not repeated.'
 ],
 'guardrails':{'bundleScan':False,'UnityPyScan':False,'gameReadOnly':True}
}
out.write_text(json.dumps(atlas,ensure_ascii=False,separators=(',',':'))+'\n','utf-8')
with tsv.open('w',encoding='utf-8',newline='') as f:
    w=csv.writer(f,delimiter='\t',lineterminator='\n');w.writerow(['score','distance','methodRid','typeRid','symbol','tags','strings','externalCalls','callers','callees'])
    for r in frontier:
        w.writerow([r['score'],'' if r['d'] is None else r['d'],r['rid'],r['typeRid'],r['symbol'],'|'.join(r['tags']),' || '.join(r['strings']),' || '.join(r['externalCalls']),'|'.join(map(str,r['callers'])),'|'.join(map(str,r['callees']))])
lines=['WfGg Last War — CODE DISCOVERY ATLAS','',f'dllSha256={atlas["source"]["sha256"]}',json.dumps(atlas['counts'],ensure_ascii=False),f'tags={json.dumps(atlas["tagCounts"],ensure_ascii=False)}','',f'json={out}',f'tsv={tsv}','', 'TOP UNKNOWN FRONTIER:']
for r in frontier[:40]:lines.append(f"UNKNOWN score={r['score']} d={r['d']} rid={r['rid']} tags={','.join(r['tags']) or '-'} {r['symbol']}")
report.write_text('\n'.join(lines)+'\n','utf-8')
print('LASTWAR_CODE_DISCOVERY_ATLAS_OK',f"types={len(types)}",f"methods={len(methods)-1}",f"known={len(seed)}",f"unknown={len(methods)-1-len(seed)}",f"frontier={len(frontier)}",f"edges={len(edges)}")
for r in frontier[:20]:print('UNKNOWN_FRONTIER',f"score={r['score']}",f"d={r['d']}",f"rid={r['rid']}",','.join(r['tags']) or '-',r['symbol'])
print('CODE_ATLAS_JSON',out);print('CODE_FRONTIER_TSV',tsv);print('CODE_ATLAS_REPORT',report)
PYEOF

git add "$OUT" "$TSV"
if ! git diff --cached --quiet; then
  git commit -m "lab: refresh Last War known unknown code atlas"
fi
git push origin "$BRANCH"
printf '%s\n' '=== CODE DISCOVERY ATLAS TERMINE ===' "JSON: $OUT" "Frontier: $TSV" "Rapport: $REPORT"
