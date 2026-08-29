#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — PHASE 52
# VERIFY EXACT MECANIM WRAPPER + AVATAR HASH RESOLUTION FOR CURRENT 15
# CODE ONLY · OFFLINE ONLY · exact Phase47 bundles + exact Phase50 clip dumps.
# No fuzzy matching, no generated motion, no Last War network.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
UNITY_VERSION="2019.4.41f1"
P47="$ROOT/frontend/lab/master-assets-v2/meta/current15-exact-bundle-stage.json"
P50="$ROOT/frontend/lab/master-assets-v2/meta/current15-rig-idle-structure-v1.json"
SRC="$ROOT/frontend/lab/local_assets/lastwar-current15-exact-v1"
CLIPS="$ROOT/frontend/lab/local_assets/lastwar-current15-rig-idle-v1"
OUT="$ROOT/frontend/lab/local_assets/lastwar-current15-phase52-probe-v1"
MANIFEST="$ROOT/frontend/lab/master-assets-v2/meta/current15-phase52-mecanim-avatar-probe-v1.json"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_PHASE52_MECANIM_AVATAR_PROBE.txt"
PY="${TMPDIR:-$HOME/.cache}/wfgg-phase52-mecanim-avatar-probe.py"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche active incorrecte"
[[ -s "$P47" ]] || fail "Phase47 absente: $P47"
[[ -s "$P50" ]] || fail "Phase50 absente: $P50"
[[ -d "$SRC" ]] || fail "bundles locaux Phase47 absents: $SRC"
[[ -d "$CLIPS" ]] || fail "dumps locaux Phase50 absents: $CLIPS"
command -v python >/dev/null 2>&1 || fail "python absent"
python - <<'PY' >/dev/null 2>&1 || fail "UnityPy absent"
import UnityPy
PY

rm -rf "$OUT"
mkdir -p "$OUT" "$(dirname "$MANIFEST")" "$(dirname "$REPORT")" "$(dirname "$PY")"

cat > "$PY" <<'PYEOF'
from __future__ import annotations
from pathlib import Path
from collections import defaultdict
import gzip, json, re, sys, zlib

p47p=Path(sys.argv[1]); p50p=Path(sys.argv[2]); src=Path(sys.argv[3]); clipsroot=Path(sys.argv[4]); outroot=Path(sys.argv[5]); manifestp=Path(sys.argv[6]); reportp=Path(sys.argv[7]); unity_version=sys.argv[8]

import UnityPy
UnityPy.config.FALLBACK_UNITY_VERSION=unity_version
p47=json.loads(p47p.read_text(encoding='utf-8'))
p50=json.loads(p50p.read_text(encoding='utf-8'))
heroes=p47.get('heroes') or []
p50by={int(x['heroId']):x for x in (p50.get('heroes') or [])}
if len(heroes)!=15 or len(p50by)!=15: raise SystemExit('expected 15 heroes in Phase47 and Phase50')

def tn(r):
    try:return r.type.name
    except Exception:return str(getattr(r,'type',''))

def ro(r):
    try:return r.read()
    except Exception:
        try:return r.parse_as_object()
        except Exception:return None

def po(ptr):
    if ptr is None:return None
    for fn in ('read','deref_parse_as_object','parse_as_object'):
        try:
            f=getattr(ptr,fn,None)
            if callable(f):return f()
        except Exception:pass
    return None

def name(o):
    if o is None:return ''
    return str(getattr(o,'m_Name','') or getattr(o,'name','') or '')

def getv(d,*names,default=None):
    if not isinstance(d,dict): return default
    for n in names:
        if n in d:return d[n]
    norm={re.sub(r'[^a-z0-9]','',str(k).lower().removeprefix('m_')):k for k in d}
    for n in names:
        q=re.sub(r'[^a-z0-9]','',str(n).lower().removeprefix('m_'))
        if q in norm:return d[norm[q]]
    return default

