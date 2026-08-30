#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — exact static connectivity between Camera.targetTexture
# and RawImage.texture using the EXISTING persistent CLR atlas only.
# No APK read, DLL scan, extraction, bundle scan, candidate promotion,
# main modification or preview modification.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
META="$ROOT/frontend/lab/master-assets-v2/meta"
INDEX="$ROOT/frontend/lab/master-assets-v2/index"
ATLAS="$INDEX/lastwar-code-discovery-atlas-v1.json"
BINDING="$META/formation-runtime-atlas-binding-v1.json"
OUT="$META/formation-camera-rawimage-connectivity-v1.json"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_FORMATION_CAMERA_RAWIMAGE_CONNECTIVITY_V1.txt"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
[[ -s "$ATLAS" ]] || fail "atlas CLR absent: $ATLAS"
[[ -s "$BINDING" ]] || fail "binding runtime absent: $BINDING"
command -v python >/dev/null 2>&1 || fail "python absent"
mkdir -p "$(dirname "$OUT")" "$(dirname "$REPORT")"

python - "$ATLAS" "$BINDING" "$OUT" "$REPORT" <<'PY'
from pathlib import Path
from collections import defaultdict, deque
import json, sys

atlas_p,binding_p,out_p,report_p=map(Path,sys.argv[1:])
a=json.loads(atlas_p.read_text('utf-8'))
b=json.loads(binding_p.read_text('utf-8'))

types=a.get('types') or []
methods=a.get('methods') or []
external=a.get('externalCalls') or []
internal=a.get('internalEdges') or []
tm={int(x['rid']):x for x in types if x.get('rid') is not None}
mm={int(x['rid']):x for x in methods if x.get('rid') is not None}

def ftype(t):
    if not t:return ''
    return ((str(t.get('namespace'))+'.') if t.get('namespace') else '')+str(t.get('name') or '')

def symbol(rid):
    m=mm.get(int(rid)) or {}; t=tm.get(int(m.get('typeRid') or 0))
    own=ftype(t)
    return (own+'.' if own else '')+str(m.get('name') or f'M:{rid}')

def strings(rid):
    vals=(mm.get(int(rid)) or {}).get('strings') or []
    if not isinstance(vals,list): vals=[vals]
    out=[]
    for v in vals:
        if isinstance(v,str):out.append(v)
        elif isinstance(v,dict):
            for k in ('string','value','text'):
                if isinstance(v.get(k),str):out.append(v[k]);break
    return out

formation_terms=('formationrt','formationbg','uiheropvpformationpanel','pvpformation','formationcontent','formationcamera','heroshow','showcamera')
video_terms=('video','webm','movie')
def corr(rid):
    s=symbol(rid); ss=strings(rid)
    low=(s+' '+json.dumps(ss,ensure_ascii=False)).lower()
    return {
        'formation':any(x in low for x in formation_terms),
        'video':any(x in low for x in video_terms),
        'strings':[x for x in ss if any(t in x.lower() for t in formation_terms)],
    }

patterns={
 'rawImageSetTexture':('unityengine.ui.rawimage.set_texture',),
 'cameraSetTargetTexture':('unityengine.camera.set_targettexture','unityengine.camera.set_target_texture'),
 'renderTexture':('unityengine.rendertexture.','unityengine.rendering.rendertexture.'),
 'graphicsBlit':('unityengine.graphics.blit',),
 'videoSetTargetTexture':('unityengine.video.videoplayer.set_targettexture','unityengine.video.videoplayer.set_target_texture'),
}
cat={k:set() for k in patterns}; targets_by_method=defaultdict(set)
for row in external:
    target=str(row.get('target') or ''); low=target.lower()
    callers=[]
    for x in row.get('callerRids') or []:
        try: callers.append(int(x))
        except: pass
    for r in callers: targets_by_method[r].add(target)
    for k,pats in patterns.items():
        if any(p in low for p in pats):cat[k].update(callers)

callers_of=defaultdict(set); callees_of=defaultdict(set); und=defaultdict(set)
for e in internal:
    if not isinstance(e,(list,tuple)) or len(e)<2:continue
    try:u,v=int(e[0]),int(e[1])
    except:continue
    callees_of[u].add(v); callers_of[v].add(u); und[u].add(v); und[v].add(u)

def row(rid):
    c=corr(rid)
    return {
      'rid':int(rid),'stableId':f'M:{int(rid)}','symbol':symbol(rid),
      'formationCorrelation':c['formation'],'formationLiteralHits':c['strings'],
      'videoCorrelation':c['video'],
      'externalTargets':sorted(targets_by_method.get(int(rid),set())),
      'callers':sorted(callers_of.get(int(rid),set())),
      'callees':sorted(callees_of.get(int(rid),set())),
    }

