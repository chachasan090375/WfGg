#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — HeroShow / Camp scene-loader audit.
# FAST: scans only recovered Assembly-CSharp CLR metadata/IL + gameres catalog.
# It DOES NOT iterate/decompress AssetBundles and does not touch the game.

PKG="com.fun.lastwar.gp"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
DLL="$HOME/storage/downloads/WFGG_LASTWAR_Assembly-CSharp_recovered.dll"
GAMERES="$ROOT/frontend/lab/local_assets/lastwar-formation-native-recipe-v1/gameres"
OUT="$ROOT/frontend/lab/master-assets-v2/meta/heroshow-scene-loader-audit-v1.json"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_HEROSHOW_SCENE_LOADER_AUDIT.txt"
PY="${TMPDIR:-$HOME/.cache}/wfgg-heroshow-scene-loader-audit.py"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
command -v python >/dev/null 2>&1 || fail "python absent"
[[ -s "$GAMERES" ]] || fail "gameres local absent"
mkdir -p "$(dirname "$OUT")" "$(dirname "$REPORT")" "$(dirname "$PY")"

# Recreate recovered DLL only if absent. Same minimal local repair as previous CLR audits.
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

cat > "$PY" <<'PYEOF'
from pathlib import Path
from collections import defaultdict,Counter
import sys,struct,json,re,time,hashlib

dll=Path(sys.argv[1]); gameres=Path(sys.argv[2]); out=Path(sys.argv[3]); report=Path(sys.argv[4])
t0=time.time(); data=dll.read_bytes(); text=gameres.read_text('utf-8',errors='replace')
u16=lambda o: struct.unpack_from('<H',data,o)[0]
u32=lambda o: struct.unpack_from('<I',data,o)[0]
u64=lambda o: struct.unpack_from('<Q',data,o)[0]
if data[:2]!=b'MZ': raise SystemExit('DLL restauree invalide: MZ absent')
e_lfanew=u32(0x3c)
if data[e_lfanew:e_lfanew+4]!=b'PE\0\0': raise SystemExit('DLL restauree invalide: PE absent')
coff=e_lfanew+4; sections=u16(coff+2); opt_size=u16(coff+16); opt=coff+20; magic=u16(opt); dd=opt+(96 if magic==0x10b else 112)
sec_off=opt+opt_size; secs=[]
for i in range(sections):
    o=sec_off+i*40; secs.append({'va':u32(o+12),'vsize':u32(o+8),'rawsize':u32(o+16),'raw':u32(o+20)})
def rva_to_off(rva):
    for s in secs:
        if s['va']<=rva<s['va']+max(s['vsize'],s['rawsize']): return s['raw']+(rva-s['va'])
    if rva<len(data): return rva
    raise ValueError
clr_rva=u32(dd+14*8); clr=rva_to_off(clr_rva); meta=rva_to_off(u32(clr+8))
if data[meta:meta+4]!=b'BSJB': raise SystemExit('BSJB absent')
ver_len=u32(meta+12); q=(meta+16+ver_len+3)&~3; streams=u16(q+2); q+=4
sm={}
for _ in range(streams):
    off=u32(q); size=u32(q+4); q+=8; e=data.find(b'\0',q,q+64); name=data[q:e].decode('ascii','replace'); q=(e+4)&~3; sm[name]={'offset':meta+off,'size':size}
strings=sm['#Strings']; us=sm.get('#US'); tables=sm.get('#~',sm.get('#-'))
def str_at(i):
    if not i:return ''
    o=strings['offset']+i; e=data.find(b'\0',o,strings['offset']+strings['size']); return data[o:(e if e>=0 else o+512)].decode('utf-8','replace')
def compint(o):
    b=data[o]
    if b<0x80:return b,1
    if b<0xC0:return ((b&0x3f)<<8)|data[o+1],2
    return ((b&0x1f)<<24)|(data[o+1]<<16)|(data[o+2]<<8)|data[o+3],4
def userstr(idx):
    if not us or idx<=0 or idx>=us['size']:return ''
    o=us['offset']+idx
    try:n,k=compint(o)
    except:return ''
    raw=data[o+k:o+k+n]
    if raw:raw=raw[:-1]
    try:return raw.decode('utf-16le','replace')
    except:return ''

