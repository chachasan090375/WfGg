#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — PHASE 43
# SELECT RENDERABLE FORMATION SCENE BUNDLES FOR ALL 31 AUTHORITATIVE UNITS
# CODE ONLY · OFFLINE ONLY · no generated artwork · no Last War network.
#
# Why this phase exists:
# Phase41/42 proved that an exact queue_model_path string can occur in a wrapper
# (WorldMonster / SoftReferencePrefab) rather than in the actual renderable hero
# scene. This phase therefore scores real geometry and rejects wrapper/UI bundles.

PKG="com.fun.lastwar.gp"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
MAP="$ROOT/frontend/lab/lastwar-hero-formation-unit-authoritative-map.js"
OUT="$ROOT/frontend/lab/master-assets-v2/meta/formation-renderable-scene-selection-31.json"
LOCAL="$ROOT/frontend/lab/local-assets/lastwar-renderable-scenes-v1"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_PHASE43_RENDERABLE_SCENES_31.txt"
PACK="$HOME/storage/downloads/WFGG_LASTWAR_PHASE43_RENDERABLE_SCENES_RAW.zip"
PY="${TMPDIR:-${HOME}/.cache}/wfgg-phase43-renderable-scenes.py"
UNITY_VERSION="2019.4.41f1"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
command -v python >/dev/null 2>&1 || fail "python absent"
python - <<'PYTEST' >/dev/null 2>&1 || fail "UnityPy absent. Relance la dépendance Phase30."
import UnityPy
PYTEST
[[ -s "$MAP" ]] || fail "référentiel 31/31 absent: $MAP"
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

import UnityPy

mapp=Path(sys.argv[1]); outp=Path(sys.argv[2]); local=Path(sys.argv[3]); reportp=Path(sys.argv[4]); unity_ver=sys.argv[5]; apks=sys.argv[6:]
text=mapp.read_text(encoding='utf-8')
data=json.loads(text.split('=',1)[1].rsplit(';',1)[0])
entries=data.get('entries') or []
if len(entries)!=31: raise SystemExit(f'expected 31 entries, got {len(entries)}')
UnityPy.config.FALLBACK_UNITY_VERSION=unity_ver

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
                if i>=len(src):raise ValueError('lz4 literal overflow')
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
    p=16;bc=struct.unpack_from('>I',raw,p)[0];p+=4
    if bc>200000:raise ValueError('bad block count')
    blocks=[]
    for _ in range(bc):
        u,c,fl=struct.unpack_from('>IIH',raw,p);p+=10;blocks.append((u,c,fl))
    nc=struct.unpack_from('>I',raw,p)[0];p+=4
    if nc>200000:raise ValueError('bad node count')
    nodes=[]
    for _ in range(nc):
        off,size,fl=struct.unpack_from('>qqI',raw,p);p+=20
        e=raw.find(b'\0',p)
        if e<0:raise ValueError('node name eof')
        path=raw[p:e].decode('utf-8','ignore');p=e+1
        nodes.append((off,size,fl,path))
    return blocks,nodes
def decode_bundle(f,start,total):
    f.seek(start)
    if read_cstr(f)!=b'UnityFS':raise ValueError('not UnityFS')
    fmt=struct.unpack('>I',f.read(4))[0];uver=read_cstr(f);urev=read_cstr(f)
    size=struct.unpack('>Q',f.read(8))[0]
    cs=struct.unpack('>I',f.read(4))[0];us=struct.unpack('>I',f.read(4))[0];flags=struct.unpack('>I',f.read(4))[0]
    hend=f.tell()
    if not (1<=fmt<=20) or size<=0 or start+size>total+16:raise ValueError('bad header')
    if size>MAX_BUNDLE_RAW:raise OverflowError('raw too large')
    aligned=start+align16(hend-start) if fmt>=7 else hend
    meta_pos=start+size-cs if flags&0x80 else aligned
    f.seek(meta_pos);meta=decomp(f.read(cs),flags&0x3f,us)
    blocks,nodes=parse_block_info(meta)
    if sum(u for u,_,_ in blocks)>MAX_BUNDLE_DECODED:raise OverflowError('decoded too large')
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

def norm(s): return re.sub(r'[^a-z0-9]+','_',str(s or '').lower()).strip('_')
def flat(s): return norm(s).replace('_','')

def identity_tokens(e):
    path=e['queueModelPath']; toks=[]
    for seg in re.split(r'[/\\]',path):
        x=re.sub(r'\.(?:prefab|fbx)$','',seg,flags=re.I)
        if x.lower().startswith('a_hero_'):
            x=re.sub(r'_(?:city|battle|pve|world|pbr_zhanshi|zhanshi)$','',x,flags=re.I)
            toks.append(norm(x))
    m=re.search(r'/Soldier/([^/]+)/',path,re.I)
    if m:toks.extend([norm(m.group(1)),'a_hero_'+norm(m.group(1))])
    # Parent token often carries the stable model family (Audie, Tesla, Tom...).
    toks=sorted(set(x for x in toks if len(x)>=5),key=len,reverse=True)
    return toks

