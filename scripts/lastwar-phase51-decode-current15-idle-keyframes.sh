#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — PHASE 51
# DECODE EXACT CURRENT-15 MECANIM IDLE / SHOW_IDLE KEYFRAMES
# CODE ONLY · OFFLINE ONLY · exact Phase47 bundles only.
#
# Phase50 established that all 15 current units contain authentic Mecanim clip
# structures. This phase decodes Unity 2019 StreamedClip + DenseClip +
# ConstantClip samples and maps Transform bindings to exact hierarchy paths via
# Unity CRC32 hashes. It never substitutes an animation, never generates motion,
# and never contacts Last War.
#
# Important: lack of MeshHandler skin weights is NOT treated as a missing model.
# When authentic Transform tracks exist, a vehicle can be animated as a rigid
# hierarchy even if the renderer does not expose vertex skin weights.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
UNITY_VERSION="2019.4.41f1"
P47="$ROOT/frontend/lab/master-assets-v2/meta/current15-exact-bundle-stage.json"
P50="$ROOT/frontend/lab/master-assets-v2/meta/current15-rig-idle-structure-v1.json"
SRC="$ROOT/frontend/lab/local_assets/lastwar-current15-exact-v1"
OUT="$ROOT/frontend/lab/local_assets/lastwar-current15-animation-v1"
MANIFEST="$ROOT/frontend/lab/master-assets-v2/meta/current15-idle-keyframes-v1.json"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_PHASE51_CURRENT15_IDLE_KEYFRAMES.txt"
PY="${TMPDIR:-$HOME/.cache}/wfgg-phase51-idle-keyframes.py"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche active incorrecte"
[[ -s "$P47" ]] || fail "Phase47 absente: $P47"
[[ -s "$P50" ]] || fail "Phase50 absente: $P50"
[[ -d "$SRC" ]] || fail "bundles locaux Phase47 absents: $SRC"
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
import gzip, hashlib, json, math, os, re, struct, sys, traceback, zlib

p47p=Path(sys.argv[1]); p50p=Path(sys.argv[2]); src=Path(sys.argv[3]); outroot=Path(sys.argv[4]); manifestp=Path(sys.argv[5]); reportp=Path(sys.argv[6]); unity_version=sys.argv[7]

p47=json.loads(p47p.read_text(encoding='utf-8'))
p50=json.loads(p50p.read_text(encoding='utf-8'))
heroes=p47.get('heroes') or []
phase50_by_id={int(x['heroId']):x for x in (p50.get('heroes') or [])}
if len(heroes)!=15: raise SystemExit(f'expected 15 Phase47 heroes, got {len(heroes)}')
if len(phase50_by_id)!=15: raise SystemExit(f'expected 15 Phase50 heroes, got {len(phase50_by_id)}')

try:
    import UnityPy
except Exception as e:
    raise SystemExit(f'UnityPy core import failed: {e!r}')
UnityPy.config.FALLBACK_UNITY_VERSION=unity_version

SAFE=re.compile(r'[^A-Za-z0-9._-]+')
def safe(s,fallback='asset'):
    x=SAFE.sub('_',str(s or '')).strip('._')
    return x[:180] or fallback

def type_name(r):
    try:return r.type.name
    except Exception:return str(getattr(r,'type',''))

def read_obj(r):
    try:return r.read()
    except Exception:
        try:return r.parse_as_object()
        except Exception:return None

def obj_name(d,fallback=''):
    if d is None:return str(fallback or '')
    return str(getattr(d,'m_Name','') or getattr(d,'name','') or fallback or '')

def reader_key_from_obj(d):
    r=getattr(d,'object_reader',None)
    if r is None:return None
    try:fn=str(getattr(getattr(r,'assets_file',None),'name','') or '')
    except Exception:fn=''
    try:pid=int(getattr(r,'path_id'))
    except Exception:return None
    return (fn,pid)

def ptr_obj(ptr):
    if ptr is None:return None
    for fn in ('read','deref_parse_as_object','parse_as_object'):
        try:
            f=getattr(ptr,fn,None)
            if callable(f):return f()
        except Exception:pass
    return None

