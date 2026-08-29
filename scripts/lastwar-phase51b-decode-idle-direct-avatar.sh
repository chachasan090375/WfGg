#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — PHASE 51B
# DIRECT MECANIM + AVATAR TOS DECODER
# CODE ONLY · OFFLINE ONLY · exact Phase47 bundles only.
#
# Phase51 proved that all 29 selected clips are present but its TypeTree-only
# traversal did not expose the compact Clip samples and resolved 0 path hashes.
# This phase follows AssetStudio's actual decoding model more closely:
#   AnimationClip.m_MuscleClip.m_Clip
#   -> StreamedClip + DenseClip + ConstantClip
#   AnimationClip.m_ClipBindingConstant.genericBindings
# and resolves path hashes first against real Transform suffix CRCs, then against
# the exact Avatar.m_TOS hash->path table used by AssetStudio FindBonePath().
# No fuzzy matching, no generated motion, no animation substitution.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
UNITY_VERSION="2019.4.41f1"
P47="$ROOT/frontend/lab/master-assets-v2/meta/current15-exact-bundle-stage.json"
P50="$ROOT/frontend/lab/master-assets-v2/meta/current15-rig-idle-structure-v1.json"
SRC="$ROOT/frontend/lab/local_assets/lastwar-current15-exact-v1"
OUT="$ROOT/frontend/lab/local_assets/lastwar-current15-animation-v2"
MANIFEST="$ROOT/frontend/lab/master-assets-v2/meta/current15-idle-keyframes-v2.json"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_PHASE51B_CURRENT15_IDLE_DIRECT_AVATAR.txt"
PY="${TMPDIR:-$HOME/.cache}/wfgg-phase51b-direct-avatar.py"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche active incorrecte"
[[ -s "$P47" ]] || fail "Phase47 absente"
[[ -s "$P50" ]] || fail "Phase50 absente"
[[ -d "$SRC" ]] || fail "bundles locaux Phase47 absents"
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
import gzip, hashlib, json, math, re, struct, sys, traceback, zlib

p47p=Path(sys.argv[1]); p50p=Path(sys.argv[2]); src=Path(sys.argv[3]); outroot=Path(sys.argv[4]); manifestp=Path(sys.argv[5]); reportp=Path(sys.argv[6]); unity_version=sys.argv[7]
p47=json.loads(p47p.read_text(encoding='utf-8'))
p50=json.loads(p50p.read_text(encoding='utf-8'))
heroes=p47.get('heroes') or []
p50_by={int(x['heroId']):x for x in (p50.get('heroes') or [])}
if len(heroes)!=15 or len(p50_by)!=15: raise SystemExit('Phase47/50 current15 incomplet')

import UnityPy
UnityPy.config.FALLBACK_UNITY_VERSION=unity_version
SAFE=re.compile(r'[^A-Za-z0-9._-]+')
def safe(s): return SAFE.sub('_',str(s or '')).strip('._')[:160] or 'asset'
def tname(r):
    try:return r.type.name
    except:return str(getattr(r,'type',''))
def robj(r):
    try:return r.read()
    except Exception:
        try:return r.parse_as_object()
        except:return None
def name(o,fb=''):
    return str(getattr(o,'m_Name','') or getattr(o,'name','') or fb or '') if o is not None else str(fb or '')
def ptr_obj(p):
    if p is None:return None
    for fn in ('read','deref_parse_as_object','parse_as_object'):
        try:
            f=getattr(p,fn,None)
            if callable(f): return f()
        except: pass
    return None
def attr(o,*ns,default=None):
    for n in ns:
        try:
            v=getattr(o,n)
            if v is not None:return v
        except:pass
    return default
def i32(v,d=0):
    try:return int(v)
    except:
        s=str(v or '').lower()
        if 'transform' in s and 'rect' not in s:return 4
        if 'skinnedmeshrenderer' in s:return 137
        m=re.search(r'-?\d+',s);return int(m.group()) if m else d
def f32(v,d=0.0):
    try:return float(v)
    except:return d
def crc(s):return zlib.crc32(str(s).encode('utf-8'))&0xffffffff
def finite(x):
    x=float(x);return x if math.isfinite(x) else 0.0