def model_core(tok):
    s=norm(tok)
    s=re.sub(r'^a_hero_','',s)
    s=re.sub(r'_(?:0?1|0?2|0?3|0?4|city|world|battle|pve)$','',s)
    return s

targets=[]
for e in entries:
    toks=identity_tokens(e)
    targets.append({**e,'tokens':toks,'cores':sorted(set(model_core(x) for x in toks if model_core(x)),key=len,reverse=True),'candidates':[]})

GEOM_MARKERS=(b'MeshRenderer',b'SkinnedMeshRenderer',b'MeshFilter',b'PPtr<Mesh>',b'm_Mesh')
WRAPPER_MARKERS=(b'WorldMonster',b'UIWorldLabel',b'SoftReferencePrefab',b'SuperTextMesh',b'AsyncPrefabPaths')
MODEL_TERMS=(b'wheel',b'chassis',b'turret',b'track',b'lvdai',b'body',b'car',b'vehicle',b'rotor',b'missile',b'launcher',b'low_skin')
EFFECT_TERMS=(b'particle',b'vfx',b'effect',b'eff_',b'bullet',b'projectile',b'smoke')

stats={'bundlesScanned':0,'bundlesDecoded':0,'errors':0,'oversize':0,'geometryBundles':0}
all_raw={}
with zipfile.ZipFile(apk) as z, z.open(info) as f:
    total=info.file_size
    while f.tell()<total:
        start=f.tell();sig=f.read(8)
        if not sig:break
        if not sig.startswith(b'UnityFS'):
            buf=sig+f.read(min(2*1024*1024,total-f.tell()))
            q=buf.find(b'UnityFS\0')
            if q<0:continue
            start+=q;f.seek(start)
        stats['bundlesScanned']+=1
        try:
            size,nodes,blob,uver,urev=decode_bundle(f,start,total);stats['bundlesDecoded']+=1
        except OverflowError:
            stats['oversize']+=1;f.seek(min(total,start+16));continue
        except Exception:
            stats['errors']+=1;f.seek(min(total,start+16));continue
        low=blob.lower();nodeblob=' '.join(n[3] for n in nodes).lower().encode('utf-8','ignore')
        merged=low+b' '+nodeblob
        geom=sum(1 for x in GEOM_MARKERS if x.lower() in merged)
        if geom:stats['geometryBundles']+=1
        if not geom:
            f.seek(start+size);continue
        wrapper=sum(1 for x in WRAPPER_MARKERS if x.lower() in merged)
        model=sum(1 for x in MODEL_TERMS if x.lower() in merged)
        effect=sum(1 for x in EFFECT_TERMS if x.lower() in merged)
        for t in targets:
            hits=[]
            for tok in t['tokens']:
                if flat(tok).encode() in re.sub(rb'[^a-z0-9]+',b'',merged):hits.append(tok)
            if not hits:
                # Stable core fallback requires an actual A_Hero-ish string nearby.
                if b'a_hero_' not in merged:continue
                mflat=re.sub(rb'[^a-z0-9]+',b'',merged)
                for core in t['cores']:
                    if len(core)>=4 and flat(core).encode() in mflat:hits.append(core)
            if not hits:continue
            # Score true renderable geometry; wrappers/effects are explicitly rejected.
            score=geom*2600 + model*550 - wrapper*5000 - effect*1800
            # Exact identity/root names are stronger than mere core names.
            score += sum(2200+len(x)*30 for x in hits if norm(x).startswith('a_hero_'))
            score += sum(600+len(x)*10 for x in hits if not norm(x).startswith('a_hero_'))
            # Bundle size is weak evidence: tiny CABs are usually manifests/wrappers.
            if len(blob)>=30000:score+=900
            if len(blob)>=100000:score+=600
            if b'assetbundle' in low:score+=100
            t['candidates'].append({
              'offset':start,'bytes':size,'decodedBytes':len(blob),'score':score,
              'geometryMarkerCount':geom,'modelMarkerCount':model,'wrapperMarkerCount':wrapper,
              'effectMarkerCount':effect,'identityHits':sorted(set(hits)),
              'nodes':[n[3] for n in nodes[:20]],'unityVersion':uver,'unityRevision':urev
            })
        f.seek(start+size)