def shortest(adj,src,dst,maxd=20):
    if src==dst:return [src]
    q=deque([src]); prev={src:None}; depth={src:0}
    while q:
        x=q.popleft(); d=depth[x]
        if d>=maxd:continue
        for y in adj.get(x,()):
            if y in prev:continue
            prev[y]=x; depth[y]=d+1
            if y==dst:
                p=[y]
                while prev[p[-1]] is not None:p.append(prev[p[-1]])
                return list(reversed(p))
            q.append(y)
    return None

def reverse_dist(seeds,maxd=12):
    q=deque(seeds); d={int(x):0 for x in seeds}
    while q:
        x=q.popleft()
        if d[x]>=maxd:continue
        for p in callers_of.get(x,()):
            if p not in d:d[p]=d[x]+1;q.append(p)
    return d

raw=sorted(cat['rawImageSetTexture']); cams=sorted(cat['cameraSetTargetTexture'])
render=cat['renderTexture']; blit=cat['graphicsBlit']; video=cat['videoSetTargetTexture']

# Exact directed and undirected pairwise connectivity.
pairs=[]
for c in cams:
    for r in raw:
        f=shortest(callees_of,c,r,20)
        rev=shortest(callees_of,r,c,20)
        u=shortest(und,c,r,12)
        if f or rev or u:
            pairs.append({
              'cameraRid':c,'rawRid':r,
              'cameraToRaw':f,'rawToCamera':rev,'undirected':u,
              'undirectedDistance':(len(u)-1 if u else None),
              'cameraSymbol':symbol(c),'rawSymbol':symbol(r),
            })
pairs.sort(key=lambda x:(x['cameraToRaw'] is None and x['rawToCamera'] is None, x['undirectedDistance'] if x['undirectedDistance'] is not None else 999, x['cameraRid'],x['rawRid']))

# Find exact common upstream MethodDef callers. This catches orchestration methods that
# independently configure a camera and a RawImage without a direct call chain between them.
cam_up={c:reverse_dist([c],12) for c in cams}
raw_up={r:reverse_dist([r],12) for r in raw}
common=[]
for c in cams:
  for r in raw:
    inter=set(cam_up[c]) & set(raw_up[r])
    for anc in inter:
      dc,dr=cam_up[c][anc],raw_up[r][anc]
      if dc==0 or dr==0:continue
      cr=corr(anc)
      common.append({
        'ancestorRid':anc,'ancestorSymbol':symbol(anc),
        'cameraRid':c,'cameraSymbol':symbol(c),'cameraDistance':dc,
        'rawRid':r,'rawSymbol':symbol(r),'rawDistance':dr,
        'totalDistance':dc+dr,
        'formationCorrelation':cr['formation'],'formationLiteralHits':cr['strings'],
        'videoCorrelation':cr['video'],
      })
common.sort(key=lambda x:(not x['formationCorrelation'],x['totalDistance'],x['videoCorrelation'],x['ancestorSymbol']))
# De-duplicate same ancestor/camera/raw tuple already naturally unique.

camera_rows=[row(x) for x in cams]
# Mark exact API composition on the camera-setting methods.
for x in camera_rows:
    rid=x['rid']; x['alsoRenderTexture']=rid in render; x['alsoGraphicsBlit']=rid in blit; x['alsoVideoTargetTexture']=rid in video

formation_common=[x for x in common if x['formationCorrelation']]
directed=[x for x in pairs if x['cameraToRaw'] or x['rawToCamera']]
closest=[x for x in pairs if x['undirected']][:40]

if formation_common:
    strategy='inspect_closest_formation_correlated_common_ancestor'
elif directed:
    strategy='inspect_exact_directed_camera_rawimage_methoddef_path'
elif common:
    strategy='inspect_closest_common_ancestor_then_non_methoddef_boundary'
else:
    strategy='trace_non_methoddef_boundary_lua_events_reflection_or_serialized_callbacks'

result={
 'format':'WFGG_LASTWAR_FORMATION_CAMERA_RAWIMAGE_CONNECTIVITY_V1',
 'sources':{'atlas':str(atlas_p),'binding':str(binding_p),'atlasDllSha256':(a.get('source') or {}).get('sha256')},
 'counts':{
   'rawImageSetTextureCallers':len(raw),'cameraSetTargetTextureCallers':len(cams),
   'renderTextureCallers':len(render),'graphicsBlitCallers':len(blit),'videoSetTargetTextureCallers':len(video),
   'pairwiseConnectivityRows':len(pairs),'directedCameraRawPaths':len(directed),
   'commonUpstreamRows':len(common),'formationCorrelatedCommonUpstreamRows':len(formation_common),
 },
 'cameraSetTargetTextureCallers':camera_rows,
 'directedConnectivity':directed[:100],
 'closestUndirectedConnectivity':closest,
 'formationCorrelatedCommonUpstream':formation_common[:100],
 'closestCommonUpstream':common[:200],
 'conclusion':{'nextStrategy':strategy,'note':'MethodDef call edges and external MemberRef calls are exact static CLR evidence; execution order and name/string correlations are not runtime proof.'},
 'guardrails':{'persistentCodeAtlasOnly':True,'apkAccess':False,'dllScan':False,'newExtraction':False,'bundleScan':False,'candidatePromotion':False,'mainUntouched':True,'previewUntouched':True}
}
out_p.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf-8')