def scalar(v,default=0):
    seen=set()
    while isinstance(v,dict) and id(v) not in seen:
        seen.add(id(v))
        moved=False
        for k in ('data','value','m_Value','first','m_First'):
            if k in v and not isinstance(v[k],(dict,list)):
                v=v[k];moved=True;break
        if not moved:break
    if isinstance(v,bool):return int(v)
    if isinstance(v,(int,float)):return int(v)
    s=str(v or '')
    sl=s.lower()
    if 'skinnedmeshrenderer' in sl:return 137
    if sl.endswith('transform') or sl=='transform':return 4
    m=re.search(r'-?\d+',s)
    return int(m.group()) if m else default

def crc(s):return zlib.crc32(str(s).encode('utf-8')) & 0xffffffff

def reader_key(o):
    r=getattr(o,'object_reader',None)
    if r is None:return ('py',id(o))
    try:pid=int(getattr(r,'path_id'))
    except Exception:pid=id(o)
    try:fn=str(getattr(getattr(r,'assets_file',None),'name','') or '')
    except Exception:fn=''
    return (fn,pid)

def transform_crc_map(readers):
    ts=[]
    for r in readers:
        if tn(r) not in ('Transform','RectTransform'):continue
        o=ro(r)
        if o is not None:ts.append(o)
    cache={};vis=set()
    def go(t):
        k=reader_key(t)
        if k in cache:return cache[k]
        if k in vis:return name(po(getattr(t,'m_GameObject',None)))
        vis.add(k)
        nm=name(po(getattr(t,'m_GameObject',None)))
        f=po(getattr(t,'m_Father',None))
        pp=go(f) if f is not None else ''
        p=(pp+'/'+nm) if pp and nm else (pp or nm)
        vis.discard(k);cache[k]=p
        return p
    paths=sorted(set(filter(None,(go(t) for t in ts))))
    hm=defaultdict(set)
    for p in paths:
        parts=p.split('/')
        for i in range(len(parts)):
            rel='/'.join(parts[i:])
            hm[crc(rel)].add(rel)
    return paths,hm

def parse_dict(r):
    try:return r.parse_as_dict(check_read=False)
    except Exception:
        try:return r.parse_as_dict()
        except Exception:return None

def uint_string_pairs(x,out=None,depth=0):
    if out is None:out={}
    if depth>14:return out
    if isinstance(x,dict):
        # Common Unity map representations: {first: uint, second: str} or direct uint->str.
        lower={str(k).lower():k for k in x}
        fk=lower.get('first') or lower.get('m_first')
        sk=lower.get('second') or lower.get('m_second')
        if fk is not None and sk is not None:
            a=x[fk];b=x[sk]
            if isinstance(a,(int,float)) and isinstance(b,str):out[int(a)&0xffffffff]=b
        for k,v in x.items():
            try:
                ki=int(k)
                if isinstance(v,str):out[ki&0xffffffff]=v
            except Exception:pass
            uint_string_pairs(v,out,depth+1)
    elif isinstance(x,list):
        for v in x:uint_string_pairs(v,out,depth+1)
    return out

def avatar_map(readers):
    out={}; avatars=0
    for r in readers:
        if tn(r)!='Avatar':continue
        avatars+=1
        d=parse_dict(r)
        if d is not None:
            tos=getv(d,'m_TOS','TOS',default=d)
            out.update(uint_string_pairs(tos))
        o=ro(r)
        if o is not None:
            tos=getattr(o,'m_TOS',None)
            try:
                if hasattr(tos,'items'):
                    for k,v in tos.items():out[int(k)&0xffffffff]=str(v)
            except Exception:pass
    return avatars,out

def find_binding_list(bc):
    cand=[]
    def walk(x,path='',depth=0):
        if depth>12:return
        if isinstance(x,dict):
            for k,v in x.items():walk(v,(path+'.'+str(k)).strip('.'),depth+1)
        elif isinstance(x,list):
            if x and all(isinstance(y,dict) for y in x[:min(8,len(x))]):
                score=0
                for y in x[:min(8,len(x))]:
                    ks=' '.join(str(k).lower() for k in y)
                    score+=int('path' in ks)+int('attribute' in ks)+int('type' in ks)
                if score>=3:cand.append((score,len(x),path,x))
            for y in x[:3]:
                if isinstance(y,(dict,list)):walk(y,path+'[]',depth+1)
    walk(bc)
    if not cand:return [],None
    cand.sort(key=lambda z:(z[0],z[1]),reverse=True)
    return cand[0][3],cand[0][2]

