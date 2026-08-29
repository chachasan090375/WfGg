#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — PHASE 41
# Resolve the 12 Phase40 not-ready formation units by scanning the installed
# UnityFS fragment for the *exact* authoritative HeroAppearance.queue_model_path.
# This deliberately does not infer prefab identity from bundle filenames.
# CODE ONLY. OFFLINE ONLY. No Last War network connection.

PKG="com.fun.lastwar.gp"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
P40="$ROOT/frontend/lab/master-assets-v2/meta/formation-unit-bundle-set-31.json"
OUT="$ROOT/frontend/lab/master-assets-v2/meta/formation-prefab-exact-resolution-31.json"
LOCAL="$ROOT/frontend/lab/local-assets/lastwar-formation-prefabs-v1"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_PHASE41_EXACT_PREFAB_RESOLUTION_31.txt"
PACK="$HOME/storage/downloads/WFGG_LASTWAR_PHASE41_EXACT_PREFABS_RAW.zip"
PY="${TMPDIR:-${HOME}/.cache}/wfgg-phase41-exact-prefab.py"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
command -v python >/dev/null 2>&1 || fail "python absent"
command -v zip >/dev/null 2>&1 || fail "zip absent"
[[ -s "$P40" ]] || fail "Phase40 absente: $P40"
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

p40p=Path(sys.argv[1]); outp=Path(sys.argv[2]); local=Path(sys.argv[3]); reportp=Path(sys.argv[4]); apks=sys.argv[5:]
p40=json.loads(p40p.read_text(encoding='utf-8'))
rows=p40.get('rows') or []
if len(rows)!=31: raise SystemExit(f'Phase40 expected 31 rows, got {len(rows)}')

not_ready=[x for x in rows if not x.get('bundleSetReady')]
if not not_ready:
    raise SystemExit('Phase40 already has 31 ready bundle sets')

ENTRY='assets/AssetBundles/BundleFragment0.bytes'
found=None
for apk in apks:
    try:
        with zipfile.ZipFile(apk) as z:
            try: info=z.getinfo(ENTRY)
            except KeyError: continue
            found=(apk,info);break
    except Exception: pass
if not found: raise SystemExit('BundleFragment0.bytes introuvable')
apk,info=found

MAX_BUNDLE_RAW=128*1024*1024
MAX_BUNDLE_DECODED=220*1024*1024

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
                if x!=255:break
        if i+lit>len(src):raise ValueError('lz4 literal range')
        out+=src[i:i+lit];i+=lit
        if i>=len(src):break
        if i+2>len(src):raise ValueError('lz4 offset eof')
        off=src[i]|(src[i+1]<<8);i+=2
        if off<=0 or off>len(out):raise ValueError('lz4 bad offset')
        ml=(token&15)+4
        if (token&15)==15:
            while True:
                if i>=len(src):raise ValueError('lz4 match overflow')
                x=src[i];i+=1;ml+=x
                if x!=255:break
        pos=len(out)-off
        for _ in range(ml):out.append(out[pos]);pos+=1
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

def decode_bundle(f,start,total,want_data=True):
    f.seek(start)
    if read_cstr(f)!=b'UnityFS':raise ValueError('not UnityFS')
    fmt=struct.unpack('>I',f.read(4))[0];unity_ver=read_cstr(f);unity_rev=read_cstr(f)
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
    if not want_data:return size,nodes,None,unity_ver.decode('ascii','ignore'),unity_rev.decode('ascii','ignore')
    if flags&0x80:data_pos=aligned
    else:
        data_pos=meta_pos+cs
        if flags&0x200:data_pos=start+align16(data_pos-start)
    f.seek(data_pos);parts=[]
    for u,c,bfl in blocks:
        blob=f.read(c)
        if len(blob)!=c:raise ValueError('block truncated')
        parts.append(decomp(blob,bfl&0x3f,u))
    return size,nodes,b''.join(parts),unity_ver.decode('ascii','ignore'),unity_rev.decode('ascii','ignore')

def normpath(s):
    s=str(s or '').replace('\\','/').lower()
    s=re.sub(r'/+','/',s)
    return s.strip()

def basename_markers(path):
    p=normpath(path); base=p.rsplit('/',1)[-1]
    stem=re.sub(r'\.prefab$','',base)
    parent=p.rsplit('/',2)[-2] if '/' in p else ''
    return [x for x in (base,stem,parent) if len(x)>=5]