lines=[
 'WfGg Last War — FORMATION CAMERA / RAWIMAGE CONNECTIVITY V1','',
 f"rawSet={len(raw)} cameraTarget={len(cams)} renderTexture={len(render)} graphicsBlit={len(blit)} videoTarget={len(video)}",
 f"directedCameraRawPaths={len(directed)} commonUpstream={len(common)} formationCommonUpstream={len(formation_common)}",'',
 'CAMERA.SET_TARGETTEXTURE CALLERS'
]
if camera_rows:
  for x in camera_rows:
    lines.append(f"  M:{x['rid']} renderRT={x['alsoRenderTexture']} blit={x['alsoGraphicsBlit']} videoTarget={x['alsoVideoTargetTexture']} formation={x['formationCorrelation']} symbol={x['symbol']}")
    if x['formationLiteralHits']:lines.append('    formationStrings='+json.dumps(x['formationLiteralHits'],ensure_ascii=False))
    lines.append('    external='+json.dumps(x['externalTargets'],ensure_ascii=False,separators=(',',':')))
else: lines.append('  NONE')
lines += ['', 'DIRECTED CAMERA <-> RAWIMAGE METHODDEF PATHS']
if directed:
  for x in directed[:40]:
    lines.append(f"  camera=M:{x['cameraRid']} raw=M:{x['rawRid']} cameraToRaw={x['cameraToRaw']} rawToCamera={x['rawToCamera']}")
else:lines.append('  NONE')
lines += ['', 'FORMATION-CORRELATED COMMON UPSTREAM CALLERS']
if formation_common:
  for x in formation_common[:60]:
    lines.append(f"  ancestor=M:{x['ancestorRid']} total={x['totalDistance']} camera=M:{x['cameraRid']}({x['cameraDistance']}) raw=M:{x['rawRid']}({x['rawDistance']}) symbol={x['ancestorSymbol']}")
    if x['formationLiteralHits']:lines.append('    strings='+json.dumps(x['formationLiteralHits'],ensure_ascii=False))
else:lines.append('  NONE')
lines += ['', 'CLOSEST COMMON UPSTREAM CALLERS']
if common:
  for x in common[:40]:
    lines.append(f"  ancestor=M:{x['ancestorRid']} total={x['totalDistance']} formation={x['formationCorrelation']} video={x['videoCorrelation']} camera=M:{x['cameraRid']} raw=M:{x['rawRid']} symbol={x['ancestorSymbol']}")
else:lines.append('  NONE')
lines += ['', 'CLOSEST UNDIRECTED CONNECTIVITY']
if closest:
  for x in closest[:30]:lines.append(f"  d={x['undirectedDistance']} camera=M:{x['cameraRid']} raw=M:{x['rawRid']} path={x['undirected']}")
else:lines.append('  NONE')
lines += ['',f"NEXT strategy={strategy}",'RULE: atlas only; exact static CLR links are evidence, names/strings are correlations. No APK/DLL scan or candidate promotion.']
report_p.write_text('\n'.join(lines)+'\n','utf-8')

print('FORMATION_CAMERA_RAWIMAGE_CONNECTIVITY_OK',f"raw={len(raw)}",f"camera={len(cams)}",f"directed={len(directed)}",f"common={len(common)}",f"formationCommon={len(formation_common)}")
for x in camera_rows:print('FORMATION_CAMERA_CALLER',f"M:{x['rid']}",f"renderRT={x['alsoRenderTexture']}",f"video={x['alsoVideoTargetTexture']}",x['symbol'])
for x in formation_common[:20]:print('FORMATION_CAMERA_COMMON',f"M:{x['ancestorRid']}",f"total={x['totalDistance']}",x['ancestorSymbol'])
print('FORMATION_CAMERA_NEXT',strategy)
print('FORMATION_CAMERA_JSON',out_p)
print('FORMATION_CAMERA_REPORT',report_p)
PY

git add "$OUT"
if ! git diff --cached --quiet; then git commit -m "lab: map Camera targetTexture to RawImage texture connectivity"; fi
git push origin "$BRANCH"
printf '%s\n' '=== FORMATION CAMERA / RAWIMAGE CONNECTIVITY V1 TERMINE ===' "JSON: $OUT" "Rapport: $REPORT"
