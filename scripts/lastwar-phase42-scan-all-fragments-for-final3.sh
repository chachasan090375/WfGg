#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — PHASE 42
# Resolve the final three formation prefabs (Mason, Violet, Venom) by scanning
# every installed BundleFragment*.bytes across all APK splits. Exact
# HeroAppearance.queue_model_path remains the only automatic success criterion.
# CODE ONLY. OFFLINE ONLY. No Last War network connection.

PKG="com.fun.lastwar.gp"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
P40="$ROOT/frontend/lab/master-assets-v2/meta/formation-unit-bundle-set-31.json"
P41="$ROOT/frontend/lab/master-assets-v2/meta/formation-prefab-exact-resolution-31.json"
OUT="$ROOT/frontend/lab/master-assets-v2/meta/formation-prefab-all-fragments-final3.json"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_PHASE42_FINAL3_ALL_FRAGMENTS.txt"
LOCAL="$ROOT/frontend/lab/local-assets/lastwar-formation-prefabs-v2"
PACK="$HOME/storage/downloads/WFGG_LASTWAR_PHASE42_FINAL3_RAW.zip"
PY="${TMPDIR:-${HOME}/.cache}/wfgg-phase42-final3.py"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
command -v python >/dev/null 2>&1 || fail "python absent"
[[ -s "$P40" ]] || fail "Phase40 absente: $P40"
[[ -s "$P41" ]] || fail "Phase41 absente: $P41"
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche active incorrecte"