def writegz(p,obj):
    raw=json.dumps(obj,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()
    with gzip.open(p,'wb',compresslevel=6) as f:f.write(raw)
    b=p.read_bytes();return len(raw),len(b),hashlib.sha256(b).hexdigest()
def clip_kind(n):
    s=str(n).lower().replace(' ','')
    if 'show_idle' in s or 'showidle' in s:return 'presentationIdle'
    if s.endswith('idle') or '_idle_' in s:return 'idle'
    return None

def obj_key(o):
    r=attr(o,'object_reader','reader')
    if r is None:return ('py',id(o))
    try:return (str(attr(attr(r,'assets_file'),'name',default='')),int(attr(r,'path_id','m_PathID')))
    except:return ('py',id(o))

def build_hierarchy(readers):
    ts=[robj(r) for r in readers if tname(r) in ('Transform','RectTransform')]
    ts=[x for x in ts if x is not None]; cache={};vis=set()
    def gon(t):return name(ptr_obj(attr(t,'m_GameObject')))
    def path(t):
        if t is None:return ''
        k=obj_key(t)
        if k in cache:return cache[k]
        if k in vis:return gon(t)
        vis.add(k); n=gon(t); fa=ptr_obj(attr(t,'m_Father'))
        p=path(fa) if fa is not None else ''
        out=(p+'/'+n) if p and n else (p or n);vis.discard(k);cache[k]=out;return out
    paths=sorted(set(p for p in (path(t) for t in ts) if p))
    hashes=defaultdict(set)
    for p in paths:
        parts=p.split('/')
        for j in range(len(parts)): hashes[crc('/'.join(parts[j:]))].add(p)
    return paths,hashes

def avatar_tos(readers):
    out=defaultdict(set)
    for r in readers:
        if tname(r)!='Avatar':continue
        o=robj(r)
        if o is None:continue
        tos=attr(o,'m_TOS','TOS',default=[])
        if isinstance(tos,dict):
            for k,v in tos.items():
                try:out[int(k)&0xffffffff].add(str(v))
                except:pass
        else:
            for x in tos or []:
                k=v=None
                if isinstance(x,(tuple,list)) and len(x)>=2:k,v=x[0],x[1]
                elif isinstance(x,dict):
                    k=x.get('first',x.get('key',x.get('Key')));v=x.get('second',x.get('value',x.get('Value')))
                else:
                    k=attr(x,'first','key','Key');v=attr(x,'second','value','Value')
                try:
                    if k is not None and v is not None:out[int(k)&0xffffffff].add(str(v))
                except:pass
    return out

def resolver(paths,hier_hashes,tos):
    def hierarchy_from_avatar(ap):
        vals=[p for p in paths if p==ap or p.endswith('/'+ap)]
        return vals[0] if len(vals)==1 else None
    def resolve(h):
        h=int(h)&0xffffffff
        hv=sorted(hier_hashes.get(h,set()))
        if len(hv)==1:return {'path':hv[0],'source':'transform-crc','avatarPath':None}
        av=sorted(tos.get(h,set()))
        if len(av)==1:
            hp=hierarchy_from_avatar(av[0])
            return {'path':hp or av[0],'source':'avatar-tos'+('-hierarchy' if hp else ''),'avatarPath':av[0]}
        return {'path':None,'source':'ambiguous' if hv or av else 'unresolved','hierarchyCandidates':hv[:8],'avatarCandidates':av[:8]}
    return resolve

def type_id(v):return i32(v,0)
def width(b):
    tid=type_id(attr(b,'typeID','m_TypeID','typeId','type'))
    at=i32(attr(b,'attribute','m_Attribute'),0)
    return {1:3,2:4,3:3,4:3}.get(at,1) if tid==4 else 1

def bindings_from_clip(c,resolve):
    bc=attr(c,'m_ClipBindingConstant','ClipBindingConstant')
    arr=attr(bc,'genericBindings','m_GenericBindings',default=[]) or []
    rows=[];cur=0
    for n,b in enumerate(arr):
        tid=type_id(attr(b,'typeID','m_TypeID','typeId','type'));at=i32(attr(b,'attribute','m_Attribute'),0)&0xffffffff
        ph=i32(attr(b,'path','m_Path'),0)&0xffffffff;w=width(b); rr=resolve(ph) if tid==4 else {'path':None,'source':'non-transform'}
        rows.append({'ordinal':n,'start':cur,'end':cur+w,'width':w,'pathHash':ph,'attribute':at,'typeID':tid,'resolvedPath':rr.get('path'),'pathSource':rr.get('source'),'avatarPath':rr.get('avatarPath')})
        cur+=w
    return rows,cur

def find_binding(rows,index):
    for b in rows:
        if b['start']<=index<b['end']:return b
    return None

def prop(b):
    if not b or b['typeID']!=4:return 'nonTransform'
    return {1:'localPosition',2:'localRotation',3:'localScale',4:'localEuler'}.get(b['attribute'],f"transformAttribute{b['attribute']}")
def webv(p,v):
    v=[finite(x) for x in v]
    if p=='localPosition' and len(v)>=3:return [-v[0],v[1],v[2]]
    if p=='localRotation' and len(v)>=4:return [v[0],-v[1],-v[2],v[3]]
    if p=='localEuler' and len(v)>=3:return [v[0],-v[1],-v[2]]
    return v

def stream_frames(sc):
    data=attr(sc,'data','m_Data',default=[]) or []
    cc=i32(attr(sc,'curveCount','m_CurveCount'),0)
    raw=b''.join(struct.pack('<I',i32(x,0)&0xffffffff) for x in data)
    pos=0;frames=[];errs=[]
    while pos<len(raw):
        if len(raw)-pos<8:errs.append('trailing');break
        tm=struct.unpack_from('<f',raw,pos)[0];pos+=4
        nk=struct.unpack_from('<i',raw,pos)[0];pos+=4
        if nk<0 or nk>100000 or pos+nk*20>len(raw):errs.append(f'badFrame:{nk}');break
        ks=[]
        for _ in range(nk):
            ix=struct.unpack_from('<i',raw,pos)[0];pos+=4
            cf=struct.unpack_from('<4f',raw,pos);pos+=16
            ks.append({'index':ix,'value':finite(cf[3]),'coeff':[finite(x) for x in cf]})
        frames.append({'time':finite(tm),'keys':ks})
    return frames,cc,len(raw),errs

def decode(c,resolve):
    muscle=attr(c,'m_MuscleClip','MuscleClip')
    compact=attr(muscle,'m_Clip','Clip')
    if compact is None:raise ValueError('direct m_MuscleClip.m_Clip absent')
    sc=attr(compact,'m_StreamedClip','StreamedClip'); dc=attr(compact,'m_DenseClip','DenseClip'); kc=attr(compact,'m_ConstantClip','ConstantClip')
    rows,total=bindings_from_clip(c,resolve)
    if not rows:raise ValueError('direct genericBindings empty')
    frames,scc,sbytes,serrs=stream_frames(sc)
    df=i32(attr(dc,'m_FrameCount','FrameCount'),0);dcc=i32(attr(dc,'m_CurveCount','CurveCount'),0);rate=f32(attr(dc,'m_SampleRate','SampleRate'),0);begin=f32(attr(dc,'m_BeginTime','BeginTime'),0)
    samples=[f32(x) for x in (attr(dc,'m_SampleArray','SampleArray',default=[]) or [])]
    const=[f32(x) for x in (attr(kc,'data','m_Data',default=[]) or [])] if kc is not None else []
    stop=f32(attr(muscle,'m_StopTime','StopTime'),0)
    tracks=defaultdict(lambda:defaultdict(list));unres=set();nont=0
    def emit(ix,tm,vals,source):
        nonlocal nont
        b=find_binding(rows,ix);w=b['width'] if b else 1
        if not b:return max(1,w)
        if b['typeID']!=4:nont+=1;return w
        if not b.get('resolvedPath'):unres.add(b['pathHash']);return w
        vv=[finite(x) for x in vals[:w]]
        if len(vv)<w:return w
        p=prop(b);tracks[b['resolvedPath']][p].append({'time':finite(tm),'unity':vv,'web':webv(p,vv),'source':source});return w
    # Match AssetStudio: skip first and last streamed sentinel frames.
    for fr in (frames[1:-1] if len(frames)>=3 else []):
        keys=fr['keys'];vals=[x['value'] for x in keys];ci=0
        while ci<len(keys):
            w=emit(keys[ci]['index'],fr['time'],vals[ci:],'streamed');ci+=max(1,w)
    if df>0 and dcc>0 and rate>0:
        for fi in range(df):
            off=fi*dcc;ci=0;tm=begin+fi/rate
            while ci<dcc:
                w=emit(scc+ci,tm,samples[off+ci:],'dense');ci+=max(1,w)
    if const:
        for tm in (0.0,stop):
            ci=0
            while ci<len(const):
                w=emit(scc+dcc+ci,tm,const[ci:],'constant');ci+=max(1,w)
    ot=[];keys=0
    for pth in sorted(tracks):
        props=[]
        for pr in sorted(tracks[pth]):
            kv=tracks[pth][pr];keys+=len(kv);props.append({'property':pr,'keys':kv})
        ot.append({'path':pth,'properties':props})
    tb=sum(1 for b in rows if b['typeID']==4); rb=sum(1 for b in rows if b['typeID']==4 and b.get('resolvedPath'))
    srcs=defaultdict(int)
    for b in rows:
        if b['typeID']==4:srcs[b['pathSource']]+=1
    return {'sampleRate':f32(attr(c,'m_SampleRate','SampleRate'),0),'stopTime':stop,'bindingCount':len(rows),'bindingScalarWidth':total,'transformBindingCount':tb,'resolvedTransformBindingCount':rb,'pathResolutionSources':dict(srcs),'unresolvedTransformBindingHashes':sorted(unres),'bindings':rows,'streamed':{'curveCount':scc,'frameCount':len(frames),'bytes':sbytes,'errors':serrs},'dense':{'curveCount':dcc,'frameCount':df,'sampleRate':rate,'beginTime':begin,'sampleCount':len(samples)},'constant':{'sampleCount':len(const)},'nonTransformGroups':nont,'transformTrackCount':len(ot),'transformKeyCount':keys,'tracks':ot}

rows=[]
for idx,h in enumerate(heroes,1):
    hid=int(h['heroId']);nm=h.get('name') or str(hid);ph=p50_by[hid];files=sorted((src/str(hid)).glob('*.bundle'));hout=outroot/str(hid);hout.mkdir(parents=True,exist_ok=True)
    selected=list(ph.get('selectedClipNames') or []);row={'heroId':hid,'name':nm,'phase50RigReady':bool(ph.get('rigReady')),'selectedClipNames':selected,'parseOk':False,'decodedClipCount':0,'clips':[],'animated':False,'rendererMode':'static','errors':[]}
    print(f'PHASE51B_HERO {idx}/15 id={hid} name={nm}',flush=True)
    try:
        env=UnityPy.load(*[str(x) for x in files]);readers=list(env.objects);row['parseOk']=True
        paths,hh=build_hierarchy(readers);tos=avatar_tos(readers);res=resolver(paths,hh,tos)
        row['transformPathCount']=len(paths);row['avatarTosHashCount']=len(tos)
        clips=[]
        for r in readers:
            if tname(r)!='AnimationClip':continue
            o=robj(r)
            if o is not None:clips.append((name(o),o))
        for sel in selected:
            c={'name':sel,'kind':clip_kind(sel),'decoded':False};hits=[o for n,o in clips if n==sel]
            if len(hits)!=1:c['error']=f'exact clip count={len(hits)}';row['clips'].append(c);continue
            try:
                dec=decode(hits[0],res);fn=('presentation-idle' if c['kind']=='presentationIdle' else 'idle')+'.json.gz';raw,gz,sha=writegz(hout/fn,{'heroId':hid,'name':nm,'clipName':sel,'queueModelPath':h.get('queueModelPath'),**dec})
                c.update({'decoded':True,'file':fn,'jsonBytes':raw,'gzipBytes':gz,'sha256':sha,'streamedCurves':dec['streamed']['curveCount'],'streamedFrames':dec['streamed']['frameCount'],'denseCurves':dec['dense']['curveCount'],'denseFrames':dec['dense']['frameCount'],'constantSamples':dec['constant']['sampleCount'],'transformBindings':dec['transformBindingCount'],'resolvedTransformBindings':dec['resolvedTransformBindingCount'],'pathSources':dec['pathResolutionSources'],'transformTracks':dec['transformTrackCount'],'transformKeys':dec['transformKeyCount'],'movingPathsSample':[x['path'] for x in dec['tracks'][:20]]});row['decodedClipCount']+=1
            except Exception as e:c['error']=repr(e);c['traceback']=traceback.format_exc()[-3000:]
            row['clips'].append(c)
        tr=sum(c.get('transformTracks',0) for c in row['clips']);ky=sum(c.get('transformKeys',0) for c in row['clips']);row['transformTrackCount']=tr;row['transformKeyCount']=ky;row['animated']=bool(tr and ky)
        if row['animated']:row['rendererMode']='skinned+hierarchy' if row['phase50RigReady'] else 'rigidHierarchy'
        elif row['phase50RigReady']:row['rendererMode']='skinned-static'
    except Exception as e:row['errors']=[repr(e),traceback.format_exc()[-4000:]]
    rows.append(row);print('PHASE51B_HERO_DONE',hid,f"decoded={row['decodedClipCount']}/{len(selected)}",f"tracks={row.get('transformTrackCount',0)}",f"keys={row.get('transformKeyCount',0)}",row['rendererMode'],flush=True)

expected=sum(len(x['selectedClipNames']) for x in rows);decoded=sum(x['decodedClipCount'] for x in rows);animated=sum(x['animated'] for x in rows);tb=sum(sum(c.get('transformBindings',0) for c in x['clips']) for x in rows);rb=sum(sum(c.get('resolvedTransformBindings',0) for c in x['clips']) for x in rows);tracks=sum(x.get('transformTrackCount',0) for x in rows);keys=sum(x.get('transformKeyCount',0) for x in rows)
summary={'format':'WFGG_LASTWAR_CURRENT15_IDLE_KEYFRAMES_V2_DIRECT_AVATAR','networkUsed':False,'unityFallback':unity_version,'heroCount':15,'parseOkCount':sum(x['parseOk'] for x in rows),'expectedSelectedClipCount':expected,'decodedClipCount':decoded,'animatedHeroCount':animated,'transformBindingCount':tb,'resolvedTransformBindingCount':rb,'transformTrackCount':tracks,'transformKeyCount':keys,'heroes':rows,'guardrails':{'exactPhase47BundlesOnly':True,'phase50ClipNamesOnly':True,'avatarTosExactFallback':True,'noFuzzyPathMatching':True,'noAnimationSubstitution':True,'noGeneratedMotion':True,'noLastWarNetwork':True}}
manifestp.write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
lines=['WfGg Last War LAB — PHASE 51B DIRECT MECANIM + AVATAR TOS','OFFLINE ONLY · exact Phase47 bundles · exact Phase50 clip names · no generated motion',f'heroes=15 parseOk={summary["parseOkCount"]}/15 clipsDecoded={decoded}/{expected} heroesAnimated={animated}/15',f'pathResolved={rb}/{tb} transformTracks={tracks} transformKeys={keys}','']
for h in rows:
    lines.append(f'HERO {h["heroId"]} {h["name"]} parse={h["parseOk"]} mode={h["rendererMode"]} animated={h["animated"]} avatarTOS={h.get("avatarTosHashCount",0)} clips={h["decodedClipCount"]}/{len(h["selectedClipNames"])} tracks={h.get("transformTrackCount",0)} keys={h.get("transformKeyCount",0)}')
    for c in h['clips']:
        if c.get('decoded'):
            lines.append(f'  CLIP {c.get("kind")} {c["name"]} stream={c.get("streamedCurves",0)}c/{c.get("streamedFrames",0)}f dense={c.get("denseCurves",0)}c/{c.get("denseFrames",0)}f constant={c.get("constantSamples",0)} bindings={c.get("resolvedTransformBindings",0)}/{c.get("transformBindings",0)} tracks={c.get("transformTracks",0)} keys={c.get("transformKeys",0)} sources={c.get("pathSources",{})}')
            if c.get('movingPathsSample'):lines.append('    MOVING_PATHS '+ ' | '.join(c['movingPathsSample'][:12]))
        else:lines.append(f'  CLIP {c.get("kind")} {c["name"]} ERROR {c.get("error")}')
    for e in h.get('errors',[]):lines.append('  ERROR '+str(e).replace('\n',' ')[:1200])
    lines.append('')
lines += ['GUARDRAILS','  exact_phase47_bundles_only=true','  phase50_clip_names_only=true','  avatar_tos_exact_fallback=true','  no_fuzzy_path_matching=true','  no_animation_substitution=true','  no_generated_motion=true','  no_lastwar_network=true']
reportp.write_text('\n'.join(lines)+'\n',encoding='utf-8')
print('PHASE51B_OK',f'clipsDecoded={decoded}/{expected}',f'heroesAnimated={animated}/15',f'pathResolved={rb}/{tb}',f'tracks={tracks}',f'keys={keys}',flush=True)
print('PHASE51B_REPORT',reportp,flush=True)
PYEOF

python "$PY" "$P47" "$P50" "$SRC" "$OUT" "$MANIFEST" "$REPORT" "$UNITY_VERSION"

git add "$MANIFEST"
if ! git diff --cached --quiet; then
  git commit -m "lab: record direct current15 Mecanim and Avatar path decode"
  git push origin "$BRANCH"
fi
printf 'PHASE51B_DONE report=%s\n' "$REPORT"