t=tables['offset']; heap=data[t+6]; valid=u64(t+8); q=t+24; rows={}
for tid in range(64):
    if (valid>>tid)&1: rows[tid]=u32(q); q+=4
rowdata=q; strsz=4 if heap&1 else 2; guidsz=4 if heap&2 else 2; blobsz=4 if heap&4 else 2
def idxsz(tid):return 4 if rows.get(tid,0)>=65536 else 2
def cidx(bits,*tids):return 4 if max((rows.get(x,0) for x in tids),default=0)>=(1<<(16-bits)) else 2
rs={0:2+strsz+guidsz*3,1:cidx(2,0,26,35,1)+strsz*2,2:4+strsz*2+cidx(2,1,2,27)+idxsz(4)+idxsz(6),3:idxsz(4),4:2+strsz+blobsz,5:idxsz(6),6:4+2+2+strsz+blobsz+idxsz(8),7:idxsz(8),8:2+2+strsz,9:idxsz(2)+cidx(2,1,2,27),10:cidx(3,2,1,26,6,27)+strsz+blobsz}
offs={};cur=rowdata
for tid in range(11):
    if (valid>>tid)&1:
        if tid not in rs: raise SystemExit(f'row size table {tid} manquante')
        offs[tid]=cur;cur+=rs[tid]*rows.get(tid,0)
def ri(o,s):return u16(o) if s==2 else u32(o)

tr=[None]
for rid in range(1,rows.get(1,0)+1):
    o=offs[1]+(rid-1)*rs[1];pos=o+cidx(2,0,26,35,1);ni=ri(pos,strsz);pos+=strsz;nsi=ri(pos,strsz)
    tr.append({'rid':rid,'name':str_at(ni),'namespace':str_at(nsi)})
methods=[None]
for rid in range(1,rows.get(6,0)+1):
    o=offs[6]+(rid-1)*rs[6]; methods.append({'rid':rid,'rva':u32(o),'name':str_at(ri(o+8,strsz))})
raw=[]
for rid in range(1,rows.get(2,0)+1):
    o=offs[2]+(rid-1)*rs[2];pos=o+4;ni=ri(pos,strsz);pos+=strsz;nsi=ri(pos,strsz);pos+=strsz;pos+=cidx(2,1,2,27);pos+=idxsz(4);ms=ri(pos,idxsz(6))
    raw.append({'rid':rid,'name':str_at(ni),'namespace':str_at(nsi),'methodStart':ms})
types=[];method_owner={}
for i,ty in enumerate(raw):
    me=(raw[i+1]['methodStart']-1 if i+1<len(raw) else rows.get(6,0))
    ty['methods']=[methods[r] for r in range(max(1,ty['methodStart']),min(me,len(methods)-1)+1)] if ty['methodStart'] else []
    for m in ty['methods']:method_owner[m['rid']]=ty
    types.append(ty)
type_by_rid={x['rid']:x for x in types}
def fulltype(ty):return ((ty.get('namespace')+'.') if ty.get('namespace') else '')+ty.get('name','')

mrs=[None]; mrps=cidx(3,2,1,26,6,27)
for rid in range(1,rows.get(10,0)+1):
    o=offs[10]+(rid-1)*rs[10];parent=ri(o,mrps);ni=ri(o+mrps,strsz);mrs.append({'rid':rid,'name':str_at(ni),'parent':parent})
def member_parent_name(c):
    tag=c&7;rid=c>>3
    if tag==0 and rid in type_by_rid:return fulltype(type_by_rid[rid])
    if tag==1 and rid<len(tr):return ((tr[rid]['namespace']+'.') if tr[rid]['namespace'] else '')+tr[rid]['name']
    if tag==3 and rid in method_owner:return fulltype(method_owner[rid])
    return f'tag{tag}:rid{rid}'