def binding_rows(tree):
    bc=getv(tree,'m_ClipBindingConstant','ClipBindingConstant',default={}) or {}
    arr,where=find_binding_list(bc)
    rows=[]
    for b in arr:
        ph=scalar(getv(b,'path','m_Path',default=0),0)&0xffffffff
        ty=scalar(getv(b,'typeID','typeId','m_TypeID','type',default=0),0)
        at=scalar(getv(b,'attribute','m_Attribute',default=0),0)&0xffffffff
        rows.append((ph,ty,at))
    return rows,where

def compact_counts(tree):
    muscle=getv(tree,'m_MuscleClip','MuscleClip',default={}) or {}
    clip=getv(muscle,'m_Clip','Clip',default={}) or {}
    data=getv(clip,'data','m_Data',default=clip) or {}
    st=getv(data,'m_StreamedClip','StreamedClip',default={}) or {}
    de=getv(data,'m_DenseClip','DenseClip',default={}) or {}
    co=getv(data,'m_ConstantClip','ConstantClip',default={}) or {}
    sd=getv(st,'data','m_Data',default=[]) or []
    sc=scalar(getv(st,'curveCount','m_CurveCount',default=0),0)
    df=scalar(getv(de,'m_FrameCount','FrameCount',default=0),0)
    dc=scalar(getv(de,'m_CurveCount','CurveCount',default=0),0)
    ds=getv(de,'m_SampleArray','SampleArray',default=[]) or []
    cd=getv(co,'data','m_Data',default=[]) or []
    return {'streamWords':len(sd),'streamCurves':sc,'denseFrames':df,'denseCurves':dc,'denseSamples':len(ds),'constantSamples':len(cd),'nonzero':bool(len(sd)>2 or sc or dc or len(ds) or len(cd))}

def load_clip_json(hid,cf):
    p=clipsroot/str(hid)/str(cf)
    if not p.is_file():return None,str(p)
    try:
        with gzip.open(p,'rt',encoding='utf-8') as f:return json.load(f),str(p)
    except Exception as e:return None,f'{p}: {e!r}'

rows=[]; total_clips=0; nonzero_clips=0; total_tb=0; resolved_transform=0; via_transform=0; via_avatar=0
for n,h in enumerate(heroes,1):
    hid=int(h['heroId']); nm=h.get('name') or str(hid); h50=p50by[hid]
    print(f'PHASE52_HERO {n}/15 id={hid} name={nm}',flush=True)
    files=sorted((src/str(hid)).glob('*.bundle'))
    env=UnityPy.load(*[str(p) for p in files])
    readers=list(env.objects)
    paths,hmap=transform_crc_map(readers)
    acount,amap=avatar_map(readers)
    hr={'heroId':hid,'name':nm,'transformPaths':len(paths),'transformHashCount':len(hmap),'avatarObjects':acount,'avatarHashCount':len(amap),'clips':[]}
    for cs in h50.get('clipStructures') or []:
        tree,pth=load_clip_json(hid,cs.get('file'))
        cr={'name':cs.get('name'),'kind':cs.get('kind'),'file':cs.get('file'),'loaded':tree is not None}
        total_clips+=1
        if tree is None:
            cr['error']=pth;hr['clips'].append(cr);continue
        counts=compact_counts(tree);cr.update(counts)
        if counts['nonzero']:nonzero_clips+=1
        binds,where=binding_rows(tree);cr['bindingContainer']=where;cr['bindingCount']=len(binds)
        tbind=[x for x in binds if x[1]==4]; cr['transformBindingCount']=len(tbind);total_tb+=len(tbind)
        r=0;rt=0;ra=0;sample=[]
        for ph,ty,at in tbind:
            hp=sorted(hmap.get(ph,set()))
            av=amap.get(ph)
            how=None;val=None
            if len(hp)==1:how='transform-crc';val=hp[0];rt+=1
            elif av:how='avatar-tos';val=av;ra+=1
            if how:r+=1
            if len(sample)<8:sample.append({'hash':ph,'attribute':at,'resolved':val,'via':how})
        cr['resolvedTransformBindings']=r;cr['resolvedViaTransformCRC']=rt;cr['resolvedViaAvatarTOS']=ra;cr['sampleTransformBindings']=sample
        resolved_transform+=r;via_transform+=rt;via_avatar+=ra
        hr['clips'].append(cr)
    rows.append(hr)