def getv(d,*names,default=None):
    if not isinstance(d,dict):return default
    for n in names:
        if n in d:return d[n]
    normalized={re.sub(r'[^a-z0-9]','',str(k).lower().removeprefix('m_')):k for k in d.keys()}
    for n in names:
        nn=re.sub(r'[^a-z0-9]','',str(n).lower().removeprefix('m_'))
        if nn in normalized:return d[normalized[nn]]
    return default

def to_int(v,default=0):
    if isinstance(v,bool):return int(v)
    if isinstance(v,(int,float)):return int(v)
    s=str(v or '').strip()
    sl=s.lower()
    if 'skinnedmeshrenderer' in sl:return 137
    if sl.endswith('transform') or sl=='transform':return 4
    m=re.search(r'-?\d+',s)
    return int(m.group()) if m else default

def to_float(v,default=0.0):
    try:return float(v)
    except Exception:return default

def crc32_utf8(s):
    return zlib.crc32(str(s).encode('utf-8')) & 0xffffffff

def write_gz_json(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    raw=json.dumps(obj,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode('utf-8')
    with gzip.open(path,'wb',compresslevel=6) as f:f.write(raw)
    h=hashlib.sha256(path.read_bytes()).hexdigest()
    return len(raw),path.stat().st_size,h

def finite(v):
    if isinstance(v,float) and not math.isfinite(v):return 0.0
    return v

def clean_values(vals):
    return [finite(float(x)) for x in vals]

def clip_kind(name):
    n=str(name or '').lower().replace(' ','')
    if 'show_idle' in n or 'showidle' in n:return 'presentationIdle'
    if n.endswith('_idle') or n.endswith('idle') or '_idle_' in n:return 'idle'
    return None

# -------------------- exact hierarchy / CRC path resolution -----------------
def build_transform_paths(readers, expected_root):
    transform_objs=[]
    for r in readers:
        if type_name(r) not in ('Transform','RectTransform'):continue
        d=read_obj(r)
        if d is not None:transform_objs.append(d)

    cache={}; visiting=set()
    def go_name_from_transform(t):
        try:return obj_name(ptr_obj(getattr(t,'m_GameObject',None)))
        except Exception:return ''
    def path_for(t):
        if t is None:return ''
        k=reader_key_from_obj(t) or ('py',id(t))
        if k in cache:return cache[k]
        if k in visiting:return go_name_from_transform(t)
        visiting.add(k)
        nm=go_name_from_transform(t)
        father=ptr_obj(getattr(t,'m_Father',None))
        if father is not None:
            pp=path_for(father)
            p=(pp+'/'+nm) if pp and nm else (pp or nm)
        else:p=nm
        visiting.discard(k);cache[k]=p
        return p

    full_paths=[]
    for t in transform_objs:
        p=path_for(t)
        if p:full_paths.append(p)
    full_paths=sorted(set(full_paths))

    # Unity animation paths can be stored relative to an Animator root. Every
    # candidate below is still an exact suffix of a real Transform path; no fuzzy
    # text matching is used. A hash resolves only when it identifies one real
    # Transform unambiguously.
    hash_candidates=defaultdict(set)
    source_candidates=defaultdict(set)
    for p in full_paths:
        parts=p.split('/')
        for i in range(len(parts)):
            rel='/'.join(parts[i:])
            h=crc32_utf8(rel)
            hash_candidates[h].add(p)
            source_candidates[(h,p)].add('full' if i==0 else 'suffix')

    expected_paths=[p for p in full_paths if p.split('/')[-1]==expected_root]
    exact_root=expected_paths[0] if len(expected_paths)==1 else None

    def resolve(h):
        h=int(h)&0xffffffff
        if h==0 and exact_root:
            return {'hash':h,'path':exact_root,'resolution':'root-zero'}
        vals=sorted(hash_candidates.get(h,set()))
        if len(vals)!=1:return {'hash':h,'path':None,'resolution':'ambiguous' if vals else 'unresolved','candidates':vals[:12]}
        p=vals[0]
        sources=sorted(source_candidates.get((h,p),set()))
        return {'hash':h,'path':p,'resolution':'+'.join(sources) or 'crc32'}
    return full_paths,resolve,exact_root

# -------------------------- binding table -----------------------------------
def find_binding_list(bc):
    candidates=[]
    def walk(x,path='',depth=0):
        if depth>10:return
        if isinstance(x,dict):
            for k,v in x.items():walk(v,(path+'.'+str(k)).strip('.'),depth+1)
        elif isinstance(x,list):
            if x and all(isinstance(y,dict) for y in x[:min(8,len(x))]):
                score=0
                for y in x[:min(8,len(x))]:
                    keys=' '.join(str(k).lower() for k in y.keys())
                    score+=int('path' in keys)+int('attribute' in keys)+int('type' in keys)
                if score>=3:candidates.append((score,len(x),path,x))
            for y in x[:3]:
                if isinstance(y,(dict,list)):walk(y,path+'[]',depth+1)
    walk(bc)
    if not candidates:return [],None
    candidates.sort(key=lambda z:(z[0],z[1]),reverse=True)
    return candidates[0][3],candidates[0][2]

def binding_width(type_id,attr):
    if int(type_id)==4:
        return {1:3,2:4,3:3,4:3}.get(int(attr),1)
    return 1

def parse_bindings(bc,resolve_path):
    arr,container=find_binding_list(bc)
    rows=[];cursor=0
    for i,b in enumerate(arr):
        path_hash=to_int(getv(b,'path','m_Path',default=0),0)&0xffffffff
        attr=to_int(getv(b,'attribute','m_Attribute',default=0),0)&0xffffffff
        type_id=to_int(getv(b,'typeID','typeId','m_TypeID','type',default=0),0)
        width=binding_width(type_id,attr)
        rr=resolve_path(path_hash) if type_id==4 else {'hash':path_hash,'path':None,'resolution':'non-transform'}
        rows.append({
          'ordinal':i,'start':cursor,'end':cursor+width,'width':width,
          'pathHash':path_hash,'attribute':attr,'typeID':type_id,
          'isPPtrCurve':bool(getv(b,'isPPtrCurve','m_IsPPtrCurve',default=False)),
          'isIntCurve':bool(getv(b,'isIntCurve','m_IsIntCurve',default=False)),
          'resolvedPath':rr.get('path'),'pathResolution':rr.get('resolution'),
          'pathCandidates':rr.get('candidates',[]),
        })
        cursor+=width
    return rows,container,cursor

def binding_for_index(rows,index):
    index=int(index)
    # GenericBinding count is small; linear scan preserves source order exactly.
    for b in rows:
        if b['start']<=index<b['end']:return b
    return None

def property_name(b):
    if not b:return 'unknown'
    if b['typeID']!=4:return 'nonTransform'
    return {1:'localPosition',2:'localRotation',3:'localScale',4:'localEuler'}.get(b['attribute'],f'transformAttribute{b["attribute"]}')

def web_values(prop,vals):
    v=clean_values(vals)
    if prop=='localPosition' and len(v)>=3:return [-v[0],v[1],v[2]]
    if prop=='localRotation' and len(v)>=4:return [v[0],-v[1],-v[2],v[3]]
    if prop=='localEuler' and len(v)>=3:return [v[0],-v[1],-v[2]]
    return v

# ------------------------- Mecanim compact data -----------------------------
def parse_streamed(streamed):
    data=getv(streamed,'data','m_Data',default=[]) or []
    curve_count=to_int(getv(streamed,'curveCount','m_CurveCount',default=0),0)
    raw=b''.join(struct.pack('<I',to_int(x,0)&0xffffffff) for x in data)
    frames=[];pos=0;errors=[]
    while pos<len(raw):
        if len(raw)-pos<8:
            errors.append(f'trailingBytes={len(raw)-pos}');break
        time=struct.unpack_from('<f',raw,pos)[0];pos+=4
        count=struct.unpack_from('<i',raw,pos)[0];pos+=4
        if count<0 or count>100000:
            errors.append(f'invalidKeyCount={count} at={pos-4}');break
        need=count*20
        if pos+need>len(raw):
            errors.append(f'truncatedFrame count={count} need={need} remain={len(raw)-pos}');break
        keys=[]
        for _ in range(count):
            index=struct.unpack_from('<i',raw,pos)[0];pos+=4
            coeff=list(struct.unpack_from('<4f',raw,pos));pos+=16
            keys.append({'index':index,'coeff':clean_values(coeff),'value':finite(float(coeff[3]))})
        frames.append({'time':finite(float(time)),'keys':keys})
    return frames,curve_count,len(raw),errors

def decode_clip_tree(tree,resolve_path):
    muscle=getv(tree,'m_MuscleClip','MuscleClip',default={}) or {}
    compact=getv(muscle,'m_Clip','Clip',default={}) or {}
    streamed=getv(compact,'m_StreamedClip','StreamedClip',default={}) or {}
    dense=getv(compact,'m_DenseClip','DenseClip',default={}) or {}
    constant=getv(compact,'m_ConstantClip','ConstantClip',default=None)
    bc=getv(tree,'m_ClipBindingConstant','ClipBindingConstant',default=None)
    if bc is None:
        bc=getv(compact,'m_ClipBindingConstant','ClipBindingConstant',default=None)
    if bc is None:
        raise ValueError('m_ClipBindingConstant absent; no binding synthesis performed')

    bindings,binding_container,total_width=parse_bindings(bc,resolve_path)
    if not bindings:raise ValueError('generic binding table unresolved')

    frames,stream_count,stream_bytes,stream_errors=parse_streamed(streamed)
    dense_frames=to_int(getv(dense,'m_FrameCount','FrameCount',default=0),0)
    dense_count=to_int(getv(dense,'m_CurveCount','CurveCount',default=0),0)
    dense_rate=to_float(getv(dense,'m_SampleRate','SampleRate',default=0.0),0.0)
    dense_begin=to_float(getv(dense,'m_BeginTime','BeginTime',default=0.0),0.0)
    dense_samples=getv(dense,'m_SampleArray','SampleArray',default=[]) or []
    dense_samples=[to_float(x,0.0) for x in dense_samples]
    const_data=[]
    if isinstance(constant,dict):
        const_data=getv(constant,'data','m_Data',default=[]) or []
        const_data=[to_float(x,0.0) for x in const_data]
    stop_time=to_float(getv(muscle,'m_StopTime','StopTime',default=0.0),0.0)

    tracks=defaultdict(lambda:defaultdict(list))
    unresolved_hashes=set(); non_transform_samples=0; emitted=0; component_samples=0

    def emit(binding_index,time,vals,source):
        nonlocal non_transform_samples,emitted,component_samples
        b=binding_for_index(bindings,binding_index)
        if b is None:return 1
        width=b['width']; prop=property_name(b)
        if b['typeID']!=4:
            non_transform_samples+=1
            return width
        if not b.get('resolvedPath'):
            unresolved_hashes.add(b['pathHash'])
            return width
        vv=clean_values(vals[:width])
        if len(vv)<width:return width
        tracks[b['resolvedPath']][prop].append({'time':finite(float(time)),'unity':vv,'web':web_values(prop,vv),'source':source})
        emitted+=1;component_samples+=width
        return width

    # AssetStudio intentionally skips the first/last streamed sentinel frames.
    usable_frames=frames[1:-1] if len(frames)>=3 else []
    streamed_emitted_frames=0
    for fr in usable_frames:
        keys=fr['keys'];values=[k['value'] for k in keys];ci=0;used=False
        while ci<len(keys):
            bidx=keys[ci]['index'];b=binding_for_index(bindings,bidx);width=(b['width'] if b else 1)
            vals=values[ci:ci+width]
            emit(bidx,fr['time'],vals,'streamed')
            ci+=max(1,width);used=True
        if used:streamed_emitted_frames+=1

    dense_emitted_frames=0
    if dense_frames>0 and dense_count>0 and dense_rate>0:
        for fi in range(dense_frames):
            t=dense_begin + fi/dense_rate;off=fi*dense_count;ci=0;used=False
            while ci<dense_count:
                absidx=stream_count+ci;b=binding_for_index(bindings,absidx);width=(b['width'] if b else 1)
                vals=dense_samples[off+ci:off+ci+width]
                emit(absidx,t,vals,'dense')
                ci+=max(1,width);used=True
            if used:dense_emitted_frames+=1

    constant_samples=0
    if const_data:
        for t in (0.0,stop_time):
            ci=0
            while ci<len(const_data):
                absidx=stream_count+dense_count+ci;b=binding_for_index(bindings,absidx);width=(b['width'] if b else 1)
                vals=const_data[ci:ci+width]
                emit(absidx,t,vals,'constant')
                ci+=max(1,width);constant_samples+=1

    out_tracks=[]
    key_count=0
    for path in sorted(tracks):
        props=[]
        for prop in sorted(tracks[path]):
            keys=tracks[path][prop]
            # exact source data may repeat identical times (e.g. stream+dense boundary);
            # preserve every sample instead of silently deduplicating.
            key_count+=len(keys)
            props.append({'property':prop,'keys':keys})
        out_tracks.append({'path':path,'properties':props})

    resolved_transform_bindings=sum(1 for b in bindings if b['typeID']==4 and b.get('resolvedPath'))
    transform_bindings=sum(1 for b in bindings if b['typeID']==4)
    return {
      'sampleRate':to_float(getv(tree,'m_SampleRate','SampleRate',default=0.0),0.0),
      'stopTime':stop_time,
      'bindingContainer':binding_container,'bindingCount':len(bindings),'bindingScalarWidth':total_width,
      'transformBindingCount':transform_bindings,'resolvedTransformBindingCount':resolved_transform_bindings,
      'unresolvedTransformBindingHashes':sorted(unresolved_hashes),
      'bindings':bindings,
      'streamed':{'curveCount':stream_count,'frameCount':len(frames),'usableFrameCount':len(usable_frames),'emittedFrameCount':streamed_emitted_frames,'bytes':stream_bytes,'errors':stream_errors},
      'dense':{'frameCount':dense_frames,'curveCount':dense_count,'sampleRate':dense_rate,'beginTime':dense_begin,'sampleCount':len(dense_samples),'emittedFrameCount':dense_emitted_frames},
      'constant':{'sampleCount':len(const_data),'bindingPassCount':constant_samples},
      'nonTransformSampleGroups':non_transform_samples,'transformSampleGroups':emitted,'transformComponentSamples':component_samples,
      'transformTrackCount':len(out_tracks),'transformKeyCount':key_count,'tracks':out_tracks,
    }

rows=[]
for hi,h in enumerate(heroes,1):
    hid=int(h['heroId']);name=h.get('name') or str(hid);ph50=phase50_by_id[hid]
    hsrc=src/str(hid);hout=outroot/str(hid);hout.mkdir(parents=True,exist_ok=True)
    files=sorted(hsrc.glob('*.bundle'))
    selected=list(ph50.get('selectedClipNames') or [])
    expected_root=Path(str(h.get('queueModelPath') or '')).stem
    row={
      'heroId':hid,'name':name,'queueModelPath':h.get('queueModelPath'),'bundleCount':len(files),'parseOk':False,
      'phase50RigReady':bool(ph50.get('rigReady')),'selectedClipNames':selected,'decodedClipCount':0,'clips':[],
      'transformPathCount':0,'rendererMode':'static','animated':False,'errors':[]
    }
    print(f'PHASE51_HERO {hi}/15 id={hid} name={name} selected={len(selected)}',flush=True)
    try:
        UnityPy.config.FALLBACK_UNITY_VERSION=unity_version
        env=UnityPy.load(*[str(p) for p in files]);readers=list(env.objects);row['parseOk']=True
        full_paths,resolve_path,exact_root=build_transform_paths(readers,expected_root)
        row['transformPathCount']=len(full_paths);row['authoritativeRootPath']=exact_root

        clip_readers=[]
        for r in readers:
            if type_name(r)!='AnimationClip':continue
            d=read_obj(r)
            if d is not None:clip_readers.append((r,obj_name(d,'AnimationClip')))

        for sel in selected:
            exact=[r for r,nm in clip_readers if nm==sel]
            c={'name':sel,'kind':clip_kind(sel),'decoded':False}
            if len(exact)!=1:
                c['error']=f'exact clip match count={len(exact)}';row['clips'].append(c);continue
            r=exact[0]
            try:
                tree=r.parse_as_dict(check_read=False)
                dec=decode_clip_tree(tree,resolve_path)
                fn=('presentation-idle' if c['kind']=='presentationIdle' else 'idle')+'.json.gz'
                payload={'heroId':hid,'name':name,'clipName':sel,'clipKind':c['kind'],'queueModelPath':h.get('queueModelPath'),'authoritativeRootPath':exact_root,**dec}
                rawb,gzb,sha=write_gz_json(hout/fn,payload)
                c.update({'decoded':True,'file':fn,'jsonBytes':rawb,'gzipBytes':gzb,'sha256':sha,
                          'streamedCurves':dec['streamed']['curveCount'],'streamedFrames':dec['streamed']['frameCount'],
                          'denseCurves':dec['dense']['curveCount'],'denseFrames':dec['dense']['frameCount'],
                          'constantSamples':dec['constant']['sampleCount'],'bindingCount':dec['bindingCount'],
                          'transformBindings':dec['transformBindingCount'],'resolvedTransformBindings':dec['resolvedTransformBindingCount'],
                          'unresolvedBindingHashes':dec['unresolvedTransformBindingHashes'],
                          'transformTracks':dec['transformTrackCount'],'transformKeys':dec['transformKeyCount']})
                row['decodedClipCount']+=1
            except Exception as e:
                c['error']=repr(e);c['traceback']=traceback.format_exc()[-6000:]
            row['clips'].append(c)

        total_tracks=sum(int(c.get('transformTracks',0) or 0) for c in row['clips'] if c.get('decoded'))
        total_keys=sum(int(c.get('transformKeys',0) or 0) for c in row['clips'] if c.get('decoded'))
        row['transformTrackCount']=total_tracks;row['transformKeyCount']=total_keys;row['animated']=bool(total_tracks and total_keys)
        if row['animated']:
            row['rendererMode']='skinned+hierarchy' if row['phase50RigReady'] else 'rigidHierarchy'
        elif row['phase50RigReady']:
            row['rendererMode']='skinned-static'
        else:row['rendererMode']='static'
    except Exception as e:
        row['errors'].append(repr(e));row['errors'].append(traceback.format_exc()[-7000:])
    rows.append(row)
    print('PHASE51_HERO_DONE',hid,name,f"decoded={row['decodedClipCount']}/{len(selected)}",f"tracks={row.get('transformTrackCount',0)}",f"keys={row.get('transformKeyCount',0)}",f"mode={row['rendererMode']}",flush=True)

clips_expected=sum(len(x.get('selectedClipNames') or []) for x in rows)
clips_decoded=sum(x['decodedClipCount'] for x in rows)
heroes_animated=sum(x['animated'] for x in rows)
rigid=sum(x['rendererMode']=='rigidHierarchy' for x in rows)
skinned=sum(x['rendererMode']=='skinned+hierarchy' for x in rows)
transform_bindings=sum(sum(int(c.get('transformBindings',0) or 0) for c in x['clips'] if c.get('decoded')) for x in rows)
resolved_bindings=sum(sum(int(c.get('resolvedTransformBindings',0) or 0) for c in x['clips'] if c.get('decoded')) for x in rows)
track_count=sum(int(x.get('transformTrackCount',0) or 0) for x in rows)
key_count=sum(int(x.get('transformKeyCount',0) or 0) for x in rows)

summary={
 'format':'WFGG_LASTWAR_CURRENT15_IDLE_KEYFRAMES_V1','networkUsed':False,'unityFallback':unity_version,
 'heroCount':15,'parseOkCount':sum(x['parseOk'] for x in rows),'expectedSelectedClipCount':clips_expected,'decodedClipCount':clips_decoded,
 'animatedHeroCount':heroes_animated,'rigidHierarchyHeroCount':rigid,'skinnedHierarchyHeroCount':skinned,
 'transformBindingCount':transform_bindings,'resolvedTransformBindingCount':resolved_bindings,
 'transformTrackCount':track_count,'transformKeyCount':key_count,'heroes':rows,
 'guardrails':{
   'exactPhase47BundlesOnly':True,'phase50ClipNamesOnly':True,'queueModelPathAuthoritative':True,
   'crc32PathResolutionOnly':True,'noFuzzyPathMatching':True,'noAnimationSubstitution':True,
   'noGeneratedMotion':True,'noLastWarNetwork':True,'localDecodedKeyframesCommitted':False
 }
}
manifestp.write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')

lines=[
 'WfGg Last War LAB — PHASE 51 CURRENT15 IDLE KEYFRAMES',
 'OFFLINE ONLY · exact Phase47 bundles · exact Phase50 clip names · no generated motion',
 f"heroes=15 parseOk={summary['parseOkCount']}/15 clipsDecoded={clips_decoded}/{clips_expected} heroesAnimated={heroes_animated}/15",
 f"pathResolved={resolved_bindings}/{transform_bindings} transformTracks={track_count} transformKeys={key_count} rigidHierarchy={rigid} skinnedHierarchy={skinned}",
 ''
]
for h in rows:
    lines.append(f"HERO {h['heroId']} {h['name']} parse={h['parseOk']} phase50Rig={h['phase50RigReady']} mode={h['rendererMode']} animated={h['animated']} clips={h['decodedClipCount']}/{len(h['selectedClipNames'])} tracks={h.get('transformTrackCount',0)} keys={h.get('transformKeyCount',0)}")
    for c in h['clips']:
        if c.get('decoded'):
            lines.append(f"  CLIP {c.get('kind')} {c['name']} decoded=True stream={c.get('streamedCurves',0)}c/{c.get('streamedFrames',0)}f dense={c.get('denseCurves',0)}c/{c.get('denseFrames',0)}f constant={c.get('constantSamples',0)} bindings={c.get('resolvedTransformBindings',0)}/{c.get('transformBindings',0)} tracks={c.get('transformTracks',0)} keys={c.get('transformKeys',0)}")
            if c.get('unresolvedBindingHashes'):lines.append('    UNRESOLVED_HASHES '+','.join(str(x) for x in c['unresolvedBindingHashes'][:30]))
        else:lines.append(f"  CLIP {c.get('kind')} {c['name']} decoded=False error={c.get('error','unknown')}")
    for e in h['errors']:lines.append('  ERROR '+str(e).replace('\n',' ')[:1600])
    lines.append('')
lines += [
 'GUARDRAILS',
 '  exact_phase47_bundles_only=true',
 '  phase50_clip_names_only=true',
 '  queue_model_path_authoritative=true',
 '  crc32_path_resolution_only=true',
 '  no_fuzzy_path_matching=true',
 '  no_animation_substitution=true',
 '  no_generated_motion=true',
 '  no_lastwar_network=true',
 '  local_decoded_keyframes_not_committed=true',
]
reportp.write_text('\n'.join(lines)+'\n',encoding='utf-8')

print('PHASE51_OK',f'clipsDecoded={clips_decoded}/{clips_expected}',f'heroesAnimated={heroes_animated}/15',f'pathResolved={resolved_bindings}/{transform_bindings}',f'rigidHierarchy={rigid}',f'skinnedHierarchy={skinned}',f'tracks={track_count}',f'keys={key_count}',flush=True)
print('PHASE51_REPORT',reportp,flush=True)
print('PHASE51_MANIFEST',manifestp,flush=True)
PYEOF

python "$PY" "$P47" "$P50" "$SRC" "$OUT" "$MANIFEST" "$REPORT" "$UNITY_VERSION"

git add "$MANIFEST"
if ! git diff --cached --quiet; then
  git commit -m "lab: record exact current15 idle keyframe decode"
  git push origin "$BRANCH"
fi

printf 'PHASE51_DONE report=%s\n' "$REPORT"