def tokname(tok):
    tid=(tok>>24)&0xff;rid=tok&0xffffff
    if tid==0x06 and rid<len(methods):return 'Method '+fulltype(method_owner.get(rid,{}))+'.'+methods[rid]['name']
    if tid==0x0a and rid<len(mrs):return 'MemberRef '+member_parent_name(mrs[rid]['parent'])+'.'+mrs[rid]['name']
    if tid==0x02 and rid in type_by_rid:return 'TypeDef '+fulltype(type_by_rid[rid])
    if tid==0x01 and rid<len(tr):return 'TypeRef '+(((tr[rid]['namespace']+'.') if tr[rid]['namespace'] else '')+tr[rid]['name'])
    return f'token 0x{tok:08x}'

def body(m):
    if not m['rva']:return None
    try:o=rva_to_off(m['rva'])
    except:return None
    b=data[o]
    if b&3==2:cs=b>>2;s=o+1
    elif b&3==3:
        h=u16(o);hs=((h>>12)&15)*4;cs=u32(o+4);s=o+hs
    else:return None
    if s+cs>len(data):return None
    return data[s:s+cs]

# Robust-enough IL walk for strings/calls/types; no decompilation required.
token_ops={0x27:'jmp',0x28:'call',0x29:'calli',0x6f:'callvirt',0x70:'cpobj',0x71:'ldobj',0x72:'ldstr',0x73:'newobj',0x74:'castclass',0x75:'isinst',0x79:'unbox',0x7b:'ldfld',0x7c:'ldflda',0x7d:'stfld',0x7e:'ldsfld',0x7f:'ldsflda',0x80:'stsfld',0x81:'stobj',0x8c:'box',0x8d:'newarr',0x8f:'ldelema',0xa3:'ldelem',0xa4:'stelem',0xa5:'unbox.any',0xc2:'refanyval',0xc6:'mkrefany',0xd0:'ldtoken'}
short1=set(range(0x2b,0x38))|{0x0e,0x0f,0x10,0x11,0x12,0x13,0x1f,0xde}
long4=set(range(0x38,0x45))|{0x20,0xdd}; long8={0x21,0x23}; float4={0x22}
fe_token={0x06:'ldftn',0x07:'ldvirtftn',0x15:'initobj',0x16:'constrained',0x1c:'sizeof'};fe_u16={0x09,0x0a,0x0b,0x0c,0x0d,0x0e};fe_u8={0x12,0x19}
def events(m):
    il=body(m)
    if il is None:return []
    ev=[];i=0
    while i<len(il):
        pc=i;op=il[i];i+=1
        if op==0xfe:
            if i>=len(il):break
            o2=il[i];i+=1
            if o2 in fe_token:
                if i+4>len(il):break
                tok=struct.unpack_from('<I',il,i)[0];i+=4;ev.append({'pc':pc,'op':'fe.'+fe_token[o2],'token':tok,'target':tokname(tok)})
            elif o2 in fe_u16:i+=2
            elif o2 in fe_u8:i+=1
            continue
        if op in token_ops:
            if i+4>len(il):break
            tok=struct.unpack_from('<I',il,i)[0];i+=4
            if op==0x72:ev.append({'pc':pc,'op':'ldstr','token':tok,'string':userstr(tok&0xffffff)})
            else:ev.append({'pc':pc,'op':token_ops[op],'token':tok,'target':tokname(tok)})
        elif op==0x45:
            if i+4>len(il):break
            n=struct.unpack_from('<I',il,i)[0];i+=4+4*n
        elif op in short1:i+=1
        elif op in long4 or op in float4:i+=4
        elif op in long8:i+=8
    return ev

re_symbol=re.compile(r'(hero.?show|formation|camp|pvpformation)',re.I)
re_string=re.compile(r'(Camp_|HeroShow|Hero Show|Formation|PVPFormation|UIHeroPVP|hero_show)',re.I)
re_scene_call=re.compile(r'(SceneManager\..*LoadScene|LoadSceneAsync|LoadScene\b|Addressables\..*LoadScene|SceneLoader|LoadLevel)',re.I)
re_resource_call=re.compile(r'(Resources\.Load|AssetBundle\..*LoadAsset|Addressables\..*LoadAsset|Instantiate\b)',re.I)