mapfile -t APK_PATHS < <(cmd package path "$PKG" 2>/dev/null | sed -n 's/^package://p')
if [[ ${#APK_PATHS[@]} -eq 0 ]]; then
  mapfile -t APK_PATHS < <(pm path "$PKG" 2>/dev/null | sed -n 's/^package://p')
fi
[[ ${#APK_PATHS[@]} -gt 0 ]] || fail "installation Last War introuvable ($PKG)"

rm -rf "$LOCAL"
mkdir -p "$LOCAL" "$(dirname "$OUT")" "$(dirname "$PY")"

cat > "$PY" <<'PYEOF'
from pathlib import Path
import io, json, lzma, os, re, struct, sys, zipfile

p40p=Path(sys.argv[1]); p41p=Path(sys.argv[2]); outp=Path(sys.argv[3]); reportp=Path(sys.argv[4]); local=Path(sys.argv[5]); apks=sys.argv[6:]
p40=json.loads(p40p.read_text(encoding='utf-8'))
p41=json.loads(p41p.read_text(encoding='utf-8'))
rows40={int(x['heroId']):x for x in p40.get('rows',[])}
if len(rows40)!=31: raise SystemExit('Phase40 incomplete')

unresolved=[int(x) for x in p41.get('unresolvedExactHeroIds',[])]
if unresolved != [50023,50025,50028]:
    print('NOTE unresolved from Phase41:', unresolved)
if not unresolved:
    raise SystemExit('Phase41 already resolved all units')

targets=[]
for hid in unresolved:
    x=rows40[hid]
    q=x['queueModelPath'].replace('\\','/')
    low=q.lower()
    base=low.rsplit('/',1)[-1]
    stem=re.sub(r'\.prefab$','',base)
    parent=low.rsplit('/',2)[-2] if '/' in low else ''
    # Family root is intentionally broader than exact path and is diagnostics only.
    family=''
    m=re.search(r'(a_hero_[a-z0-9_]+)',low)
    if m: family=m.group(1)
    targets.append({
      'heroId':hid,'name':x['name'],'queueModelPath':q,'queueLower':low,
      'exactBytes':low.encode('utf-8'),
      'relativeBytes':(low[7:] if low.startswith('assets/') else low).encode('utf-8'),
      'base':base,'stem':stem,'parent':parent,'family':family,
      'hits':[]
    })

# Find every BundleFragment*.bytes in every installed split.
fragment_entries=[]
standalone_entries=[]
for apk in apks:
    try:
        with zipfile.ZipFile(apk) as z:
            for zi in z.infolist():
                n=zi.filename
                nl=n.lower()
                if nl.startswith('assets/assetbundles/') and re.search(r'bundlefragment\d*\.bytes$',nl):
                    fragment_entries.append((apk,n,zi.file_size))
                # Some asset packs can carry individual UnityFS files. Only consider entries
                # whose names themselves mention one of the final-three families.
                if nl.startswith('assets/assetbundles/') and zi.file_size>0 and zi.file_size<=64*1024*1024:
                    if any(t['family'] and t['family'] in nl for t in targets):
                        standalone_entries.append((apk,n,zi.file_size))
    except Exception: pass

if not fragment_entries:
    raise SystemExit('aucun BundleFragment*.bytes installé')

MAX_BUNDLE_RAW=160*1024*1024
MAX_BUNDLE_DECODED=260*1024*1024

def read_cstr(f,maxlen=16384):
    b=bytearray()
    while len(b)<maxlen:
        c=f.read(1)
        if not c: raise EOFError('cstr eof')
        if c==b'\0': return bytes(b)
        b+=c
    raise ValueError('cstr too long')

def align16(n): return (n+15)&~15

def lz4_block(src,expected=None):
    src=memoryview(src);i=0;out=bytearray()
    while i<len(src):
        token=src[i];i+=1;lit=token>>4
        if lit==15:
            while True:
                if i>=len(src): raise ValueError('lz4 literal overflow')
                x=src[i];i+=1;lit+=x
                if x!=255: break
        if i+lit>len(src): raise ValueError('lz4 literal range')
        out+=src[i:i+lit];i+=lit
        if i>=len(src): break
        if i+2>len(src): raise ValueError('lz4 offset eof')
        off=src[i]|(src[i+1]<<8);i+=2
        if off<=0 or off>len(out): raise ValueError('lz4 bad offset')
        ml=(token&15)+4
        if (token&15)==15:
            while True:
                if i>=len(src): raise ValueError('lz4 match overflow')
                x=src[i];i+=1;ml+=x
                if x!=255: break
        pos=len(out)-off
        for _ in range(ml): out.append(out[pos]);pos+=1
    return bytes(out)

def decomp(blob,typ,expected=None):
    typ &= 0x3f
    if typ==0:return blob
    if typ in (2,3):return lz4_block(blob,expected)
    if typ==1:
        for fmt in (lzma.FORMAT_AUTO,lzma.FORMAT_ALONE):
            try:return lzma.decompress(blob,format=fmt)
            except Exception:pass
        raise ValueError('lzma decode failed')
    raise ValueError(f'compression {typ}')

def parse_block_info(raw):
    if len(raw)<20:raise ValueError('blockinfo short')
    p=16;bc=struct.unpack_from('>I',raw,p)[0];p+=4
    if bc>200000:raise ValueError('bad block count')
    blocks=[]
    for _ in range(bc):
        if p+10>len(raw):raise ValueError('block list truncated')
        u,c,fl=struct.unpack_from('>IIH',raw,p);p+=10;blocks.append((u,c,fl))
    if p+4>len(raw):raise ValueError('node count missing')
    nc=struct.unpack_from('>I',raw,p)[0];p+=4
    if nc>200000:raise ValueError('bad node count')
    nodes=[]
    for _ in range(nc):
        if p+20>len(raw):raise ValueError('node record truncated')
        off,size,fl=struct.unpack_from('>qqI',raw,p);p+=20
        e=raw.find(b'\0',p)
        if e<0:raise ValueError('node name eof')
        path=raw[p:e].decode('utf-8','ignore');p=e+1
        nodes.append((off,size,fl,path))
    return blocks,nodes

def decode_bundle_stream(f,start,total,want_data=True):
    f.seek(start)
    if read_cstr(f)!=b'UnityFS':raise ValueError('not UnityFS')
    fmt=struct.unpack('>I',f.read(4))[0];uver=read_cstr(f);urev=read_cstr(f)
    size=struct.unpack('>Q',f.read(8))[0]
    cs=struct.unpack('>I',f.read(4))[0];us=struct.unpack('>I',f.read(4))[0];flags=struct.unpack('>I',f.read(4))[0]
    hend=f.tell()
    if not (1<=fmt<=20) or size<=0 or start+size>total+16:raise ValueError('bad header')
    if size>MAX_BUNDLE_RAW:raise OverflowError('bundle raw too large')
    aligned=start+align16(hend-start) if fmt>=7 else hend
    meta_pos=start+size-cs if flags&0x80 else aligned
    f.seek(meta_pos);meta=decomp(f.read(cs),flags&0x3f,us)
    blocks,nodes=parse_block_info(meta)
    decoded_size=sum(u for u,_,_ in blocks)
    if decoded_size>MAX_BUNDLE_DECODED:raise OverflowError('bundle decoded too large')
    if not want_data:return size,nodes,None,uver.decode('ascii','ignore'),urev.decode('ascii','ignore')
    if flags&0x80:data_pos=aligned
    else:
        data_pos=meta_pos+cs
        if flags&0x200:data_pos=start+align16(data_pos-start)
    f.seek(data_pos);parts=[]
    for u,c,bfl in blocks:
        blob=f.read(c)
        if len(blob)!=c:raise ValueError('block truncated')
        parts.append(decomp(blob,bfl&0x3f,u))
    return size,nodes,b''.join(parts),uver.decode('ascii','ignore'),urev.decode('ascii','ignore')

def evaluate(data,nodes,t):
    low=data.lower(); nodeblob=' '.join(n[3] for n in nodes).lower()
    exact=t['exactBytes'] in low
    exact_rel=t['relativeBytes'] in low
    # diagnostic siblings (world/city/pve variants) remain non-authoritative
    fam=t['family'].encode() in low if t['family'] else False
    stem=t['stem'].encode() in low
    variants=[]
    if fam:
        for m in re.finditer(rb'assets/[ -~]{0,180}?\.prefab',low):
            s=m.group().decode('latin1','ignore')
            if t['family'] in s and s not in variants: variants.append(s)
            if len(variants)>=12: break
    return exact,exact_rel,fam or stem or (t['family'] in nodeblob if t['family'] else False),variants

stats={'fragments':[],'bundlesScanned':0,'bundlesDecoded':0,'decodeErrors':0,'oversizeSkipped':0,'candidateBundles':0,'standaloneScanned':0}

# Scan all fragment streams.
for apk,en,entry_size in fragment_entries:
    frag={'apk':os.path.basename(apk),'entry':en,'bytes':entry_size,'scanned':0,'decoded':0,'errors':0}
    with zipfile.ZipFile(apk) as z, z.open(en) as f:
        total=entry_size
        while f.tell()<total:
            start=f.tell();sig=f.read(8)
            if not sig:break
            if not sig.startswith(b'UnityFS'):
                buf=sig+f.read(min(2*1024*1024,total-f.tell()))
                q=buf.find(b'UnityFS\0')
                if q<0:continue
                start+=q;f.seek(start)
            stats['bundlesScanned']+=1;frag['scanned']+=1
            try:
                size,nodes,data,uver,urev=decode_bundle_stream(f,start,total,True)
                stats['bundlesDecoded']+=1;frag['decoded']+=1
            except OverflowError:
                stats['oversizeSkipped']+=1;f.seek(min(total,start+16));continue
            except Exception:
                stats['decodeErrors']+=1;frag['errors']+=1;f.seek(min(total,start+16));continue
            matched=[]
            for t in targets:
                exact,exact_rel,diag,variants=evaluate(data,nodes,t)
                if not (exact or exact_rel or diag):continue
                hit={'apk':os.path.basename(apk),'entry':en,'offset':start,'bytes':size,
                     'unityVersion':uver,'unityRevision':urev,'exactQueuePath':bool(exact),
                     'exactQueuePathRelative':bool(exact_rel),'diagnosticFamily':bool(diag),
                     'variantPrefabPaths':variants,'nodes':[n[3] for n in nodes[:40]]}
                t['hits'].append(hit);matched.append(str(t['heroId']))
            if matched:
                stats['candidateBundles']+=1
                f.seek(start);raw=f.read(size)
                name=f"{Path(apk).stem}_{Path(en).stem}_{start:010d}_{size}_{'-'.join(matched)}.bundle"
                p=local/name
                if not p.exists():p.write_bytes(raw)
            f.seek(start+size)
    stats['fragments'].append(frag)

# Also inspect small standalone asset-bundle entries whose entry name already matches a target family.
for apk,en,entry_size in standalone_entries:
    try:
        with zipfile.ZipFile(apk) as z:
            raw=z.read(en)
        if not raw.startswith(b'UnityFS\0'):continue
        stats['standaloneScanned']+=1
        f=io.BytesIO(raw)
        size,nodes,data,uver,urev=decode_bundle_stream(f,0,len(raw),True)
        for t in targets:
            exact,exact_rel,diag,variants=evaluate(data,nodes,t)
            if not (exact or exact_rel or diag):continue
            hit={'apk':os.path.basename(apk),'entry':en,'offset':0,'bytes':size,
                 'unityVersion':uver,'unityRevision':urev,'exactQueuePath':bool(exact),
                 'exactQueuePathRelative':bool(exact_rel),'diagnosticFamily':bool(diag),
                 'variantPrefabPaths':variants,'nodes':[n[3] for n in nodes[:40]],'standalone':True}
            t['hits'].append(hit)
            p=local/(Path(apk).stem+'_'+re.sub(r'[^A-Za-z0-9_.-]+','_',en)[-120:])
            if not p.suffix:p=p.with_suffix('.bundle')
            if not p.exists():p.write_bytes(raw)
    except Exception:pass

rows=[]
for t in targets:
    exact=[h for h in t['hits'] if h['exactQueuePath'] or h['exactQueuePathRelative']]
    diag=[h for h in t['hits'] if h not in exact]
    variants=[]
    for h in diag:
        for p in h.get('variantPrefabPaths',[]):
            if p not in variants:variants.append(p)
    rows.append({'heroId':t['heroId'],'name':t['name'],'queueModelPath':t['queueModelPath'],
                 'resolvedExact':bool(exact),'exactHitCount':len(exact),'diagnosticHitCount':len(diag),
                 'exactHits':exact,'diagnosticHits':diag[:30],'variantPrefabPaths':variants[:30]})
    print(f"FINAL3 {t['heroId']} {t['name']}: exact={len(exact)} diagnostic={len(diag)} resolved={bool(exact)}")

phase41_ready=set(int(x) for x in p41.get('combinedReadyHeroIds',[]))
new_exact={x['heroId'] for x in rows if x['resolvedExact']}
combined=sorted(phase41_ready|new_exact)
unresolved2=sorted(x['heroId'] for x in rows if not x['resolvedExact'])
out={'format':'WFGG_LASTWAR_FORMATION_PREFAB_ALL_FRAGMENTS_FINAL3_V1','networkUsed':False,
     'fragmentEntries':[{'apk':os.path.basename(a),'entry':e,'bytes':s} for a,e,s in fragment_entries],
     'stats':stats,'rows':rows,'combinedReadyHeroIds':combined,'combinedReadyCount':len(combined),
     'unresolvedExactHeroIds':unresolved2}
outp.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')

lines=[
 'WfGg Last War LAB — PHASE 42 FINAL 3 / ALL INSTALLED FRAGMENTS',
 'OFFLINE ONLY · exact HeroAppearance.queue_model_path remains authoritative',
 f"fragments={len(fragment_entries)} bundlesScanned={stats['bundlesScanned']} bundlesDecoded={stats['bundlesDecoded']} errors={stats['decodeErrors']} oversize={stats['oversizeSkipped']}",
 f"phase41Ready={len(phase41_ready)}/31 newExact={len(new_exact)}/3 combinedReady={len(combined)}/31 unresolved={len(unresolved2)}",
 ''
]
for f in stats['fragments']:
    lines.append(f"FRAGMENT apk={f['apk']} entry={f['entry']} bytes={f['bytes']} scanned={f['scanned']} decoded={f['decoded']} errors={f['errors']}")
lines.append('')
for x in rows:
    lines.append(f"HERO {x['heroId']} {x['name']} resolvedExact={x['resolvedExact']} exactHits={x['exactHitCount']} diagnosticHits={x['diagnosticHitCount']}")
    lines.append('  queue_model_path='+x['queueModelPath'])
    for h in x['exactHits']:
        lines.append(f"  EXACT apk={h['apk']} entry={h['entry']} offset={h['offset']} bytes={h['bytes']}")
    for p in x['variantPrefabPaths'][:12]:lines.append('  VARIANT '+p)
    lines.append('')
lines.append('combinedReadyHeroIds='+','.join(map(str,combined)))
lines.append('unresolvedExactHeroIds='+','.join(map(str,unresolved2)))
reportp.write_text('\n'.join(lines)+'\n',encoding='utf-8')
print('PHASE42_OK',f"exactNew={len(new_exact)}/3",f"combined={len(combined)}/31",f"unresolved={len(unresolved2)}",f"fragments={len(fragment_entries)}")
PYEOF

python "$PY" "$P40" "$P41" "$OUT" "$REPORT" "$LOCAL" "${APK_PATHS[@]}"
rm -f "$PY"

rm -f "$PACK" "$PACK.sha256"
if find "$LOCAL" -type f -name '*.bundle' -print -quit | grep -q .; then
  python - "$LOCAL" "$PACK" <<'PYZIP'
from pathlib import Path
import sys,zipfile
src=Path(sys.argv[1]);dst=Path(sys.argv[2]);fs=sorted(src.glob('*.bundle'))
with zipfile.ZipFile(dst,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
    for f in fs:z.write(f,arcname=f.name)
print(f"PHASE42_PACK_OK files={len(fs)} bytes={dst.stat().st_size}")
PYZIP
  sha256sum "$PACK" > "$PACK.sha256"
fi
cat > "$LOCAL/.gitignore" <<'EOF'
*
!.gitignore
EOF

git add -f frontend/lab/master-assets-v2/meta/formation-prefab-all-fragments-final3.json scripts/lastwar-phase42-scan-all-fragments-for-final3.sh
if git diff --cached --quiet -- frontend/lab/master-assets-v2/meta/formation-prefab-all-fragments-final3.json scripts/lastwar-phase42-scan-all-fragments-for-final3.sh; then
  echo "Aucun changement à committer."
else
  git commit -m "lab: scan all installed fragments for final three formation prefabs"
fi
git push origin "$BRANCH"

echo "=== PHASE 42 TERMINEE ==="
echo "Rapport: $REPORT"
if [[ -s "$PACK" ]]; then
  echo "Bundles bruts: $PACK"
  echo "SHA256: $PACK.sha256"
fi
echo "Ne lance pas encore la page Escouades."
echo "main non modifiée."
