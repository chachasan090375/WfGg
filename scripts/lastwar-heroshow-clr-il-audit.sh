#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — targeted CLR field + IL audit.
# Reads recovered Assembly-CSharp locally and maps HeroShowSetting / Formation-camera references.
# No game/network mutation. No preview mutation. main untouched.

PKG="com.fun.lastwar.gp"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
DLL="$HOME/storage/downloads/WFGG_LASTWAR_Assembly-CSharp_recovered.dll"
OUT="$ROOT/frontend/lab/master-assets-v2/meta/heroshow-clr-il-audit-v1.json"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_HEROSHOW_CLR_IL_AUDIT.txt"
PY="${TMPDIR:-$HOME/.cache}/wfgg-heroshow-clr-il-audit.py"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
command -v python >/dev/null 2>&1 || fail "python absent"
mkdir -p "$(dirname "$OUT")" "$(dirname "$REPORT")" "$(dirname "$PY")"

# Recreate the recovered DLL only if the previous local copy is absent.
if [[ ! -s "$DLL" ]]; then
  mapfile -t APKS < <(cmd package path "$PKG" 2>/dev/null | sed -n 's/^package://p')
  [[ ${#APKS[@]} -gt 0 ]] || fail "APK Last War introuvable"
  python - "$DLL" "${APKS[@]}" <<'PYREC'
from pathlib import Path
import sys,zipfile
out=Path(sys.argv[1]); apks=[Path(x) for x in sys.argv[2:]]
data=None
for apk in apks:
    try:
        with zipfile.ZipFile(apk) as z:
            n='assets/Assemblies/Assembly-CSharp.mdl'
            if n in z.namelist(): data=bytearray(z.read(n)); break
    except Exception: pass
if data is None: raise SystemExit('Assembly-CSharp.mdl introuvable')
canonical=bytes.fromhex('4d5a90000300000004000000ffff0000b80000')
for i,b in enumerate(canonical):
    if data[i] == (b ^ 0x13): data[i]=b
data[0:2]=b'MZ'; out.write_bytes(data)
PYREC
fi

cat > "$PY" <<'PYEOF'
from pathlib import Path
import sys,struct,json,re

p=Path(sys.argv[1]); out=Path(sys.argv[2]); report=Path(sys.argv[3]); data=p.read_bytes()
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
    raise ValueError(f'RVA {rva:#x} hors sections')
clr_rva=u32(dd+14*8); clr=rva_to_off(clr_rva); meta=rva_to_off(u32(clr+8))
if data[meta:meta+4]!=b'BSJB': raise SystemExit('BSJB absent')
ver_len=u32(meta+12); q=meta+16+ver_len; q=(q+3)&~3; streams=u16(q+2); q+=4
sm={}
for _ in range(streams):
    off=u32(q); size=u32(q+4); q+=8; e=data.find(b'\0',q,q+64); name=data[q:e].decode('ascii','replace'); q=(e+1+3)&~3; sm[name]={'offset':meta+off,'size':size}
strings=sm['#Strings']; us=sm.get('#US'); tables=sm.get('#~',sm.get('#-'))
def str_at(i):
    if not i:return ''
    o=strings['offset']+i; e=data.find(b'\0',o,strings['offset']+strings['size']); return data[o:(e if e>=0 else o+256)].decode('utf-8','replace')
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
    if raw: raw=raw[:-1]
    try:return raw.decode('utf-16le','replace')
    except:return ''

t=tables['offset']; heap=data[t+6]; valid=u64(t+8); q=t+24; rows={}
for tid in range(64):
    if (valid>>tid)&1: rows[tid]=u32(q); q+=4
rowdata=q; strsz=4 if heap&1 else 2; guidsz=4 if heap&2 else 2; blobsz=4 if heap&4 else 2
def idxsz(tid):return 4 if rows.get(tid,0)>=65536 else 2
def cidx(bits,*tids):return 4 if max((rows.get(x,0) for x in tids),default=0)>=(1<<(16-bits)) else 2
rs={
0:2+strsz+guidsz*3,
1:cidx(2,0,26,35,1)+strsz*2,
2:4+strsz*2+cidx(2,1,2,27)+idxsz(4)+idxsz(6),
3:idxsz(4),
4:2+strsz+blobsz,
5:idxsz(6),
6:4+2+2+strsz+blobsz+idxsz(8),
7:idxsz(8),
8:2+2+strsz,
9:idxsz(2)+cidx(2,1,2,27),
10:cidx(3,2,1,26,6,27)+strsz+blobsz,
}
offs={}; cur=rowdata
for tid in range(11):
    if (valid>>tid)&1:
        if tid not in rs: raise SystemExit(f'row size table {tid} manquante')
        offs[tid]=cur; cur+=rs[tid]*rows.get(tid,0)
def ri(o,s):return u16(o) if s==2 else u32(o)

# TypeRef
tr=[None]
for rid in range(1,rows.get(1,0)+1):
    o=offs[1]+(rid-1)*rs[1]; pos=o+cidx(2,0,26,35,1); ni=ri(pos,strsz);pos+=strsz; nsi=ri(pos,strsz)
    tr.append({'rid':rid,'name':str_at(ni),'namespace':str_at(nsi)})
# Fields
fields=[None]
for rid in range(1,rows.get(4,0)+1):
    o=offs[4]+(rid-1)*rs[4]; ni=ri(o+2,strsz); sigi=ri(o+2+strsz,blobsz); fields.append({'rid':rid,'name':str_at(ni),'sigBlob':sigi})
# Methods
methods=[None]
for rid in range(1,rows.get(6,0)+1):
    o=offs[6]+(rid-1)*rs[6]; methods.append({'rid':rid,'rva':u32(o),'name':str_at(ri(o+8,strsz))})
# TypeDef raw ranges
raw=[]
for rid in range(1,rows.get(2,0)+1):
    o=offs[2]+(rid-1)*rs[2]; pos=o+4; ni=ri(pos,strsz);pos+=strsz; nsi=ri(pos,strsz);pos+=strsz; pos+=cidx(2,1,2,27); fs=ri(pos,idxsz(4));pos+=idxsz(4); ms=ri(pos,idxsz(6))
    raw.append({'rid':rid,'name':str_at(ni),'namespace':str_at(nsi),'fieldStart':fs,'methodStart':ms})
types=[]; method_owner={}; field_owner={}
for i,ty in enumerate(raw):
    fe=(raw[i+1]['fieldStart']-1 if i+1<len(raw) else rows.get(4,0)); me=(raw[i+1]['methodStart']-1 if i+1<len(raw) else rows.get(6,0))
    ty['fields']=[fields[r] for r in range(max(1,ty['fieldStart']),min(fe,len(fields)-1)+1)] if ty['fieldStart'] else []
    ty['methods']=[methods[r] for r in range(max(1,ty['methodStart']),min(me,len(methods)-1)+1)] if ty['methodStart'] else []
    for m in ty['methods']:method_owner[m['rid']]=ty
    for f in ty['fields']:field_owner[f['rid']]=ty
    types.append(ty)
type_by_rid={x['rid']:x for x in types}
# MemberRef
mrs=[None]
mrps=cidx(3,2,1,26,6,27)
for rid in range(1,rows.get(10,0)+1):
    o=offs[10]+(rid-1)*rs[10]; parent=ri(o,mrps); ni=ri(o+mrps,strsz); mrs.append({'rid':rid,'name':str_at(ni),'parent':parent})
def fulltype(ty):return ((ty.get('namespace')+'.') if ty.get('namespace') else '')+ty.get('name','')
def member_parent_name(c):
    tag=c&7; rid=c>>3
    if tag==0 and rid in type_by_rid:return fulltype(type_by_rid[rid])
    if tag==1 and rid<len(tr):return ((tr[rid]['namespace']+'.') if tr[rid]['namespace'] else '')+tr[rid]['name']
    if tag==3 and rid in method_owner:return fulltype(method_owner[rid])
    return f'tag{tag}:rid{rid}'
def tokname(tok):
    tid=(tok>>24)&0xff; rid=tok&0xffffff
    if tid==0x02 and rid in type_by_rid:return 'TypeDef '+fulltype(type_by_rid[rid])
    if tid==0x01 and rid<len(tr):return 'TypeRef '+(((tr[rid]['namespace']+'.') if tr[rid]['namespace'] else '')+tr[rid]['name'])
    if tid==0x04 and rid<len(fields):return 'Field '+fulltype(field_owner.get(rid,{}))+'.'+fields[rid]['name']
    if tid==0x06 and rid<len(methods):return 'Method '+fulltype(method_owner.get(rid,{}))+'.'+methods[rid]['name']
    if tid==0x0a and rid<len(mrs):return 'MemberRef '+member_parent_name(mrs[rid]['parent'])+'.'+mrs[rid]['name']
    return f'token 0x{tok:08x}'

# IL decoder: operand widths for the opcodes that carry data.
short1=set(range(0x2b,0x38))|{0x0e,0x0f,0x10,0x11,0x12,0x13,0x1f,0xde}
long4=set(range(0x38,0x45))|{0x20,0xdd}
float4={0x22}; long8={0x21,0x23}
token_ops={0x27:'jmp',0x28:'call',0x29:'calli',0x6f:'callvirt',0x70:'cpobj',0x71:'ldobj',0x72:'ldstr',0x73:'newobj',0x74:'castclass',0x75:'isinst',0x79:'unbox',0x7b:'ldfld',0x7c:'ldflda',0x7d:'stfld',0x7e:'ldsfld',0x7f:'ldsflda',0x80:'stsfld',0x81:'stobj',0x8c:'box',0x8d:'newarr',0x8f:'ldelema',0xa3:'ldelem',0xa4:'stelem',0xa5:'unbox.any',0xc2:'refanyval',0xc6:'mkrefany',0xd0:'ldtoken'}
fe_token={0x06:'ldftn',0x07:'ldvirtftn',0x15:'initobj',0x16:'constrained',0x1c:'sizeof'}
fe_u16={0x09,0x0a,0x0b,0x0c,0x0d,0x0e}
fe_u8={0x12}
def body(m):
    if not m['rva']:return None
    try:o=rva_to_off(m['rva'])
    except:return None
    b=data[o]
    if b&3==2: cs=b>>2; s=o+1
    elif b&3==3:
        h=u16(o); hs=((h>>12)&0xf)*4; cs=u32(o+4); s=o+hs
    else:return None
    if s+cs>len(data):return None
    return data[s:s+cs]
def events(m):
    il=body(m)
    if il is None:return []
    ev=[]; i=0
    while i<len(il):
        pc=i; op=il[i]; i+=1
        if op==0xfe:
            if i>=len(il):break
            op2=il[i];i+=1
            if op2 in fe_token:
                if i+4>len(il):break
                tok=struct.unpack_from('<I',il,i)[0];i+=4;ev.append({'pc':pc,'op':'fe.'+fe_token[op2],'token':tok,'target':tokname(tok)})
            elif op2 in fe_u16:i+=2
            elif op2 in fe_u8:i+=1
            continue
        if op in token_ops:
            if i+4>len(il):break
            tok=struct.unpack_from('<I',il,i)[0];i+=4
            if op==0x72: ev.append({'pc':pc,'op':'ldstr','token':tok,'string':userstr(tok&0xffffff)})
            else: ev.append({'pc':pc,'op':token_ops[op],'token':tok,'target':tokname(tok)})
        elif op==0x45:
            if i+4>len(il):break
            n=struct.unpack_from('<I',il,i)[0];i+=4+4*n
        elif op in short1:i+=1
        elif op in long4 or op in float4:i+=4
        elif op in long8:i+=8
    return ev

hero=next((x for x in types if x['name']=='HeroShowSetting'),None)
mobile=next((x for x in types if x['name']=='MobileTouchCamera' and x['namespace']=='BitBenderGames'),None)
if not hero: raise SystemExit('HeroShowSetting introuvable')
hero_method_ids={m['rid'] for m in hero['methods']}; hero_rid=hero['rid']
hero_detail={'rid':hero_rid,'name':fulltype(hero),'fields':hero['fields'],'methods':[]}
for m in hero['methods']:
    hero_detail['methods'].append({**m,'events':events(m)})
mobile_detail={'rid':mobile['rid'],'name':fulltype(mobile),'fields':mobile['fields'],'methods':[]} if mobile else None
if mobile:
    for m in mobile['methods']:
        if re.search(r'Formation|Awake|ZoomParams|Focus',m['name'],re.I): mobile_detail['methods'].append({**m,'events':events(m)})

# Find callers / users of HeroShowSetting and formation-camera symbols.
refs=[]; rx=re.compile(r'(HeroShowSetting|CamZoomFormation|CamZoomFocusFormationRotation|RenderTexture|FormationRT|FormationBg|HeroShow)',re.I)
for m in methods[1:]:
    if not m or not m['rva']:continue
    owner=method_owner.get(m['rid']); ownername=fulltype(owner) if owner else ''
    if owner is hero:continue
    hit=[]
    for e in events(m):
        target=e.get('target',''); s=e.get('string','')
        tok=e.get('token',0); tid=(tok>>24)&0xff; rid=tok&0xffffff
        direct=(tid==0x02 and rid==hero_rid) or (tid==0x06 and rid in hero_method_ids)
        if direct or rx.search(target) or rx.search(s): hit.append(e)
    if hit: refs.append({'owner':ownername,'method':m['name'],'rid':m['rid'],'rva':m['rva'],'events':hit[:40]})
refs.sort(key=lambda x:(x['owner'],x['method']))

summary={'format':'WFGG_LASTWAR_HEROSHOW_CLR_IL_AUDIT_V1','source':str(p),'tables':{'TypeDef':rows.get(2,0),'Field':rows.get(4,0),'MethodDef':rows.get(6,0),'MemberRef':rows.get(10,0)},'heroShowSetting':hero_detail,'mobileTouchCamera':mobile_detail,'referenceCount':len(refs),'references':refs[:800],'guardrails':{'gameReadOnly':True,'previewUntouched':True,'mainUntouched':True}}
out.write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n','utf-8')
lines=['WfGg Last War — HEROSHOW CLR IL AUDIT','',f"HeroShowSetting fields={len(hero['fields'])} methods={len(hero['methods'])}"]
for f in hero['fields']:lines.append('  FIELD '+f['name'])
for m in hero_detail['methods']:
    lines.append('  METHOD '+m['name']+f" rva=0x{m['rva']:x}")
    for e in m['events'][:30]:lines.append('    '+e['op']+' '+(e.get('target') or repr(e.get('string',''))))
if mobile:
    lines+=['',f"MobileTouchCamera targetedMethods={len(mobile_detail['methods'])}"]
    for m in mobile_detail['methods']:
        lines.append('  METHOD '+m['name']+f" rva=0x{m['rva']:x}")
        for e in m['events'][:20]:lines.append('    '+e['op']+' '+(e.get('target') or repr(e.get('string',''))))
lines+=['',f'REFERENCES={len(refs)}']
for r in refs[:120]:
    lines.append(f"REF {r['owner']}.{r['method']} rva=0x{r['rva']:x}")
    for e in r['events'][:12]:lines.append('  '+e['op']+' '+(e.get('target') or repr(e.get('string',''))))
report.write_text('\n'.join(lines)+'\n','utf-8')
print('HEROSHOW_CLR_IL_AUDIT_OK',f"heroFields={len(hero['fields'])}",f"heroMethods={len(hero['methods'])}",f"references={len(refs)}")
for f in hero['fields'][:40]:print('HEROSHOW_FIELD',f['name'])
for m in hero_detail['methods'][:20]:print('HEROSHOW_METHOD',m['name'],f"events={len(m['events'])}")
for r in refs[:20]:print('HEROSHOW_REF',r['owner']+'.'+r['method'])
print('HEROSHOW_CLR_IL_JSON',out)
print('HEROSHOW_CLR_IL_REPORT',report)
PYEOF

python "$PY" "$DLL" "$OUT" "$REPORT"
rm -f "$PY"

git add scripts/lastwar-heroshow-clr-il-audit.sh "$OUT"
if ! git diff --cached --quiet; then
  git commit -m "lab: inspect HeroShow Formation CLR IL"
  git push origin "$BRANCH"
fi

echo "=== HEROSHOW CLR IL AUDIT TERMINE ==="
echo "JSON: $OUT"
echo "Rapport: $REPORT"
echo "Preview inchangée. main non modifiée."