symbol_methods=[]; string_methods=[]; scene_load_methods=[]; contextual_resource_loads=[]; all_string_hits=[]
method_events={}; target_callers=defaultdict(list)
for m in methods[1:]:
    ty=method_owner.get(m['rid'],{}); owner=fulltype(ty); name=m['name']; ev=events(m); method_events[m['rid']]=ev
    strings_here=[e['string'] for e in ev if e.get('op')=='ldstr' and e.get('string')]
    calls=[e['target'] for e in ev if e.get('target') and e.get('op') in ('call','callvirt','newobj','jmp','fe.ldftn','fe.ldvirtftn')]
    for e in ev:
        if e.get('op') in ('call','callvirt','newobj','jmp') and ((e.get('token',0)>>24)&0xff)==0x06:
            target_callers[e['token']&0xffffff].append({'owner':owner,'method':name,'rid':m['rid'],'pc':e['pc']})
    rec={'owner':owner,'method':name,'rid':m['rid'],'rva':m['rva'],'strings':strings_here,'calls':calls}
    if re_symbol.search(owner+' '+name):symbol_methods.append(rec)
    matched=[s for s in strings_here if re_string.search(s)]
    if matched:
        rr=dict(rec);rr['matchedStrings']=matched;string_methods.append(rr)
        for s in matched:all_string_hits.append({'owner':owner,'method':name,'rid':m['rid'],'string':s})
    sc=[c for c in calls if re_scene_call.search(c)]
    if sc:
        rr=dict(rec);rr['sceneCalls']=sc;scene_load_methods.append(rr)
    rc=[c for c in calls if re_resource_call.search(c)]
    if rc and (matched or re_symbol.search(owner+' '+name)):
        rr=dict(rec);rr['resourceCalls']=rc;contextual_resource_loads.append(rr)

# Reverse callers for the most useful symbol methods (depth 1); this finds controllers calling named HeroShow/Formation methods.
interesting_rids={r['rid'] for r in symbol_methods if re_symbol.search(r['owner'])}
reverse=[]
for rid in sorted(interesting_rids):
    m=methods[rid];owner=fulltype(method_owner.get(rid,{}));callers=target_callers.get(rid,[])
    if callers:reverse.append({'targetOwner':owner,'targetMethod':m['name'],'targetRid':rid,'callers':callers})

# Parse canonical gameres scene/resource catalog and resolve bundle IDs.
def section(name):
    mm=re.search(rf'^\[{re.escape(name)}\]\s*$',text,re.M)
    if not mm:return []
    s=mm.end();nn=re.search(r'^\[[^\]]+\]\s*$',text[s:],re.M);e=s+nn.start() if nn else len(text)
    return [x for x in text[s:e].splitlines() if x.strip()]
dirs={}
for ln in section('Directories'):
    try:i,p=ln.split(',',1);dirs[int(i)]=p
    except:pass
paths={}
for ln in section('Paths'):
    try:pid,did,n=ln.split(',',2);paths[int(pid)]=dirs[int(did)].rstrip('/')+'/'+n
    except:pass
path_to_bundle={};bundle_meta={}
for ln in section('Bundles'):
    p=ln.split(',')
    if len(p)<8:continue
    try:
        bid=int(p[0]);ids=[int(x) for x in p[4].split('|') if x];asset=[paths[x] for x in ids if x in paths]
        bundle_meta[bid]={'bundleId':bid,'logicalName':p[1],'aliasName':p[7],'assetPaths':asset,'dependencyBundleIds':[int(x) for x in p[5].split('|') if x]}
        for ap in asset:path_to_bundle[ap]=bid
    except:pass

def score_path(p):
    l=p.lower();s=0
    if p.endswith('.unity'):s+=100
    for k,w in [('heroshow',120),('hero_show',120),('formation',120),('pvp',70),('/camp',90),('camp_',100),('/scene',25),('hero',20),('world',10)]:
        if k in l:s+=w
    return s
catalog=[]
for ap,bid in path_to_bundle.items():
    s=score_path(ap)
    if ap.endswith('.unity') or s>=90:
        b=bundle_meta[bid];catalog.append({'score':s,'assetPath':ap,'bundleId':bid,'logicalName':b['logicalName'],'aliasName':b['aliasName'],'dependencyBundleIds':b['dependencyBundleIds']})
catalog.sort(key=lambda x:(-x['score'],x['assetPath']))