targets=[]
for x in not_ready:
    qp=normpath(x['queueModelPath'])
    targets.append({
      'heroId':x['heroId'],'name':x['name'],'queueModelPath':x['queueModelPath'],
      'queueLower':qp,'queueBytes':qp.encode('utf-8'),
      'markers':[m.lower() for m in basename_markers(qp)],
      'identityTokens':[str(t).lower() for t in x.get('identityTokens',[])],
      'hits':[]
    })

stats={'bundlesScanned':0,'bundlesDecoded':0,'decodeErrors':0,'oversizeSkipped':0,'candidateBundles':0}

with zipfile.ZipFile(apk) as z, z.open(info) as f:
    total=info.file_size
    while f.tell()<total:
        start=f.tell(); sig=f.read(8)
        if not sig:break
        if not sig.startswith(b'UnityFS'):
            # bounded resync; same proven strategy as Phase30B
            buf=sig+f.read(min(2*1024*1024,total-f.tell()))
            q=buf.find(b'UnityFS\0')
            if q<0:continue
            start+=q;f.seek(start)
        stats['bundlesScanned']+=1
        try:
            size,nodes,data,uver,urev=decode_bundle(f,start,total,True)
            stats['bundlesDecoded']+=1
        except OverflowError:
            stats['oversizeSkipped']+=1
            f.seek(min(total,start+16));continue
        except Exception:
            stats['decodeErrors']+=1
            f.seek(min(total,start+16));continue
        low=data.lower()
        nodeblob=' '.join(n[3] for n in nodes).lower()
        anyhit=False
        for t in targets:
            exact=t['queueBytes'] in low
            # Some Unity AssetBundle containers store a lower-cased path without Assets/ prefix.
            qrel=t['queueLower']
            if qrel.startswith('assets/'):qrel=qrel[7:]
            exact_rel=qrel.encode('utf-8') in low
            marker_hits=[m for m in t['markers'] if m.encode('utf-8') in low or m in nodeblob]
            identity_hits=[m for m in t['identityTokens'] if m.encode('utf-8') in low or m in nodeblob]
            if not (exact or exact_rel or (marker_hits and identity_hits)):
                continue
            # Strong confidence requires the exact queue path. Marker+identity is retained only
            # as diagnostics and cannot auto-promote the unit to resolvedExact.
            hit={
              'offset':start,'bytes':size,'unityVersion':uver,'unityRevision':urev,
              'nodes':[n[3] for n in nodes[:80]],
              'exactQueuePath':bool(exact),'exactQueuePathRelative':bool(exact_rel),
              'markerHits':marker_hits,'identityHits':identity_hits
            }
            t['hits'].append(hit);anyhit=True
        if anyhit:
            stats['candidateBundles']+=1
            # Save the authentic raw UnityFS bundle once. Later phases can parse hierarchy,
            # meshes/material references and animations without rescanning the APK.
            f.seek(start); raw=f.read(size)
            by_targets=[]
            for t in targets:
                if t['hits'] and t['hits'][-1]['offset']==start:
                    by_targets.append(str(t['heroId']))
            outname=f"{start:010d}_{size}_{'-'.join(by_targets)}.bundle"
            outpath=local/outname
            if not outpath.exists():outpath.write_bytes(raw)
        f.seek(start+size)

rows=[]
for t in targets:
    exact_hits=[h for h in t['hits'] if h['exactQueuePath'] or h['exactQueuePathRelative']]
    diag_hits=[h for h in t['hits'] if h not in exact_hits]
    # Multiple exact hits are preserved; the actual prefab hierarchy will be selected in Phase42.
    row={
      'heroId':t['heroId'],'name':t['name'],'queueModelPath':t['queueModelPath'],
      'exactHitCount':len(exact_hits),'diagnosticHitCount':len(diag_hits),
      'resolvedExact':bool(exact_hits),'exactHits':exact_hits,'diagnosticHits':diag_hits[:12]
    }
    rows.append(row)
    print(f"PREFAB {t['heroId']} {t['name']}: exact={len(exact_hits)} diagnostic={len(diag_hits)} resolved={row['resolvedExact']}")