manifest={
 'format':'WFGG_LASTWAR_PHASE52_MECANIM_AVATAR_PROBE_V1','networkUsed':False,'unityFallback':unity_version,
 'heroCount':len(rows),'clipCount':total_clips,'compactNonzeroClips':nonzero_clips,
 'transformBindingCount':total_tb,'resolvedTransformBindings':resolved_transform,
 'resolvedViaTransformCRC':via_transform,'resolvedViaAvatarTOS':via_avatar,'heroes':rows,
 'guardrails':{'exactPhase47BundlesOnly':True,'exactPhase50ClipDumpsOnly':True,'mMuscleClipDataWrapperRequired':True,'avatarTOSExactHashFallback':True,'noFuzzyPathMatching':True,'noGeneratedMotion':True,'noLastWarNetwork':True}
}
manifestp.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
lines=[]
lines.append('WfGg Last War LAB — PHASE 52 MECANIM WRAPPER + AVATAR HASH PROBE')
lines.append('OFFLINE ONLY · exact Phase47 bundles · exact Phase50 clip dumps · no generated motion')
lines.append(f'heroes={len(rows)} clips={total_clips} compactNonzero={nonzero_clips}/{total_clips}')
lines.append(f'transformBindings={resolved_transform}/{total_tb} viaTransformCRC={via_transform} viaAvatarTOS={via_avatar}')
lines.append('')
for h in rows:
    lines.append(f"HERO {h['heroId']} {h['name']} transformPaths={h['transformPaths']} transformHashes={h['transformHashCount']} avatars={h['avatarObjects']} avatarHashes={h['avatarHashCount']}")
    for c in h['clips']:
        if not c.get('loaded'):
            lines.append(f"  CLIP {c.get('kind')} {c.get('name')} loaded=False error={c.get('error')}")
            continue
        lines.append(f"  CLIP {c.get('kind')} {c.get('name')} compact={c.get('nonzero')} stream={c.get('streamCurves')}c/{c.get('streamWords')}w dense={c.get('denseCurves')}c/{c.get('denseFrames')}f/{c.get('denseSamples')}s constant={c.get('constantSamples')} bindings={c.get('resolvedTransformBindings')}/{c.get('transformBindingCount')} crc={c.get('resolvedViaTransformCRC')} avatar={c.get('resolvedViaAvatarTOS')}")
        for s in c.get('sampleTransformBindings') or []:
            lines.append(f"    HASH {s['hash']} attr={s['attribute']} via={s['via'] or '-'} path={s['resolved'] or '-'}")
    lines.append('')
lines += ['GUARDRAILS','  exact_phase47_bundles_only=true','  exact_phase50_clip_dumps_only=true','  m_muscleclip_clip_data_wrapper=true','  avatar_tos_exact_hash_fallback=true','  no_fuzzy_path_matching=true','  no_generated_motion=true','  no_lastwar_network=true']
reportp.write_text('\n'.join(lines)+'\n',encoding='utf-8')
print(f"PHASE52_OK compactNonzero={nonzero_clips}/{total_clips} transformBindings={resolved_transform}/{total_tb} viaCRC={via_transform} viaAvatar={via_avatar}")
print(f'PHASE52_DONE report={reportp}')
PYEOF

python "$PY" "$P47" "$P50" "$SRC" "$CLIPS" "$OUT" "$MANIFEST" "$REPORT" "$UNITY_VERSION"

git add "$MANIFEST"
if ! git diff --cached --quiet; then
  git commit -m "lab: record Phase52 Mecanim wrapper and Avatar hash probe"
  git push origin "$BRANCH"
fi

printf 'PHASE52_DONE report=%s\n' "$REPORT"