# Cross-score scene loaders with their literal strings and catalog basenames.
loader_strings=[]
for r in scene_load_methods:
    for s in r['strings']:
        if s and len(s)<300:loader_strings.append({'owner':r['owner'],'method':r['method'],'rid':r['rid'],'literal':s})

res={
 'format':'WFGG_LASTWAR_HEROSHOW_SCENE_LOADER_AUDIT_V1',
 'source':{'dll':str(dll),'dllSha256':hashlib.sha256(data).hexdigest(),'gameres':str(gameres)},
 'elapsedSeconds':round(time.time()-t0,3),
 'counts':{'types':len(types),'methods':len(methods)-1,'symbolMethods':len(symbol_methods),'relevantStringMethods':len(string_methods),'sceneLoadMethods':len(scene_load_methods),'contextualResourceLoads':len(contextual_resource_loads),'reverseGroups':len(reverse),'catalogCandidates':len(catalog)},
 'conclusionGuardrail':'This audit maps code/catalog only; it does not assert a scene is Formation until a loader/string/call-chain link supports it.',
 'symbolMethods':symbol_methods,
 'relevantStringMethods':string_methods,
 'sceneLoadMethods':scene_load_methods,
 'sceneLoaderLiterals':loader_strings,
 'contextualResourceLoads':contextual_resource_loads,
 'reverseCallers':reverse,
 'catalogCandidates':catalog,
 'heroShowKnownRuntime':{'HeroShowSettingUpdate':'GameObject.Find("Camp_" + level), then find/create GrabCamera','CampSerializedBundleScan':'8012 bundles scanned previously; no strong serialized fingerprint'},
 'guardrails':{'bundleScan':False,'UnityPyScan':False,'apkReadOnly':True,'previewUntouched':True,'mainUntouched':True}
}
out.write_text(json.dumps(res,ensure_ascii=False,indent=2)+'\n','utf-8')
lines=['WfGg Last War — HEROSHOW SCENE LOADER AUDIT','',f'elapsedSeconds={res["elapsedSeconds"]}',json.dumps(res['counts'],ensure_ascii=False),'']
for r in scene_load_methods[:30]:
    lines.append(f"SCENE_LOADER {r['owner']}.{r['method']} rid={r['rid']} strings={r['strings'][:8]} calls={r.get('sceneCalls',[])}")
for r in string_methods[:30]:
    lines.append(f"RELEVANT_STRING {r['owner']}.{r['method']} rid={r['rid']} strings={r.get('matchedStrings',[])}")
for c in catalog[:50]:
    lines.append(f"SCENE_CANDIDATE score={c['score']} bundle={c['bundleId']} {c['assetPath']}")
report.write_text('\n'.join(lines)+'\n','utf-8')
print('HEROSHOW_SCENE_LOADER_AUDIT_OK',f"elapsed={res['elapsedSeconds']}",f"sceneLoaders={len(scene_load_methods)}",f"strings={len(string_methods)}",f"catalog={len(catalog)}")
for r in scene_load_methods[:12]:print('SCENE_LOADER',r['owner']+'.'+r['method'],'rid='+str(r['rid']),'strings='+repr(r['strings'][:5]))
for r in string_methods[:12]:print('RELEVANT_STRING',r['owner']+'.'+r['method'],'rid='+str(r['rid']),'hits='+repr(r.get('matchedStrings',[])))
for c in catalog[:12]:print('SCENE_CANDIDATE',f"score={c['score']}",f"bundle={c['bundleId']}",c['assetPath'])
print('HEROSHOW_SCENE_LOADER_JSON',out)
print('HEROSHOW_SCENE_LOADER_REPORT',report)
PYEOF

python "$PY" "$DLL" "$GAMERES" "$OUT" "$REPORT"

git add "$OUT"
if ! git diff --cached --quiet; then
  git commit -m "lab: trace HeroShow Camp scene loader"
fi
git push origin "$BRANCH"
printf '%s\n' '=== HEROSHOW SCENE LOADER AUDIT TERMINE ===' "JSON: $OUT" "Rapport: $REPORT" 'Indexable via master-assets-v2/meta; aucun scan bundle effectue.'