# Carry the 19 Phase40-ready units as already resolved by explicit prefab bundle names.
ready_ids=[x['heroId'] for x in rows if x['resolvedExact']]
phase40_ready=[x['heroId'] for x in p40['rows'] if x.get('bundleSetReady')]
combined_ready=sorted(set(phase40_ready+ready_ids))
unresolved=sorted(x['heroId'] for x in rows if not x['resolvedExact'])

out={
 'format':'WFGG_LASTWAR_FORMATION_PREFAB_EXACT_RESOLUTION_31_V1','networkUsed':False,
 'sourcePhase40':'formation-unit-bundle-set-31.json','fragmentSource':{'apk':os.path.basename(apk),'entry':ENTRY,'bytes':info.file_size},
 'stats':stats,'phase40ReadyHeroIds':phase40_ready,'phase41Rows':rows,
 'combinedReadyHeroIds':combined_ready,'combinedReadyCount':len(combined_ready),
 'unresolvedExactHeroIds':unresolved
}
outp.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')

lines=[
 'WfGg Last War LAB — PHASE 41 EXACT PREFAB RESOLUTION 31',
 'OFFLINE ONLY · exact HeroAppearance.queue_model_path searched inside decoded UnityFS bundles',
 f"phase40Ready={len(phase40_ready)}/31 phase41Targets={len(rows)} resolvedExact={len(ready_ids)}/{len(rows)} combinedReady={len(combined_ready)}/31",
 f"bundlesScanned={stats['bundlesScanned']} bundlesDecoded={stats['bundlesDecoded']} candidateBundles={stats['candidateBundles']} decodeErrors={stats['decodeErrors']} oversizeSkipped={stats['oversizeSkipped']}",
 ''
]
for x in rows:
    lines.append(f"HERO {x['heroId']} {x['name']} resolvedExact={x['resolvedExact']} exactHits={x['exactHitCount']} diagnosticHits={x['diagnosticHitCount']}")
    lines.append('  queue_model_path='+x['queueModelPath'])
    for h in x['exactHits']:
        lines.append(f"  EXACT offset={h['offset']} bytes={h['bytes']} unity={h['unityVersion'] or '-'} rev={h['unityRevision'] or '-'}")
        if h['nodes']:lines.append('    nodes='+','.join(h['nodes'][:12]))
    for h in x['diagnosticHits'][:3]:
        lines.append(f"  DIAG offset={h['offset']} bytes={h['bytes']} markers={','.join(h['markerHits']) or '-'} identity={','.join(h['identityHits']) or '-'}")
    lines.append('')
lines.append('combinedReadyHeroIds='+','.join(map(str,combined_ready)))
lines.append('unresolvedExactHeroIds='+','.join(map(str,unresolved)))
reportp.write_text('\n'.join(lines)+'\n',encoding='utf-8')
print('PHASE41_OK',f"exact={len(ready_ids)}/{len(rows)}",f"combined={len(combined_ready)}/31",f"unresolved={len(unresolved)}")
PYEOF

python "$PY" "$P40" "$OUT" "$LOCAL" "$REPORT" "${APK_PATHS[@]}"
rm -f "$PY"

# Raw authentic bundles are intentionally not committed to Git. Package them for
# handoff/recovery; Git receives only the exact-resolution metadata and script.
rm -f "$PACK"
if find "$LOCAL" -type f -name '*.bundle' -print -quit | grep -q .; then
  (cd "$LOCAL" && zip -q -9 "$PACK" ./*.bundle)
  sha256sum "$PACK" > "$PACK.sha256"
fi
cat > "$LOCAL/.gitignore" <<'EOF'
*
!.gitignore
EOF

git add -f frontend/lab/master-assets-v2/meta/formation-prefab-exact-resolution-31.json scripts/lastwar-phase41-resolve-missing-prefab-bundles.sh
if git diff --cached --quiet -- frontend/lab/master-assets-v2/meta/formation-prefab-exact-resolution-31.json scripts/lastwar-phase41-resolve-missing-prefab-bundles.sh; then
  echo "Aucun changement à committer."
else
  git commit -m "lab: resolve missing formation prefabs by exact queue model path"
fi
git push origin "$BRANCH"

echo "=== PHASE 41 TERMINEE ==="
echo "Rapport: $REPORT"
if [[ -s "$PACK" ]]; then
  echo "Bundles bruts: $PACK"
  echo "SHA256: $PACK.sha256"
fi
echo "Ne lance pas encore la page Escouades."
echo "main non modifiée."