# Select top candidates first, then materialize only a compact set for UnityPy inspection.
for t in targets:
    t['candidates'].sort(key=lambda x:(x['score'],x['decodedBytes']),reverse=True)
    t['candidates']=t['candidates'][:12]

wanted_offsets=sorted(set(c['offset'] for t in targets for c in t['candidates'][:4] if c['score']>0))
with zipfile.ZipFile(apk) as z, z.open(info) as f:
    total=info.file_size
    for off in wanted_offsets:
        try:
            size,nodes,blob,uver,urev=decode_bundle(f,off,total)
            f.seek(off);raw=f.read(size)
            all_raw[off]=raw
        except Exception:pass

# Put each hero's top four raw bundles in a private local directory, then let UnityPy
# inspect actual object types/names. This is the decisive geometry evidence.
def safe(v):return re.sub(r'[^A-Za-z0-9_.-]+','_',str(v))
rows=[]
for t in targets:
    hdir=local/f"{t['heroId']}_{safe(t['name'])}";hdir.mkdir(parents=True,exist_ok=True)
    chosen=[]
    for i,c in enumerate(t['candidates'][:4]):
        raw=all_raw.get(c['offset'])
        if not raw:continue
        p=hdir/f"candidate_{i+1}_{c['offset']}_{c['bytes']}.bundle";p.write_bytes(raw)
        chosen.append((c,p))
    inspected=[]
    for c,p in chosen:
        item={**c,'file':p.name,'objectCounts':{},'gameObjects':[],'meshes':[],'renderers':[],'animationClips':[],'materials':[],'textures':[],'parseError':None}
        try:
            UnityPy.config.FALLBACK_UNITY_VERSION=unity_ver
            env=UnityPy.load(str(p))
            counts={}
            for obj in env.objects:
                typ=getattr(obj.type,'name',str(obj.type));counts[typ]=counts.get(typ,0)+1
                if typ not in ('GameObject','Mesh','MeshRenderer','SkinnedMeshRenderer','MeshFilter','AnimationClip','Animator','Material','Texture2D'):continue
                try:d=obj.read()
                except Exception:continue
                nm=str(getattr(d,'m_Name','') or getattr(d,'name','') or '')
                if typ=='GameObject' and nm:item['gameObjects'].append(nm)
                elif typ=='Mesh' and nm:item['meshes'].append(nm)
                elif typ in ('MeshRenderer','SkinnedMeshRenderer','MeshFilter'):
                    try:
                        go=getattr(d,'m_GameObject',None);gd=go.read() if go else None;gn=str(getattr(gd,'m_Name','') or '')
                    except Exception:gn=''
                    item['renderers'].append(gn or nm or typ)
                elif typ=='AnimationClip' and nm:item['animationClips'].append(nm)
                elif typ=='Material' and nm:item['materials'].append(nm)
                elif typ=='Texture2D' and nm:item['textures'].append(nm)
            item['objectCounts']=counts
        except Exception as ex:item['parseError']=repr(ex)
        for k in ('gameObjects','meshes','renderers','animationClips','materials','textures'):
            item[k]=list(dict.fromkeys(item[k]))[:80]
        # Final score now rewards real Unity scene objects and penalizes wrappers again.
        sceneScore=item['score']
        sceneScore+=len(item['meshes'])*1200+len(item['renderers'])*700+len(item['gameObjects'])*80
        names=' '.join(item['gameObjects']+item['meshes']+item['renderers']).lower()
        if 'worldmonster' in names:sceneScore-=10000
        if 'uiworldlabel' in names:sceneScore-=10000
        coreEvidence=sum(1 for core in t['cores'] if core and core in norm(names))
        sceneScore+=coreEvidence*2500
        item['sceneScore']=sceneScore
        inspected.append(item)
    inspected.sort(key=lambda x:(x['sceneScore'],len(x['meshes']),len(x['renderers'])),reverse=True)
    selected=inspected[0] if inspected else None
    confidence='none'
    if selected:
        if selected['parseError'] is None and selected['meshes'] and selected['renderers'] and selected['wrapperMarkerCount']==0:confidence='high'
        elif selected['parseError'] is None and (selected['meshes'] or selected['renderers']) and selected['wrapperMarkerCount']==0:confidence='medium'
        else:confidence='low'
    rows.append({
      'heroId':t['heroId'],'name':t['name'],'formationKind':t['formationKind'],'queueModelPath':t['queueModelPath'],
      'identityTokens':t['tokens'],'confidence':confidence,'selected':selected,'alternates':inspected[1:4]
    })
    if selected:
        print(f"SCENE {t['heroId']} {t['name']}: confidence={confidence} meshes={len(selected['meshes'])} renderers={len(selected['renderers'])} gameObjects={len(selected['gameObjects'])} wrappers={selected['wrapperMarkerCount']} file={selected['file']}")
    else:print(f"SCENE {t['heroId']} {t['name']}: UNRESOLVED")

out={
 'format':'WFGG_LASTWAR_RENDERABLE_FORMATION_SCENES_31_V1','networkUsed':False,'unityFallback':unity_ver,
 'sourceMap':'lastwar-hero-formation-unit-authoritative-map.js','fragment':{'apk':os.path.basename(apk),'entry':ENTRY,'bytes':info.file_size},
 'stats':stats,'rows':rows
}
out['selectedCount']=sum(1 for x in rows if x['selected'])
out['highCount']=sum(1 for x in rows if x['confidence']=='high')
out['mediumOrHighCount']=sum(1 for x in rows if x['confidence'] in ('high','medium'))
out['unresolvedHeroIds']=[x['heroId'] for x in rows if not x['selected']]
outp.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')

lines=[
 'WfGg Last War LAB — PHASE 43 RENDERABLE FORMATION SCENES 31',
 'OFFLINE ONLY · geometry-first selection · wrappers rejected',
 f"selected={out['selectedCount']}/31 high={out['highCount']}/31 mediumOrHigh={out['mediumOrHighCount']}/31",
 f"bundlesScanned={stats['bundlesScanned']} bundlesDecoded={stats['bundlesDecoded']} geometryBundles={stats['geometryBundles']} errors={stats['errors']}",''
]
for x in rows:
    lines.append(f"HERO {x['heroId']} {x['name']} kind={x['formationKind']} confidence={x['confidence']}")
    lines.append('  queue_model_path='+x['queueModelPath'])
    s=x['selected']
    if s:
        lines.append(f"  SELECT offset={s['offset']} bytes={s['bytes']} decoded={s['decodedBytes']} score={s['sceneScore']} wrappers={s['wrapperMarkerCount']} effects={s['effectMarkerCount']} file={s['file']}")
        lines.append('  gameObjects='+(','.join(s['gameObjects'][:20]) or '-'))
        lines.append('  meshes='+(','.join(s['meshes'][:20]) or '-'))
        lines.append('  renderers='+(','.join(s['renderers'][:20]) or '-'))
        lines.append('  animationClips='+(','.join(s['animationClips'][:12]) or '-'))
        lines.append('  objectCounts='+json.dumps(s['objectCounts'],ensure_ascii=False,sort_keys=True))
    lines.append('')
lines.append('unresolvedHeroIds='+','.join(map(str,out['unresolvedHeroIds'])))
reportp.write_text('\n'.join(lines)+'\n',encoding='utf-8')
print('PHASE43_OK',f"selected={out['selectedCount']}/31",f"high={out['highCount']}/31",f"mediumOrHigh={out['mediumOrHighCount']}/31",f"unresolved={len(out['unresolvedHeroIds'])}")
PYEOF

python "$PY" "$MAP" "$OUT" "$LOCAL" "$REPORT" "$UNITY_VERSION" "${APK_PATHS[@]}"
rm -f "$PY"

# Package selected candidate bundles with Python only. Raw authentic bundles stay out of Git.
rm -f "$PACK" "$PACK.sha256"
python - "$LOCAL" "$PACK" <<'PYZIP'
from pathlib import Path
import sys,zipfile
src=Path(sys.argv[1]);dst=Path(sys.argv[2]);files=sorted(src.rglob('*.bundle'))
with zipfile.ZipFile(dst,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
    for f in files:z.write(f,arcname=str(f.relative_to(src)))
print(f"PHASE43_PACK_OK files={len(files)} bytes={dst.stat().st_size}")
PYZIP
sha256sum "$PACK" > "$PACK.sha256"

find "$LOCAL" -type f ! -name '.gitignore' -delete || true
find "$LOCAL" -type d -empty -delete || true
mkdir -p "$LOCAL"
printf '*\n!.gitignore\n' > "$LOCAL/.gitignore"

git add -f frontend/lab/master-assets-v2/meta/formation-renderable-scene-selection-31.json scripts/lastwar-phase43-renderable-scene-select-31.sh
if git diff --cached --quiet -- frontend/lab/master-assets-v2/meta/formation-renderable-scene-selection-31.json scripts/lastwar-phase43-renderable-scene-select-31.sh; then
  echo "Aucun changement à committer."
else
  git commit -m "lab: select authentic renderable formation scenes for all 31 heroes"
fi
git push origin "$BRANCH"

echo "=== PHASE 43 TERMINEE ==="
echo "Rapport: $REPORT"
echo "Bundles candidats: $PACK"
echo "SHA256: $PACK.sha256"
echo "Ne lance pas encore la page Escouades."
echo "main non modifiée."
